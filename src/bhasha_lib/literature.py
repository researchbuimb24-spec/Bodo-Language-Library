"""Bodo literature, poems, stories, novels, plays, and author metadata module.

💡 FILE INSIGHT & PURPOSE:
Manages the Bodo literary catalog across 8 genres (poem, short story, novel, play, essay, etc.).
Provides metadata validation, author indexing, historical periodical attribution (Bibar, Alari),
and lossless CSV/JSON data export/import equipped with dry-run safety and automatic backups.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
import unicodedata
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from bhasha_lib.audit import check_needs_citation_detail, is_vague_source
from bhasha_lib.db import (
    DEFAULT_DB_PATH,
    VALID_CONFIDENCE_LEVELS,
    VALID_DATE_PRECISIONS,
    VALID_LITERARY_TYPES,
    add_literature_item,
    backup_db,
    get_connection,
    init_db,
)

__all__ = [
    "CSV_LITERATURE_COLUMNS",
    "VALID_CONFIDENCE_LEVELS",
    "VALID_DATE_PRECISIONS",
    "VALID_LITERARY_TYPES",
    "add_literary_record",
    "export_literature_csv",
    "export_literature_json",
    "filter_literature",
    "format_literature_item",
    "get_literary_by_author",
    "get_literary_record",
    "get_literature_by_author",
    "get_literature_missing_citations",
    "get_unverified_literature",
    "import_literature_csv",
    "import_literature_json",
    "main",
    "print_literature",
    "search_literature",
    "validate_literary_record",
]

CSV_LITERATURE_COLUMNS: list[str] = [
    "id",
    "title",
    "title_en",
    "roman_title",
    "literary_type",
    "author",
    "translator",
    "editor",
    "contributor",
    "original_language",
    "translation_languages",
    "year",
    "year_end",
    "date_precision",
    "book_title",
    "publisher",
    "edition",
    "description",
    "people",
    "places",
    "literary_movement",
    "source_id",
    "primary_sources",
    "secondary_sources",
    "source_url",
    "license",
    "confidence",
    "verified_by",
    "verified_on",
    "created_at",
    "updated_at",
]

LITERATURE_FIELDS_SQL = """
    li.id, li.title, li.title_en, li.roman_title, li.literary_type,
    li.author, li.translator, li.editor, li.contributor,
    li.original_language, li.translation_languages,
    li.year, li.year_end, li.date_precision,
    li.book_title, li.publisher, li.edition, li.description,
    li.people, li.places, li.literary_movement,
    li.source_id, li.primary_sources, li.secondary_sources,
    li.source_url, li.license, li.confidence,
    li.verified_by, li.verified_on, li.created_at, li.updated_at,
    s.title AS source_title, s.license AS source_license,
    s.url AS source_ref_url, s.author AS source_author
