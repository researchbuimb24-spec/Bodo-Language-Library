"""Chronological timeline module for historical and cultural milestones.

💡 FILE INSIGHT & PURPOSE:
Manages historical chronology, socio-political movements, accords, and literary foundations.
Provides filtering by year range, search by entities/places/organizations, citation audits
(`get_events_missing_citations()`), and the CLI utility `python -m bhasha_lib.timeline`.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path
from typing import Any

from bhasha_lib.audit import check_needs_citation_detail, is_vague_source
from bhasha_lib.db import (
    DEFAULT_DB_PATH,
    VALID_CONFIDENCE_LEVELS,
    VALID_DATE_PRECISIONS,
    add_culture_item,
    get_connection,
    init_db,
)

__all__ = [
    "VALID_CONFIDENCE_LEVELS",
    "VALID_DATE_PRECISIONS",
    "add_event",
    "add_historical_event",
    "filter_events",
    "format_year_range",
    "get_event",
    "get_events_missing_citations",
    "get_historical_event",
    "get_timeline",
    "get_unverified_events",
    "main",
    "print_timeline",
    "search_events",
    "validate_historical_event",
]

EVENT_FIELDS_SQL = """
    ci.id, ci.category, ci.title, ci.description, ci.region,
    ci.related_words, ci.source_id, ci.media_path, ci.year_start,
    ci.year_end, ci.confidence, ci.verified_on, ci.date_precision,
    ci.people, ci.places, ci.organizations, ci.books,
    ci.primary_sources, ci.secondary_sources, ci.source_url, ci.license,
    ci.created_at, ci.updated_at,
    s.title AS source_title, s.license AS source_license,
    s.url AS source_ref_url, s.author AS source_author
"""


def _escape_like(text: str, escape_char: str = "\\") -> str:
    """Escape special pattern characters (%, _, and escape_char) for SQLite LIKE."""
    escaped = text.replace(escape_char, escape_char + escape_char)
    escaped = escaped.replace("%", escape_char + "%")
    return escaped.replace("_", escape_char + "_")


def _clean_str(val: Any) -> str | None:
    """Normalize string and strip whitespace."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _format_list_or_str(val: Any) -> str | None:
    """Format string or list of strings into a normalized comma-separated string."""
    if val is None:
        return None
    if isinstance(val, (list, tuple, set)):
        items = [_clean_str(item) for item in val if _clean_str(item)]
        return ", ".join(items) if items else None
    return _clean_str(val)


