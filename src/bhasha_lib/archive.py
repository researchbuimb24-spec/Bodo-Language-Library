"""Utilities for interacting with language archive directories.

💡 FILE INSIGHT & PURPOSE:
Manages canonical filesystem paths for regional language archives (`data/archive/<language>/`).
Standardizes directory categories (books, datasets, history, culture, folk_songs)
and provides directory resolution and structural integrity verification (`verify_archive_structure()`).
"""

from __future__ import annotations

from pathlib import Path

ARCHIVE_CATEGORIES: tuple[str, ...] = (
    "books",
    "datasets",
    "history",
    "culture",
    "folk_songs",
)


def get_archive_base_dir(base_dir: Path | str | None = None) -> Path:
    """Resolve the base path for Bodo archive data."""
    if base_dir is not None:
        return Path(base_dir).resolve()

    candidates = [
        Path("data/archive/bodo"),
        Path(__file__).resolve().parent.parent.parent / "data" / "archive" / "bodo",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()

    return Path("data/archive/bodo").resolve()


def get_archive_path(category: str, base_dir: Path | str | None = None) -> Path:
    """Get the directory path for a specific archive category."""
    if category not in ARCHIVE_CATEGORIES:
        raise ValueError(
            f"Unknown archive category '{category}'. "
            f"Must be one of {ARCHIVE_CATEGORIES}."
        )
    return get_archive_base_dir(base_dir) / category


def verify_archive_structure(base_dir: Path | str | None = None) -> dict[str, bool]:
    """Verify that all required archive subdirectories exist."""
    base = get_archive_base_dir(base_dir)
    return {category: (base / category).is_dir() for category in ARCHIVE_CATEGORIES}


def list_archive_files(
    category: str,
    base_dir: Path | str | None = None,
    include_gitkeep: bool = False,
) -> list[Path]:
    """List files stored under a specific archive category."""
    category_dir = get_archive_path(category, base_dir)
    if not category_dir.is_dir():
        return []
    files = [f for f in category_dir.iterdir() if f.is_file()]
    if not include_gitkeep:
        files = [f for f in files if f.name != ".gitkeep"]
    return sorted(files)