"""


def _escape_like(text: str, escape_char: str = "\\") -> str:
    """Escape special pattern characters (%, _, and escape_char) for SQLite LIKE."""
    escaped = text.replace(escape_char, escape_char + escape_char)
    escaped = escaped.replace("%", escape_char + "%")
    return escaped.replace("_", escape_char + "_")


def _clean_str(val: Any) -> str | None:
    """Normalize string using Unicode NFC and strip whitespace."""
    if val is None:
        return None
    s = unicodedata.normalize("NFC", str(val).strip())
    return s if s else None


def _format_list_or_str(val: Any) -> str | None:
    """Format string or list of strings into a normalized comma-separated string."""
    if val is None:
        return None
    if isinstance(val, (list, tuple, set)):
        items = [_clean_str(item) for item in val if _clean_str(item)]
        return ", ".join(items) if items else None
    return _clean_str(val)


def validate_literary_record(data: dict[str, Any]) -> list[str]:
    """Validate literary record dictionary against schema and cultural rules.

    Checks:
    - Required 'title' and non-empty.
    - 'literary_type' within VALID_LITERARY_TYPES.
    - Integer 'year' and 'year_end' within realistic range (-5000 to 2100).
    - End year not earlier than publication year.
    - 'date_precision' within VALID_DATE_PRECISIONS.
    - Precision 'exact' or 'range' requires 'year'.
    - 'confidence' within VALID_CONFIDENCE_LEVELS.
    - 'verified' records require non-future 'verified_on' date (YYYY-MM-DD).
    - Verifies license and copyright safety.

    Returns:
        List of validation failure reasons. Empty if valid.
    """
    errors: list[str] = []

    title = data.get("title")
    if not title or not str(title).strip():
        errors.append("Missing required 'title' field.")

    lit_type = data.get("literary_type")
    if not lit_type or not str(lit_type).strip():
        errors.append("Missing required 'literary_type' field.")
    else:
        clean_type = str(lit_type).strip().lower()
        if clean_type not in VALID_LITERARY_TYPES:
            errors.append(
                f"Invalid 'literary_type': '{lit_type}'. Must be one of: "
                f"{sorted(VALID_LITERARY_TYPES)}."
            )

    year = data.get("year")
    year_end = data.get("year_end")

    y_int: int | None = None
    if year is not None and str(year).strip():
        try:
            y_int = int(year)
            if y_int < -5000 or y_int > 2100:
                errors.append(f"Publication year {y_int} is out of realistic range.")
        except (ValueError, TypeError):
            errors.append(f"Invalid 'year' value: {year} (must be an integer).")

    ye_int: int | None = None
    if year_end is not None and str(year_end).strip():
        try:
            ye_int = int(year_end)
            if ye_int < -5000 or ye_int > 2100:
                errors.append(f"End year {ye_int} is out of realistic range.")
        except (ValueError, TypeError):
            errors.append(f"Invalid 'year_end' value: {year_end} (must be an integer).")

    if y_int is not None and ye_int is not None and ye_int < y_int:
        errors.append(
            f"Invalid date range: End year ({ye_int}) cannot be earlier than "
            f"publication year ({y_int})."
        )

    date_precision = data.get("date_precision")
    if date_precision is not None and str(date_precision).strip():
        clean_prec = str(date_precision).strip().lower()
        if clean_prec not in VALID_DATE_PRECISIONS:
            errors.append(
                f"Invalid 'date_precision': '{date_precision}'. Must be one of "
                f"{sorted(VALID_DATE_PRECISIONS)}."
            )
        if clean_prec in ("exact", "range") and y_int is None:
            errors.append(f"Date precision '{clean_prec}' requires a non-null 'year'.")

    confidence = data.get("confidence")
    if confidence is not None and str(confidence).strip():
        clean_conf = str(confidence).strip().lower()
        if clean_conf not in VALID_CONFIDENCE_LEVELS:
            errors.append(
                f"Invalid 'confidence': '{confidence}'. Must be one of "
                f"{sorted(VALID_CONFIDENCE_LEVELS)}."
            )
        if clean_conf == "verified":
            verified_on = data.get("verified_on")
            if not verified_on or not str(verified_on).strip():
                errors.append("'confidence: verified' requires 'verified_on' date.")
            else:
                try:
                    v_date = date.fromisoformat(str(verified_on).strip())
                    if v_date > date.today():
                        errors.append(
                            f"'verified_on' date cannot be in future: {v_date}."
                        )
                except ValueError:
                    errors.append(
                        f"Invalid 'verified_on' date format: {verified_on} "
                        "(must be YYYY-MM-DD)."
                    )

    # Copyright safety check: description must be short factual metadata or summary
    desc = data.get("description")
    if desc and len(str(desc).strip()) > 2500:
        errors.append(
            "Description is excessively long (>2500 chars). Store short factual "
            "summaries only; do not copy full texts or book chapters."
        )

    return errors


def add_literary_record(
    title: str,
    literary_type: str,
    title_en: str | None = None,
    roman_title: str | None = None,
    author: str | None = None,
    translator: str | None = None,
    editor: str | None = None,
    contributor: str | None = None,
    original_language: str | None = "brx",
    translation_languages: list[str] | str | None = None,
    year: int | None = None,
    year_end: int | None = None,
    date_precision: str | None = None,
    book_title: str | None = None,
    publisher: str | None = None,
    edition: str | None = None,
    description: str | None = None,
    people: list[str] | str | None = None,
    places: list[str] | str | None = None,
    literary_movement: str | None = None,
    source_id: int | None = None,
    source_title: str | None = None,
    primary_sources: list[str] | str | None = None,
    secondary_sources: list[str] | str | None = None,
    source_url: str | None = None,
    license: str | None = "own_words",
    confidence: str = "needs_check",
    verified_by: str | None = None,
    verified_on: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
    raise_on_duplicate: bool = False,
) -> int:
    """Insert or update a structured literary record in the database.

    Enforces foreign keys, validates required metadata, dates, and verification.
    Preserves Unicode text with NFC normalization.

    Raises:
        ValueError: If validation fails or duplicate is disallowed.
        sqlite3.IntegrityError: If foreign-key constraint is violated.
    """
    init_db(db_path)

    clean_title = _clean_str(title)
    clean_type = str(literary_type).strip().lower() if literary_type else ""
    clean_conf = _clean_str(confidence) or "needs_check"

    clean_prec = _clean_str(date_precision)
    if clean_prec is None:
        if year is None:
            clean_prec = "unknown"
        elif year_end is not None and year_end != year:
            clean_prec = "range"
        else:
            clean_prec = "exact"

    payload = {
        "title": clean_title,
        "literary_type": clean_type,
        "year": year,
        "year_end": year_end,
        "date_precision": clean_prec,
        "confidence": clean_conf,
        "verified_on": verified_on,
        "description": description,
    }
    validation_errors = validate_literary_record(payload)
    if validation_errors:
        raise ValueError(
            f"Literary record validation failed: {'; '.join(validation_errors)}"
        )

    clean_title_en = _clean_str(title_en)
    clean_roman_title = _clean_str(roman_title)
    clean_author = _clean_str(author)
    clean_translator = _clean_str(translator)
    clean_editor = _clean_str(editor)
    clean_contributor = _clean_str(contributor)
    clean_orig_lang = _clean_str(original_language) or "brx"
    clean_trans_langs = _format_list_or_str(translation_languages)
    clean_book_title = _clean_str(book_title)
    clean_publisher = _clean_str(publisher)
    clean_edition = _clean_str(edition)
    clean_desc = _clean_str(description)
    clean_people = _format_list_or_str(people)
    clean_places = _format_list_or_str(places)
    clean_movement = _clean_str(literary_movement)
    clean_primary = _format_list_or_str(primary_sources)
    clean_secondary = _format_list_or_str(secondary_sources)
    clean_url = _clean_str(source_url)
    clean_license = _clean_str(license) or "own_words"
    clean_vo = _clean_str(verified_on)
    clean_vb = _clean_str(verified_by)

    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        resolved_source_id = source_id
        if resolved_source_id is not None:
            cursor.execute("SELECT id FROM sources WHERE id = ?", (resolved_source_id,))
            if cursor.fetchone() is None:
                raise sqlite3.IntegrityError(
                    f"FOREIGN KEY constraint failed: source_id {resolved_source_id} "
                    "not found in sources."
                )
        elif source_title and source_title.strip():
            st_clean = source_title.strip()
            cursor.execute("SELECT id FROM sources WHERE title = ?", (st_clean,))
            s_row = cursor.fetchone()
            if s_row is not None:
                resolved_source_id = int(s_row[0])
            else:
                cursor.execute(
                    """
                    INSERT INTO sources (title, type, license, url, author)
                    VALUES (?, 'literature_source', ?, ?, ?)
                    """,
                    (
                        st_clean,
                        clean_license or "own_words",
                        clean_url,
                        clean_author,
                    ),
                )
                resolved_source_id = int(cursor.lastrowid)

        # Duplicate check: same title, literary_type, and author
        if clean_author is not None:
            cursor.execute(
                """
                SELECT id FROM literature_items
                WHERE title = ? AND literary_type = ? AND author = ?
                """,
                (clean_title, clean_type, clean_author),
            )
        else:
            cursor.execute(
                """
                SELECT id FROM literature_items
                WHERE title = ? AND literary_type = ? AND author IS NULL
                """,
                (clean_title, clean_type),
            )
        existing = cursor.fetchone()

        if existing is not None:
            if raise_on_duplicate:
                author_str = f" by '{clean_author}'" if clean_author else ""
                raise ValueError(
                    f"Literary record '{clean_title}' ({clean_type}){author_str} "
                    "already exists in database."
                )
            existing_id = int(existing["id"])
            cursor.execute(
                """
                UPDATE literature_items SET
                    title_en = COALESCE(?, title_en),
                    roman_title = COALESCE(?, roman_title),
                    translator = COALESCE(?, translator),
                    editor = COALESCE(?, editor),
                    contributor = COALESCE(?, contributor),
                    original_language = COALESCE(?, original_language),
                    translation_languages = COALESCE(?, translation_languages),
                    year = COALESCE(?, year),
                    year_end = COALESCE(?, year_end),
                    date_precision = COALESCE(?, date_precision),
                    book_title = COALESCE(?, book_title),
                    publisher = COALESCE(?, publisher),
                    edition = COALESCE(?, edition),
                    description = COALESCE(?, description),
                    people = COALESCE(?, people),
                    places = COALESCE(?, places),
                    literary_movement = COALESCE(?, literary_movement),
                    source_id = COALESCE(?, source_id),
                    primary_sources = COALESCE(?, primary_sources),
                    secondary_sources = COALESCE(?, secondary_sources),
                    source_url = COALESCE(?, source_url),
                    license = COALESCE(?, license),
                    confidence = COALESCE(?, confidence),
                    verified_by = COALESCE(?, verified_by),
                    verified_on = COALESCE(?, verified_on),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    clean_title_en,
                    clean_roman_title,
                    clean_translator,
                    clean_editor,
                    clean_contributor,
                    clean_orig_lang,
                    clean_trans_langs,
                    year,
                    year_end,
                    clean_prec,
                    clean_book_title,
                    clean_publisher,
                    clean_edition,
                    clean_desc,
                    clean_people,
                    clean_places,
                    clean_movement,
                    resolved_source_id,
                    clean_primary,
                    clean_secondary,
                    clean_url,
                    clean_license,
                    clean_conf,
                    clean_vb,
                    clean_vo,
                    datetime.now(UTC).isoformat(),
                    existing_id,
                ),
            )
            return existing_id

    # If new record, insert via add_literature_item
    return add_literature_item(
        title=clean_title or "",
        literary_type=clean_type,
        title_en=clean_title_en,
        roman_title=clean_roman_title,
        author=clean_author,
        translator=clean_translator,
        editor=clean_editor,
        contributor=clean_contributor,
        original_language=clean_orig_lang,
        translation_languages=clean_trans_langs,
        year=year,
        year_end=year_end,
        date_precision=clean_prec,
        book_title=clean_book_title,
        publisher=clean_publisher,
        edition=clean_edition,
        description=clean_desc,
        people=clean_people,
        places=clean_places,
        literary_movement=clean_movement,
        source_id=resolved_source_id,
        primary_sources=clean_primary,
        secondary_sources=clean_secondary,
        source_url=clean_url,
        license=clean_license,
        confidence=clean_conf,
        verified_by=clean_vb,
        verified_on=clean_vo,
        db_path=db_path,
    )


