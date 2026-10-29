"""Loader for the AI4Bharat Aksharantar Bodo transliteration dataset.

💡 FILE INSIGHT & PURPOSE:
Ingests AI4Bharat Aksharantar dataset zip archives (`brx.zip`) into SQLite.
Unpacks JSON/CSV transliteration pairs in-memory, validates Devanagari script coverage,
creates the dataset source record, and batch-inserts words with their Roman transliterations.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import zipfile
from pathlib import Path

from bhasha_lib.db import (
    DEFAULT_DB_PATH,
    add_source,
    get_connection,
    init_db,
)
from bhasha_lib.tokenizer import normalize

SOURCE_TITLE = "Aksharantar brx"
SOURCE_TYPE = "dataset"
SOURCE_AUTHOR = "AI4Bharat"
SOURCE_URL = "https://huggingface.co/datasets/ai4bharat/Aksharantar"
BATCH_SIZE = 5000


def _has_devanagari(text: str) -> bool:
    """Check if the text contains at least one Devanagari character (0900-097F)."""
    return any("\u0900" <= ch <= "\u097f" for ch in text)


def _iter_zip_records(z: zipfile.ZipFile):
    """Yield raw dictionary records from jsonl/json/csv files within the zip."""
    for filename in sorted(z.namelist()):
        if filename.endswith("/"):
            continue

        with z.open(filename) as raw_file:
            # Handle JSON / JSONL files
            if filename.endswith((".json", ".jsonl")):
                text_stream = io.TextIOWrapper(raw_file, encoding="utf-8")
                # Try reading line by line (JSON lines format)
                first_line = text_stream.readline()
                if not first_line:
                    continue

                first_stripped = first_line.strip()
                if first_stripped.startswith("["):
                    # Whole-file JSON array
                    rest = text_stream.read()
                    data = json.loads(first_line + rest)
                    for item in data:
                        if isinstance(item, dict):
                            yield item
                else:
                    # JSON Lines format
                    if first_stripped:
                        try:
                            yield json.loads(first_stripped)
                        except json.JSONDecodeError:
                            pass
                    for line in text_stream:
                        line_stripped = line.strip()
                        if line_stripped:
                            try:
                                yield json.loads(line_stripped)
                            except json.JSONDecodeError:
                                pass
            elif filename.endswith((".csv", ".tsv")):
                text_stream = io.TextIOWrapper(raw_file, encoding="utf-8")
                delimiter = "\t" if filename.endswith(".tsv") else ","
                reader = csv.DictReader(text_stream, delimiter=delimiter)
                yield from reader


def load_aksharantar(
    zip_path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
    license: str = "",
) -> dict[str, int]:
    """Load Aksharantar transliteration records directly into the database.

    1. Reads zip in-memory without extracting to disk.
    2. Normalizes Bodo words and skips empty or non-Devanagari entries.
    3. Adds a source record for AI4Bharat Aksharantar.
    4. Stores each unique word once (freq=1) with batched transactions.
    5. No occurrences rows are created.
    6. Prints and returns summary statistics.
    """
    archive_path = Path(zip_path)
    if not archive_path.is_file():
        raise FileNotFoundError(f"Dataset archive not found: {archive_path}")

    # Ensure DB tables exist
    init_db(db_path)

    # Register source record
    source_id = add_source(
        title=SOURCE_TITLE,
        type=SOURCE_TYPE,
        author=SOURCE_AUTHOR,
        url=SOURCE_URL,
        license=license,
        db_path=db_path,
    )

    records_read = 0
    records_skipped = 0
    unique_words: dict[str, str] = {}

    with zipfile.ZipFile(archive_path, "r") as z:
        for record in _iter_zip_records(z):
            records_read += 1

            native_val = (
                record.get("native word")
                or record.get("native_word")
                or record.get("native")
                or record.get("bodo")
            )
            roman_val = (
                record.get("english word")
                or record.get("english_word")
                or record.get("roman")
                or record.get("english")
            )

            if not native_val or not str(native_val).strip():
                records_skipped += 1
                continue

            normalized_word = normalize(str(native_val).strip())

            # Skip words containing no Devanagari characters
            if not normalized_word or not _has_devanagari(normalized_word):
                records_skipped += 1
                continue

            clean_roman = str(roman_val).strip() if roman_val else None

            # Track unique words (keep first valid roman transliteration)
            if normalized_word not in unique_words:
                unique_words[normalized_word] = clean_roman or ""
            elif clean_roman and not unique_words[normalized_word]:
                unique_words[normalized_word] = clean_roman

    # Batched insertion into words table (freq=1)
    insert_items = list(unique_words.items())
    unique_words_stored = len(insert_items)

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        for i in range(0, unique_words_stored, BATCH_SIZE):
            chunk = insert_items[i : i + BATCH_SIZE]
            cursor.executemany(
                """
                INSERT INTO words (word, roman, freq)
                VALUES (?, ?, 1)
                ON CONFLICT(word) DO UPDATE SET
                    roman = COALESCE(words.roman, excluded.roman)
                """,
                [(w, r if r else None) for w, r in chunk],
            )

    summary = {
        "records_read": records_read,
        "unique_words_stored": unique_words_stored,
        "records_skipped": records_skipped,
        "source_id": source_id,
    }

    print(
        f"Aksharantar brx summary: records read={records_read}, "
        f"unique words stored={unique_words_stored}, "
        f"records skipped={records_skipped}"
    )

    return summary


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point for loading Aksharantar dataset."""
    parser = argparse.ArgumentParser(
        description="Load AI4Bharat Aksharantar brx dataset zip into SQLite database."
    )
    parser.add_argument("zip_path", type=str, help="Path to brx.zip file")
    parser.add_argument(
        "--license",
        type=str,
        required=True,
        help="License for the dataset source record",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    args = parser.parse_args(argv)

    load_aksharantar(
        zip_path=args.zip_path,
        db_path=args.db,
        license=args.license,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
