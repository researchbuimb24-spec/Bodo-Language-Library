"""English word detection and filtering utilities for Latin-script extraction.

💡 FILE INSIGHT & PURPOSE:
Filters English prose and loanword noise from bilingual historical books (Anderson 1895).
Crucially defines `BODO_PROTECTED_WORDS` (native words like ai, mai, dui, ha, no, so, be)
and English inflection rules to prevent native Bodo words from being incorrectly discarded.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

# Core Bodo vocabulary, pronouns, numerals, and grammatical affixes
# in Roman script that must NEVER be classified as English.
BODO_PROTECTED_WORDS: frozenset[str] = frozenset(
    {
        "ada",
        "afa",
        "agui",
        "ang",
        "aronai",
        "ba",
        "baro",
        "bathou",
        "bi",
        "bodo",
        "boro",
        "brui",
        "bwisagu",
        "da",
        "darrang",
        "dath",
        "do",
        "dokhona",
        "domashi",
        "fai",
        "frai",
        "futh",
        "gaham",
        "gaon",
        "gongse",
        "gu",
        "ha",
        "huth",
        "hwn",
        "kachari",
        "kachári",
        "khalam",
        "kham",
        "kherai",
        "kho",
        "khun",
        "lai",
        "lauthi",
        "ma",
        "man",
        "mosa",
        "mosau",
        "nai",
        "napham",
        "nau",
        "ni",
        "no",
        "nuise",
        "nwi",
        "nwng",
        "phan",
        "phai",
        "rao",
        "sa",
        "se",
        "serja",
        "siphung",
        "sni",
        "som",
        "song",
        "swr",
        "tham",
        "thang",
        "thannai",
        "za",
        "zi",
        "zong",
    }
)

_RESOURCE_DIR = Path(__file__).resolve().parent / "resources"
_DEFAULT_WORDS_FILE = _RESOURCE_DIR / "english_words.txt"


@lru_cache(maxsize=1)
def load_english_words(file_path: Path | None = None) -> frozenset[str]:
    """Load the curated English vocabulary list into an in-memory set.

    Args:
        file_path: Optional path to an alternative wordlist file.

    Returns:
        frozenset of lowercase English words.
    """
    path = file_path or _DEFAULT_WORDS_FILE
    if not path.is_file():
        return frozenset()
    content = path.read_text(encoding="utf-8")
    words = {
        line.strip().lower()
        for line in content.splitlines()
        if line.strip() and not line.startswith("#")
    }
    return frozenset(words)


def is_english_word(
    token: str,
    custom_words: frozenset[str] | set[str] | None = None,
) -> bool:
    """Determine whether a token in Latin script is an English word.

    Applies protection for core Bodo words, direct lookup in the English
    lexicon, and standard inflection checks.

    Args:
        token: Word string to evaluate.
        custom_words: Optional custom set of English words.

    Returns:
        True if the token is identified as English, False otherwise.
    """
    clean = token.strip().lower()
    if not clean or len(clean) < 2:
        return False

    # Check protected Bodo vocabulary first
    if clean in BODO_PROTECTED_WORDS:
        return False

    # Check hyphenated agglutinative compounds (e.g. 'hd-su-nai-khai')
    if "-" in clean:
        parts = [p for p in clean.split("-") if p]
        if any(p in BODO_PROTECTED_WORDS for p in parts):
            return False

    eng_set = custom_words if custom_words is not None else load_english_words()
    if clean in eng_set:
        return True

    # Standard English inflection suffixes
    suffixes = ("'s", "ed", "ing", "ly", "ment", "tion", "ness", "es", "s")
    for suffix in suffixes:
        if clean.endswith(suffix) and len(clean) > len(suffix) + 2:
            stem = clean[: -len(suffix)]
            if stem in BODO_PROTECTED_WORDS:
                return False
            if stem in eng_set or (stem + "e") in eng_set:
                return True

    return False
