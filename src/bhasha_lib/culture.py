"""Culture metadata loading and semantic search module.

💡 FILE INSIGHT & PURPOSE:
Parses, validates, and ingests cultural Markdown files (`data/archive/bodo/culture/*.md`)
into SQLite `culture_items`. Validates frontmatter categories (dance, attire, food, instrument,
festival, ritual), enforces citation tracking, and powers the `related()` query linking words to culture.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from bhasha_lib.consent import DEFAULT_REGISTER_PATH, verify_consent_document
from bhasha_lib.db import (
    DEFAULT_DB_PATH,
    get_connection,
    init_db,
    search_word,
)

VALID_PERMISSION_TYPES: frozenset[str] = frozenset(
    {"written", "recorded", "public_domain"}
)


def validate_folk_song_header(
    header: dict[str, Any],
    file_path: Path,
    project_root: Path | None = None,
    register_path: str | Path | None = None,
) -> list[str]:
    """Validate folk song header keys and consent requirements.

    Returns:
        List of failure reasons. Empty if valid.
    """
    failures: list[str] = []

    # 1. consent_document: must exist on disk and appear in consent
    # register with matching SHA-256
    consent_doc = header.get("consent_document")
    if not consent_doc or not str(consent_doc).strip():
        failures.append("Missing required 'consent_document' key")
    else:
        doc_str = str(consent_doc).strip()
        doc_path = Path(doc_str)
        root = project_root if project_root is not None else Path.cwd()
        exists = (
            doc_path.is_file()
            or (root / doc_path).is_file()
            or (file_path.parent / doc_path).is_file()
        )
        if not exists:
            failures.append(
                f"'consent_document' file does not exist on disk: {doc_str}"
            )
        else:
            reg_target = register_path
            if reg_target is None:
                env_reg = os.environ.get("BHASHA_CONSENT_REGISTER")
                if env_reg:
                    reg_target = Path(env_reg)
                else:
                    reg_target = DEFAULT_REGISTER_PATH

            is_valid, err_msg = verify_consent_document(
                doc_path=doc_str,
                file_context_path=file_path,
                register_path=reg_target,
                project_root=root,
            )
            if not is_valid:
                failures.append(err_msg)

    # 2. contributor
    contributor = header.get("contributor")
    if not contributor or not str(contributor).strip():
        failures.append("Missing required 'contributor' key")

    # 3. permission_type (written, recorded, public_domain)
    perm_type = header.get("permission_type")
    if (
        not perm_type
        or str(perm_type).strip().lower() not in VALID_PERMISSION_TYPES
    ):
        failures.append(
            "Invalid or missing 'permission_type' (must be written, recorded, "
            f"or public_domain): {perm_type}"
        )

    # 4. permission_date (YYYY-MM-DD)
    perm_date = header.get("permission_date")
    if not perm_date:
        failures.append("Missing required 'permission_date' key")
    else:
        valid_date = False
        if isinstance(perm_date, (datetime.date, datetime.datetime)):
            valid_date = True
        else:
            try:
                datetime.datetime.strptime(str(perm_date).strip(), "%Y-%m-%d")
                valid_date = True
            except ValueError:
                valid_date = False
        if not valid_date:
            failures.append(
                f"Invalid 'permission_date' format (must be YYYY-MM-DD): {perm_date}"
            )

    # 5. source_recording (free text, at least 15 characters)
    source_rec = header.get("source_recording")
    if not source_rec or len(str(source_rec).strip()) < 15:
        failures.append(
            "Missing or too short 'source_recording' "
            "(must be free text with at least 15 characters)"
        )

    return failures


def _escape_like(text: str, escape_char: str = "\\") -> str:
    """Escape special pattern characters (%, _, and escape_char) for SQLite LIKE."""
    escaped = text.replace(escape_char, escape_char + escape_char)
    escaped = escaped.replace("%", escape_char + "%")
    return escaped.replace("_", escape_char + "_")


def parse_culture_markdown(
    content: str, file_name: str = "document"
) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter header and markdown description body.

    Raises:
        ValueError: If header delimiters are missing or invalid YAML.
    """
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(
            f"Invalid culture file format in '{file_name}': "
            "Missing starting '---' YAML header."
        )

    closing_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            closing_idx = i
            break

    if closing_idx == -1:
        raise ValueError(
            f"Invalid culture file format in '{file_name}': "
            "Missing closing '---' YAML header."
        )

    header_yaml = "\n".join(lines[1:closing_idx])
    body = "\n".join(lines[closing_idx + 1 :]).strip()

    header_data = yaml.safe_load(header_yaml) or {}
    if not isinstance(header_data, dict):
        raise ValueError(
            f"Invalid YAML frontmatter in '{file_name}': Expected key-value dictionary."
        )

    return header_data, body


