"""Historical public domain books loader from archive.org for bhasha_lib.

💡 FILE INSIGHT & PURPOSE:
Ingests historical 19th-century public-domain books from the Internet Archive (archive.org).
Provides built-in presets (Anderson 1895, Endle 1884), automated OCR text downloading,
and direct piping into the text extraction and frequency counting pipeline.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from bhasha_lib.archive import get_archive_path
from bhasha_lib.db import DEFAULT_DB_PATH, add_source, get_connection, init_db
from bhasha_lib.extract import extract_file


@dataclass(frozen=True)
class BookPreset:
    """Metadata and download info for a historical public-domain book."""

    preset_id: str
    title: str
    author: str
    year: int
    license: str
    identifier: str
    text_filename: str
    url: str

    @property
    def download_url(self) -> str:
        """Direct URL to download the raw OCR text from archive.org."""
        return f"https://archive.org/download/{self.identifier}/{self.text_filename}"


HISTORICAL_BOOKS: dict[str, BookPreset] = {
    "anderson_1895": BookPreset(
        preset_id="anderson_1895",
        title="A Collection of Kachari Folk-Tales and Rhymes",
        author="J. D. Anderson",
        year=1895,
        license="public_domain",
        identifier="dli.csl.5540",
        text_filename="5540_djvu.txt",
        url="https://archive.org/details/dli.csl.5540",
    ),
    "endle_1884": BookPreset(
        preset_id="endle_1884",
        title="Outline Grammar of the Kachári (Bårå) Language",
        author="Sidney Endle",
        year=1884,
        license="public_domain",
        identifier="outlinegrammarof00endlrich",
        text_filename="outlinegrammarof00endlrich_djvu.txt",
        url="https://archive.org/details/outlinegrammarof00endlrich",
    ),
    "endle_1911": BookPreset(
        preset_id="endle_1911",
        title="The Kacháris",
        author="Sidney Endle",
        year=1911,
        license="public_domain",
        identifier="in.ernet.dli.2015.228431",
        text_filename="2015.228431.The-Kacharis_djvu.txt",
        url="https://archive.org/details/in.ernet.dli.2015.228431",
    ),
    "hodgson_1847": BookPreset(
        preset_id="hodgson_1847",
        title="Essay the First: On the Kocch, Bódo and Dhimál Tribes",
        author="Brian Houghton Hodgson",
        year=1847,
        license="public_domain",
        identifier="dli.ministry.01968",
        text_filename="20849.176.E.7_djvu.txt",
        url="https://archive.org/details/dli.ministry.01968",
    ),
    "grierson_1903": BookPreset(
        preset_id="grierson_1903",
        title="Linguistic Survey of India: Specimens of the Bodo, Naga and Kachin Groups (Vol. III, Pt. II)",
        author="George A. Grierson",
        year=1903,
        license="public_domain",
        identifier="in.ernet.dli.2015.107131",
        text_filename="2015.107131.Linguistic-Survery-Of-India-Specimens-Of-The-Bodo-Naga-And-Kachin-Groups-Vol3-Pt2_djvu.txt",
        url="https://archive.org/details/in.ernet.dli.2015.107131",
    ),
}


def get_default_books_dir() -> Path:
    """Get the target directory for downloaded books in the local archive."""
    return get_archive_path("books")


def download_book_text(
    preset_or_id: str | BookPreset,
    target_dir: str | Path | None = None,
) -> Path:
    """Download the raw text of a historical book from archive.org.

    Args:
        preset_or_id: Preset key ('anderson_1895', 'endle_1884') or BookPreset.
        target_dir: Directory where the text should be saved.

    Returns:
        Path to the saved text file.
    """
    if isinstance(preset_or_id, BookPreset):
        preset = preset_or_id
    elif preset_or_id in HISTORICAL_BOOKS:
        preset = HISTORICAL_BOOKS[preset_or_id]
    else:
        raise ValueError(
            f"Unknown book preset: '{preset_or_id}'. "
            f"Available presets: {list(HISTORICAL_BOOKS.keys())}"
        )

    out_directory = Path(target_dir) if target_dir else get_default_books_dir()
    out_directory.mkdir(parents=True, exist_ok=True)
    out_file = out_directory / f"{preset.preset_id}.txt"

    if out_file.is_file() and out_file.stat().st_size > 0:
        return out_file

    req = urllib.request.Request(
        preset.download_url,
        headers={"User-Agent": "bhasha-lib/0.1.0 (archive research)"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        content = response.read()

    # Normalize line endings to UTF-8 text
    text_data = content.decode("utf-8", errors="ignore")
    out_file.write_text(text_data, encoding="utf-8")
    return out_file


def load_historical_book(
    preset_or_id: str | BookPreset,
    db_path: str | Path = DEFAULT_DB_PATH,
    filter_english: bool = False,
    mark_english: bool = True,
    target_dir: str | Path | None = None,
) -> tuple[int, dict[str, int]]:
    """Download, register source, and extract vocabulary from a historical book.

    Args:
        preset_or_id: Book identifier or BookPreset instance.
        db_path: Path to the SQLite database.
        filter_english: If True, skips storing English words in the lexicon.
        mark_english: If True, tags English words with dialect='english'.
        target_dir: Directory to save downloaded book text.

    Returns:
        Tuple of (source_id, dict of extracted word frequencies).
    """
    if isinstance(preset_or_id, BookPreset):
        preset = preset_or_id
    else:
        preset = HISTORICAL_BOOKS[preset_or_id]

    text_path = download_book_text(preset, target_dir=target_dir)
    init_db(db_path)

    # Check if source already exists
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM sources WHERE title = ? AND year = ?",
            (preset.title, preset.year),
        )
        row = cursor.fetchone()
        if row is not None:
            source_id = int(row[0])
        else:
            source_id = add_source(
                title=preset.title,
                type="book",
                author=preset.author,
                year=preset.year,
                license=preset.license,
                url=preset.url,
                file_path=str(text_path),
                db_path=db_path,
            )

    stats = extract_file(
        path=text_path,
        db_path=db_path,
        source_id=source_id,
        license=preset.license,
        script="latin",
        mark_english=mark_english,
        filter_english=filter_english,
    )
    return source_id, stats


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for downloading and ingesting archive.org books."""
    parser = argparse.ArgumentParser(
        description=(
            "Download and ingest historical Latin-script books from archive.org."
        )
    )
    parser.add_argument(
        "--book",
        choices=list(HISTORICAL_BOOKS.keys()),
        help="Preset identifier of the historical book to load.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available historical book presets and exit.",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH}).",
    )
    parser.add_argument(
        "--filter-english",
        action="store_true",
        default=False,
        help="Exclude identified English words from being inserted into words table.",
    )
    parser.add_argument(
        "--no-mark-english",
        action="store_true",
        default=False,
        help="Do not tag English words with dialect='english'.",
    )
    args = parser.parse_args(argv)

    if args.list:
        print("Available archive.org historical book presets:")
        for key, p in HISTORICAL_BOOKS.items():
            print(f"  - {key}: '{p.title}' by {p.author} ({p.year}) [{p.license}]")
        return 0

    if not args.book:
        parser.error("--book is required unless --list is specified.")

    print(f"Fetching and ingesting '{args.book}' from archive.org...")
    source_id, stats = load_historical_book(
        preset_or_id=args.book,
        db_path=args.db,
        filter_english=args.filter_english,
        mark_english=not args.no_mark_english,
    )
    print(f"Done! Registered source #{source_id}. Extracted {len(stats)} unique words.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
