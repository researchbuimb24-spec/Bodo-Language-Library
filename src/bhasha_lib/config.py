"""Language configuration parser and dataclasses for bhasha_lib.

💡 FILE INSIGHT & PURPOSE:
Loads and validates language YAML files (`bodo.yaml`).
Defines the `LanguageConfig` dataclass storing language name, ISO code (`brx`), target script,
and Unicode boundary ranges to parameterize tokenizers and linguistic validators dynamically.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class LanguageConfig:
    """Represents linguistic configuration and metadata for a language."""

    code: str
    script: str
    unicode_range: str
    tonal: bool
    name: str = ""

    @property
    def unicode_start(self) -> int:
        """Hexadecimal start of the Unicode block."""
        start_hex, _ = self.unicode_range.split("-")
        return int(start_hex, 16)

    @property
    def unicode_end(self) -> int:
        """Hexadecimal end of the Unicode block."""
        _, end_hex = self.unicode_range.split("-")
        return int(end_hex, 16)

    def contains_char(self, char: str) -> bool:
        """Check if a character falls within this language's unicode range."""
        if not char:
            return False
        code_point = ord(char[0])
        return self.unicode_start <= code_point <= self.unicode_end

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary representation."""
        data: dict[str, Any] = {
            "code": self.code,
            "script": self.script,
            "unicode_range": self.unicode_range,
            "tonal": self.tonal,
        }
        if self.name:
            data["name"] = self.name
        return data


def find_default_config(filename: str = "bodo.yaml") -> Path | None:
    """Search for the language config file in standard project paths."""
    candidates = [
        Path(filename),
        Path("configs") / filename,
        Path("data/archive/bodo") / filename,
        Path(__file__).resolve().parent.parent.parent / filename,
        Path(__file__).resolve().parent.parent.parent / "configs" / filename,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def load_config(path: str | Path | None = None) -> LanguageConfig:
    """Load language configuration from a YAML file.

    If path is None, searches default locations for 'bodo.yaml'.
    """
    if path is None:
        found = find_default_config("bodo.yaml")
        if found is None:
            raise FileNotFoundError(
                "Could not locate 'bodo.yaml' in standard directories. "
                "Please provide an explicit file path."
            )
        resolved_path = found
    else:
        resolved_path = Path(path).resolve()
        if not resolved_path.is_file():
            raise FileNotFoundError(f"Configuration file not found: {resolved_path}")

    with open(resolved_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return LanguageConfig(
        code=str(data.get("code", "")),
        script=str(data.get("script", "")),
        unicode_range=str(data.get("unicode_range", "")),
        tonal=bool(data.get("tonal", False)),
        name=str(data.get("name", "")),
    )


def get_bodo_config() -> LanguageConfig:
    """Get the standard configuration for Bodo language."""
    try:
        return load_config()
    except FileNotFoundError:
        # Fallback to standard spec defaults if file is unavailable
        return LanguageConfig(
            code="brx",
            script="Devanagari",
            unicode_range="0900-097F",
            tonal=True,
            name="Bodo",
        )
