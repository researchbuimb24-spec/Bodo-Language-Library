"""Composite translation engine coordinating online service and offline fallback.

💡 FILE INSIGHT & PURPOSE:
Implements the hybrid resilient translation pipeline (`CompositeBodoEngine`).
Attempts online neural translation first (Google GTX); if offline mode is requested
or network errors occur, seamlessly falls back to the deterministic local offline engine.
"""

from __future__ import annotations

import logging
from typing import Any

from bhasha_lib.engines.base import BaseTranslationEngine
from bhasha_lib.engines.google_gtx import GoogleGTXEngine
from bhasha_lib.engines.offline_engine import BodoOfflineEngine

logger = logging.getLogger(__name__)


class CompositeBodoEngine(BaseTranslationEngine):
    """Resilient multi-engine coordinator with automatic offline fallback."""

    def __init__(
        self,
        primary_engine: BaseTranslationEngine | None = None,
        fallback_engine: BaseTranslationEngine | None = None,
        force_offline: bool = False,
    ) -> None:
        self.primary_engine = primary_engine or GoogleGTXEngine()
        self.fallback_engine = fallback_engine or BodoOfflineEngine()
        self.force_offline = force_offline

    def get_supported_languages(self) -> dict[str, str]:
        """Return merged dictionary of supported languages from both engines."""
        languages = self.fallback_engine.get_supported_languages()
        try:
            languages.update(self.primary_engine.get_supported_languages())
        except Exception:
            pass
        return languages

    def translate(
        self,
        text: str,
        source: str = "auto",
        target: str = "brx",
        force_offline: bool | None = None,
    ) -> str:
        """Translate text with online primary engine and automatic offline fallback."""
        if not text or not text.strip():
            return ""

        should_use_offline = (
            force_offline if force_offline is not None else self.force_offline
        )

        if should_use_offline:
            return self.fallback_engine.translate(
                text, source=source, target=target
            )

        try:
            return self.primary_engine.translate(
                text, source=source, target=target
            )
        except Exception as exc:
            logger.warning(
                "Primary translation failed (%s); falling back to offline.",
                exc,
            )
            return self.fallback_engine.translate(
                text, source=source, target=target
            )

    def detect_language(
        self,
        text: str,
        force_offline: bool | None = None,
    ) -> str:
        """Detect language with primary engine and offline fallback."""
        if not text or not text.strip():
            return "unknown"

        should_use_offline = (
            force_offline if force_offline is not None else self.force_offline
        )

        if should_use_offline:
            return self.fallback_engine.detect_language(text)

        try:
            detected = self.primary_engine.detect_language(text)
            if detected and detected != "unknown":
                return detected
        except Exception as exc:
            logger.warning(
                "Primary detection failed (%s); falling back to offline.",
                exc,
            )

        return self.fallback_engine.detect_language(text)

    def translate_batch(
        self,
        texts: list[str],
        source: str = "auto",
        target: str = "en",
        **kwargs: Any,
    ) -> list[str]:
        """Translate multiple texts sequentially with fallback handling."""
        force_offline = kwargs.get("force_offline")
        return [
            self.translate(
                t,
                source=source,
                target=target,
                force_offline=force_offline,
            )
            for t in texts
        ]