def get_literary_record(
    record_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any] | None:
    """Retrieve a single literary record by its unique ID.

    Returns:
        Dictionary containing all literature fields and linked source metadata,
        or None if not found.
    """
    init_db(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        query = f"""
            SELECT
                {LITERATURE_FIELDS_SQL}
            FROM literature_items li
            LEFT JOIN sources s ON li.source_id = s.id
            WHERE li.id = ?
        """
        cursor.execute(query, (int(record_id),))
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)


def filter_literature(
    db_path: str | Path = DEFAULT_DB_PATH,
    literary_type: str | None = None,
    author: str | None = None,
    from_year: int | None = None,
    to_year: int | None = None,
    confidence: str | None = None,
    date_precision: str | None = None,
    original_language: str | None = None,
    literary_movement: str | None = None,
    include_unknown_dates: bool = False,
    sort_order: str = "asc",
) -> list[dict[str, Any]]:
    """Filter literature items by type, author, date range, and confidence.

    Args:
        db_path: Path to SQLite database.
        literary_type: Filter by literary type (poem, novel, play, etc.).
        author: Filter by author name (case-insensitive substring match).
        from_year: Earliest publication year to include.
        to_year: Latest publication year to include.
        confidence: Filter by verification status.
        date_precision: Filter by precision ('exact', 'approximate',
            'range', 'unknown').
        original_language: Filter by original language code.
        literary_movement: Filter by literary movement.
        include_unknown_dates: If False (default), items with null year are excluded.
        sort_order: 'asc' (default) or 'desc'.

    Returns:
        List of literature dictionaries matching the criteria, chronologically ordered.
    """
    init_db(db_path)
    conditions: list[str] = []
    params: list[Any] = []

    if not include_unknown_dates:
        conditions.append("li.year IS NOT NULL")

    if literary_type:
        conditions.append("li.literary_type = ?")
        params.append(literary_type.strip().lower())

    if author:
        clean_author = _escape_like(author.strip())
        conditions.append("li.author LIKE ? ESCAPE '\\'")
        params.append(f"%{clean_author}%")

    if from_year is not None:
        conditions.append("li.year >= ?")
        params.append(int(from_year))

    if to_year is not None:
        conditions.append("li.year <= ?")
        params.append(int(to_year))

    if confidence:
        conditions.append("li.confidence = ?")
        params.append(confidence.strip().lower())

    if date_precision:
        conditions.append("li.date_precision = ?")
        params.append(date_precision.strip().lower())

    if original_language:
        conditions.append("li.original_language = ?")
        params.append(original_language.strip().lower())

    if literary_movement:
        clean_mov = _escape_like(literary_movement.strip())
        conditions.append("li.literary_movement LIKE ? ESCAPE '\\'")
        params.append(f"%{clean_mov}%")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    order = "DESC" if str(sort_order).lower() == "desc" else "ASC"

    query = f"""
        SELECT
            {LITERATURE_FIELDS_SQL}
        FROM literature_items li
        LEFT JOIN sources s ON li.source_id = s.id
        {where_clause}
        ORDER BY
            CASE WHEN li.year IS NULL THEN 1 ELSE 0 END,
            li.year {order},
            COALESCE(li.year_end, li.year) {order},
            li.title ASC
    """

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_literature_by_author(
    author: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """Retrieve literary works by a specific author.

    Returns:
        List of matching literature records, including works with unknown years.
    """
    clean_author = _clean_str(author)
    if not clean_author:
        return []
    return filter_literature(
        db_path=db_path,
        author=clean_author,
        include_unknown_dates=True,
    )


get_literary_by_author = get_literature_by_author


def search_literature(
    query: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    literary_type: str | None = None,
    author: str | None = None,
) -> list[dict[str, Any]]:
    """Search literature records across title, author, description, movement, or source.

    Uses safe wildcard pattern escaping and returns chronologically ordered records.
    """
    clean_query = str(query or "").strip()
    if not clean_query:
        return []

    init_db(db_path)
    pattern = f"%{_escape_like(clean_query)}%"
    conditions = [
        """(
            li.title LIKE ? ESCAPE '\\'
            OR li.title_en LIKE ? ESCAPE '\\'
            OR li.roman_title LIKE ? ESCAPE '\\'
            OR li.author LIKE ? ESCAPE '\\'
            OR li.translator LIKE ? ESCAPE '\\'
            OR li.editor LIKE ? ESCAPE '\\'
            OR li.contributor LIKE ? ESCAPE '\\'
            OR li.book_title LIKE ? ESCAPE '\\'
            OR li.publisher LIKE ? ESCAPE '\\'
            OR li.description LIKE ? ESCAPE '\\'
            OR li.people LIKE ? ESCAPE '\\'
            OR li.places LIKE ? ESCAPE '\\'
            OR li.literary_movement LIKE ? ESCAPE '\\'
            OR li.primary_sources LIKE ? ESCAPE '\\'
            OR li.secondary_sources LIKE ? ESCAPE '\\'
            OR s.title LIKE ? ESCAPE '\\'
        )"""
    ]
    params: list[Any] = [pattern] * 16

    if literary_type:
        conditions.append("li.literary_type = ?")
        params.append(literary_type.strip().lower())

    if author:
        clean_author = _escape_like(author.strip())
        conditions.append("li.author LIKE ? ESCAPE '\\'")
        params.append(f"%{clean_author}%")

    where_clause = f"WHERE {' AND '.join(conditions)}"
    sql = f"""
        SELECT
            {LITERATURE_FIELDS_SQL}
        FROM literature_items li
        LEFT JOIN sources s ON li.source_id = s.id
        {where_clause}
        ORDER BY
            CASE WHEN li.year IS NULL THEN 1 ELSE 0 END,
            li.year ASC,
            COALESCE(li.year_end, li.year) ASC,
            li.title ASC
    """

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def get_literature_missing_citations(
    db_path: str | Path = DEFAULT_DB_PATH,
    literary_type: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve literary records that lack sufficient bibliographic citations.

    A literary work is flagged if:
    - It has no source_id and no primary or secondary bibliographic citations.
    - Its linked source is missing a title or has an empty title.
    - Its source title is only a vague generic site (e.g., 'Wikipedia', 'Google').
    - Its source title is under 15 characters without independent primary citations.
    - Its source lacks specific publication or page details.

    Returns:
        List of literature dictionaries with attached 'missing_reasons' and
        'missing_reason' summary.
    """
    init_db(db_path)
    conditions: list[str] = []
    params: list[Any] = []
    if literary_type:
        conditions.append("li.literary_type = ?")
        params.append(literary_type.strip().lower())

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT
            {LITERATURE_FIELDS_SQL}
        FROM literature_items li
        LEFT JOIN sources s ON li.source_id = s.id
        {where_clause}
        ORDER BY li.id ASC
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]

    flagged: list[dict[str, Any]] = []
    for r in rows:
        source_id = r.get("source_id")
        source_title = (r.get("source_title") or "").strip()
        pri_src = (r.get("primary_sources") or "").strip()
        sec_src = (r.get("secondary_sources") or "").strip()

        missing_reasons: list[str] = []
        if source_id is None and not pri_src and not sec_src:
            missing_reasons.append("Missing citation: No source_id or citations linked")
        elif source_id is not None and not source_title:
            missing_reasons.append("Missing citation: Linked source has empty title")
        elif source_title:
            if is_vague_source(source_title):
                missing_reasons.append(
                    f"Vague citation: Source '{source_title}' is only generic domain"
                )
            elif len(source_title) < 15 and not pri_src and not sec_src:
                missing_reasons.append(
                    f"Short citation: Source '{source_title}' is under 15 characters"
                )
            elif (
                check_needs_citation_detail(source_title)
                and not pri_src
                and not sec_src
            ):
                missing_reasons.append(
                    f"Incomplete citation: Generic site '{source_title}' "
                    "lacks specific publication or page details"
                )

        if missing_reasons:
            item_copy = dict(r)
            item_copy["missing_reasons"] = missing_reasons
            item_copy["missing_reason"] = "; ".join(missing_reasons)
            flagged.append(item_copy)

    return flagged


def get_unverified_literature(
    db_path: str | Path = DEFAULT_DB_PATH,
    literary_type: str | None = None,
) -> list[dict[str, Any]]:
    """List literary records that have not reached 'verified' status.

    Includes records with confidence 'unverified', 'needs_check', or 'disputed'.
    Ordered chronologically.
    """
    init_db(db_path)
    conditions = ["(li.confidence != 'verified' OR li.confidence IS NULL)"]
    params: list[Any] = []
    if literary_type:
        conditions.append("li.literary_type = ?")
        params.append(literary_type.strip().lower())

    where_clause = f"WHERE {' AND '.join(conditions)}"
    query = f"""
        SELECT
            {LITERATURE_FIELDS_SQL}
        FROM literature_items li
        LEFT JOIN sources s ON li.source_id = s.id
        {where_clause}
        ORDER BY
            CASE WHEN li.year IS NULL THEN 1 ELSE 0 END,
            li.year ASC,
            COALESCE(li.year_end, li.year) ASC,
            li.title ASC
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def export_literature_csv(
    csv_path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
    literary_type: str | None = None,
) -> int:
    """Export literary records to a CSV file.

    Returns:
        Number of exported records.
    """
    records = filter_literature(
        db_path=db_path,
        literary_type=literary_type,
        include_unknown_dates=True,
    )
    target = Path(csv_path)
    if target.parent and not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)

    with open(target, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=CSV_LITERATURE_COLUMNS, extrasaction="ignore"
        )
        writer.writeheader()
        for r in records:
            writer.writerow(r)

    return len(records)


def export_literature_json(
    json_path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
    literary_type: str | None = None,
    indent: int = 2,
) -> int:
    """Export literary records to a JSON file.

    Returns:
        Number of exported records.
    """
    records = filter_literature(
        db_path=db_path,
        literary_type=literary_type,
        include_unknown_dates=True,
    )
    target = Path(json_path)
    if target.parent and not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)

    with open(target, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=indent, ensure_ascii=False)

    return len(records)


