"""Offline rule-based and lexicon translation engine for Bodo.

💡 FILE INSIGHT & PURPOSE:
Self-contained, offline translation engine (`BodoOfflineEngine`).
Combines SQLite dictionary lookups with Bodo morphological analysis—stripping
and reconstructing grammatical case suffixes (genitive -नि, accusative -खौ, dative -नो,
locative -आव) and plural markers (-फोर) for bidirectional Bodo <-> English/Hindi translation.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from bhasha_lib.db import DEFAULT_DB_PATH
from bhasha_lib.engines.base import BaseTranslationEngine, normalize_language_code

# Bodo morphological suffixes for case markers and plurals
# Ordered by length descending so compound suffixes match first
BODO_SUFFIXES: list[str] = [
    "निफ्राय",  # from (ablative)
    "फोरखौ",    # plural accusative
    "फोरनि",    # plural genitive
    "फोर",      # plural marker
    "सिम",      # towards / up to (allative)
    "खौ",       # accusative / object marker
    "नि",       # of / 's (genitive)
    "आव",       # in / at / on (locative)
    "जों",      # with / by (instrumental)
    "नो",       # to / for (dative)
]

ENGLISH_SUFFIX_GLOSS: dict[str, str] = {
    "निफ्राय": "from {root}",
    "फोरखौ": "{root}s",
    "फोरनि": "of {root}s",
    "फोर": "{root}s",
    "सिम": "towards {root}",
    "खौ": "{root}",
    "नि": "of {root}",
    "आव": "in {root}",
    "जों": "with {root}",
    "नो": "to {root}",
}

HINDI_SUFFIX_GLOSS: dict[str, str] = {
    "निफ्राय": "{root} से",
    "फोरखौ": "{root} को",
    "फोरनि": "{root} का",
    "फोर": "{root} लोग",
    "सिम": "{root} तक",
    "खौ": "{root} को",
    "नि": "{root} का",
    "आव": "{root} में",
    "जों": "{root} से",
    "नो": "{root} को",
}

SUPPORTED_OFFLINE_LANGUAGES: dict[str, str] = {
    "brx": "Bodo",
    "en": "English",
    "hi": "Hindi",
    "roman": "Bodo (Roman)",
}


class BodoOfflineEngine(BaseTranslationEngine):
    """Offline translation engine powered by SQLite lexicon and morphology."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self._cache: dict[str, dict[str, Any] | None] = {}
        self._reverse_cache: dict[str, str] = {}

    def get_supported_languages(self) -> dict[str, str]:
        """Return supported languages for offline translation."""
        return dict(SUPPORTED_OFFLINE_LANGUAGES)

    def _get_connection(self) -> sqlite3.Connection | None:
        if not self.db_path.is_file():
            return None
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def lookup_word(self, token: str) -> dict[str, Any] | None:
        """Look up word entry from lexicon database."""
        clean = token.strip()
        if not clean:
            return None

        if clean in self._cache:
            return self._cache[clean]

        conn = self._get_connection()
        if conn is None:
            return None

        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT word, roman, meaning_hi, meaning_en
                FROM words
                WHERE word = ?
                LIMIT 1
                """,
                (clean,),
            )
            row = cursor.fetchone()
            result = dict(row) if row else None
            self._cache[clean] = result
            return result
        except sqlite3.Error:
            return None
        finally:
            conn.close()

    def lookup_reverse(self, text: str, source_lang: str = "auto") -> str | None:
        """Look up Bodo word corresponding to English, Hindi, or Roman meaning."""
        clean = text.strip().lower()
        if not clean:
            return None

        cache_key = f"{source_lang}:{clean}"
        if cache_key in self._reverse_cache:
            return self._reverse_cache[cache_key]

        conn = self._get_connection()
        if conn is None:
            return None

        try:
            cursor = conn.cursor()
            if source_lang == "hi":
                cursor.execute(
                    "SELECT word FROM words WHERE LOWER(meaning_hi) = ? LIMIT 1",
                    (clean,),
                )
            elif source_lang == "en":
                cursor.execute(
                    "SELECT word FROM words WHERE LOWER(meaning_en) = ? LIMIT 1",
                    (clean,),
                )
            else:
                cursor.execute(
                    """
                    SELECT word FROM words
                    WHERE LOWER(meaning_en) = ?
                       OR LOWER(meaning_hi) = ?
                       OR LOWER(roman) = ?
                    LIMIT 1
                    """,
                    (clean, clean, clean),
                )
            row = cursor.fetchone()
            if row:
                res = str(row["word"])
                self._reverse_cache[cache_key] = res
                return res

            # Fallback to LIKE prefix / substring match
            cursor.execute(
                """
                SELECT word FROM words
                WHERE LOWER(meaning_en) LIKE ?
                   OR LOWER(meaning_hi) LIKE ?
                LIMIT 1
                """,
                (f"%{clean}%", f"%{clean}%"),
            )
            row = cursor.fetchone()
            if row:
                res = str(row["word"])
                self._reverse_cache[cache_key] = res
                return res

            return None
        except sqlite3.Error:
            return None
        finally:
            conn.close()

    def strip_suffix(self, token: str) -> tuple[str, str | None]:
        """Extract morphological root by stripping Bodo case and plural suffixes."""
        clean = token.strip()
        for sfx in BODO_SUFFIXES:
            if clean.endswith(sfx) and len(clean) > len(sfx):
                root = clean[: -len(sfx)]
                return root, sfx
        return clean, None

    def _translate_token(self, token: str, target_lang: str) -> str:
        """Translate single token using direct lookup or root extraction."""
        # 1. Direct dictionary match
        entry = self.lookup_word(token)
        if entry is not None:
            if target_lang == "hi" and entry.get("meaning_hi"):
                return str(entry["meaning_hi"]).strip()
            if target_lang == "en" and entry.get("meaning_en"):
                return str(entry["meaning_en"]).strip()
            if target_lang == "roman" and entry.get("roman"):
                return str(entry["roman"]).strip()

        # 2. Morphological suffix stripping
        root, sfx = self.strip_suffix(token)
        if sfx is not None:
            root_entry = self.lookup_word(root)
            if root_entry is not None:
                if target_lang == "hi" and root_entry.get("meaning_hi"):
                    base = str(root_entry["meaning_hi"]).strip()
                    template = HINDI_SUFFIX_GLOSS.get(sfx, "{root}")
                    return template.format(root=base)
                if target_lang == "en" and root_entry.get("meaning_en"):
                    base = str(root_entry["meaning_en"]).strip()
                    template = ENGLISH_SUFFIX_GLOSS.get(sfx, "{root}")
                    return template.format(root=base)
                if target_lang == "roman" and root_entry.get("roman"):
                    return str(root_entry["roman"]).strip()

        # 3. Fallback to roman transliteration if target is en/roman
        if target_lang in ("en", "roman") and entry and entry.get("roman"):
            return str(entry["roman"]).strip()

        # Default: preserve original token
        return token

    def translate(
        self,
        text: str,
        source: str = "auto",
        target: str = "brx",
    ) -> str:
        """Translate text using offline dictionary and morphological rules."""
        if not text or not text.strip():
            return ""

        src_lang = normalize_language_code(source)
        tgt_lang = normalize_language_code(target)

        # Translating into Bodo from another language (target is brx/bodo)
        if tgt_lang in ("brx", "bodo", "boro"):
            tokens = re.split(r"(\s+|[.,!?;:\"'()\-।॥])", text)
            out_segments: list[str] = []
            for t in tokens:
                if not t or re.match(r"^\s+$|^[.,!?;:\"'()\-।॥]+$", t):
                    out_segments.append(t)
                else:
                    bodo_word = self.lookup_reverse(t, source_lang=src_lang)
                    out_segments.append(bodo_word if bodo_word else t)
            return "".join(out_segments)

        # Standard forward translation (Bodo -> Target)
        tokens = re.split(r"(\s+|[.,!?;:\"'()\-।॥])", text)
        translated_segments: list[str] = []
        for t in tokens:
            if not t or re.match(r"^\s+$|^[.,!?;:\"'()\-।॥]+$", t):
                translated_segments.append(t)
            else:
                translated_segments.append(self._translate_token(t, tgt_lang))

        return "".join(translated_segments)

    def detect_language(self, text: str) -> str:
        """Heuristic language detection for offline mode."""
        if not text or not text.strip():
            return "unknown"

        # Check for Devanagari script range (U+0900 - U+097F)
        devanagari_chars = sum(
            1 for c in text if "\u0900" <= c <= "\u097f"
        )
        total_alpha = sum(1 for c in text if c.isalpha())

        if total_alpha > 0 and (devanagari_chars / total_alpha) > 0.4:
            return "brx"

        # Check Latin characters
        latin_chars = sum(
            1 for c in text if ("a" <= c <= "z") or ("A" <= c <= "Z")
        )
        if total_alpha > 0 and (latin_chars / total_alpha) > 0.5:
            return "en"

        return "brx" if devanagari_chars > 0 else "unknown"
