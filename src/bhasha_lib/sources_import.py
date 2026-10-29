"""Command and utilities for importing sources metadata from CSV.

💡 FILE INSIGHT & PURPOSE:
Imports bibliography and reference data from CSV files into the SQLite `sources` table.
Strictly validates mandatory licensing (`license` field cannot be empty) and supports
safe upserting so duplicate bibliographic entries are reconciled cleanly.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from bhasha_lib.db import (
    DEFAULT_DB_PATH,
    add_source,
    get_connection,
    init_db,
)


def import_sources_csv(
    csv_path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, int]:
    """Import sources from a CSV file into the database.

    Expected CSV columns:
    title, type, author, year, license, url, file_path

    Rules:
    - Skips lines whose title already exists in sources table.
    - Rejects any line with an empty license and prints which line was rejected.

    Returns:
        Dictionary with 'imported', 'skipped', and 'rejected' counts.
    """
    file_path = Path(csv_path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Sources CSV file not found: {file_path}")

    init_db(db_path)

    imported_count = 0
    skipped_count = 0
    rejected_count = 0

    with open(file_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row_idx, raw_row in enumerate(reader, start=2):
            # Normalize dictionary keys by stripping whitespace
            row = {
                (k.strip() if k else ""): (v.strip() if v else "")
                for k, v in raw_row.items()
            }

            title = row.get("title", "")
            type_val = row.get("type", "") or None
            author = row.get("author", "") or None
            year_str = row.get("year", "")
            year_val = int(year_str) if year_str.isdigit() else None
            license_val = row.get("license", "")
            url = row.get("url", "") or None
            item_file_path = row.get("file_path", "") or None

            # Reject lines with empty license
            if not license_val:
                rejected_count += 1
                source_desc = f"'{title}'" if title else f"line {row_idx}"
                print(
                    f"Rejected line {row_idx}: Empty license for source {source_desc}."
                )
                continue

            # Reject lines with missing title
            if not title:
                rejected_count += 1
                print(f"Rejected line {row_idx}: Missing title.")
                continue

            # Skip lines whose title already exists in sources
            with get_connection(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM sources WHERE title = ?",
                    (title,),
                )
                if cursor.fetchone() is not None:
                    skipped_count += 1
                    continue

            add_source(
                title=title,
                type=type_val,
                author=author,
                year=year_val,
                license=license_val,
                url=url,
                file_path=item_file_path,
                db_path=db_path,
            )
            imported_count += 1

    stats = {
        "imported": imported_count,
        "skipped": skipped_count,
        "rejected": rejected_count,
    }

    print(
        f"Sources import complete: {imported_count} imported, "
        f"{skipped_count} skipped, {rejected_count} rejected."
    )
    return stats


def main(argv: list[str] | None = None) -> int:
    """Command-line interface entry point."""
    parser = argparse.ArgumentParser(
        description="Import sources from a CSV file into SQLite database."
    )
    parser.add_argument("csv_file", type=str, help="Path to sources CSV file")
    parser.add_argument(
        "--db",
        type=str,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    args = parser.parse_args(argv)

    import_sources_csv(args.csv_file, db_path=args.db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
