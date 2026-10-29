"""Lexical annotation and review workflow module for bhasha_lib.

💡 FILE INSIGHT & PURPOSE:
Manages lexical meaning enrichment and community review cycles for dictionary definitions.
Supports bootstrapping high-frequency seed vocabulary (`bootstrap_seed_meanings()`), exporting unannotated
words to review CSVs (`export_for_review()`), validating submissions, and calculating annotation progress stats.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bhasha_lib.db import (
    DEFAULT_DB_PATH,
    VALID_ORIGINS,
    get_connection,
    init_db,
    update_word_meaning,
)

REQUIRED_CSV_FIELDS: frozenset[str] = frozenset(
    {"word", "meaning_hi", "meaning_en", "verified_by"}
)

CSV_FIELDNAMES: list[str] = [
    "word",
    "roman",
    "meaning_hi",
    "meaning_en",
    "pos",
    "origin",
    "dialect",
    "verified_by",
    "notes",
]


def _resolve_paths(
    p1: str | Path,
    p2: str | Path,
) -> tuple[Path, Path]:
    """Helper to flexibly handle (db_path, csv_path) or (csv_path, db_path)."""
    s1, s2 = str(p1), str(p2)
    if (s1.endswith(".sqlite") or s1.endswith(".db")) or s2.endswith(".csv"):
        return Path(p1), Path(p2)
    if (s2.endswith(".sqlite") or s2.endswith(".db")) or s1.endswith(".csv"):
        return Path(p2), Path(p1)
    return Path(p1), Path(p2)


CONTEXT_1_COL: str = "context_1 (do not edit)"
CONTEXT_2_COL: str = "context_2 (do not edit)"


def export_for_review(
    db_path: str | Path = DEFAULT_DB_PATH,
    csv_path: str | Path = "data/review_batch_1.csv",
    limit: int | None = 500,
    only_empty: bool = True,
    seed: int = 1,
    source_id: int | None = None,
    with_context: bool = False,
    min_freq: int = 1,
    order: str = "random",
    exclude_hyphen: bool = False,
    batch_name: str | None = None,
    words_file: str | Path | None = None,
    only_without_occurrences: bool = False,
    exclude_origin: str | None = None,
    skip_exported: bool = False,
) -> int:
    """Export words needing review into a UTF-8 with BOM CSV template.

    Picks words where meaning_hi and meaning_en are both empty.
    Supports filtering by source, minimum frequency, excluding hyphenated words,
    words file, origin exclusion, occurrence exclusion, skipping already exported words,
    sorting by frequency or repeatable random shuffle, and adding occurrence contexts.
    Records export batch and words into review_batches and review_batch_words.

    Args:
        db_path: Path to the SQLite database.
        csv_path: Destination CSV file path.
        limit: Maximum number of rows to export (default: 500, or None).
        only_empty: Only include words with both meanings empty (default: True).
        seed: Random seed for deterministic reproducibility (default: 1).
        source_id: If given, only includes words having an occurrence from this source.
        with_context: If True, adds read-only context_1 and context_2 columns.
        min_freq: Minimum frequency threshold (default: 1).
        order: Ordering strategy: 'random' (default) or 'freq' (descending).
        exclude_hyphen: If True, skips words containing a hyphen.
        batch_name: Name of the review batch (required in CLI, fails if exists).
        words_file: Path to a UTF-8 file with words to export (one per line).
        only_without_occurrences: Only words that have no rows in occurrences.
        exclude_origin: Origin to skip (e.g. 'loan').
        skip_exported: Skip words already recorded in any earlier batch.

    Returns:
        Number of word rows exported.
    """
    actual_db_path, actual_csv_path = _resolve_paths(db_path, csv_path)
    init_db(actual_db_path)

    clean_batch_name = batch_name.strip() if batch_name is not None else None
    if clean_batch_name:
        with get_connection(actual_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM review_batches WHERE batch_name = ?",
                (clean_batch_name,),
            )
            if cursor.fetchone() is not None:
                raise ValueError(f"Batch '{clean_batch_name}' already exists.")

    words_file_set: set[str] | None = None
    if words_file is not None:
        wf_path = Path(words_file)
        if not wf_path.is_file():
            raise FileNotFoundError(f"Words file not found: {wf_path}")
        with open(wf_path, encoding="utf-8-sig") as f:
            words_file_set = {line.strip() for line in f if line.strip()}

    conditions: list[str] = []
    params: list[Any] = []

    if only_empty:
        conditions.append(
            "(words.meaning_hi IS NULL OR words.meaning_hi = '') AND "
            "(words.meaning_en IS NULL OR words.meaning_en = '')"
        )

    if min_freq > 1:
        conditions.append("words.freq >= ?")
        params.append(min_freq)

    if exclude_hyphen:
        conditions.append("words.word NOT LIKE '%-%'")

    if source_id is not None:
        conditions.append(
            "words.word IN (SELECT word FROM occurrences WHERE source_id = ?)"
        )
        params.append(source_id)

    if only_without_occurrences:
        conditions.append(
            "words.word NOT IN (SELECT word FROM occurrences WHERE word IS NOT NULL)"
        )

    if exclude_origin:
        conditions.append("(words.origin IS NULL OR LOWER(words.origin) != ?)")
        params.append(exclude_origin.strip().lower())

    if skip_exported:
        conditions.append(
            "words.word NOT IN ("
            "SELECT word FROM review_batch_words WHERE word IS NOT NULL"
            ")"
        )

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    if order.lower() == "freq":
        order_clause = "ORDER BY words.freq DESC, words.word ASC"
    else:
        order_clause = "ORDER BY words.word ASC"

    query = f"""
        SELECT words.word, words.roman, words.meaning_hi, words.meaning_en,
               words.pos, words.origin, words.dialect, words.verified_by, words.freq
        FROM words
        {where_clause}
        {order_clause}
    """

    with get_connection(actual_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        candidate_rows = [dict(r) for r in cursor.fetchall()]

    if words_file_set is not None:
        candidate_rows = [r for r in candidate_rows if r["word"] in words_file_set]

    # If random ordering is requested, shuffle with reproducible seed
    if order.lower() != "freq":
        rng = random.Random(seed)
        rng.shuffle(candidate_rows)

    if limit is not None and limit >= 0:
        selected_rows = candidate_rows[:limit]
    else:
        selected_rows = candidate_rows

    contexts_map: dict[str, list[str]] = {}
    if with_context and selected_rows:
        with get_connection(actual_db_path) as conn:
            cursor = conn.cursor()
            for r in selected_rows:
                w = r["word"]
                if source_id is not None:
                    cursor.execute(
                        """
                        SELECT context FROM occurrences
                        WHERE word = ?
                        ORDER BY (CASE WHEN source_id = ? THEN 0 ELSE 1 END), rowid ASC
                        LIMIT 2
                        """,
                        (w, source_id),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT context FROM occurrences
                        WHERE word = ?
                        ORDER BY rowid ASC
                        LIMIT 2
                        """,
                        (w,),
                    )
                snippets = [row[0] for row in cursor.fetchall() if row[0]]
                contexts_map[w] = snippets

    fieldnames = list(CSV_FIELDNAMES)
    if with_context:
        fieldnames.extend([CONTEXT_1_COL, CONTEXT_2_COL])

    actual_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(actual_csv_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in selected_rows:
            w = row.get("word") or ""
            row_dict: dict[str, Any] = {
                "word": w,
                "roman": row.get("roman") or "",
                "meaning_hi": row.get("meaning_hi") or "",
                "meaning_en": row.get("meaning_en") or "",
                "pos": row.get("pos") or "",
                "origin": row.get("origin") or "",
                "dialect": row.get("dialect") or "",
                "verified_by": row.get("verified_by") or "",
                "notes": "",
            }
            if with_context:
                snippets = contexts_map.get(w, [])
                row_dict[CONTEXT_1_COL] = snippets[0] if len(snippets) > 0 else ""
                row_dict[CONTEXT_2_COL] = snippets[1] if len(snippets) > 1 else ""

            writer.writerow(row_dict)

    if clean_batch_name:
        now_iso = datetime.now(UTC).isoformat()
        with get_connection(actual_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO review_batches (
                    batch_name, created_at, csv_path, words_count, imported_at
                ) VALUES (?, ?, ?, ?, NULL)
                """,
                (clean_batch_name, now_iso, str(actual_csv_path), len(selected_rows)),
            )
            for row in selected_rows:
                cursor.execute(
                    """
                    INSERT INTO review_batch_words (batch_name, word)
                    VALUES (?, ?)
                    """,
                    (clean_batch_name, row["word"]),
                )

    return len(selected_rows)


# Alias for backwards compatibility
export_meanings_csv = export_for_review


def import_meanings(
    csv_path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
    batch_name: str | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Import reviewed meanings from CSV into database with robust validation.

    Rules:
    - Validates required CSV headers:
      'word', 'meaning_hi', 'meaning_en', 'verified_by'.
    - Reads the CSV as UTF-8 (accepts BOM).
    - Preserves the original CSV file on disk.
    - Normalizes words and text annotations to Unicode NFC.
    - Skips a row if both meaning_hi and meaning_en are empty.
    - REJECTS a row (prints line number) if verified_by is empty, or if origin is
      not one of bodo, loan, unsure (empty origin is allowed and stays unchanged).
    - REJECTS a row if status is supplied and not in ('community', 'expert').
    - Never overwrites an existing non-empty meaning. If a meaning already exists
      and differs, prints a conflict line and skips it.
    - Never changes the word text itself.
    - Sets status to 'community' (or 'expert' if explicitly specified)
      and stores verified_by.
    - If dry_run is True, prints what would be updated/skipped/rejected/conflicting,
      writes NOTHING to database, and does not set imported_at.
    - If batch_name is provided and not dry_run, sets imported_at for that batch.
    - Prints a summary: updated, skipped, rejected, conflicts.

    Returns:
        Summary dict containing counts of added, updated, skipped,
        rejected, and conflicts.
    """
    actual_db_path, actual_csv_path = _resolve_paths(db_path, csv_path)
    if not actual_csv_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {actual_csv_path}")

    init_db(actual_db_path)
    added = 0
    updated = 0
    skipped = 0
    rejected = 0
    conflicts = 0

    with open(actual_csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"Invalid review CSV: '{actual_csv_path.name}' is empty.")

        fieldnames_set = {f.strip() for f in reader.fieldnames if f}
        missing_headers = REQUIRED_CSV_FIELDS - fieldnames_set
        if missing_headers:
            raise ValueError(
                f"Invalid review CSV '{actual_csv_path.name}': "
                f"missing required header(s): {sorted(missing_headers)}"
            )

        for line_no, row in enumerate(reader, start=2):  # Header is line 1
            raw_word = (row.get("word") or "").strip()
            if not raw_word:
                continue

            word = unicodedata.normalize("NFC", raw_word)
            raw_hi = (row.get("meaning_hi") or "").strip()
            meaning_hi = unicodedata.normalize("NFC", raw_hi) if raw_hi else None

            raw_en = (row.get("meaning_en") or "").strip()
            meaning_en = unicodedata.normalize("NFC", raw_en) if raw_en else None

            origin_raw = (row.get("origin") or "").strip().lower()
            origin = origin_raw if origin_raw else None

            raw_verified = (row.get("verified_by") or "").strip()
            verified_by = (
                unicodedata.normalize("NFC", raw_verified) if raw_verified else None
            )

            raw_pos = (row.get("pos") or "").strip()
            pos = unicodedata.normalize("NFC", raw_pos) if raw_pos else None

            raw_dialect = (row.get("dialect") or "").strip()
            dialect = unicodedata.normalize("NFC", raw_dialect) if raw_dialect else None

            # Skip row if both meanings are empty (unannotated row)
            if not meaning_hi and not meaning_en:
                if dry_run:
                    print(
                        f"Line {line_no}: Skipped - Both meanings empty "
                        f"for word '{word}'."
                    )
                skipped += 1
                continue

            raw_status = (row.get("status") or "").strip().lower()
            if raw_status:
                if raw_status not in ("community", "expert"):
                    print(
                        f"Line {line_no}: Rejected - Invalid status '{raw_status}' "
                        f"for word '{word}'. Must be 'community' or 'expert'."
                    )
                    rejected += 1
                    continue
                target_status = raw_status
            else:
                target_status = "community"

            # Validation: verified_by is mandatory when meanings are supplied
            if not verified_by:
                print(
                    f"Line {line_no}: Rejected - 'verified_by' is empty "
                    f"for word '{word}'."
                )
                rejected += 1
                continue

            # Validation: origin must be bodo, loan, unsure, or empty
            if origin and origin not in VALID_ORIGINS:
                print(
                    f"Line {line_no}: Rejected - Invalid origin '{origin}' "
                    f"for word '{word}'. Must be one of: "
                    f"{sorted(VALID_ORIGINS)} or empty."
                )
                rejected += 1
                continue

            # Fetch existing word details
            with get_connection(actual_db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT meaning_hi, meaning_en, origin FROM words WHERE word = ?",
                    (word,),
                )
                existing = cursor.fetchone()

            if existing is not None:
                exist_hi = existing["meaning_hi"] or None
                exist_en = existing["meaning_en"] or None
                exist_origin = existing["origin"] or None

                # Check for conflicts on non-empty existing meanings
                conflict_found = False
                if exist_hi and meaning_hi and exist_hi != meaning_hi:
                    print(
                        f"Line {line_no}: Conflict - Word '{word}' already has "
                        f"meaning_hi='{exist_hi}', incoming='{meaning_hi}'. Skipping."
                    )
                    conflict_found = True
                if exist_en and meaning_en and exist_en != meaning_en:
                    print(
                        f"Line {line_no}: Conflict - Word '{word}' already has "
                        f"meaning_en='{exist_en}', incoming='{meaning_en}'. Skipping."
                    )
                    conflict_found = True

                if conflict_found:
                    conflicts += 1
                    continue

                target_hi = exist_hi if exist_hi else meaning_hi
                target_en = exist_en if exist_en else meaning_en
                target_origin = origin if origin else exist_origin

                if dry_run:
                    print(
                        f"Line {line_no}: Would update - Word '{word}' "
                        f"(meaning_hi='{target_hi}', meaning_en='{target_en}', "
                        f"origin='{target_origin}', status='{target_status}', "
                        f"verified_by='{verified_by}')."
                    )
                    updated += 1
                else:
                    update_word_meaning(
                        word=word,
                        meaning_hi=target_hi,
                        meaning_en=target_en,
                        pos=pos,
                        origin=target_origin,
                        status=target_status,
                        verified_by=verified_by,
                        dialect=dialect,
                        db_path=actual_db_path,
                    )
                    updated += 1
            else:
                if dry_run:
                    print(
                        f"Line {line_no}: Skipped - Word '{word}' "
                        f"not found in database."
                    )
                skipped += 1

    summary = {
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "rejected": rejected,
        "conflicts": conflicts,
    }
    print(
        f"Summary: {updated} updated, {skipped} skipped, "
        f"{rejected} rejected, {conflicts} conflicts."
    )

    clean_batch_name = batch_name.strip() if batch_name is not None else None
    if clean_batch_name and not dry_run:
        now_iso = datetime.now(UTC).isoformat()
        with get_connection(actual_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE review_batches SET imported_at = ? WHERE batch_name = ?",
                (now_iso, clean_batch_name),
            )

    return summary


# Alias for backwards compatibility
import_meanings_csv = import_meanings


def validate_review_csv(csv_path: str | Path) -> bool:
    """Validate that a review CSV file exists and contains all required headers.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If file is empty or missing required headers.
    """
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"Review CSV not found: {path}")
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"Invalid review CSV: '{path.name}' is empty.")
        fieldnames_set = {f.strip() for f in reader.fieldnames if f}
        missing_headers = REQUIRED_CSV_FIELDS - fieldnames_set
        if missing_headers:
            headers_str = ", ".join(sorted(missing_headers))
            raise ValueError(
                f"Missing required CSV headers in '{path.name}': {headers_str}"
            )
    return True


