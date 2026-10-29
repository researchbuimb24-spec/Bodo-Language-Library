"""Abstract base class for translation engines.

💡 FILE INSIGHT & PURPOSE:
Defines the translation architecture foundation: the abstract `BaseTranslationEngine`
interface, standard ISO-639 language code aliases (e.g. 'bodo' -> 'brx'), and the
`TranslationResult` structure that standardizes translations, confidence scores, and engine source.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

# Standard language alias normalization mapping
LANGUAGE_ALIASES: dict[str, str] = {
    "bodo": "brx",
    "boro": "brx",
    "english": "en",
    "hindi": "hi",
    "assamese": "as",
    "bengali": "bn",
    "auto": "auto",
}


def normalize_language_code(lang: str) -> str:
    """Normalize language name or code to ISO 639-3 or standard code."""
    cleaned = (lang or "").strip().lower()
    return LANGUAGE_ALIASES.get(cleaned, cleaned)


class BaseTranslationEngine(ABC):
    """Abstract base class defining translation and detection interfaces."""

    @abstractmethod
    def translate(
        self,
        text: str,
        source: str = "auto",
        target: str = "brx",
    ) -> str:
        """Translate given text from source language to target language.

        Args:
            text: Input string to translate.
            source: Source language code or name (e.g., 'brx', 'bodo', 'auto').
            target: Target language code or name (e.g., 'en', 'hi', 'brx').

        Returns:
            Translated string.
        """

    @abstractmethod
    def detect_language(self, text: str) -> str:
        """Detect the language code of the input text.

        Args:
            text: Input string to analyze.

        Returns:
            Detected language code (e.g., 'brx', 'en', 'hi').
        """

    @abstractmethod
    def get_supported_languages(self) -> dict[str, str]:
        """Return dict of supported language codes and human-readable names."""

    def translate_batch(
        self,
        texts: list[str],
        source: str = "auto",
        target: str = "en",
    ) -> list[str]:
        """Translate a batch of texts.

        Args:
            texts: List of strings to translate.
            source: Source language code.
            target: Target language code.

        Returns:
            List of translated strings.
        """
        return [self.translate(t, source=source, target=target) for t in texts]