def import_literature_csv(
    csv_path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Import and validate literary records from a CSV file.

    Creates an ACID-compliant backup before writing changes (if not dry_run).
    Validates required fields and reports rejected rows and duplicates.

    Returns:
        Dictionary with statistics:
        'total', 'imported', 'updated', 'skipped', 'rejected', 'errors', 'dry_run'.
    """
    target = Path(csv_path)
    if not target.is_file():
        raise FileNotFoundError(f"Literature CSV file not found: {target}")

    init_db(db_path)

    backup_file: Path | None = None
    if not dry_run and str(db_path) != ":memory:" and Path(db_path).is_file():
        backup_file = backup_db(db_path)

    stats: dict[str, Any] = {
        "total": 0,
        "imported": 0,
        "updated": 0,
        "skipped": 0,
        "rejected": 0,
        "errors": [],
        "dry_run": dry_run,
        "backup_path": str(backup_file) if backup_file else None,
    }

    with open(target, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row_idx, raw_row in enumerate(reader, start=2):
            stats["total"] += 1
            row = {
                (k.strip() if k else ""): (v.strip() if v else "")
                for k, v in raw_row.items()
            }

            title = row.get("title") or ""
            lit_type = row.get("literary_type") or ""

            year_str = row.get("year", "")
            year_val: int | None = None
            if year_str:
                try:
                    year_val = int(year_str)
                except ValueError:
                    stats["rejected"] += 1
                    stats["errors"].append(
                        f"Row {row_idx} ('{title}'): Invalid year '{year_str}'."
                    )
                    continue

            year_end_str = row.get("year_end", "")
            year_end_val: int | None = None
            if year_end_str:
                try:
                    year_end_val = int(year_end_str)
                except ValueError:
                    stats["rejected"] += 1
                    stats["errors"].append(
                        f"Row {row_idx} ('{title}'): Invalid year_end '{year_end_str}'."
                    )
                    continue

            src_id_str = row.get("source_id", "")
            src_id_val: int | None = None
            if src_id_str:
                try:
                    src_id_val = int(src_id_str)
                except ValueError:
                    stats["rejected"] += 1
                    stats["errors"].append(
                        f"Row {row_idx} ('{title}'): Invalid source_id '{src_id_str}'."
                    )
                    continue

            payload = {
                "title": title,
                "literary_type": lit_type,
                "year": year_val,
                "year_end": year_end_val,
                "date_precision": row.get("date_precision") or None,
                "confidence": row.get("confidence") or "needs_check",
                "verified_on": row.get("verified_on") or None,
                "description": row.get("description") or None,
            }

            validation_errors = validate_literary_record(payload)
            if validation_errors:
                stats["rejected"] += 1
                stats["errors"].append(
                    f"Row {row_idx} ('{title}'): {'; '.join(validation_errors)}"
                )
                continue

            author = row.get("author") or None

            # Check if record already exists
            with get_connection(db_path) as conn:
                cursor = conn.cursor()
                if author is not None:
                    cursor.execute(
                        """
                        SELECT id FROM literature_items
                        WHERE title = ? AND literary_type = ? AND author = ?
                        """,
                        (title, lit_type.lower(), author),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT id FROM literature_items
                        WHERE title = ? AND literary_type = ? AND author IS NULL
                        """,
                        (title, lit_type.lower()),
                    )
                existing = cursor.fetchone()

            if existing is not None:
                if dry_run:
                    stats["updated"] += 1
                else:
                    try:
                        add_literary_record(
                            title=title,
                            literary_type=lit_type,
                            title_en=row.get("title_en") or None,
                            roman_title=row.get("roman_title") or None,
                            author=author,
                            translator=row.get("translator") or None,
                            editor=row.get("editor") or None,
                            contributor=row.get("contributor") or None,
                            original_language=row.get("original_language") or "brx",
                            translation_languages=row.get("translation_languages")
                            or None,
                            year=year_val,
                            year_end=year_end_val,
                            date_precision=row.get("date_precision") or None,
                            book_title=row.get("book_title") or None,
                            publisher=row.get("publisher") or None,
                            edition=row.get("edition") or None,
                            description=row.get("description") or None,
                            people=row.get("people") or None,
                            places=row.get("places") or None,
                            literary_movement=row.get("literary_movement") or None,
                            source_id=src_id_val,
                            primary_sources=row.get("primary_sources") or None,
                            secondary_sources=row.get("secondary_sources") or None,
                            source_url=row.get("source_url") or None,
                            license=row.get("license") or "own_words",
                            confidence=row.get("confidence") or "needs_check",
                            verified_by=row.get("verified_by") or None,
                            verified_on=row.get("verified_on") or None,
                            db_path=db_path,
                            raise_on_duplicate=False,
                        )
                        stats["updated"] += 1
                    except Exception as exc:
                        stats["rejected"] += 1
                        stats["errors"].append(
                            f"Row {row_idx} ('{title}'): Failed to update: {exc}"
                        )
            else:
                if dry_run:
                    stats["imported"] += 1
                else:
                    try:
                        add_literary_record(
                            title=title,
                            literary_type=lit_type,
                            title_en=row.get("title_en") or None,
                            roman_title=row.get("roman_title") or None,
                            author=author,
                            translator=row.get("translator") or None,
                            editor=row.get("editor") or None,
                            contributor=row.get("contributor") or None,
                            original_language=row.get("original_language") or "brx",
                            translation_languages=row.get("translation_languages")
                            or None,
                            year=year_val,
                            year_end=year_end_val,
                            date_precision=row.get("date_precision") or None,
                            book_title=row.get("book_title") or None,
                            publisher=row.get("publisher") or None,
                            edition=row.get("edition") or None,
                            description=row.get("description") or None,
                            people=row.get("people") or None,
                            places=row.get("places") or None,
                            literary_movement=row.get("literary_movement") or None,
                            source_id=src_id_val,
                            primary_sources=row.get("primary_sources") or None,
                            secondary_sources=row.get("secondary_sources") or None,
                            source_url=row.get("source_url") or None,
                            license=row.get("license") or "own_words",
                            confidence=row.get("confidence") or "needs_check",
                            verified_by=row.get("verified_by") or None,
                            verified_on=row.get("verified_on") or None,
                            db_path=db_path,
                            raise_on_duplicate=False,
                        )
                        stats["imported"] += 1
                    except Exception as exc:
                        stats["rejected"] += 1
                        stats["errors"].append(
                            f"Row {row_idx} ('{title}'): Failed to insert: {exc}"
                        )

    return stats