def validate_historical_event(event_data: dict[str, Any]) -> list[str]:
    """Validate historical event dictionary against schema and historical rules.

    Checks:
    - Required title and description
    - Integer year_start and year_end within valid range
    - End year not earlier than start year
    - Precision within VALID_DATE_PRECISIONS
    - Precision 'exact' or 'range' requires year_start
    - Confidence level within VALID_CONFIDENCE_LEVELS
    - 'verified' events require non-future verified_on date

    Returns:
        List of validation failure reasons. Empty if valid.
    """
    errors: list[str] = []

    title = event_data.get("title")
    if not title or not str(title).strip():
        errors.append("Missing required 'title' field.")

    description = event_data.get("description")
    if not description or not str(description).strip():
        errors.append("Missing required 'description' field.")

    year_start = event_data.get("year_start")
    year_end = event_data.get("year_end")

    ys_int: int | None = None
    if year_start is not None:
        try:
            ys_int = int(year_start)
            if ys_int < -5000 or ys_int > 2100:
                errors.append(f"Start year {ys_int} is out of realistic range.")
        except (ValueError, TypeError):
            errors.append(
                f"Invalid 'year_start' value: {year_start} (must be an integer)."
            )

    ye_int: int | None = None
    if year_end is not None:
        try:
            ye_int = int(year_end)
            if ye_int < -5000 or ye_int > 2100:
                errors.append(f"End year {ye_int} is out of realistic range.")
        except (ValueError, TypeError):
            errors.append(
                f"Invalid 'year_end' value: {year_end} (must be an integer)."
            )

    if ys_int is not None and ye_int is not None and ye_int < ys_int:
        errors.append(
            f"Invalid date range: End year ({ye_int}) cannot be earlier than "
            f"start year ({ys_int})."
        )

    date_precision = event_data.get("date_precision")
    if date_precision is not None:
        clean_prec = str(date_precision).strip().lower()
        if clean_prec not in VALID_DATE_PRECISIONS:
            errors.append(
                f"Invalid 'date_precision': '{date_precision}'. Must be one of "
                f"{sorted(VALID_DATE_PRECISIONS)}."
            )
        if clean_prec in ("exact", "range") and ys_int is None:
            errors.append(
                f"Date precision '{clean_prec}' requires a non-null 'year_start'."
            )

    confidence = event_data.get("confidence")
    if confidence is not None:
        clean_conf = str(confidence).strip().lower()
        if clean_conf not in VALID_CONFIDENCE_LEVELS:
            errors.append(
                f"Invalid 'confidence': '{confidence}'. Must be one of "
                f"{sorted(VALID_CONFIDENCE_LEVELS)}."
            )
        if clean_conf == "verified":
            verified_on = event_data.get("verified_on")
            if not verified_on or not str(verified_on).strip():
                errors.append(
                    "'confidence: verified' requires 'verified_on' date."
                )
            else:
                try:
                    v_date = datetime.date.fromisoformat(
                        str(verified_on).strip()
                    )
                    if v_date > datetime.date.today():
                        errors.append(
                            f"'verified_on' date cannot be in future: {v_date}."
                        )
                except ValueError:
                    errors.append(
                        f"Invalid 'verified_on' date format: {verified_on} "
                        "(must be YYYY-MM-DD)."
                    )

    return errors


