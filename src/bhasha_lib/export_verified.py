"""Export verified lexicon data and license metadata.

💡 FILE INSIGHT & PURPOSE:
Public distribution and release packaging pipeline (`export_verified`).
Extracts only community- or expert-verified dictionary words with non-empty definitions,
generating clean BOM-encoded UTF-8 CSV (`lexicon_verified.csv`), JSON (`lexicon_verified.json`),
and accompanying license manifests (`DATA_LICENSE.txt`) while protecting reviewer privacy.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from bhasha_lib.db import DEFAULT_DB_PATH, get_connection, init_db

EXPORT_COLUMNS: list[str] = [
    "word",
    "roman",
    "meaning_hi",
    "meaning_en",
    "pos",
    "origin",
    "dialect",
    "status",
]


def export_verified(
    out_folder: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Export verified words and licensing information.

    Exports only words whose status is 'community' or 'expert' and which have
    at least one meaning (meaning_hi or meaning_en non-empty).
    Excludes verified_by for contributor privacy.
    Outputs:
    - out_folder/lexicon_verified.csv (UTF-8 with BOM)
    - out_folder/lexicon_verified.json (UTF-8)
    - out_folder/DATA_LICENSE.txt

    Returns:
        Summary dict containing counts and generated file paths.
    """
    out_dir = Path(out_folder)
    out_dir.mkdir(parents=True, exist_ok=True)

    init_db(db_path)

    # 1. Fetch verified words with at least one meaning
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT word, roman, meaning_hi, meaning_en, pos, origin, dialect, status
            FROM words
            WHERE status IN ('community', 'expert')
              AND (
                (meaning_hi IS NOT NULL AND trim(meaning_hi) != '')
                OR
                (meaning_en IS NOT NULL AND trim(meaning_en) != '')
              )
            ORDER BY word ASC
            """
        )
        rows = [dict(r) for r in cursor.fetchall()]

        # 2. Fetch distinct sources and licenses
        cursor.execute(
            """
            SELECT DISTINCT title, license
            FROM sources
            ORDER BY title ASC
            """
        )
        sources = [
            (
                row["title"] or "Untitled source",
                row["license"] or "Unspecified license",
            )
            for row in cursor.fetchall()
        ]

    # Prepare data records
    export_records: list[dict[str, Any]] = []
    origin_counts: dict[str, int] = {}

    for row in rows:
        record = {
            col: (row.get(col) if row.get(col) is not None else "")
            for col in EXPORT_COLUMNS
        }
        export_records.append(record)

        orig = (row.get("origin") or "").strip().lower()
        key = orig if orig else "unset"
        origin_counts[key] = origin_counts.get(key, 0) + 1

    # 3. Write CSV (UTF-8 with BOM)
    csv_path = out_dir / "lexicon_verified.csv"
    with open(csv_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        for record in export_records:
            writer.writerow(record)

    # 4. Write JSON (UTF-8)
    json_path = out_dir / "lexicon_verified.json"
    with open(json_path, mode="w", encoding="utf-8") as f:
        json.dump(export_records, f, ensure_ascii=False, indent=2)

    # 5. Write DATA_LICENSE.txt
    license_path = out_dir / "DATA_LICENSE.txt"
    lines: list[str] = [
        "Each word list entry comes with the license of its source.",
        "",
        "Distinct sources and licenses:",
    ]
    if sources:
        for title, lic in sources:
            lines.append(f"- {title}: {lic}")
    else:
        lines.append("- (No sources recorded)")

    lines.append("")
    lines.append("Contributor names are not published.")
    lines.append("")

    with open(license_path, mode="w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # Print summary
    print(f"Exported {len(export_records)} verified word(s) to {out_dir}.")
    print("Count by origin:")
    if origin_counts:
        for orig, count in sorted(origin_counts.items()):
            print(f"  - {orig}: {count}")
    else:
        print("  (no verified words exported)")

    return {
        "count": len(export_records),
        "origin_counts": origin_counts,
        "csv_path": csv_path,
        "json_path": json_path,
        "license_path": license_path,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for verified lexicon export."""
    parser = argparse.ArgumentParser(
        description="Export verified words and dataset licensing to a folder."
    )
    parser.add_argument(
        "out_folder",
        type=str,
        help="Destination folder for exported files",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    args = parser.parse_args(argv)

    export_verified(args.out_folder, db_path=args.db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
