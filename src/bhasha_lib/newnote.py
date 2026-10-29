"""CLI and helper to create skeleton culture markdown notes.

💡 FILE INSIGHT & PURPOSE:
Scaffolding utility (`create_new_note`) and CLI tool for creating valid cultural Markdown notes.
Generates compliant skeleton YAML frontmatter (with category, title, region, and default `needs_check` confidence)
to prevent formatting errors when contributors draft new cultural or historical articles.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def make_slug(title: str) -> str:
    """Generate a clean lowercase slug from a title string."""
    clean = title.strip().lower()
    slug = re.sub(r"[^\w]+", "_", clean).strip("_")
    return slug or "untitled"


def create_new_note(
    category: str,
    title: str,
    out_dir: str | Path,
) -> Path:
    """Create a skeleton culture markdown note.

    Contains only the mandatory metadata structure with confidence 'needs_check'
    and a body containing 'TODO'. Refuses to overwrite an existing file.

    Args:
        category: Cultural item category (e.g., dance, festival, attire).
        title: Item title.
        out_dir: Destination directory.

    Returns:
        Path of the newly created file.

    Raises:
        ValueError: If category or title is empty.
        FileExistsError: If destination file already exists.
    """
    clean_cat = category.strip()
    clean_title = title.strip()
    if not clean_cat:
        raise ValueError("Category cannot be empty.")
    if not clean_title:
        raise ValueError("Title cannot be empty.")

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    slug = make_slug(clean_title)
    target_file = out_path / f"{slug}.md"

    if target_file.exists():
        raise FileExistsError(f"File already exists: {target_file}")

    content = (
        "---\n"
        f"category: {clean_cat}\n"
        f"title: {clean_title}\n"
        "region:\n"
        "year_start:\n"
        "year_end:\n"
        "source:\n"
        "confidence: needs_check\n"
        "related_words: []\n"
        "---\n"
        "TODO\n"
    )
    target_file.write_text(content, encoding="utf-8")
    return target_file


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for newnote."""
    parser = argparse.ArgumentParser(
        description="Create a skeleton culture note markdown file."
    )
    parser.add_argument(
        "--category",
        required=True,
        help="Category of the culture item (e.g. dance, festival)",
    )
    parser.add_argument(
        "--title",
        required=True,
        help="Title of the culture item",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Destination folder path",
    )

    args = parser.parse_args(argv)

    try:
        created = create_new_note(
            category=args.category,
            title=args.title,
            out_dir=args.out,
        )
    except (FileExistsError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    print(f"Created skeleton note: {created}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
