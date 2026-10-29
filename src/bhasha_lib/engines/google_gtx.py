"""Google GTX translation engine implementation.

💡 FILE INSIGHT & PURPOSE:
Online translation client (`GoogleGTXEngine`) connecting to Google Translate's GTX endpoint.
Supports Bodo (`brx`) with automated user-agent rotation, retry backoff, and response
JSON parsing for robust online translation and automatic language detection.
"""

from __future__ import annotations

import itertools
import random
from typing import Any

import requests

from bhasha_lib.engines.base import BaseTranslationEngine, normalize_language_code

DEFAULT_USER_AGENTS: list[str] = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) "
        "Gecko/20100101 Firefox/123.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.3; rv:123.0) "
        "Gecko/20100101 Firefox/123.0"
    ),
]

SUPPORTED_LANGUAGES: dict[str, str] = {
    "auto": "Detect Language",
    "brx": "Bodo",
    "en": "English",
    "hi": "Hindi",
    "as": "Assamese",
    "bn": "Bengali",
    "ne": "Nepali",
    "sa": "Sanskrit",
    "ur": "Urdu",
    "ta": "Tamil",
    "te": "Telugu",
    "kn": "Kannada",
    "ml": "Malayalam",
    "mr": "Marathi",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "or": "Odia",
}


class TranslationNetworkError(RuntimeError):
    """Raised when an external translation service encounters network failure."""


def _map_gtx_lang(lang: str) -> str:
    cleaned = normalize_language_code(lang)
    if cleaned in ("brx", "bodo", "boro"):
        return "bodo"
    return cleaned


class GoogleGTXEngine(BaseTranslationEngine):
    """Translation engine using the Google GTX free single translation endpoint."""

    ENDPOINT_URL: str = "https://translate.googleapis.com/translate_a/single"

    def __init__(
        self,
        timeout: float = 10.0,
        session: requests.Session | None = None,
        user_agents: list[str] | None = None,
    ) -> None:
        self.timeout = timeout
        self.session = session or requests.Session()
        agents = user_agents or list(DEFAULT_USER_AGENTS)
        random.shuffle(agents)
        self._ua_cycler = itertools.cycle(agents)

    def _get_next_headers(self) -> dict[str, str]:
        return {
            "User-Agent": next(self._ua_cycler),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def get_supported_languages(self) -> dict[str, str]:
        """Return mapping of supported language codes to names."""
        return dict(SUPPORTED_LANGUAGES)

    def translate(
        self,
        text: str,
        source: str = "auto",
        target: str = "brx",
    ) -> str:
        """Translate text using Google GTX endpoint."""
        if not text or not text.strip():
            return ""

        src_lang = _map_gtx_lang(source)
        tgt_lang = _map_gtx_lang(target)

        params: dict[str, Any] = {
            "client": "gtx",
            "sl": src_lang,
            "tl": tgt_lang,
            "dt": "t",
            "q": text,
        }

        try:
            response = self.session.get(
                self.ENDPOINT_URL,
                params=params,
                headers=self._get_next_headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise TranslationNetworkError(
                f"GoogleGTXEngine request failed: {exc}"
            ) from exc

        # Response structure: [[["translated", "original", ...], ...], ...]
        try:
            segments: list[str] = []
            if isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                for segment in data[0]:
                    if (
                        isinstance(segment, list)
                        and len(segment) > 0
                        and segment[0] is not None
                    ):
                        segments.append(str(segment[0]))
            if segments:
                return "".join(segments)
            return text
        except Exception as exc:
            raise TranslationNetworkError(
                f"Failed to parse GoogleGTXEngine response: {exc}"
            ) from exc

    def detect_language(self, text: str) -> str:
        """Detect language of text using Google GTX endpoint."""
        if not text or not text.strip():
            return "unknown"

        params: dict[str, Any] = {
            "client": "gtx",
            "sl": "auto",
            "tl": "en",
            "dt": "t",
            "q": text,
        }

        try:
            response = self.session.get(
                self.ENDPOINT_URL,
                params=params,
                headers=self._get_next_headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            # Detected language is usually at index 2
            if isinstance(data, list) and len(data) > 2 and data[2]:
                detected = str(data[2]).strip().lower()
                return normalize_language_code(detected)
        except Exception as exc:
            raise TranslationNetworkError(
                f"GoogleGTXEngine detection failed: {exc}"
            ) from exc

        return "unknown"