def import_literature_json(
    json_path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Import and validate literary records from a JSON file.

    Creates an ACID-compliant backup before writing changes (if not dry_run).
    Validates required fields and reports rejected rows and duplicates.

    Returns:
        Dictionary with statistics:
        'total', 'imported', 'updated', 'skipped', 'rejected', 'errors', 'dry_run'.
    """
    target = Path(json_path)
    if not target.is_file():
        raise FileNotFoundError(f"Literature JSON file not found: {target}")

    init_db(db_path)

    backup_file: Path | None = None
    if not dry_run and str(db_path) != ":memory:" and Path(db_path).is_file():
        backup_file = backup_db(db_path)

    with open(target, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("JSON file must contain a list of literary records.")

    stats: dict[str, Any] = {
        "total": 0,
        "imported": 0,
        "updated": 0,
        "skipped": 0,
        "rejected": 0,
        "errors": [],
        "dry_run": dry_run,
        "backup_path": str(backup_file) if backup_file else None,
    }

    for idx, item in enumerate(data, start=1):
        stats["total"] += 1
        if not isinstance(item, dict):
            stats["rejected"] += 1
            stats["errors"].append(f"Item #{idx}: Expected dict, got {type(item)}.")
            continue

        title = str(item.get("title") or "").strip()
        lit_type = str(item.get("literary_type") or "").strip().lower()

        year_val = item.get("year")
        if year_val is not None:
            try:
                year_val = int(year_val)
            except (ValueError, TypeError):
                stats["rejected"] += 1
                stats["errors"].append(
                    f"Item #{idx} ('{title}'): Invalid year '{year_val}'."
                )
                continue

        year_end_val = item.get("year_end")
        if year_end_val is not None:
            try:
                year_end_val = int(year_end_val)
            except (ValueError, TypeError):
                stats["rejected"] += 1
                stats["errors"].append(
                    f"Item #{idx} ('{title}'): Invalid year_end '{year_end_val}'."
                )
                continue

        src_id_val = item.get("source_id")
        if src_id_val is not None:
            try:
                src_id_val = int(src_id_val)
            except (ValueError, TypeError):
                stats["rejected"] += 1
                stats["errors"].append(
                    f"Item #{idx} ('{title}'): Invalid source_id '{src_id_val}'."
                )
                continue

        payload = {
            "title": title,
            "literary_type": lit_type,
            "year": year_val,
            "year_end": year_end_val,
            "date_precision": item.get("date_precision"),
            "confidence": item.get("confidence") or "needs_check",
            "verified_on": item.get("verified_on"),
            "description": item.get("description"),
        }

        validation_errors = validate_literary_record(payload)
        if validation_errors:
            stats["rejected"] += 1
            stats["errors"].append(
                f"Item #{idx} ('{title}'): {'; '.join(validation_errors)}"
            )
            continue

        author = item.get("author")

        # Check existing
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            if author is not None:
                cursor.execute(
                    """
                    SELECT id FROM literature_items
                    WHERE title = ? AND literary_type = ? AND author = ?
                    """,
                    (title, lit_type, author),
                )
            else:
                cursor.execute(
                    """
                    SELECT id FROM literature_items
                    WHERE title = ? AND literary_type = ? AND author IS NULL
                    """,
                    (title, lit_type),
                )
            existing = cursor.fetchone()

        if existing is not None:
            if dry_run:
                stats["updated"] += 1
            else:
                try:
                    add_literary_record(
                        title=title,
                        literary_type=lit_type,
                        title_en=item.get("title_en"),
                        roman_title=item.get("roman_title"),
                        author=author,
                        translator=item.get("translator"),
                        editor=item.get("editor"),
                        contributor=item.get("contributor"),
                        original_language=item.get("original_language") or "brx",
                        translation_languages=item.get("translation_languages"),
                        year=year_val,
                        year_end=year_end_val,
                        date_precision=item.get("date_precision"),
                        book_title=item.get("book_title"),
                        publisher=item.get("publisher"),
                        edition=item.get("edition"),
                        description=item.get("description"),
                        people=item.get("people"),
                        places=item.get("places"),
                        literary_movement=item.get("literary_movement"),
                        source_id=src_id_val,
                        primary_sources=item.get("primary_sources"),
                        secondary_sources=item.get("secondary_sources"),
                        source_url=item.get("source_url"),
                        license=item.get("license") or "own_words",
                        confidence=item.get("confidence") or "needs_check",
                        verified_by=item.get("verified_by"),
                        verified_on=item.get("verified_on"),
                        db_path=db_path,
                        raise_on_duplicate=False,
                    )
                    stats["updated"] += 1
                except Exception as exc:
                    stats["rejected"] += 1
                    stats["errors"].append(
                        f"Item #{idx} ('{title}'): Failed to update: {exc}"
                    )
        else:
            if dry_run:
                stats["imported"] += 1
            else:
                try:
                    add_literary_record(
                        title=title,
                        literary_type=lit_type,
                        title_en=item.get("title_en"),
                        roman_title=item.get("roman_title"),
                        author=author,
                        translator=item.get("translator"),
                        editor=item.get("editor"),
                        contributor=item.get("contributor"),
                        original_language=item.get("original_language") or "brx",
                        translation_languages=item.get("translation_languages"),
                        year=year_val,
                        year_end=year_end_val,
                        date_precision=item.get("date_precision"),
                        book_title=item.get("book_title"),
                        publisher=item.get("publisher"),
                        edition=item.get("edition"),
                        description=item.get("description"),
                        people=item.get("people"),
                        places=item.get("places"),
                        literary_movement=item.get("literary_movement"),
                        source_id=src_id_val,
                        primary_sources=item.get("primary_sources"),
                        secondary_sources=item.get("secondary_sources"),
                        source_url=item.get("source_url"),
                        license=item.get("license") or "own_words",
                        confidence=item.get("confidence") or "needs_check",
                        verified_by=item.get("verified_by"),
                        verified_on=item.get("verified_on"),
                        db_path=db_path,
                        raise_on_duplicate=False,
                    )
                    stats["imported"] += 1
                except Exception as exc:
                    stats["rejected"] += 1
                    stats["errors"].append(
                        f"Item #{idx} ('{title}'): Failed to insert: {exc}"
                    )

    return stats


def format_literature_item(item: dict[str, Any], verbose: bool = False) -> str:
    """Format single literary record into human-readable text."""
    title = item.get("title") or "Untitled"
    title_en = item.get("title_en")
    title_str = f"{title} ({title_en})" if title_en else title
    lit_type = item.get("literary_type") or "work"
    author = item.get("author") or "Unknown Author"

    year = item.get("year")
    year_end = item.get("year_end")
    prec = item.get("date_precision") or "exact"
    if year is None:
        year_str = "Unknown Year"
    elif year_end is not None and year_end != year:
        year_str = f"{year} - {year_end}"
    else:
        year_str = str(year)
    if prec in ("approximate", "approx", "circa", "c."):
        year_str = f"c. {year_str}"

    confidence = item.get("confidence") or "needs_check"
    conf_marker = f" [{confidence}]" if confidence != "verified" else ""

    lines = [f"• {title_str} - {author} ({year_str}) [{lit_type}]{conf_marker}"]

    desc = (item.get("description") or "").strip()
    if desc:
        first_line = desc.split("\n\n")[0].replace("\n", " ").strip()
        lines.append(f"    Summary: {first_line}")

    if verbose:
        book = item.get("book_title")
        pub = item.get("publisher")
        if book or pub:
            lines.append(f"    Publication: {book or ''} {pub or ''}".strip())
        trans = item.get("translator")
        if trans:
            lines.append(f"    Translator: {trans}")
        movement = item.get("literary_movement")
        if movement:
            lines.append(f"    Movement: {movement}")
        src = (
            item.get("source_title")
            or item.get("primary_sources")
            or item.get("source_url")
        )
        if src:
            lines.append(f"    Source/Citation: {src}")
        if item.get("missing_reason"):
            lines.append(f"    Citation Issue: {item.get('missing_reason')}")

    return "\n".join(lines)


def print_literature(items: list[dict[str, Any]], verbose: bool = False) -> None:
    """Display literature records in human-readable format."""
    if not items:
        print("No literary records found.")
        return

    print(f"Bodo Literature & Works ({len(items)} record(s)):\n")
    for item in items:
        print(format_literature_item(item, verbose=verbose))
        print()


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for querying, exporting, and managing literature records."""
    parser = argparse.ArgumentParser(
        description="Query, filter, export, and import Bodo literature records."
    )
    parser.add_argument(
        "--db",
        type=str,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--search",
        type=str,
        default=None,
        help="Search literature by title, author, description, or keyword",
    )
    parser.add_argument(
        "--author",
        type=str,
        default=None,
        help="Filter literature by author name",
    )
    parser.add_argument(
        "--type",
        type=str,
        default=None,
        choices=sorted(VALID_LITERARY_TYPES),
        help="Filter by literary type",
    )
    parser.add_argument(
        "--from-year",
        type=int,
        default=None,
        help="Earliest publication year to include",
    )
    parser.add_argument(
        "--to-year",
        type=int,
        default=None,
        help="Latest publication year to include",
    )
    parser.add_argument(
        "--confidence",
        type=str,
        default=None,
        choices=sorted(VALID_CONFIDENCE_LEVELS),
        help="Filter by confidence status",
    )
    parser.add_argument(
        "--include-unknown",
        action="store_true",
        help="Include works with unknown publication years",
    )
    parser.add_argument(
        "--missing-citations",
        action="store_true",
        help="List works lacking adequate bibliographic citations",
    )
    parser.add_argument(
        "--unverified",
        action="store_true",
        help="List only unverified or needs_check works",
    )
    parser.add_argument(
        "--export-csv",
        type=str,
        default=None,
        help="Export matching records to specified CSV path",
    )
    parser.add_argument(
        "--export-json",
        type=str,
        default=None,
        help="Export matching records to specified JSON path",
    )
    parser.add_argument(
        "--import-csv",
        type=str,
        default=None,
        help="Import literary records from CSV file",
    )
    parser.add_argument(
        "--import-json",
        type=str,
        default=None,
        help="Import literary records from JSON file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate import without making changes to database",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Display extended bibliographic and source details",
    )

    args = parser.parse_args(argv)

    if args.import_csv:
        stats = import_literature_csv(
            csv_path=args.import_csv,
            db_path=args.db,
            dry_run=args.dry_run,
        )
        mode = "Dry Run Import" if args.dry_run else "Import"
        print(f"=== {mode} Statistics ===")
        print(f"Total Rows:     {stats['total']}")
        print(f"Imported (New): {stats['imported']}")
        print(f"Updated:        {stats['updated']}")
        print(f"Rejected:       {stats['rejected']}")
        if stats.get("backup_path"):
            print(f"Backup created: {stats['backup_path']}")
        if stats["errors"]:
            print(f"\nErrors ({len(stats['errors'])}):")
            for err in stats["errors"][:10]:
                print(f"  - {err}")
            if len(stats["errors"]) > 10:
                print(f"  ... and {len(stats['errors']) - 10} more.")
        return 0

    if args.import_json:
        stats = import_literature_json(
            json_path=args.import_json,
            db_path=args.db,
            dry_run=args.dry_run,
        )
        mode = "Dry Run Import" if args.dry_run else "Import"
        print(f"=== {mode} Statistics ===")
        print(f"Total Items:    {stats['total']}")
        print(f"Imported (New): {stats['imported']}")
        print(f"Updated:        {stats['updated']}")
        print(f"Rejected:       {stats['rejected']}")
        if stats.get("backup_path"):
            print(f"Backup created: {stats['backup_path']}")
        if stats["errors"]:
            print(f"\nErrors ({len(stats['errors'])}):")
            for err in stats["errors"][:10]:
                print(f"  - {err}")
            if len(stats["errors"]) > 10:
                print(f"  ... and {len(stats['errors']) - 10} more.")
        return 0

    if args.export_csv:
        count = export_literature_csv(
            csv_path=args.export_csv,
            db_path=args.db,
            literary_type=args.type,
        )
        print(f"Successfully exported {count} literary records to {args.export_csv}")
        return 0

    if args.export_json:
        count = export_literature_json(
            json_path=args.export_json,
            db_path=args.db,
            literary_type=args.type,
        )
        print(f"Successfully exported {count} literary records to {args.export_json}")
        return 0

    if args.missing_citations:
        flagged = get_literature_missing_citations(
            db_path=args.db, literary_type=args.type
        )
        if not flagged:
            print("No literary records with missing citations found.")
            return 0
        print(
            f"Literature with Missing or Insufficient Citations "
            f"({len(flagged)} found):\n"
        )
        for idx, item in enumerate(flagged, start=1):
            title = item.get("title") or "Untitled"
            author = item.get("author") or "Unknown"
            year = item.get("year") or "Unknown"
            reason = item.get("missing_reason") or "Missing citation"
            print(f"[{idx}] {year}: {title} by {author}")
            print(f"    Issue: {reason}")
            print()
        return 0

    if args.unverified:
        items = get_unverified_literature(db_path=args.db, literary_type=args.type)
        print_literature(items, verbose=args.verbose)
        return 0

    if args.search:
        items = search_literature(
            args.search,
            db_path=args.db,
            literary_type=args.type,
            author=args.author,
        )
        print_literature(items, verbose=args.verbose)
        return 0

    items = filter_literature(
        db_path=args.db,
        literary_type=args.type,
        author=args.author,
        from_year=args.from_year,
        to_year=args.to_year,
        confidence=args.confidence,
        include_unknown_dates=args.include_unknown,
    )
    print_literature(items, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