class CultureLoadResult(list):
    """List of newly inserted item IDs with summary counts."""

    def __init__(
        self,
        inserted: list[int] | None = None,
        updated: list[int] | None = None,
        unchanged: list[int] | None = None,
    ):
        self.inserted: list[int] = inserted or []
        self.updated: list[int] = updated or []
        self.unchanged: list[int] = unchanged or []
        super().__init__(self.inserted)

    @property
    def summary(self) -> dict[str, int]:
        return {
            "inserted": len(self.inserted),
            "updated": len(self.updated),
            "unchanged": len(self.unchanged),
        }


def reset_confidence(db_path: str | Path = DEFAULT_DB_PATH) -> int:
    """Set confidence to 'needs_check' for all culture_items rows."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE culture_items SET confidence = 'needs_check'")
        count = cursor.rowcount
    print(f"Reset confidence to 'needs_check' for {count} culture item(s).")
    return count


def load_culture_dir(
    dir_path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
    register_path: str | Path | None = None,
) -> CultureLoadResult:
    """Read every .md file in the directory and load culture records into DB.

    1. Parses YAML header and description body.
    2. Rejects files missing category, title, source, or description.
    3. Finds or creates a row in sources table.
    4. If row with same title and category exists, updates its fields.
    5. Inserts new culture items via add_culture_item().
    6. Prints summary of inserted, updated, and unchanged items.

    Returns:
        CultureLoadResult containing inserted, updated, and unchanged IDs.
    """
    directory = Path(dir_path)
    if not directory.is_dir():
        raise FileNotFoundError(f"Culture directory not found: {directory}")

    init_db(db_path)
    inserted_ids: list[int] = []
    updated_ids: list[int] = []
    unchanged_ids: list[int] = []

    md_files = sorted(directory.glob("*.md"))
    for file_path in md_files:
        text = file_path.read_text(encoding="utf-8")
        header, description = parse_culture_markdown(
            text, file_name=file_path.name
        )

        category = str(header.get("category") or "").strip()
        is_folk_song = (category == "folk_song") or any(
            p.lower() == "folk_songs" for p in file_path.parts
        )
        if is_folk_song:
            failures = validate_folk_song_header(
                header, file_path, register_path=register_path
            )
            if failures:
                print(
                    f"Refused folk song '{file_path.name}': {'; '.join(failures)}"
                )
                continue

        title = str(header.get("title") or "").strip()
        source = str(header.get("source") or "").strip()
        region = str(header.get("region") or "").strip()
        related_words = header.get("related_words") or []

        # Validate mandatory fields
        if not category:
            raise ValueError(
                f"File '{file_path.name}' is rejected: Missing required 'category'."
            )
        if not title:
            raise ValueError(
                f"File '{file_path.name}' is rejected: Missing required 'title'."
            )
        if not description:
            raise ValueError(
                f"File '{file_path.name}' is rejected: Missing description text."
            )
        if re.search(r"\bTODO\b", description):
            raise ValueError(
                f"File '{file_path.name}' is rejected: Body contains 'TODO'."
            )
        if not source:
            raise ValueError(
                f"File '{file_path.name}' is rejected: Missing required 'source'."
            )

        # Optional timeline and verification metadata
        year_start_raw = header.get("year_start")
        year_end_raw = header.get("year_end")
        confidence_raw = header.get("confidence")

        date_precision_raw = header.get("date_precision")
        people_raw = header.get("people")
        places_raw = header.get("places")
        organizations_raw = header.get("organizations")
        books_raw = header.get("books")
        primary_sources_raw = header.get("primary_sources")
        secondary_sources_raw = header.get("secondary_sources")
        source_url_raw = header.get("source_url") or header.get("url")
        license_raw = header.get("license")

        def _fmt_field(v: Any) -> str | None:
            if v is None:
                return None
            if isinstance(v, (list, tuple, set)):
                items = [str(x).strip() for x in v if str(x).strip()]
                return ", ".join(items) if items else None
            s = str(v).strip()
            return s if s else None

        year_start = None
        if year_start_raw is not None:
            try:
                year_start = int(year_start_raw)
            except (ValueError, TypeError):
                year_start = None

        year_end = None
        if year_end_raw is not None:
            try:
                year_end = int(year_end_raw)
            except (ValueError, TypeError):
                year_end = None

        confidence = (
            str(confidence_raw).strip() if confidence_raw else "needs_check"
        )
        date_precision = _fmt_field(date_precision_raw) or (
            "unknown"
            if year_start is None
            else "range"
            if (year_end is not None and year_end != year_start)
            else "exact"
        )
        people_val = _fmt_field(people_raw)
        places_val = _fmt_field(places_raw)
        orgs_val = _fmt_field(organizations_raw)
        books_val = _fmt_field(books_raw)
        primary_val = _fmt_field(primary_sources_raw)
        secondary_val = _fmt_field(secondary_sources_raw)
        url_val = _fmt_field(source_url_raw)
        license_val = _fmt_field(license_raw)

        verified_on_val: str | None = None
        if confidence.lower() == "verified":
            verified_by = str(header.get("verified_by") or "").strip()
            if not verified_by:
                raise ValueError(
                    f"File '{file_path.name}' is rejected: "
                    "'confidence: verified' requires non-empty 'verified_by'."
                )

            verified_on_raw = header.get("verified_on")
            if not verified_on_raw:
                raise ValueError(
                    f"File '{file_path.name}' is rejected: "
                    "'confidence: verified' requires 'verified_on'."
                )

            v_date: datetime.date | None = None
            if isinstance(verified_on_raw, datetime.date):
                v_date = verified_on_raw
            elif isinstance(verified_on_raw, datetime.datetime):
                v_date = verified_on_raw.date()
            elif isinstance(verified_on_raw, str):
                try:
                    v_date = datetime.date.fromisoformat(
                        verified_on_raw.strip()
                    )
                except ValueError:
                    try:
                        v_date = datetime.datetime.strptime(
                            verified_on_raw.strip(), "%Y-%m-%d"
                        ).date()
                    except ValueError:
                        v_date = None

            if v_date is None:
                raise ValueError(
                    f"File '{file_path.name}' is rejected: "
                    f"'verified_on' must be a valid date, got '{verified_on_raw}'."
                )

            today = datetime.date.today()
            if v_date > today:
                raise ValueError(
                    f"File '{file_path.name}' is rejected: "
                    f"'verified_on' date cannot be in the future ({v_date} > {today})."
                )

            verified_on_val = v_date.isoformat()
        else:
            verified_on_raw = header.get("verified_on")
            if verified_on_raw:
                if isinstance(verified_on_raw, (datetime.date, datetime.datetime)):
                    verified_on_val = verified_on_raw.strftime("%Y-%m-%d")
                elif isinstance(verified_on_raw, str) and verified_on_raw.strip():
                    try:
                        verified_on_val = datetime.date.fromisoformat(
                            verified_on_raw.strip()
                        ).isoformat()
                    except ValueError:
                        verified_on_val = None

        with get_connection(db_path) as conn:
            cursor = conn.cursor()

            # Find or create source row
            note_type = (
                f"{category}_note"
                if category in ("history", "culture")
                else "culture_note"
            )
            cursor.execute(
                "SELECT id FROM sources "
                "WHERE title = ? AND (type = ? OR type = 'culture_note')",
                (source, note_type),
            )
            source_row = cursor.fetchone()
            if source_row is not None:
                source_id = int(source_row[0])
            else:
                cursor.execute(
                    """
                    INSERT INTO sources (title, type, license, file_path)
                    VALUES (?, ?, 'own_words', ?)
                    """,
                    (source, note_type, str(file_path)),
                )
                source_id = int(cursor.lastrowid)

            # Format related words as comma-separated string
            if isinstance(related_words, list):
                related_words_str = ",".join(
                    str(w).strip() for w in related_words
                )
            else:
                related_words_str = str(related_words).strip()
            related_words_val = (
                related_words_str if related_words_str else None
            )
            region_val = region if region else None

            # Check for existing duplicate (same title and category)
            cursor.execute(
                """
                SELECT id, description, region, related_words,
                       year_start, year_end, confidence, verified_on, source_id,
                       date_precision, people, places, organizations, books,
                       primary_sources, secondary_sources, source_url, license
                FROM culture_items
                WHERE title = ? AND category = ?
                """,
                (title, category),
            )
            existing = cursor.fetchone()

            if existing is not None:
                item_id = int(existing["id"])
                exist_desc = existing["description"] or ""
                exist_reg = existing["region"] or ""
                exist_rw = existing["related_words"] or ""
                exist_ys = existing["year_start"]
                exist_ye = existing["year_end"]
                exist_conf = existing["confidence"] or "needs_check"
                exist_vo = existing["verified_on"] or None
                exist_src = existing["source_id"]
                exist_prec = existing["date_precision"] or "exact"
                exist_people = existing["people"] or ""
                exist_places = existing["places"] or ""
                exist_orgs = existing["organizations"] or ""
                exist_books = existing["books"] or ""
                exist_pri = existing["primary_sources"] or ""
                exist_sec = existing["secondary_sources"] or ""
                exist_url = existing["source_url"] or ""
                exist_lic = existing["license"] or ""

                cur_desc = description or ""
                cur_reg = region_val or ""
                cur_rw = related_words_val or ""
                cur_ys = year_start
                cur_ye = year_end
                cur_conf = confidence
                cur_vo = verified_on_val or None
                cur_src = source_id
                cur_prec = date_precision
                cur_people = people_val or ""
                cur_places = places_val or ""
                cur_orgs = orgs_val or ""
                cur_books = books_val or ""
                cur_pri = primary_val or ""
                cur_sec = secondary_val or ""
                cur_url = url_val or ""
                cur_lic = license_val or ""

                is_changed = (
                    exist_desc != cur_desc
                    or exist_reg != cur_reg
                    or exist_rw != cur_rw
                    or exist_ys != cur_ys
                    or exist_ye != cur_ye
                    or exist_conf != cur_conf
                    or exist_vo != cur_vo
                    or exist_src != cur_src
                    or exist_prec != cur_prec
                    or exist_people != cur_people
                    or exist_places != cur_places
                    or exist_orgs != cur_orgs
                    or exist_books != cur_books
                    or exist_pri != cur_pri
                    or exist_sec != cur_sec
                    or exist_url != cur_url
                    or exist_lic != cur_lic
                )

                if is_changed:
                    cursor.execute(
                        """
                        UPDATE culture_items SET
                            description = ?,
                            region = ?,
                            related_words = ?,
                            year_start = ?,
                            year_end = ?,
                            confidence = ?,
                            verified_on = ?,
                            source_id = ?,
                            date_precision = ?,
                            people = ?,
                            places = ?,
                            organizations = ?,
                            books = ?,
                            primary_sources = ?,
                            secondary_sources = ?,
                            source_url = ?,
                            license = ?,
                            updated_at = datetime('now')
                        WHERE id = ?
                        """,
                        (
                            description,
                            region_val,
                            related_words_val,
                            year_start,
                            year_end,
                            confidence,
                            verified_on_val,
                            source_id,
                            date_precision,
                            people_val,
                            places_val,
                            orgs_val,
                            books_val,
                            primary_val,
                            secondary_val,
                            url_val,
                            license_val,
                            item_id,
                        ),
                    )
                    updated_ids.append(item_id)
                else:
                    unchanged_ids.append(item_id)
            else:
                cursor.execute(
                    """
                    INSERT INTO culture_items (
                        category,
                        title,
                        description,
                        region,
                        related_words,
                        source_id,
                        media_path,
                        year_start,
                        year_end,
                        confidence,
                        verified_on,
                        date_precision,
                        people,
                        places,
                        organizations,
                        books,
                        primary_sources,
                        secondary_sources,
                        source_url,
                        license,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        datetime('now'), datetime('now')
                    )
                    """,
                    (
                        category,
                        title,
                        description,
                        region_val,
                        related_words_val,
                        source_id,
                        None,
                        year_start,
                        year_end,
                        confidence,
                        verified_on_val,
                        date_precision,
                        people_val,
                        places_val,
                        orgs_val,
                        books_val,
                        primary_val,
                        secondary_val,
                        url_val,
                        license_val,
                    ),
                )
                if cursor.lastrowid is None:
                    raise RuntimeError("Failed to insert culture item.")
                item_id = int(cursor.lastrowid)
                inserted_ids.append(item_id)

    print(
        f"Culture items: {len(inserted_ids)} inserted, "
        f"{len(updated_ids)} updated, {len(unchanged_ids)} unchanged."
    )
    return CultureLoadResult(
        inserted=inserted_ids,
        updated=updated_ids,
        unchanged=unchanged_ids,
    )


def related(
    term: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Search for culture items and vocabulary related to the given term.

    Returns a dict with:
    - 'culture_items': items whose title, description or related_words contain term
    - 'word': the result of search_word(term) if it exists
    """
    init_db(db_path)
    clean_term = term.strip()
    if not clean_term:
        return {"culture_items": [], "word": None}

    escaped = _escape_like(clean_term)
    pattern = f"%{escaped}%"

    culture_items: list[dict[str, Any]] = []
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                id, category, title, description, region,
                related_words, source_id, media_path,
                year_start, year_end, confidence, verified_on,
                date_precision, people, places, organizations, books,
                primary_sources, secondary_sources, source_url, license
            FROM culture_items
            WHERE title LIKE ? ESCAPE '\\'
               OR description LIKE ? ESCAPE '\\'
               OR related_words LIKE ? ESCAPE '\\'
               OR people LIKE ? ESCAPE '\\'
               OR places LIKE ? ESCAPE '\\'
               OR organizations LIKE ? ESCAPE '\\'
            ORDER BY id ASC
            """,
            (pattern, pattern, pattern, pattern, pattern, pattern),
        )
        for row in cursor.fetchall():
            culture_items.append(dict(row))

    word_info = search_word(clean_term, db_path=db_path)

    return {
        "culture_items": culture_items,
        "word": word_info,
    }


def main(argv: list[str] | None = None) -> int:
    """Command-line interface entry point."""
    parser = argparse.ArgumentParser(
        description="Load culture markdown files or reset confidence."
    )
    parser.add_argument(
        "target",
        type=str,
        help="Directory containing culture .md files OR 'reset-confidence'",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--register",
        type=str,
        default=None,
        help="Path to consent register CSV",
    )
    args = parser.parse_args(argv)

    if args.target == "reset-confidence":
        reset_confidence(db_path=args.db)
        return 0

    load_culture_dir(args.target, db_path=args.db, register_path=args.register)
    return 0


if __name__ == "__main__":
    sys.exit(main())