def import_reviewed_csv(
    csv_path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
    batch_name: str | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Import reviewed annotations with safety checks and dry-run mode."""
    validate_review_csv(csv_path)
    res = import_meanings(
        csv_path=csv_path,
        db_path=db_path,
        batch_name=batch_name,
        dry_run=dry_run,
    )
    if dry_run:
        res["would_update"] = res.get("updated", 0)
    return res


def bootstrap_seed_meanings(
    db_path: str | Path = DEFAULT_DB_PATH,
    dry_run: bool = False,
) -> dict[str, int]:
    """Inspect verified meanings in lexicon database and report bootstrap metrics.

    Never fabricates or auto-generates meanings without human or community review.

    Returns:
        Summary dict containing counts of words with meanings and total words.
    """
    actual_db_path = Path(db_path)
    init_db(actual_db_path)
    stats = get_meanings_stats(db_path=actual_db_path)
    words_with_meaning = stats.get("words_with_meaning", 0)
    total_words = stats.get("total_words", 0)
    status_counts = stats.get("status_counts", {})
    print(
        f"Bootstrap status: {words_with_meaning} of {total_words} "
        "words have verified meanings."
    )
    print(f"Status distribution: {status_counts}")
    return {
        "bootstrapped": 0,
        "total_words": total_words,
        "words_with_meaning": words_with_meaning,
    }


def get_meanings_stats(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Return statistical summary of meanings, status, and origins."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Total words
        cursor.execute("SELECT count(1) FROM words")
        total_words = int(cursor.fetchone()[0])

        # Words with any meaning
        cursor.execute(
            """
            SELECT count(1) FROM words
            WHERE (meaning_hi IS NOT NULL AND meaning_hi != '')
               OR (meaning_en IS NOT NULL AND meaning_en != '')
            """
        )
        words_with_meaning = int(cursor.fetchone()[0])

        # Count by status
        cursor.execute(
            "SELECT COALESCE(status, 'unverified') as st, count(1) "
            "FROM words GROUP BY st"
        )
        status_counts = {row["st"]: row[1] for row in cursor.fetchall()}

        # Count by origin
        cursor.execute(
            "SELECT COALESCE(origin, 'unset') as orig, count(1) "
            "FROM words GROUP BY orig"
        )
        origin_counts = {row["orig"]: row[1] for row in cursor.fetchall()}

    return {
        "total_words": total_words,
        "words_with_meaning": words_with_meaning,
        "status_counts": status_counts,
        "origin_counts": origin_counts,
    }


def print_stats(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Print meanings statistics to standard output."""
    stats = get_meanings_stats(db_path=db_path)
    print("Lexicon Meanings Statistics:")
    print(f"  Total words: {stats['total_words']}")
    print(f"  Words with any meaning: {stats['words_with_meaning']}")
    print("  Count by status:")
    for st, count in sorted(stats["status_counts"].items()):
        print(f"    - {st}: {count}")
    print("  Count by origin:")
    for orig, count in sorted(stats["origin_counts"].items()):
        print(f"    - {orig}: {count}")
    return stats


def get_progress_stats(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Return progress statistics per review batch and overall totals."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Batches
        cursor.execute(
            """
            SELECT batch_name, created_at, csv_path, words_count, imported_at
            FROM review_batches
            ORDER BY created_at ASC, batch_name ASC
            """
        )
        batch_rows = cursor.fetchall()
        batches: list[dict[str, Any]] = []
        for b in batch_rows:
            b_name = b["batch_name"]
            cursor.execute(
                """
                SELECT count(DISTINCT rbw.word)
                FROM review_batch_words rbw
                JOIN words w ON rbw.word = w.word
                WHERE rbw.batch_name = ?
                  AND ((w.meaning_hi IS NOT NULL AND w.meaning_hi != '')
                    OR (w.meaning_en IS NOT NULL AND w.meaning_en != ''))
                """,
                (b_name,),
            )
            words_with_meaning = int(cursor.fetchone()[0])
            batches.append(
                {
                    "batch_name": b_name,
                    "created_at": b["created_at"],
                    "csv_path": b["csv_path"],
                    "words_exported": b["words_count"],
                    "words_with_meaning": words_with_meaning,
                    "imported_at": b["imported_at"],
                }
            )

        # Totals
        cursor.execute("SELECT count(1) FROM words")
        total_words = int(cursor.fetchone()[0])

        cursor.execute(
            """
            SELECT count(1) FROM words
            WHERE (meaning_hi IS NOT NULL AND meaning_hi != '')
               OR (meaning_en IS NOT NULL AND meaning_en != '')
            """
        )
        total_words_with_meaning = int(cursor.fetchone()[0])

        cursor.execute(
            "SELECT COALESCE(status, 'unverified') as st, count(1) "
            "FROM words GROUP BY st"
        )
        status_counts = {row["st"]: row[1] for row in cursor.fetchall()}

        cursor.execute(
            "SELECT COALESCE(origin, 'unset') as orig, count(1) "
            "FROM words GROUP BY orig"
        )
        origin_counts = {row["orig"]: row[1] for row in cursor.fetchall()}

    return {
        "batches": batches,
        "totals": {
            "total_words": total_words,
            "words_with_meaning": total_words_with_meaning,
            "status_counts": status_counts,
            "origin_counts": origin_counts,
        },
    }


def print_progress(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Print progress per review batch and overall totals to standard output."""
    stats = get_progress_stats(db_path=db_path)
    print("Review Batches Progress:")
    if not stats["batches"]:
        print("  No review batches found.")
    else:
        for b in stats["batches"]:
            imported_str = b["imported_at"] if b["imported_at"] else "None"
            print(f"  Batch: {b['batch_name']}")
            print(f"    Words exported: {b['words_exported']}")
            print(f"    Words with meaning: {b['words_with_meaning']}")
            print(f"    Imported at: {imported_str}")

    totals = stats["totals"]
    print("\nTotals:")
    print(f"  Words with a meaning: {totals['words_with_meaning']}")
    print("  Count by status:")
    for st, count in sorted(totals["status_counts"].items()):
        print(f"    - {st}: {count}")
    print("  Count by origin:")
    for orig, count in sorted(totals["origin_counts"].items()):
        print(f"    - {orig}: {count}")

    return stats


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for export, import, progress, and stats."""
    parser = argparse.ArgumentParser(
        description="Manage lexical meanings review workflow."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # export
    p_export = subparsers.add_parser("export", help="Export words for community review")
    p_export.add_argument("out_csv", type=str, help="Destination CSV file path")
    p_export.add_argument(
        "--batch-name",
        type=str,
        required=True,
        help="Batch name (required when writing a CSV; fails if exists)",
    )
    p_export.add_argument(
        "--words-file",
        type=str,
        default=None,
        help="Path to UTF-8 file with words to export (one per line)",
    )
    p_export.add_argument(
        "--only-without-occurrences",
        action="store_true",
        default=False,
        help="Only words that have no rows in occurrences",
    )
    p_export.add_argument(
        "--exclude-origin",
        type=str,
        default=None,
        help="Skip words whose origin matches this value (e.g. loan)",
    )
    p_export.add_argument(
        "--skip-exported",
        action="store_true",
        default=False,
        help="Skip words already in any earlier batch",
    )
    p_export.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum words to export (default: 500)",
    )
    p_export.add_argument(
        "--db",
        type=str,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    p_export.add_argument(
        "--seed",
        type=int,
        default=1,
        help="Random seed for repeatable sampling (default: 1)",
    )
    p_export.add_argument(
        "--source-id",
        type=int,
        default=None,
        help="Only words that have an occurrence from this source ID",
    )
    p_export.add_argument(
        "--with-context",
        action="store_true",
        default=False,
        help="Add read-only context_1 and context_2 columns to the CSV",
    )
    p_export.add_argument(
        "--min-freq",
        type=int,
        default=1,
        help="Only words with freq >= N (default: 1)",
    )
    p_export.add_argument(
        "--order",
        type=str,
        choices=["random", "freq"],
        default="random",
        help="Ordering strategy: random (default) or freq (descending)",
    )
    p_export.add_argument(
        "--exclude-hyphen",
        action="store_true",
        default=False,
        help="Skip words that contain a hyphen",
    )

    # import
    p_import = subparsers.add_parser(
        "import", help="Import filled review CSV into database"
    )
    p_import.add_argument("in_csv", type=str, help="Reviewed input CSV path")
    p_import.add_argument(
        "--db",
        type=str,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    p_import.add_argument(
        "--batch-name",
        type=str,
        default=None,
        help="Batch name to set imported_at",
    )
    p_import.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be updated/skipped/rejected/conflicting without writing",
    )

    # progress
    p_progress = subparsers.add_parser(
        "progress", help="Display review batches progress and totals"
    )
    p_progress.add_argument(
        "--db",
        type=str,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )

    # stats
    p_stats = subparsers.add_parser("stats", help="Display lexicon meanings statistics")
    p_stats.add_argument(
        "--db",
        type=str,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )

    # bootstrap
    p_bootstrap = subparsers.add_parser(
        "bootstrap", help="Inspect and report verified meanings status"
    )
    p_bootstrap.add_argument(
        "--db",
        type=str,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    p_bootstrap.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Simulate bootstrap process without modifying database",
    )

    args = parser.parse_args(argv)

    if args.command == "export":
        try:
            exported = export_for_review(
                db_path=args.db,
                csv_path=args.out_csv,
                limit=args.limit,
                seed=args.seed,
                source_id=args.source_id,
                with_context=args.with_context,
                min_freq=args.min_freq,
                order=args.order,
                exclude_hyphen=args.exclude_hyphen,
                batch_name=args.batch_name,
                words_file=args.words_file,
                only_without_occurrences=args.only_without_occurrences,
                exclude_origin=args.exclude_origin,
                skip_exported=args.skip_exported,
            )
        except ValueError as err:
            print(f"Error: {err}", file=sys.stderr)
            return 1
        print(f"Exported {exported} words for review to '{args.out_csv}'.")
        return 0

    if args.command == "import":
        import_meanings(
            csv_path=args.in_csv,
            db_path=args.db,
            batch_name=args.batch_name,
            dry_run=args.dry_run,
        )
        return 0

    if args.command == "progress":
        print_progress(db_path=args.db)
        return 0

    if args.command == "stats":
        print_stats(db_path=args.db)
        return 0

    if args.command == "bootstrap":
        bootstrap_seed_meanings(db_path=args.db, dry_run=args.dry_run)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