def add_historical_event(
    title: str,
    description: str,
    year_start: int | None = None,
    year_end: int | None = None,
    date_precision: str | None = None,
    category: str = "history",
    people: list[str] | str | None = None,
    places: list[str] | str | None = None,
    organizations: list[str] | str | None = None,
    books: list[str] | str | None = None,
    primary_sources: list[str] | str | None = None,
    secondary_sources: list[str] | str | None = None,
    source_id: int | None = None,
    source_title: str | None = None,
    source_url: str | None = None,
    license: str | None = None,
    confidence: str = "needs_check",
    verified_on: str | None = None,
    region: str | None = None,
    related_words: list[str] | str | None = None,
    media_path: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
    raise_on_duplicate: bool = False,
) -> int:
    """Insert or update a structured historical event in the database.

    Enforces foreign keys, validates required metadata, dates, and verification.

    Raises:
        ValueError: If validation fails or event duplicate is disallowed.
        sqlite3.IntegrityError: If foreign-key constraint is violated.
    """
    init_db(db_path)

    clean_title = _clean_str(title)
    clean_desc = _clean_str(description)
    clean_cat = _clean_str(category) or "history"
    clean_conf = _clean_str(confidence) or "needs_check"

    clean_prec = _clean_str(date_precision)
    if clean_prec is None:
        if year_start is None:
            clean_prec = "unknown"
        elif year_end is not None and year_end != year_start:
            clean_prec = "range"
        else:
            clean_prec = "exact"

    payload = {
        "title": clean_title,
        "description": clean_desc,
        "year_start": year_start,
        "year_end": year_end,
        "date_precision": clean_prec,
        "category": clean_cat,
        "confidence": clean_conf,
        "verified_on": verified_on,
    }
    validation_errors = validate_historical_event(payload)
    if validation_errors:
        raise ValueError(
            f"Historical event validation failed: {'; '.join(validation_errors)}"
        )

    clean_people = _format_list_or_str(people)
    clean_places = _format_list_or_str(places)
    clean_orgs = _format_list_or_str(organizations)
    clean_books = _format_list_or_str(books)
    clean_primary = _format_list_or_str(primary_sources)
    clean_secondary = _format_list_or_str(secondary_sources)
    clean_url = _clean_str(source_url)
    clean_license = _clean_str(license)
    clean_region = _clean_str(region) or clean_places
    clean_related = _format_list_or_str(related_words)
    clean_media = _clean_str(media_path)
    clean_vo = _clean_str(verified_on)

    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        resolved_source_id = source_id
        if resolved_source_id is not None:
            cursor.execute(
                "SELECT id FROM sources WHERE id = ?", (resolved_source_id,)
            )
            if cursor.fetchone() is None:
                import sqlite3

                raise sqlite3.IntegrityError(
                    f"FOREIGN KEY constraint failed: source_id {resolved_source_id} "
                    "not found in sources."
                )
        elif source_title and source_title.strip():
            st_clean = source_title.strip()
            cursor.execute(
                "SELECT id FROM sources WHERE title = ?", (st_clean,)
            )
            s_row = cursor.fetchone()
            if s_row is not None:
                resolved_source_id = int(s_row[0])
            else:
                cursor.execute(
                    """
                    INSERT INTO sources (title, type, license, url)
                    VALUES (?, 'history_source', ?, ?)
                    """,
                    (st_clean, clean_license or "own_words", clean_url),
                )
                resolved_source_id = int(cursor.lastrowid)

        cursor.execute(
            "SELECT id FROM culture_items WHERE title = ? AND category = ?",
            (clean_title, clean_cat),
        )
        existing = cursor.fetchone()

        if existing is not None:
            if raise_on_duplicate:
                raise ValueError(
                    f"Historical event '{clean_title}' in category '{clean_cat}' "
                    "already exists in database."
                )
            existing_id = int(existing["id"])
            cursor.execute(
                """
                UPDATE culture_items SET
                    description = COALESCE(?, description),
                    year_start = COALESCE(?, year_start),
                    year_end = COALESCE(?, year_end),
                    date_precision = COALESCE(?, date_precision),
                    confidence = COALESCE(?, confidence),
                    verified_on = COALESCE(?, verified_on),
                    source_id = COALESCE(?, source_id),
                    region = COALESCE(?, region),
                    people = COALESCE(?, people),
                    places = COALESCE(?, places),
                    organizations = COALESCE(?, organizations),
                    books = COALESCE(?, books),
                    primary_sources = COALESCE(?, primary_sources),
                    secondary_sources = COALESCE(?, secondary_sources),
                    source_url = COALESCE(?, source_url),
                    license = COALESCE(?, license),
                    media_path = COALESCE(?, media_path),
                    related_words = COALESCE(?, related_words),
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    clean_desc,
                    year_start,
                    year_end,
                    clean_prec,
                    clean_conf,
                    clean_vo,
                    resolved_source_id,
                    clean_region,
                    clean_people,
                    clean_places,
                    clean_orgs,
                    clean_books,
                    clean_primary,
                    clean_secondary,
                    clean_url,
                    clean_license,
                    clean_media,
                    clean_related,
                    existing_id,
                ),
            )
            return existing_id

    return add_culture_item(
        category=clean_cat,
        title=clean_title,
        description=clean_desc,
        region=clean_region,
        related_words=clean_related,
        source_id=resolved_source_id,
        media_path=clean_media,
        year_start=year_start,
        year_end=year_end,
        confidence=clean_conf,
        verified_on=clean_vo,
        date_precision=clean_prec,
        people=clean_people,
        places=clean_places,
        organizations=clean_orgs,
        books=clean_books,
        primary_sources=clean_primary,
        secondary_sources=clean_secondary,
        source_url=clean_url,
        license=clean_license,
        db_path=db_path,
    )


add_event = add_historical_event


def get_historical_event(
    event_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any] | None:
    """Retrieve a single historical event by its unique ID.

    Returns:
        Dictionary containing all event fields and linked source metadata,
        or None if not found.
    """
    init_db(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        query = f"""
            SELECT
                {EVENT_FIELDS_SQL}
            FROM culture_items ci
            LEFT JOIN sources s ON ci.source_id = s.id
            WHERE ci.id = ?
        """
        cursor.execute(query, (int(event_id),))
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)


get_event = get_historical_event


def filter_events(
    db_path: str | Path = DEFAULT_DB_PATH,
    category: str | None = None,
    from_year: int | None = None,
    to_year: int | None = None,
    confidence: str | None = None,
    date_precision: str | None = None,
    include_unknown_dates: bool = False,
    sort_order: str = "asc",
) -> list[dict[str, Any]]:
    """Filter historical and cultural events by category, year range, and confidence.

    Args:
        db_path: Path to SQLite database.
        category: Filter by specific category.
        from_year: Earliest year_start to include.
        to_year: Latest year_start to include.
        confidence: Filter by confidence status.
        date_precision: Filter by precision ('exact', 'approximate', 'range').
        include_unknown_dates: If False (default), items with null year are excluded.
        sort_order: 'asc' (default) or 'desc'.

    Returns:
        List of event dictionaries matching the criteria, ordered chronologically.
    """
    init_db(db_path)
    conditions: list[str] = []
    params: list[Any] = []

    if not include_unknown_dates:
        conditions.append("ci.year_start IS NOT NULL")

    if category:
        conditions.append("ci.category = ?")
        params.append(category.strip())

    if from_year is not None:
        conditions.append("ci.year_start >= ?")
        params.append(int(from_year))

    if to_year is not None:
        conditions.append("ci.year_start <= ?")
        params.append(int(to_year))

    if confidence:
        conditions.append("ci.confidence = ?")
        params.append(confidence.strip())

    if date_precision:
        conditions.append("ci.date_precision = ?")
        params.append(date_precision.strip())

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    order = "DESC" if str(sort_order).lower() == "desc" else "ASC"

    query = f"""
        SELECT
            {EVENT_FIELDS_SQL}
        FROM culture_items ci
        LEFT JOIN sources s ON ci.source_id = s.id
        {where_clause}
        ORDER BY
            CASE WHEN ci.year_start IS NULL THEN 1 ELSE 0 END,
            ci.year_start {order},
            COALESCE(ci.year_end, ci.year_start) {order},
            ci.title ASC
    """

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_timeline(
    db_path: str | Path = DEFAULT_DB_PATH,
    category: str | None = None,
    from_year: int | None = None,
    to_year: int | None = None,
    confidence: str | None = None,
    include_unknown_dates: bool = False,
    date_precision: str | None = None,
    sort_order: str = "asc",
) -> list[dict[str, Any]]:
    """Retrieve chronological timeline events from culture_items.

    Preserves 100% backward compatibility with existing callers.
    Filters items where year_start is specified by default, ordering by
    year_start ASC, year_end ASC, title ASC.
    """
    return filter_events(
        db_path=db_path,
        category=category,
        from_year=from_year,
        to_year=to_year,
        confidence=confidence,
        date_precision=date_precision,
        include_unknown_dates=include_unknown_dates,
        sort_order=sort_order,
    )


def search_events(
    query: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Search historical events by title, description, entities, or keywords.

    Uses safe wildcard pattern escaping and returns chronologically ordered events.
    """
    clean_query = str(query or "").strip()
    if not clean_query:
        return []

    init_db(db_path)
    pattern = f"%{_escape_like(clean_query)}%"
    conditions = [
        """(
            ci.title LIKE ? ESCAPE '\\'
            OR ci.description LIKE ? ESCAPE '\\'
            OR ci.people LIKE ? ESCAPE '\\'
            OR ci.places LIKE ? ESCAPE '\\'
            OR ci.region LIKE ? ESCAPE '\\'
            OR ci.organizations LIKE ? ESCAPE '\\'
            OR ci.books LIKE ? ESCAPE '\\'
            OR ci.primary_sources LIKE ? ESCAPE '\\'
            OR ci.secondary_sources LIKE ? ESCAPE '\\'
            OR ci.related_words LIKE ? ESCAPE '\\'
            OR s.title LIKE ? ESCAPE '\\'
        )"""
    ]
    params: list[Any] = [pattern] * 11

    if category:
        conditions.append("ci.category = ?")
        params.append(category.strip())

    where_clause = f"WHERE {' AND '.join(conditions)}"
    sql = f"""
        SELECT
            {EVENT_FIELDS_SQL}
        FROM culture_items ci
        LEFT JOIN sources s ON ci.source_id = s.id
        {where_clause}
        ORDER BY
            CASE WHEN ci.year_start IS NULL THEN 1 ELSE 0 END,
            ci.year_start ASC,
            COALESCE(ci.year_end, ci.year_start) ASC,
            ci.title ASC
    """

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def get_events_missing_citations(
    db_path: str | Path = DEFAULT_DB_PATH,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve historical and cultural events that lack sufficient citations.

    An event is flagged if:
    - It has no source_id and no primary or secondary sources specified.
    - Its linked source is missing a title or has a title shorter than 15 characters.
    - Its source is only a vague site name (e.g., 'Wikipedia', 'Google').
    - Its source lacks specific publication or page details.

    Returns:
        List of event dictionaries with an attached 'missing_reason' summary.
    """
    init_db(db_path)
    conditions: list[str] = []
    params: list[Any] = []
    if category:
        conditions.append("ci.category = ?")
        params.append(category.strip())

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT
            {EVENT_FIELDS_SQL}
        FROM culture_items ci
        LEFT JOIN sources s ON ci.source_id = s.id
        {where_clause}
        ORDER BY ci.id ASC
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
            missing_reasons.append(
                "Missing citation: No source_id or citations linked"
            )
        elif source_id is not None and not source_title:
            missing_reasons.append(
                "Missing citation: Linked source has empty title"
            )
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
                    "lacks specific page or second source"
                )

        if missing_reasons:
            event_copy = dict(r)
            event_copy["missing_reasons"] = missing_reasons
            event_copy["missing_reason"] = "; ".join(missing_reasons)
            flagged.append(event_copy)

    return flagged


def get_unverified_events(
    db_path: str | Path = DEFAULT_DB_PATH,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """List historical and cultural records that have not reached 'verified' status.

    Includes records with confidence 'unverified', 'needs_check', or 'disputed'.
    Ordered chronologically.
    """
    init_db(db_path)
    conditions = ["(ci.confidence != 'verified' OR ci.confidence IS NULL)"]
    params: list[Any] = []
    if category:
        conditions.append("ci.category = ?")
        params.append(category.strip())

    where_clause = f"WHERE {' AND '.join(conditions)}"
    query = f"""
        SELECT
            {EVENT_FIELDS_SQL}
        FROM culture_items ci
        LEFT JOIN sources s ON ci.source_id = s.id
        {where_clause}
        ORDER BY
            CASE WHEN ci.year_start IS NULL THEN 1 ELSE 0 END,
            ci.year_start ASC,
            COALESCE(ci.year_end, ci.year_start) ASC,
            ci.title ASC
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def format_year_range(
    year_start: int | None,
    year_end: int | None = None,
    precision: str | None = None,
) -> str:
    """Format single year or year interval string with precision awareness."""
    if year_start is None:
        return "Unknown"

    if year_end is not None and year_end != year_start:
        base = f"{year_start} - {year_end}"
    else:
        base = str(year_start)

    clean_prec = str(precision).strip().lower() if precision else ""
    if clean_prec in ("approximate", "approx", "circa", "c."):
        return f"c. {base}"
    return base


def print_timeline(
    events: list[dict[str, Any]],
    verbose: bool = False,
) -> None:
    """Display timeline items in human-readable chronological format."""
    if not events:
        print("No timeline events found.")
        return

    print(f"Bodo Language & Cultural Timeline ({len(events)} event(s)):\n")
    for idx, event in enumerate(events, start=1):
        year_str = format_year_range(
            event.get("year_start"),
            event.get("year_end"),
            precision=event.get("date_precision"),
        )
        title = event.get("title") or "Untitled"
        cat = event.get("category") or "general"
        region = event.get("region") or event.get("places")
        region_str = f" ({region})" if region else ""
        confidence = event.get("confidence") or "verified"
        conf_marker = f" [{confidence}]" if confidence != "verified" else ""

        print(f"[{idx}] {year_str}: {title}{region_str} - {cat}{conf_marker}")
        desc = (event.get("description") or "").strip()
        if desc:
            first_para = desc.split("\n\n")[0].replace("\n", " ").strip()
            print(f"    {first_para}")

        if verbose:
            prec = event.get("date_precision") or "exact"
            if prec != "exact":
                print(f"    Date Precision: {prec}")
            people = event.get("people")
            if people:
                print(f"    People: {people}")
            orgs = event.get("organizations")
            if orgs:
                print(f"    Organizations: {orgs}")
            src = event.get("source_title") or event.get("primary_sources")
            if src:
                print(f"    Source: {src}")
            if event.get("missing_reason"):
                print(f"    Citation Issue: {event.get('missing_reason')}")

        print()


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for viewing the historical timeline and records."""
    parser = argparse.ArgumentParser(
        description="Display chronological timeline of language and culture."
    )
    parser.add_argument(
        "--db",
        type=str,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Filter events by category (e.g. history, festival)",
    )
    parser.add_argument(
        "--from-year",
        type=int,
        default=None,
        help="Earliest year_start to include",
    )
    parser.add_argument(
        "--to-year",
        type=int,
        default=None,
        help="Latest year_start to include",
    )
    parser.add_argument(
        "--confidence",
        type=str,
        default=None,
        help="Filter events by confidence status (e.g. verified, needs_check)",
    )
    parser.add_argument(
        "--include-unknown",
        action="store_true",
        help="Include events without exact or known years",
    )
    parser.add_argument(
        "--missing-citations",
        action="store_true",
        help="List events with missing or insufficient citations",
    )
    parser.add_argument(
        "--unverified",
        action="store_true",
        help="List only unverified or needs_check records",
    )
    parser.add_argument(
        "--search",
        type=str,
        default=None,
        help="Search events by query string",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Display extended metadata and source citations",
    )
    args = parser.parse_args(argv)

    if args.missing_citations:
        events = get_events_missing_citations(
            db_path=args.db, category=args.category
        )
        if not events:
            print("No events with missing citations found.")
            return 0
        print(
            f"Events with Missing or Insufficient Citations ({len(events)} found):\n"
        )
        for idx, event in enumerate(events, start=1):
            title = event.get("title") or "Untitled"
            cat = event.get("category") or "general"
            year = event.get("year_start") or "Unknown"
            reason = event.get("missing_reason") or "Missing citation"
            print(f"[{idx}] {year}: {title} ({cat})")
            print(f"    Issue: {reason}")
            print()
        return 0

    if args.unverified:
        events = get_unverified_events(db_path=args.db, category=args.category)
        print_timeline(events, verbose=args.verbose)
        return 0

    if args.search:
        events = search_events(
            args.search, db_path=args.db, category=args.category
        )
        print_timeline(events, verbose=args.verbose)
        return 0

    events = get_timeline(
        db_path=args.db,
        category=args.category,
        from_year=args.from_year,
        to_year=args.to_year,
        confidence=args.confidence,
        include_unknown_dates=args.include_unknown,
    )
    print_timeline(events, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
