"""High-level translation API for Bodo language processing.

💡 FILE INSIGHT & PURPOSE:
Provides the primary Python interface for Bodo language translation and detection.
Exposes the `BodoTranslator` class alongside helper functions `translate()`,
`translate_batch()`, and `detect()`. Coordinates engine initialization, translation
caching, and automatic fallback from online neural models to offline local lexicons.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bhasha_lib.db import DEFAULT_DB_PATH
from bhasha_lib.engines.base import BaseTranslationEngine
from bhasha_lib.engines.composite import CompositeBodoEngine
from bhasha_lib.engines.google_gtx import GoogleGTXEngine
from bhasha_lib.engines.offline_engine import BodoOfflineEngine


class BodoTranslator:
    """High-level translation coordinator for Bodo language."""

    def __init__(
        self,
        engine: BaseTranslationEngine | None = None,
        force_offline: bool = False,
        db_path: str | Path = DEFAULT_DB_PATH,
    ) -> None:
        if engine is not None:
            self.engine = engine
        else:
            self.engine = CompositeBodoEngine(
                primary_engine=GoogleGTXEngine(),
                fallback_engine=BodoOfflineEngine(db_path=db_path),
                force_offline=force_offline,
            )
        self.force_offline = force_offline

    def translate(
        self,
        text: str,
        source: str = "auto",
        target: str = "brx",
        offline: bool = False,
    ) -> str:
        """Translate text with online engine and automatic offline fallback."""
        if hasattr(self.engine, "translate"):
            if isinstance(self.engine, CompositeBodoEngine):
                return self.engine.translate(
                    text,
                    source=source,
                    target=target,
                    force_offline=offline or self.force_offline,
                )
            return self.engine.translate(text, source=source, target=target)
        raise RuntimeError("Configured engine does not implement translate()")

    def translate_batch(
        self,
        texts: list[str],
        source: str = "auto",
        target: str = "brx",
        offline: bool = False,
    ) -> list[str]:
        """Translate a collection of texts."""
        return [
            self.translate(t, source=source, target=target, offline=offline)
            for t in texts
        ]

    def detect(self, text: str, offline: bool = False) -> str:
        """Detect the language code of the input text."""
        if isinstance(self.engine, CompositeBodoEngine):
            return self.engine.detect_language(
                text, force_offline=offline or self.force_offline
            )
        return self.engine.detect_language(text)

    def get_supported_languages(self) -> dict[str, str]:
        """Return supported languages mapping."""
        return self.engine.get_supported_languages()


_default_translator: BodoTranslator | None = None


def _get_default_translator(**kwargs: Any) -> BodoTranslator:
    global _default_translator
    if _default_translator is None or kwargs:
        return BodoTranslator(**kwargs)
    return _default_translator


def translate(
    text: str,
    source: str = "auto",
    target: str = "brx",
    offline: bool = False,
    **kwargs: Any,
) -> str:
    """Translate text using default high-level Bodo translator.

    Args:
        text: Input string.
        source: Source language code (default: 'auto').
        target: Target language code (default: 'brx' for Bodo).
        offline: If True, bypass online API and use offline lexicon/rules.
        **kwargs: Additional engine options (e.g., db_path).

    Returns:
        Translated text.
    """
    translator = _get_default_translator(**kwargs)
    return translator.translate(text, source=source, target=target, offline=offline)


def translate_batch(
    texts: list[str],
    source: str = "auto",
    target: str = "brx",
    offline: bool = False,
    **kwargs: Any,
) -> list[str]:
    """Translate a list of texts using default high-level Bodo translator."""
    translator = _get_default_translator(**kwargs)
    return translator.translate_batch(
        texts, source=source, target=target, offline=offline
    )


def detect(text: str, offline: bool = False, **kwargs: Any) -> str:
    """Detect language of the given text."""
    translator = _get_default_translator(**kwargs)
    return translator.detect(text, offline=offline)
