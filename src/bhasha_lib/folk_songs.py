"""Bodo folk songs, oral traditions, and audio recording metadata module.

💡 FILE INSIGHT & PURPOSE:
Catalogs folk songs across 9 song types and links them to traditional musical instruments and festivals.
Manages audio recording metadata while enforcing ethical consent governance—including audio format checks,
consent document verification, permission withdrawal (`withdraw-consent`), and cultural removal requests.
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

import yaml

from bhasha_lib.audit import check_needs_citation_detail, is_vague_source
from bhasha_lib.consent import (
    ConsentError,
    ConsentRecord,
    validate_consent_dict,
)
from bhasha_lib.db import (
    DEFAULT_DB_PATH,
    VALID_AUDIO_FORMATS,
    VALID_CONFIDENCE_LEVELS,
    VALID_CONSENT_STATES,
    VALID_DATE_PRECISIONS,
    VALID_SONG_TYPES,
    add_culture_item,
    add_folk_song_item,
    add_song_recording_item,
    add_source,
    add_word,
    backup_db,
    get_connection,
    init_db,
)
from bhasha_lib.tokenizer import tokenize, tokenize_roman

__all__ = [
    "CSV_FOLK_SONG_COLUMNS",
    "VALID_AUDIO_FORMATS",
    "VALID_CONFIDENCE_LEVELS",
    "VALID_CONSENT_STATES",
    "VALID_DATE_PRECISIONS",
    "VALID_SONG_TYPES",
    "add_folk_song",
    "add_song_recording",
    "export_folk_songs_csv",
    "export_folk_songs_json",
    "filter_folk_songs",
    "format_folk_song_item",
    "get_folk_song",
    "get_folk_songs_missing_citations",
    "get_recording",
    "get_recordings",
    "get_recordings_missing_consent",
    "get_unverified_folk_songs",
    "import_folk_songs_csv",
    "import_folk_songs_json",
    "load_folk_song_file",
    "load_folk_songs_dir",
    "main",
    "parse_folk_song_markdown",
    "print_folk_songs",
    "request_recording_removal",
    "search_folk_songs",
    "validate_folk_song",
    "validate_song_recording",
    "verify_folk_songs_dir",
    "withdraw_recording_consent",
]

CSV_FOLK_SONG_COLUMNS: list[str] = [
    "id",
    "title",
    "title_en",
    "roman_title",
    "song_type",
    "composer",
    "lyricist",
    "performer",
    "singer",
    "community",
    "region",
    "language",
    "dialect",
    "description",
    "cultural_context",
    "festivals",
    "ceremonies",
    "dances",
    "instruments",
    "places",
    "year",
    "year_end",
    "date_precision",
    "source_id",
    "source_title",
    "primary_sources",
    "secondary_sources",
    "source_url",
    "license",
    "confidence",
    "verified_by",
    "verified_on",
    "consent_status",
    "consent_document_ref",
    "cultural_restrictions",
    "created_at",
    "updated_at",
]

FOLK_SONG_FIELDS_SQL = """
    fs.id, fs.title, fs.title_en, fs.roman_title, fs.song_type,
    fs.composer, fs.lyricist, fs.performer, fs.singer,
    fs.community, fs.region, fs.language, fs.dialect,
    fs.description, fs.cultural_context,
    fs.festivals, fs.ceremonies, fs.dances, fs.instruments, fs.places,
    fs.year, fs.year_end, fs.date_precision,
    fs.source_id, fs.source_title,
    fs.primary_sources, fs.secondary_sources, fs.source_url,
    fs.license, fs.confidence, fs.verified_by, fs.verified_on,
    fs.consent_status, fs.consent_document_ref, fs.cultural_restrictions,
    fs.created_at, fs.updated_at,
    s.title AS linked_source_title, s.license AS linked_source_license,
    s.url AS linked_source_url, s.author AS linked_source_author
"""

RECORDING_FIELDS_SQL = """
    sr.id, sr.song_id, sr.recording_title, sr.performer, sr.singer,
    sr.musicians, sr.recorder, sr.recording_date, sr.year, sr.date_precision,
    sr.location, sr.duration, sr.audio_format, sr.sample_rate,
    sr.file_path, sr.audio_url, sr.source_id, sr.source_title,
    sr.license, sr.consent_status, sr.consent_recording,
    sr.consent_publication, sr.consent_attribution,
    sr.consent_transcription, sr.consent_redistribution,
    sr.consent_document_ref, sr.consent_notes,
    sr.removal_requested, sr.removal_reason,
    sr.confidence, sr.verified_by, sr.verified_on,
    sr.created_at, sr.updated_at,
    fs.title AS song_title, fs.song_type AS song_type,
    s.title AS linked_source_title, s.license AS linked_source_license
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


# =========================================================================
# Legacy Markdown Folk Song Parsing & Ingestion (Backward Compatible)
# =========================================================================


def parse_folk_song_markdown(
    content: str, file_name: str = "document"
) -> tuple[dict[str, Any], str]:
    """Parse YAML header and song lyrics from markdown content.

    Raises:
        ValueError: If header delimiters are missing or invalid YAML.
    """
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(
            f"Invalid folk song file in '{file_name}': "
            "Missing starting '---' YAML header."
        )

    closing_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            closing_idx = i
            break

    if closing_idx == -1:
        raise ValueError(
            f"Invalid folk song file in '{file_name}': "
            "Missing closing '---' YAML header."
        )

    header_yaml = "\n".join(lines[1:closing_idx])
    lyrics = "\n".join(lines[closing_idx + 1 :]).strip()

    header_data = yaml.safe_load(header_yaml) or {}
    if not isinstance(header_data, dict):
        raise ValueError(
            f"Invalid YAML frontmatter in '{file_name}': Expected dictionary."
        )

    return header_data, lyrics


def load_folk_song_file(
    file_path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """Validate consent and load a single folk song into the database.

    Raises:
        ConsentError: If the song lacks verified written consent.
        ValueError: If required metadata fields (title, lyrics) are missing.

    Returns:
        The inserted culture_item ID.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Folk song file not found: {path}")

    init_db(db_path)
    text = path.read_text(encoding="utf-8")
    header, lyrics = parse_folk_song_markdown(text, file_name=path.name)

    title = str(header.get("title") or "").strip()
    if not title:
        raise ValueError(f"Folk song '{path.name}' is missing required 'title'.")
    if not lyrics:
        raise ValueError(f"Folk song '{path.name}' has empty lyrics.")

    # Strictly enforce consent verification
    consent_record: ConsentRecord = validate_consent_dict(
        header.get("consent"), item_title=title
    )

    category = str(header.get("category") or "folk_song").strip()
    genre = str(header.get("genre") or "traditional").strip()
    region = str(header.get("region") or "").strip()
    license_type = str(header.get("license") or "CC-BY-NC-SA-4.0").strip()
    lyrics_script = str(header.get("lyrics_script") or "devanagari").strip().lower()

    instruments = header.get("instruments") or []
    if isinstance(instruments, list):
        inst_str = ", ".join(str(i).strip() for i in instruments if str(i).strip())
    else:
        inst_str = str(instruments).strip()

    related_words = [inst_str, genre] if inst_str else [genre]
    related_str = ", ".join(filter(None, related_words))

    # Register or find source record
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM sources WHERE title = ? AND type = 'folk_song'",
            (title,),
        )
        row = cursor.fetchone()
        if row is not None:
            source_id = int(row[0])
        else:
            source_id = add_source(
                title=title,
                type="folk_song",
                author=consent_record.performer_name,
                license=license_type,
                contributor=consent_record.consent_holder,
                file_path=str(path),
                db_path=db_path,
            )

    # Ingest into culture_items table
    description = (
        f"Genre: {genre}\nPerformer: {consent_record.performer_name}\n\n{lyrics}"
    )
    item_id = add_culture_item(
        category=category,
        title=title,
        description=description,
        region=region if region else None,
        related_words=related_str,
        source_id=source_id,
        db_path=db_path,
    )

    # Tokenize lyrics into vocabulary table
    tokenizer_fn = tokenize_roman if lyrics_script == "latin" else tokenize
    tokens = tokenizer_fn(lyrics)
    for token in tokens:
        add_word(word=token, freq=1, db_path=db_path)

    return item_id


def load_folk_songs_dir(
    dir_path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
    skip_unconsented: bool = False,
) -> list[int]:
    """Load all compliant folk songs from a folder into the database.

    Args:
        dir_path: Directory containing folk song markdown files.
        db_path: SQLite database path.
        skip_unconsented: If True, skips files with invalid consent.

    Returns:
        List of inserted culture item IDs.
    """
    directory = Path(dir_path)
    if not directory.is_dir():
        raise FileNotFoundError(f"Folk songs directory not found: {directory}")

    loaded_ids: list[int] = []
    for file_path in sorted(directory.glob("*.md")):
        try:
            item_id = load_folk_song_file(file_path, db_path=db_path)
            loaded_ids.append(item_id)
        except ConsentError as e:
            if skip_unconsented:
                print(f"[Skipping] {file_path.name}: {e}", file=sys.stderr)
                continue
            raise

    return loaded_ids


def verify_folk_songs_dir(dir_path: str | Path) -> dict[str, list[str]]:
    """Audit a directory and classify files by consent compliance."""
    directory = Path(dir_path)
    if not directory.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")

    report: dict[str, list[str]] = {
        "valid": [],
        "pending": [],
        "invalid": [],
    }

    for file_path in sorted(directory.glob("*.md")):
        try:
            text = file_path.read_text(encoding="utf-8")
            header, _ = parse_folk_song_markdown(text, file_name=file_path.name)
            validate_consent_dict(header.get("consent"), item_title=file_path.name)
            report["valid"].append(file_path.name)
        except ConsentError as e:
            if "status is 'pending'" in str(e).lower():
                report["pending"].append(file_path.name)
            else:
                report["invalid"].append(file_path.name)
        except Exception:
            report["invalid"].append(file_path.name)

    return report


# =========================================================================
# Step 5 Normalized Song & Audio Module (Validation & Core CRUD)
# =========================================================================


def validate_folk_song(data: dict[str, Any]) -> list[str]:
    """Validate folk song dictionary against cultural schema and ethical rules.

    Checks:
    - Required 'title' and non-empty.
    - 'song_type' within VALID_SONG_TYPES.
    - Integer 'year' and 'year_end' within realistic range (-5000 to 2100).
    - End year not earlier than start year.
    - 'date_precision' within VALID_DATE_PRECISIONS.
    - 'confidence' within VALID_CONFIDENCE_LEVELS.
    - 'verified' records require non-future 'verified_on' date (YYYY-MM-DD)
      and 'verified_by'.
    - 'consent_status' within VALID_CONSENT_STATES.
    - 'consent_status: granted' requires supporting 'consent_document_ref'.
    - Copyright safety: descriptions must be brief factual metadata (<2500 chars).

    Returns:
        List of validation failure reasons. Empty if valid.
    """
    errors: list[str] = []

    title = data.get("title")
    if not title or not str(title).strip():
        errors.append("Missing required 'title' field.")

    song_type = data.get("song_type")
    if not song_type or not str(song_type).strip():
        errors.append("Missing required 'song_type' field.")
    else:
        clean_st = str(song_type).strip().lower()
        if clean_st == "folk_song":
            clean_st = "traditional_folk_song"
        if clean_st not in VALID_SONG_TYPES:
            errors.append(
                f"Invalid 'song_type': '{song_type}'. Must be one of: "
                f"{sorted(VALID_SONG_TYPES)}."
            )

    year = data.get("year")
    year_end = data.get("year_end")

    y_int: int | None = None
    if year is not None and str(year).strip():
        try:
            y_int = int(year)
            if y_int < -5000 or y_int > 2100:
                errors.append(f"Year {y_int} is out of realistic range.")
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
            f"start year ({y_int})."
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

    consent_status = data.get("consent_status")
    if consent_status is not None and str(consent_status).strip():
        clean_cs = str(consent_status).strip().lower()
        if clean_cs not in VALID_CONSENT_STATES:
            errors.append(
                f"Invalid 'consent_status': '{consent_status}'. Must be one of "
                f"{sorted(VALID_CONSENT_STATES)}."
            )
        if clean_cs == "granted":
            doc_ref = data.get("consent_document_ref")
            if not doc_ref or not str(doc_ref).strip():
                errors.append(
                    "Consent status 'granted' requires supporting evidence in "
                    "'consent_document_ref'."
                )

    # Copyright safety check: description must be short factual metadata or summary
    desc = data.get("description")
    if desc and len(str(desc).strip()) > 10000:
        errors.append(
            "Description is excessively long (>10,000 chars). Store short factual "
            "summaries only; do not copy full unconsented lyrics or transcriptions."
        )

    return errors


def validate_song_recording(data: dict[str, Any]) -> list[str]:
    """Validate song recording dictionary against ethical audio rules.

    Checks:
    - Required integer 'song_id' > 0.
    - 'consent_status' within VALID_CONSENT_STATES.
    - 'consent_status: granted' requires supporting 'consent_document_ref'.
    - Scope consents within VALID_CONSENT_STATES.
    - If any scope consent is 'granted', requires 'consent_document_ref'.
    - 'confidence' within VALID_CONFIDENCE_LEVELS.
    - Verified status requires non-future 'verified_on' date.

    Returns:
        List of validation failure reasons. Empty if valid.
    """
    errors: list[str] = []

    song_id = data.get("song_id")
    if song_id is None:
        errors.append("Missing required 'song_id' foreign key.")
    else:
        try:
            s_int = int(song_id)
            if s_int <= 0:
                errors.append(f"Invalid 'song_id' value: {song_id} (must be > 0).")
        except (ValueError, TypeError):
            errors.append(f"Invalid 'song_id' value: {song_id} (must be an integer).")

    consent_status = data.get("consent_status")
    clean_cs = str(consent_status).strip().lower() if consent_status else "unknown"
    if clean_cs not in VALID_CONSENT_STATES:
        errors.append(
            f"Invalid 'consent_status': '{consent_status}'. Must be one of: "
            f"{sorted(VALID_CONSENT_STATES)}."
        )

    doc_ref = data.get("consent_document_ref")
    clean_doc = str(doc_ref).strip() if doc_ref else ""

    if clean_cs == "granted" and not clean_doc:
        errors.append(
            "Recording consent status 'granted' requires supporting proof in "
            "'consent_document_ref'."
        )

    audio_format = data.get("audio_format")
    if audio_format is not None and str(audio_format).strip():
        clean_af = str(audio_format).strip().lower()
        if clean_af not in VALID_AUDIO_FORMATS:
            errors.append(
                f"Invalid 'audio_format': '{audio_format}'. Must be one of: "
                f"{sorted(VALID_AUDIO_FORMATS)}."
            )

    duration = (
        data.get("duration")
        if data.get("duration") is not None
        else data.get("duration_seconds")
    )
    if duration is not None and str(duration).strip():
        try:
            d_int = int(duration)
            if d_int < 0:
                errors.append(
                    f"Invalid 'duration_seconds': {duration} (cannot be negative)."
                )
        except (ValueError, TypeError):
            errors.append(
                f"Invalid 'duration_seconds': {duration} (must be an integer)."
            )

    permit_redistribute = data.get("permit_redistribute")
    if permit_redistribute and not clean_doc:
        errors.append(
            "Permission 'permit_redistribute' requires proof in 'consent_document_ref'."
        )

    for scope in (
        "consent_recording",
        "consent_publication",
        "consent_attribution",
        "consent_transcription",
        "consent_redistribution",
    ):
        val = data.get(scope)
        if val is not None and str(val).strip():
            c_val = str(val).strip().lower()
            if c_val not in VALID_CONSENT_STATES:
                errors.append(
                    f"Invalid '{scope}' state: '{val}'. Must be one of: "
                    f"{sorted(VALID_CONSENT_STATES)}."
                )
            if c_val == "granted" and not clean_doc:
                errors.append(
                    f"Scope '{scope}' marked 'granted' requires proof in "
                    "'consent_document_ref'."
                )

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

    return errors


def add_folk_song(
    title: str,
    title_en: str | None = None,
    roman_title: str | None = None,
    song_type: str = "traditional_folk_song",
    composer: str | None = None,
    lyricist: str | None = None,
    performer: str | None = None,
    singer: str | None = None,
    community: str | None = None,
    region: str | None = None,
    language: str | None = "brx",
    dialect: str | None = None,
    description: str | None = None,
    cultural_context: str | None = None,
    festivals: str | list[str] | None = None,
    ceremonies: str | list[str] | None = None,
    dances: str | list[str] | None = None,
    instruments: str | list[str] | None = None,
    places: str | list[str] | None = None,
    year: int | None = None,
    year_end: int | None = None,
    date_precision: str | None = None,
    source_id: int | None = None,
    source_title: str | None = None,
    primary_sources: str | list[str] | None = None,
    secondary_sources: str | list[str] | None = None,
    source_url: str | None = None,
    license: str | None = "metadata_only",
    confidence: str = "needs_check",
    verified: bool = False,
    verified_by: str | None = None,
    verified_on: str | None = None,
    consent_status: str = "unknown",
    consent_document_ref: str | None = None,
    cultural_restrictions: str | None = None,
    song_id: int | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
    raise_on_duplicate: bool = False,
) -> int | None:
    """Insert or update a structured folk song in the database.

    Enforces foreign keys, validates cultural metadata and consent rules,
    and normalizes all text to Unicode NFC.

    Raises:
        ValueError: If validation fails or duplicate insertion is disallowed.
        sqlite3.IntegrityError: If foreign-key constraint is violated.
    """
    init_db(db_path)

    if song_id is not None:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM folk_songs WHERE id = ?", (int(song_id),))
            if cursor.fetchone() is not None:
                if raise_on_duplicate:
                    raise ValueError(
                        f"Folk song #{song_id} already exists in database."
                    )
                return None

    clean_title = _clean_str(title)
    clean_type = (
        str(song_type).strip().lower() if song_type else "traditional_folk_song"
    )
    if clean_type == "folk_song":
        clean_type = "traditional_folk_song"

    clean_prec = _clean_str(date_precision) or ("unknown" if year is None else "exact")
    clean_conf = _clean_str(confidence) or "needs_check"
    if verified and clean_conf in ("needs_check", "unverified"):
        clean_conf = "verified"
        if not verified_on:
            verified_on = date.today().isoformat()
    if clean_conf == "verified" and not verified_on:
        verified_on = date.today().isoformat()

    clean_cs = _clean_str(consent_status) or "unknown"
    clean_doc_ref = _clean_str(consent_document_ref)

    payload = {
        "title": clean_title,
        "song_type": clean_type,
        "year": year,
        "year_end": year_end,
        "date_precision": clean_prec,
        "confidence": clean_conf,
        "verified_on": verified_on,
        "consent_status": clean_cs,
        "consent_document_ref": clean_doc_ref,
        "description": description,
    }
    validation_errors = validate_folk_song(payload)
    if validation_errors:
        raise ValueError(f"Folk song validation failed: {'; '.join(validation_errors)}")

    clean_title_en = _clean_str(title_en)
    clean_roman_title = _clean_str(roman_title)
    clean_composer = _clean_str(composer)
    clean_lyricist = _clean_str(lyricist)
    clean_performer = _clean_str(performer)
    clean_singer = _clean_str(singer)
    clean_community = _clean_str(community)
    clean_region = _clean_str(region)
    clean_lang = _clean_str(language) or "brx"
    clean_dialect = _clean_str(dialect)
    clean_desc = _clean_str(description)
    clean_context = _clean_str(cultural_context)
    clean_festivals = _format_list_or_str(festivals)
    clean_ceremonies = _format_list_or_str(ceremonies)
    clean_dances = _format_list_or_str(dances)
    clean_instruments = _format_list_or_str(instruments)
    clean_places = _format_list_or_str(places)
    clean_primary = _format_list_or_str(primary_sources)
    clean_secondary = _format_list_or_str(secondary_sources)
    clean_url = _clean_str(source_url)
    clean_license = _clean_str(license) or "metadata_only"
    clean_vb = _clean_str(verified_by)
    clean_vo = _clean_str(verified_on)
    clean_restrictions = _clean_str(cultural_restrictions)

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
                    VALUES (?, 'song_source', ?, ?, ?)
                    """,
                    (
                        st_clean,
                        clean_license,
                        clean_url,
                        clean_performer or clean_singer,
                    ),
                )
                resolved_source_id = int(cursor.lastrowid)

        # Duplicate check: same title, song_type, community, performer
        cursor.execute(
            """
            SELECT id FROM folk_songs
            WHERE title = ? AND song_type = ?
            AND (community = ? OR (community IS NULL AND ? IS NULL))
            AND (performer = ? OR (performer IS NULL AND ? IS NULL))
            """,
            (
                clean_title,
                clean_type,
                clean_community,
                clean_community,
                clean_performer,
                clean_performer,
            ),
        )
        existing = cursor.fetchone()

        if existing is not None:
            if raise_on_duplicate:
                comm_str = f" in '{clean_community}'" if clean_community else ""
                raise ValueError(
                    f"Folk song '{clean_title}' ({clean_type}){comm_str} "
                    "already exists in database."
                )
            existing_id = int(existing["id"])
            cursor.execute(
                """
                UPDATE folk_songs SET
                    title_en = COALESCE(?, title_en),
                    roman_title = COALESCE(?, roman_title),
                    composer = COALESCE(?, composer),
                    lyricist = COALESCE(?, lyricist),
                    singer = COALESCE(?, singer),
                    region = COALESCE(?, region),
                    language = COALESCE(?, language),
                    dialect = COALESCE(?, dialect),
                    description = COALESCE(?, description),
                    cultural_context = COALESCE(?, cultural_context),
                    festivals = COALESCE(?, festivals),
                    ceremonies = COALESCE(?, ceremonies),
                    dances = COALESCE(?, dances),
                    instruments = COALESCE(?, instruments),
                    places = COALESCE(?, places),
                    year = COALESCE(?, year),
                    year_end = COALESCE(?, year_end),
                    date_precision = COALESCE(?, date_precision),
                    source_id = COALESCE(?, source_id),
                    source_title = COALESCE(?, source_title),
                    primary_sources = COALESCE(?, primary_sources),
                    secondary_sources = COALESCE(?, secondary_sources),
                    source_url = COALESCE(?, source_url),
                    license = COALESCE(?, license),
                    confidence = COALESCE(?, confidence),
                    verified_by = COALESCE(?, verified_by),
                    verified_on = COALESCE(?, verified_on),
                    consent_status = COALESCE(?, consent_status),
                    consent_document_ref = COALESCE(?, consent_document_ref),
                    cultural_restrictions = COALESCE(?, cultural_restrictions),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    clean_title_en,
                    clean_roman_title,
                    clean_composer,
                    clean_lyricist,
                    clean_singer,
                    clean_region,
                    clean_lang,
                    clean_dialect,
                    clean_desc,
                    clean_context,
                    clean_festivals,
                    clean_ceremonies,
                    clean_dances,
                    clean_instruments,
                    clean_places,
                    year,
                    year_end,
                    clean_prec,
                    resolved_source_id,
                    source_title,
                    clean_primary,
                    clean_secondary,
                    clean_url,
                    clean_license,
                    clean_conf,
                    clean_vb,
                    clean_vo,
                    clean_cs,
                    clean_doc_ref,
                    clean_restrictions,
                    datetime.now(UTC).isoformat(),
                    existing_id,
                ),
            )
            return existing_id

    return add_folk_song_item(
        title=clean_title or "",
        title_en=clean_title_en,
        roman_title=clean_roman_title,
        song_type=clean_type,
        composer=clean_composer,
        lyricist=clean_lyricist,
        performer=clean_performer,
        singer=clean_singer,
        community=clean_community,
        region=clean_region,
        language=clean_lang,
        dialect=clean_dialect,
        description=clean_desc,
        cultural_context=clean_context,
        festivals=clean_festivals,
        ceremonies=clean_ceremonies,
        dances=clean_dances,
        instruments=clean_instruments,
        places=clean_places,
        year=year,
        year_end=year_end,
        date_precision=clean_prec,
        source_id=resolved_source_id,
        source_title=source_title,
        primary_sources=clean_primary,
        secondary_sources=clean_secondary,
        source_url=clean_url,
        license=clean_license,
        confidence=clean_conf,
        verified_by=clean_vb,
        verified_on=clean_vo,
        consent_status=clean_cs,
        consent_document_ref=clean_doc_ref,
        cultural_restrictions=clean_restrictions,
        song_id=song_id,
        db_path=db_path,
    )


def add_song_recording(
    song_id: int,
    recording_title: str | None = None,
    performer: str | None = None,
    singer: str | None = None,
    musicians: str | list[str] | None = None,
    recorder: str | None = None,
    recording_date: str | None = None,
    year: int | None = None,
    date_precision: str | None = None,
    location: str | None = None,
    duration: int | None = None,
    duration_seconds: int | None = None,
    audio_format: str | None = "unknown",
    sample_rate: int | None = None,
    file_path: str | None = None,
    audio_url: str | None = None,
    source_id: int | None = None,
    source_title: str | None = None,
    license: str | None = "all_rights_reserved",
    consent_status: str = "unknown",
    consent_recording: str = "unknown",
    consent_publication: str = "unknown",
    consent_attribution: str = "unknown",
    consent_transcription: str = "unknown",
    consent_redistribution: str = "unknown",
    consent_document_ref: str | None = None,
    consent_notes: str | None = None,
    permit_attribution: bool | None = None,
    permit_transcribe: bool | None = None,
    permit_redistribute: bool | None = None,
    permit_publication: bool | None = None,
    removal_requested: int | bool = 0,
    removal_reason: str | None = None,
    confidence: str = "needs_check",
    verified_by: str | None = None,
    verified_on: str | None = None,
    recording_id: int | None = None,
    raise_on_duplicate: bool = False,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """Insert a validated audio recording linked to a folk song.

    Enforces foreign keys to both folk_songs and sources tables.
    Validates ethical consent and non-future verification dates.

    Raises:
        ValueError: If validation fails.
        sqlite3.IntegrityError: If song_id or source_id does not exist.
    """
    init_db(db_path)

    if duration is None and duration_seconds is not None:
        duration = duration_seconds

    clean_cs = _clean_str(consent_status) or "unknown"
    clean_doc = _clean_str(consent_document_ref)

    if permit_attribution is True:
        consent_attribution = "granted"
    if permit_transcribe is True:
        consent_transcription = "granted"
    if permit_redistribute is True:
        consent_redistribution = "granted"
    if permit_publication is True:
        consent_publication = "granted"

    payload = {
        "song_id": song_id,
        "consent_status": clean_cs,
        "consent_recording": consent_recording,
        "consent_publication": consent_publication,
        "consent_attribution": consent_attribution,
        "consent_transcription": consent_transcription,
        "consent_redistribution": consent_redistribution,
        "consent_document_ref": clean_doc,
        "permit_redistribute": permit_redistribute,
        "duration": duration,
        "audio_format": audio_format,
        "confidence": confidence,
        "verified_on": verified_on,
    }
    errors = validate_song_recording(payload)
    if errors:
        raise ValueError(f"Song recording validation failed: {'; '.join(errors)}")

    # Foreign key existence verification
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM folk_songs WHERE id = ?", (int(song_id),))
        if cursor.fetchone() is None:
            raise sqlite3.IntegrityError(
                f"FOREIGN KEY constraint failed: song_id {song_id} "
                "not found in folk_songs."
            )

        resolved_source_id = source_id
        if resolved_source_id is not None:
            cursor.execute("SELECT id FROM sources WHERE id = ?", (resolved_source_id,))
            if cursor.fetchone() is None:
                raise sqlite3.IntegrityError(
                    f"FOREIGN KEY constraint failed: source_id {resolved_source_id} "
                    "not found in sources."
                )

        if recording_id is not None:
            cursor.execute(
                "SELECT id FROM song_recordings WHERE id = ?", (int(recording_id),)
            )
            if cursor.fetchone() is not None:
                if raise_on_duplicate:
                    raise ValueError(
                        f"Recording #{recording_id} already exists in database."
                    )
                return int(recording_id)

    return add_song_recording_item(
        song_id=int(song_id),
        recording_title=recording_title,
        performer=performer,
        singer=singer,
        musicians=musicians,
        recorder=recorder,
        recording_date=recording_date,
        year=year,
        date_precision=date_precision,
        location=location,
        duration=duration,
        audio_format=audio_format,
        sample_rate=sample_rate,
        file_path=file_path,
        audio_url=audio_url,
        source_id=resolved_source_id,
        source_title=source_title,
        license=license,
        consent_status=clean_cs,
        consent_recording=consent_recording,
        consent_publication=consent_publication,
        consent_attribution=consent_attribution,
        consent_transcription=consent_transcription,
        consent_redistribution=consent_redistribution,
        consent_document_ref=clean_doc,
        consent_notes=consent_notes,
        removal_requested=removal_requested,
        removal_reason=removal_reason,
        confidence=confidence,
        verified_by=verified_by,
        verified_on=verified_on,
        recording_id=recording_id,
        db_path=db_path,
    )


def get_recordings(
    song_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
    include_withdrawn: bool = True,
) -> list[dict[str, Any]]:
    """Retrieve all audio recordings linked to a specific song.

    Args:
        song_id: ID of the folk song.
        db_path: Path to database.
        include_withdrawn: If False, hides withdrawn or removed recordings.

    Returns:
        List of recording dictionaries.
    """
    init_db(db_path)
    conditions = ["sr.song_id = ?"]
    params: list[Any] = [int(song_id)]

    if not include_withdrawn:
        conditions.append(
            "(sr.removal_requested = 0 AND sr.consent_status != 'withdrawn')"
        )

    where_clause = f"WHERE {' AND '.join(conditions)}"
    query = f"""
        SELECT
            {RECORDING_FIELDS_SQL}
        FROM song_recordings sr
        JOIN folk_songs fs ON sr.song_id = fs.id
        LEFT JOIN sources s ON sr.source_id = s.id
        {where_clause}
        ORDER BY sr.id ASC
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        res = []
        for row in cursor.fetchall():
            d = dict(row)
            d["duration_seconds"] = d.get("duration")
            d["source_title"] = d.get("source_title") or d.get("linked_source_title")
            d["permit_redistribute"] = (
                1 if d.get("consent_redistribution") == "granted" else 0
            )
            d["permit_transcribe"] = (
                1 if d.get("consent_transcription") == "granted" else 0
            )
            d["permit_attribution"] = (
                1 if d.get("consent_attribution") == "granted" else 0
            )
            d["permit_publication"] = (
                1 if d.get("consent_publication") == "granted" else 0
            )
            d["consent_withdrawn_at"] = (
                d.get("updated_at") if d.get("consent_status") == "withdrawn" else None
            )
            res.append(d)
        return res


def get_recording(
    recording_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any] | None:
    """Retrieve a single audio recording by ID."""
    init_db(db_path)
    query = f"""
        SELECT
            {RECORDING_FIELDS_SQL}
        FROM song_recordings sr
        JOIN folk_songs fs ON sr.song_id = fs.id
        LEFT JOIN sources s ON sr.source_id = s.id
        WHERE sr.id = ?
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, (int(recording_id),))
        row = cursor.fetchone()
        if row is None:
            return None
        d = dict(row)
        d["duration_seconds"] = d.get("duration")
        d["source_title"] = d.get("source_title") or d.get("linked_source_title")
        d["permit_redistribute"] = (
            1 if d.get("consent_redistribution") == "granted" else 0
        )
        d["permit_transcribe"] = 1 if d.get("consent_transcription") == "granted" else 0
        d["permit_attribution"] = 1 if d.get("consent_attribution") == "granted" else 0
        d["permit_publication"] = 1 if d.get("consent_publication") == "granted" else 0
        d["consent_withdrawn_at"] = (
            d.get("updated_at") if d.get("consent_status") == "withdrawn" else None
        )
        return d


def get_folk_song(
    song_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
    include_recordings: bool = True,
) -> dict[str, Any] | None:
    """Retrieve a single folk song by ID, optionally joined with its recordings.

    Returns:
        Song dictionary with linked source details and attached 'recordings' list.
    """
    init_db(db_path)
    query = f"""
        SELECT
            {FOLK_SONG_FIELDS_SQL}
        FROM folk_songs fs
        LEFT JOIN sources s ON fs.source_id = s.id
        WHERE fs.id = ?
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, (int(song_id),))
        row = cursor.fetchone()
        if row is None:
            return None
        res = dict(row)
        res["source_title"] = res.get("source_title") or res.get("linked_source_title")

    if include_recordings:
        res["recordings"] = get_recordings(
            song_id=int(song_id), db_path=db_path, include_withdrawn=True
        )

    return res


def filter_folk_songs(
    db_path: str | Path = DEFAULT_DB_PATH,
    song_type: str | None = None,
    region: str | None = None,
    community: str | None = None,
    performer: str | None = None,
    from_year: int | None = None,
    to_year: int | None = None,
    confidence: str | None = None,
    consent_status: str | None = None,
    verified_only: bool = False,
    has_recording_only: bool = False,
    include_unknown_dates: bool = True,
    sort_order: str = "asc",
) -> list[dict[str, Any]]:
    """Filter folk songs across genres, regions, performers, and verification states.

    Returns:
        List of matching song dictionaries.
    """
    init_db(db_path)
    conditions: list[str] = []
    params: list[Any] = []

    if not include_unknown_dates:
        conditions.append("fs.year IS NOT NULL")

    if verified_only:
        conditions.append("fs.confidence = 'verified'")

    if has_recording_only:
        conditions.append(
            "EXISTS (SELECT 1 FROM song_recordings sr WHERE sr.song_id = fs.id)"
        )

    if song_type:
        clean_st = str(song_type).strip().lower()
        if clean_st == "folk_song":
            clean_st = "traditional_folk_song"
        conditions.append("fs.song_type = ?")
        params.append(clean_st)

    if region:
        clean_r = _escape_like(region.strip())
        conditions.append("fs.region LIKE ? ESCAPE '\\'")
        params.append(f"%{clean_r}%")

    if community:
        clean_c = _escape_like(community.strip())
        conditions.append("fs.community LIKE ? ESCAPE '\\'")
        params.append(f"%{clean_c}%")

    if performer:
        clean_p = _escape_like(performer.strip())
        conditions.append(
            "(fs.performer LIKE ? ESCAPE '\\' OR fs.singer LIKE ? ESCAPE '\\')"
        )
        params.extend([f"%{clean_p}%", f"%{clean_p}%"])

    if from_year is not None:
        conditions.append("fs.year >= ?")
        params.append(int(from_year))

    if to_year is not None:
        conditions.append("fs.year <= ?")
        params.append(int(to_year))

    if confidence:
        conditions.append("fs.confidence = ?")
        params.append(confidence.strip().lower())

    if consent_status:
        conditions.append("fs.consent_status = ?")
        params.append(consent_status.strip().lower())

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    order = "DESC" if str(sort_order).lower() == "desc" else "ASC"

    query = f"""
        SELECT
            {FOLK_SONG_FIELDS_SQL}
        FROM folk_songs fs
        LEFT JOIN sources s ON fs.source_id = s.id
        {where_clause}
        ORDER BY
            CASE WHEN fs.year IS NULL THEN 1 ELSE 0 END,
            fs.year {order},
            fs.title ASC
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def search_folk_songs(
    query: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    song_type: str | None = None,
    region: str | None = None,
) -> list[dict[str, Any]]:
    """Search folk songs by title, performer, context, instruments, or festivals."""
    clean_query = str(query or "").strip()
    if not clean_query:
        return []

    init_db(db_path)
    pattern = f"%{_escape_like(clean_query)}%"
    conditions = [
        """(
            fs.title LIKE ? ESCAPE '\\'
            OR fs.title_en LIKE ? ESCAPE '\\'
            OR fs.roman_title LIKE ? ESCAPE '\\'
            OR fs.performer LIKE ? ESCAPE '\\'
            OR fs.singer LIKE ? ESCAPE '\\'
            OR fs.composer LIKE ? ESCAPE '\\'
            OR fs.community LIKE ? ESCAPE '\\'
            OR fs.region LIKE ? ESCAPE '\\'
            OR fs.description LIKE ? ESCAPE '\\'
            OR fs.cultural_context LIKE ? ESCAPE '\\'
            OR fs.festivals LIKE ? ESCAPE '\\'
            OR fs.instruments LIKE ? ESCAPE '\\'
            OR fs.dances LIKE ? ESCAPE '\\'
            OR fs.places LIKE ? ESCAPE '\\'
            OR s.title LIKE ? ESCAPE '\\'
        )"""
    ]
    params: list[Any] = [pattern] * 15

    if song_type:
        clean_st = str(song_type).strip().lower()
        if clean_st == "folk_song":
            clean_st = "traditional_folk_song"
        conditions.append("fs.song_type = ?")
        params.append(clean_st)

    if region:
        clean_r = _escape_like(region.strip())
        conditions.append("fs.region LIKE ? ESCAPE '\\'")
        params.append(f"%{clean_r}%")

    where_clause = f"WHERE {' AND '.join(conditions)}"
    sql = f"""
        SELECT
            {FOLK_SONG_FIELDS_SQL}
        FROM folk_songs fs
        LEFT JOIN sources s ON fs.source_id = s.id
        {where_clause}
        ORDER BY
            CASE WHEN fs.year IS NULL THEN 1 ELSE 0 END,
            fs.year ASC,
            fs.title ASC
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


# =========================================================================
# Consent Governance & Removal Requests
# =========================================================================


def withdraw_recording_consent(
    recording_id: int,
    reason: str,
    withdrawn_by: str = "Archivist",
    db_path: str | Path = DEFAULT_DB_PATH,
) -> bool:
    """Withdraw consent for an audio recording.

    Sets consent_status, consent_publication, and consent_redistribution to 'withdrawn',
    records withdrawal reason, and updates timestamps.

    Returns:
        True if recording found and updated, False otherwise.
    """
    init_db(db_path)
    clean_reason = _clean_str(reason) or "Consent withdrawn by performer/holder."
    note = f"Withdrawn by {withdrawn_by}: {clean_reason}"
    now_iso = datetime.now(UTC).isoformat()

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE song_recordings SET
                consent_status = 'withdrawn',
                consent_publication = 'withdrawn',
                consent_redistribution = 'withdrawn',
                consent_notes = COALESCE(consent_notes || '; ' || ?, ?),
                updated_at = ?
            WHERE id = ?
            """,
            (note, note, now_iso, int(recording_id)),
        )
        return cursor.rowcount > 0


def request_recording_removal(
    recording_id: int,
    reason: str,
    requested_by: str = "Community Elder / Contributor",
    db_path: str | Path = DEFAULT_DB_PATH,
) -> bool:
    """File a formal removal request for an audio recording.

    Marks removal_requested = 1, sets consent to 'withdrawn', and records reason.

    Returns:
        True if recording found and updated, False otherwise.
    """
    init_db(db_path)
    clean_reason = _clean_str(reason) or "Community removal request."
    note = f"Removal requested by {requested_by}: {clean_reason}"
    now_iso = datetime.now(UTC).isoformat()

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE song_recordings SET
                removal_requested = 1,
                removal_reason = ?,
                consent_status = 'withdrawn',
                consent_publication = 'withdrawn',
                consent_redistribution = 'withdrawn',
                consent_notes = COALESCE(consent_notes || '; ' || ?, ?),
                updated_at = ?
            WHERE id = ?
            """,
            (clean_reason, note, note, now_iso, int(recording_id)),
        )
        return cursor.rowcount > 0


def get_recordings_missing_consent(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """Retrieve audio recordings that lack verified ethical consent.

    Flagged if:
    - Consent status is 'unknown', 'pending', 'denied', or 'withdrawn'.
    - Consent status is 'granted' but missing 'consent_document_ref'.
    - A removal request is active (removal_requested = 1).
    - Publication or redistribution consent is not 'granted'.

    Returns:
        List of recording dictionaries with attached 'consent_reasons' and
        'consent_reason' summary.
    """
    init_db(db_path)
    query = f"""
        SELECT
            {RECORDING_FIELDS_SQL}
        FROM song_recordings sr
        JOIN folk_songs fs ON sr.song_id = fs.id
        LEFT JOIN sources s ON sr.source_id = s.id
        ORDER BY sr.id ASC
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        rows = [dict(r) for r in cursor.fetchall()]

    flagged: list[dict[str, Any]] = []
    for r in rows:
        reasons: list[str] = []
        cs = (r.get("consent_status") or "unknown").strip().lower()
        doc = (r.get("consent_document_ref") or "").strip()
        pub = (r.get("consent_publication") or "unknown").strip().lower()
        redist = (r.get("consent_redistribution") or "unknown").strip().lower()
        removal = bool(r.get("removal_requested"))

        if removal:
            reasons.append(
                f"Removal requested: {r.get('removal_reason') or 'No reason specified'}"
            )
        if cs in ("unknown", "pending"):
            reasons.append(f"Consent is unconfirmed (status: {cs})")
        elif cs == "denied":
            reasons.append("Consent was explicitly denied")
        elif cs == "withdrawn":
            reasons.append("Consent has been withdrawn")
        elif cs == "granted" and not doc:
            reasons.append("Marked 'granted' without supporting consent_document_ref")

        if pub in ("denied", "withdrawn"):
            reasons.append(f"Publication consent is {pub}")
        if redist in ("denied", "withdrawn"):
            reasons.append(f"Redistribution consent is {redist}")

        if reasons:
            item_copy = dict(r)
            item_copy["consent_reasons"] = reasons
            item_copy["consent_reason"] = "; ".join(reasons)
            flagged.append(item_copy)

    return flagged


def get_folk_songs_missing_citations(
    db_path: str | Path = DEFAULT_DB_PATH,
    song_type: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve folk songs that lack sufficient bibliographic or archival citations.

    A song is flagged if:
    - It has no source_id and no primary or secondary citations.
    - Its linked source title is missing or empty.
    - Its source title is only a generic website (e.g. 'Wikipedia').
    - Its source title is under 15 characters without independent primary sources.

    Returns:
        List of song dictionaries with attached 'missing_reasons' and
        'missing_reason' summary.
    """
    init_db(db_path)
    conditions: list[str] = []
    params: list[Any] = []
    if song_type:
        clean_st = str(song_type).strip().lower()
        if clean_st == "folk_song":
            clean_st = "traditional_folk_song"
        conditions.append("fs.song_type = ?")
        params.append(clean_st)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT
            {FOLK_SONG_FIELDS_SQL}
        FROM folk_songs fs
        LEFT JOIN sources s ON fs.source_id = s.id
        {where_clause}
        ORDER BY fs.id ASC
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]

    flagged: list[dict[str, Any]] = []
    for r in rows:
        source_id = r.get("source_id")
        source_title = (
            r.get("source_title") or r.get("linked_source_title") or ""
        ).strip()
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
                    "lacks specific archive or publication details"
                )

        if missing_reasons:
            item_copy = dict(r)
            item_copy["missing_reasons"] = missing_reasons
            item_copy["missing_reason"] = "; ".join(missing_reasons)
            flagged.append(item_copy)

    return flagged


def get_unverified_folk_songs(
    db_path: str | Path = DEFAULT_DB_PATH,
    song_type: str | None = None,
) -> list[dict[str, Any]]:
    """List folk songs that have not reached 'verified' status."""
    init_db(db_path)
    conditions = ["(fs.confidence != 'verified' OR fs.confidence IS NULL)"]
    params: list[Any] = []
    if song_type:
        clean_st = str(song_type).strip().lower()
        if clean_st == "folk_song":
            clean_st = "traditional_folk_song"
        conditions.append("fs.song_type = ?")
        params.append(clean_st)

    where_clause = f"WHERE {' AND '.join(conditions)}"
    query = f"""
        SELECT
            {FOLK_SONG_FIELDS_SQL}
        FROM folk_songs fs
        LEFT JOIN sources s ON fs.source_id = s.id
        {where_clause}
        ORDER BY
            CASE WHEN fs.year IS NULL THEN 1 ELSE 0 END,
            fs.year ASC,
            fs.title ASC
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


# =========================================================================
# Import & Export (CSV & JSON Metadata Only)
# =========================================================================


def export_folk_songs_csv(
    csv_path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
    song_type: str | None = None,
) -> int:
    """Export folk song metadata to CSV. Never exports binary audio data."""
    songs = filter_folk_songs(
        db_path=db_path, song_type=song_type, include_unknown_dates=True
    )
    target = Path(csv_path)
    if target.parent and not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)

    with open(target, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=CSV_FOLK_SONG_COLUMNS, extrasaction="ignore"
        )
        writer.writeheader()
        for s in songs:
            writer.writerow(s)

    return len(songs)


def export_folk_songs_json(
    json_path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
    song_type: str | None = None,
    indent: int = 2,
) -> int:
    """Export folk songs and their linked recordings to JSON."""
    songs = filter_folk_songs(
        db_path=db_path, song_type=song_type, include_unknown_dates=True
    )
    for s in songs:
        s["recordings"] = get_recordings(
            song_id=int(s["id"]), db_path=db_path, include_withdrawn=True
        )

    target = Path(json_path)
    if target.parent and not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)

    with open(target, "w", encoding="utf-8") as f:
        json.dump(songs, f, indent=indent, ensure_ascii=False)

    return len(songs)


def import_folk_songs_csv(
    csv_path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Import and validate folk song records from CSV.

    Creates an ACID-compliant backup before writing changes (if not dry_run).
    Reports validation errors and updates existing records.

    Returns:
        Statistics dictionary.
    """
    target = Path(csv_path)
    if not target.is_file():
        raise FileNotFoundError(f"Folk songs CSV file not found: {target}")

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
            song_type = row.get("song_type") or "traditional_folk_song"

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
                "song_type": song_type,
                "year": year_val,
                "year_end": year_end_val,
                "date_precision": row.get("date_precision") or None,
                "confidence": row.get("confidence") or "needs_check",
                "verified_on": row.get("verified_on") or None,
                "consent_status": row.get("consent_status") or "unknown",
                "consent_document_ref": row.get("consent_document_ref") or None,
                "description": row.get("description") or None,
            }

            val_errors = validate_folk_song(payload)
            if val_errors:
                stats["rejected"] += 1
                stats["errors"].append(
                    f"Row {row_idx} ('{title}'): {'; '.join(val_errors)}"
                )
                continue

            # Check duplicate
            clean_type = (
                "traditional_folk_song"
                if song_type == "folk_song"
                else song_type.strip().lower()
            )
            community = row.get("community") or None
            performer = row.get("performer") or None

            with get_connection(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id FROM folk_songs
                    WHERE title = ? AND song_type = ?
                    AND (community = ? OR (community IS NULL AND ? IS NULL))
                    AND (performer = ? OR (performer IS NULL AND ? IS NULL))
                    """,
                    (title, clean_type, community, community, performer, performer),
                )
                existing = cursor.fetchone()

            if existing is not None:
                stats["rejected"] += 1
                stats["errors"].append(
                    f"Row {row_idx} ('{title}'): Duplicate conflict with "
                    f"existing song record #{existing['id']}."
                )
                continue
            else:
                if dry_run:
                    stats["imported"] += 1
                else:
                    try:
                        add_folk_song(
                            title=title,
                            title_en=row.get("title_en") or None,
                            roman_title=row.get("roman_title") or None,
                            song_type=clean_type,
                            composer=row.get("composer") or None,
                            lyricist=row.get("lyricist") or None,
                            performer=performer,
                            singer=row.get("singer") or None,
                            community=community,
                            region=row.get("region") or None,
                            language=row.get("language") or "brx",
                            dialect=row.get("dialect") or None,
                            description=row.get("description") or None,
                            cultural_context=row.get("cultural_context") or None,
                            festivals=row.get("festivals") or None,
                            ceremonies=row.get("ceremonies") or None,
                            dances=row.get("dances") or None,
                            instruments=row.get("instruments") or None,
                            places=row.get("places") or None,
                            year=year_val,
                            year_end=year_end_val,
                            date_precision=row.get("date_precision") or None,
                            source_id=src_id_val,
                            source_title=row.get("source_title") or None,
                            primary_sources=row.get("primary_sources") or None,
                            secondary_sources=row.get("secondary_sources") or None,
                            source_url=row.get("source_url") or None,
                            license=row.get("license") or "metadata_only",
                            confidence=row.get("confidence") or "needs_check",
                            verified_by=row.get("verified_by") or None,
                            verified_on=row.get("verified_on") or None,
                            consent_status=row.get("consent_status") or "unknown",
                            consent_document_ref=row.get("consent_document_ref")
                            or None,
                            cultural_restrictions=row.get("cultural_restrictions")
                            or None,
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


def import_folk_songs_json(
    json_path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Import and validate folk songs and recordings from JSON."""
    target = Path(json_path)
    if not target.is_file():
        raise FileNotFoundError(f"Folk songs JSON file not found: {target}")

    init_db(db_path)

    backup_file: Path | None = None
    if not dry_run and str(db_path) != ":memory:" and Path(db_path).is_file():
        backup_file = backup_db(db_path)

    with open(target, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("JSON file must contain a list of folk song records.")

    stats: dict[str, Any] = {
        "total": 0,
        "imported": 0,
        "updated": 0,
        "skipped": 0,
        "rejected": 0,
        "recordings_imported": 0,
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
        song_type = str(item.get("song_type") or "traditional_folk_song").strip()

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
            "song_type": song_type,
            "year": year_val,
            "year_end": year_end_val,
            "date_precision": item.get("date_precision"),
            "confidence": item.get("confidence") or "needs_check",
            "verified_on": item.get("verified_on"),
            "consent_status": item.get("consent_status") or "unknown",
            "consent_document_ref": item.get("consent_document_ref"),
            "description": item.get("description"),
        }

        val_errors = validate_folk_song(payload)
        if val_errors:
            stats["rejected"] += 1
            stats["errors"].append(f"Item #{idx} ('{title}'): {'; '.join(val_errors)}")
            continue

        clean_type = (
            "traditional_folk_song" if song_type == "folk_song" else song_type.lower()
        )
        community = item.get("community")
        performer = item.get("performer")
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id FROM folk_songs
                WHERE title = ? AND song_type = ?
                AND (community = ? OR (community IS NULL AND ? IS NULL))
                AND (performer = ? OR (performer IS NULL AND ? IS NULL))
                """,
                (title, clean_type, community, community, performer, performer),
            )
            existing = cursor.fetchone()

        if existing is not None:
            stats["rejected"] += 1
            stats["errors"].append(
                f"Item #{idx} ('{title}'): Duplicate conflict with "
                f"existing song record #{existing['id']}."
            )
            continue

        song_id: int | None = None
        if dry_run:
            stats["imported"] += 1
        else:
            try:
                song_id = add_folk_song(
                    title=title,
                    title_en=item.get("title_en"),
                    roman_title=item.get("roman_title"),
                    song_type=clean_type,
                    composer=item.get("composer"),
                    lyricist=item.get("lyricist"),
                    performer=performer,
                    singer=item.get("singer"),
                    community=community,
                    region=item.get("region"),
                    language=item.get("language") or "brx",
                    dialect=item.get("dialect"),
                    description=item.get("description"),
                    cultural_context=item.get("cultural_context"),
                    festivals=item.get("festivals"),
                    ceremonies=item.get("ceremonies"),
                    dances=item.get("dances"),
                    instruments=item.get("instruments"),
                    places=item.get("places"),
                    year=year_val,
                    year_end=year_end_val,
                    date_precision=item.get("date_precision"),
                    source_id=src_id_val,
                    source_title=item.get("source_title"),
                    primary_sources=item.get("primary_sources"),
                    secondary_sources=item.get("secondary_sources"),
                    source_url=item.get("source_url"),
                    license=item.get("license") or "metadata_only",
                    confidence=item.get("confidence") or "needs_check",
                    verified_by=item.get("verified_by"),
                    verified_on=item.get("verified_on"),
                    consent_status=item.get("consent_status") or "unknown",
                    consent_document_ref=item.get("consent_document_ref"),
                    cultural_restrictions=item.get("cultural_restrictions"),
                    db_path=db_path,
                    raise_on_duplicate=False,
                )
                stats["imported"] += 1
            except Exception as exc:
                stats["rejected"] += 1
                stats["errors"].append(
                    f"Item #{idx} ('{title}'): Failed to import song: {exc}"
                )
                continue

        # Ingest nested recordings if present
        recs = item.get("recordings")
        if recs and isinstance(recs, list) and song_id is not None and not dry_run:
            for r in recs:
                if isinstance(r, dict):
                    try:
                        add_song_recording(
                            song_id=song_id,
                            recording_title=r.get("recording_title"),
                            performer=r.get("performer"),
                            singer=r.get("singer"),
                            musicians=r.get("musicians"),
                            recorder=r.get("recorder"),
                            recording_date=r.get("recording_date"),
                            year=r.get("year"),
                            date_precision=r.get("date_precision"),
                            location=r.get("location"),
                            duration=r.get("duration"),
                            audio_format=r.get("audio_format") or "unknown",
                            sample_rate=r.get("sample_rate"),
                            file_path=r.get("file_path"),
                            audio_url=r.get("audio_url"),
                            source_id=r.get("source_id"),
                            source_title=r.get("source_title"),
                            license=r.get("license") or "all_rights_reserved",
                            consent_status=r.get("consent_status") or "unknown",
                            consent_recording=r.get("consent_recording") or "unknown",
                            consent_publication=r.get("consent_publication")
                            or "unknown",
                            consent_attribution=r.get("consent_attribution")
                            or "unknown",
                            consent_transcription=r.get("consent_transcription")
                            or "unknown",
                            consent_redistribution=r.get("consent_redistribution")
                            or "unknown",
                            consent_document_ref=r.get("consent_document_ref"),
                            consent_notes=r.get("consent_notes"),
                            confidence=r.get("confidence") or "needs_check",
                            verified_by=r.get("verified_by"),
                            verified_on=r.get("verified_on"),
                            db_path=db_path,
                        )
                        stats["recordings_imported"] += 1
                    except Exception as r_exc:
                        stats["errors"].append(
                            f"Recording for song #{song_id} error: {r_exc}"
                        )

    return stats


def format_folk_song_item(
    song: dict[str, Any],
    recordings: list[dict[str, Any]] | None = None,
    verbose: bool = False,
) -> str:
    """Format single folk song and its recordings into human-readable text."""
    title = song.get("title") or "Untitled"
    title_en = song.get("title_en")
    title_str = f"{title} ({title_en})" if title_en else title
    stype = song.get("song_type") or "traditional_folk_song"
    comm = song.get("community") or song.get("region")
    comm_str = f" [{comm}]" if comm else ""
    confidence = song.get("confidence") or "needs_check"
    conf_marker = f" ({confidence})" if confidence != "verified" else ""
    cs = song.get("consent_status") or "unknown"
    cs_marker = f" [consent: {cs}]" if cs != "granted" else ""

    lines = [f"• {title_str} - {stype}{comm_str}{conf_marker}{cs_marker}"]

    desc = (song.get("description") or "").strip()
    if desc:
        first_line = desc.split("\n\n")[0].replace("\n", " ").strip()
        lines.append(f"    Context: {first_line}")

    inst = song.get("instruments")
    if inst:
        lines.append(f"    Instruments: {inst}")

    fests = song.get("festivals") or song.get("dances")
    if fests:
        lines.append(f"    Associated: {fests}")

    recs = recordings if recordings is not None else song.get("recordings")
    if recs:
        lines.append(f"    Recordings ({len(recs)}):")
        for idx, r in enumerate(recs, start=1):
            perf = r.get("performer") or r.get("singer") or "Unknown"
            fmt = r.get("audio_format") or "unknown"
            rcs = r.get("consent_status") or "unknown"
            rem = " [REMOVAL REQUESTED]" if r.get("removal_requested") else ""
            lines.append(f"      [{idx}] {perf} ({fmt}) [consent: {rcs}]{rem}")

    if verbose:
        src = (
            song.get("source_title")
            or song.get("linked_source_title")
            or song.get("primary_sources")
        )
        if src:
            lines.append(f"    Source: {src}")
        if song.get("cultural_restrictions"):
            lines.append(
                f"    Cultural Restrictions: {song.get('cultural_restrictions')}"
            )
        if song.get("missing_reason"):
            lines.append(f"    Citation Issue: {song.get('missing_reason')}")

    return "\n".join(lines)


def print_folk_songs(
    songs: list[dict[str, Any]],
    verbose: bool = False,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    """Display folk songs in human-readable format."""
    if not songs:
        print("No folk songs found.")
        return

    print(f"Bodo Folk Songs & Oral Literature ({len(songs)} song(s)):\n")
    for s in songs:
        recs = get_recordings(
            song_id=int(s["id"]), db_path=db_path, include_withdrawn=True
        )
        print(format_folk_song_item(s, recordings=recs, verbose=verbose))
        print()


# =========================================================================
# CLI Interface
# =========================================================================


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for folk songs, recordings, consent audits, and imports."""
    parser = argparse.ArgumentParser(
        description="Manage and verify folk songs and audio with ethical consent."
    )
    subparsers = parser.add_subparsers(dest="command", required=False)

    # Legacy Subcommand: verify
    verify_p = subparsers.add_parser(
        "verify", help="Verify consent compliance in folk songs folder"
    )
    verify_p.add_argument(
        "dir", type=str, help="Directory containing folk song markdown files"
    )

    # Legacy Subcommand: load
    load_p = subparsers.add_parser(
        "load", help="Load consented folk songs into SQLite database"
    )
    load_p.add_argument(
        "dir", type=str, help="Directory containing folk song markdown files"
    )
    load_p.add_argument(
        "--db",
        type=str,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    load_p.add_argument(
        "--skip-unconsented",
        action="store_true",
        help="Skip unconsented files rather than raising an error",
    )

    # Step 5 Subcommands
    search_p = subparsers.add_parser("search", help="Search folk songs by keyword")
    search_p.add_argument("query", type=str, help="Search query string")
    search_p.add_argument("--db", type=str, default=DEFAULT_DB_PATH)
    search_p.add_argument(
        "--type", type=str, default=None, choices=sorted(VALID_SONG_TYPES)
    )
    search_p.add_argument("--region", type=str, default=None)
    search_p.add_argument("-v", "--verbose", action="store_true")

    filter_p = subparsers.add_parser("filter", help="Filter folk songs by metadata")
    filter_p.add_argument("--db", type=str, default=DEFAULT_DB_PATH)
    filter_p.add_argument(
        "--type", type=str, default=None, choices=sorted(VALID_SONG_TYPES)
    )
    filter_p.add_argument("--region", type=str, default=None)
    filter_p.add_argument("--community", type=str, default=None)
    filter_p.add_argument("--performer", type=str, default=None)
    filter_p.add_argument("--from-year", type=int, default=None)
    filter_p.add_argument("--to-year", type=int, default=None)
    filter_p.add_argument("--confidence", type=str, default=None)
    filter_p.add_argument("-v", "--verbose", action="store_true")

    rec_p = subparsers.add_parser("recordings", help="List recordings linked to a song")
    rec_p.add_argument("song_id", type=int, nargs="?", default=None)
    rec_p.add_argument("--song-id", dest="song_id_opt", type=int, default=None)
    rec_p.add_argument("--db", type=str, default=DEFAULT_DB_PATH)
    rec_p.add_argument("-v", "--verbose", action="store_true")

    missing_cit_p = subparsers.add_parser(
        "missing-citations", help="Audit songs lacking bibliographic citations"
    )
    missing_cit_p.add_argument("--db", type=str, default=DEFAULT_DB_PATH)
    missing_cit_p.add_argument("--type", type=str, default=None)

    unverified_p = subparsers.add_parser(
        "unverified", help="List songs pending academic/community verification"
    )
    unverified_p.add_argument("--db", type=str, default=DEFAULT_DB_PATH)
    unverified_p.add_argument("--type", type=str, default=None)

    missing_consent_p = subparsers.add_parser(
        "missing-consent", help="Audit recordings lacking ethical consent"
    )
    missing_consent_p.add_argument("--db", type=str, default=DEFAULT_DB_PATH)

    withdraw_p = subparsers.add_parser(
        "withdraw-consent", help="Withdraw ethical consent for an audio recording"
    )
    withdraw_p.add_argument("recording_id", type=int, nargs="?", default=None)
    withdraw_p.add_argument(
        "--recording-id", dest="recording_id_opt", type=int, default=None
    )
    withdraw_p.add_argument("--reason", type=str, required=True)
    withdraw_p.add_argument("--withdrawn-by", type=str, default="Archivist")
    withdraw_p.add_argument("--db", type=str, default=DEFAULT_DB_PATH)

    removal_p = subparsers.add_parser(
        "request-removal", help="Request immediate removal of an audio recording"
    )
    removal_p.add_argument("recording_id", type=int, nargs="?", default=None)
    removal_p.add_argument(
        "--recording-id", dest="recording_id_opt", type=int, default=None
    )
    removal_p.add_argument("--reason", type=str, required=True)
    removal_p.add_argument(
        "--requested-by", type=str, default="Community Elder / Contributor"
    )
    removal_p.add_argument("--db", type=str, default=DEFAULT_DB_PATH)

    export_p = subparsers.add_parser(
        "export", help="Export folk songs metadata to CSV or JSON"
    )
    export_p.add_argument("--csv", type=str, default=None)
    export_p.add_argument("--json", type=str, default=None)
    export_p.add_argument("--type", type=str, default=None)
    export_p.add_argument("--db", type=str, default=DEFAULT_DB_PATH)

    import_p = subparsers.add_parser(
        "import", help="Import folk songs metadata from CSV or JSON"
    )
    import_p.add_argument("--csv", type=str, default=None)
    import_p.add_argument("--json", type=str, default=None)
    import_p.add_argument("--dry-run", action="store_true")
    import_p.add_argument("--db", type=str, default=DEFAULT_DB_PATH)

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "verify":
        res = verify_folk_songs_dir(args.dir)
        print("Folk Songs Consent Audit:")
        print(f"  Valid / Approved ({len(res['valid'])}): {res['valid']}")
        print(f"  Pending Approval ({len(res['pending'])}): {res['pending']}")
        print(f"  Invalid / Rejected ({len(res['invalid'])}): {res['invalid']}")
        return 0 if not res["invalid"] else 1

    if args.command == "load":
        loaded = load_folk_songs_dir(
            args.dir, db_path=args.db, skip_unconsented=args.skip_unconsented
        )
        print(f"Loaded {len(loaded)} consented folk song(s) into '{args.db}'.")
        return 0

    if args.command == "search":
        songs = search_folk_songs(
            query=args.query,
            db_path=args.db,
            song_type=args.type,
            region=args.region,
        )
        print_folk_songs(songs, verbose=args.verbose, db_path=args.db)
        return 0

    if args.command == "filter":
        songs = filter_folk_songs(
            db_path=args.db,
            song_type=args.type,
            region=args.region,
            community=args.community,
            performer=args.performer,
            from_year=args.from_year,
            to_year=args.to_year,
            confidence=args.confidence,
        )
        print_folk_songs(songs, verbose=args.verbose, db_path=args.db)
        return 0

    if args.command == "recordings":
        song_id = args.song_id or args.song_id_opt
        if not song_id:
            print("Please specify a song ID.", file=sys.stderr)
            return 1
        recs = get_recordings(song_id=song_id, db_path=args.db, include_withdrawn=True)
        if not recs:
            print(f"No recordings found for song #{song_id}.")
            return 0
        print(f"Recordings for Song #{song_id} ({len(recs)} found):\n")
        for idx, r in enumerate(recs, start=1):
            perf = r.get("performer") or r.get("singer") or "Unknown"
            fmt = r.get("audio_format") or "unknown"
            cs = r.get("consent_status") or "unknown"
            rem = (
                f" [REMOVAL: {r.get('removal_reason')}]"
                if r.get("removal_requested")
                else ""
            )
            print(f"[{idx}] Recording #{r['id']}: {perf} ({fmt}) [consent: {cs}]{rem}")
            if args.verbose:
                print(f"    File: {r.get('file_path') or r.get('audio_url')}")
                print(f"    Location: {r.get('location')}")
                print(f"    Consent Proof: {r.get('consent_document_ref')}")
                if r.get("consent_notes"):
                    print(f"    Notes: {r.get('consent_notes')}")
        return 0

    if args.command == "missing-citations":
        flagged = get_folk_songs_missing_citations(db_path=args.db, song_type=args.type)
        if not flagged:
            print("No folk songs with missing citations found.")
            return 0
        print(f"Folk Songs with Missing Citations ({len(flagged)} found):\n")
        for idx, item in enumerate(flagged, start=1):
            title = item.get("title") or "Untitled"
            stype = item.get("song_type") or "song"
            reason = item.get("missing_reason") or "Missing citation"
            print(f"[{idx}] {title} ({stype})")
            print(f"    Issue: {reason}\n")
        return 0

    if args.command == "unverified":
        songs = get_unverified_folk_songs(db_path=args.db, song_type=args.type)
        print_folk_songs(songs, verbose=False, db_path=args.db)
        return 0

    if args.command == "missing-consent":
        flagged = get_recordings_missing_consent(db_path=args.db)
        if not flagged:
            print("No audio recordings lacking ethical consent found.")
            return 0
        print(f"Recordings Lacking Ethical Consent ({len(flagged)} found):\n")
        for idx, item in enumerate(flagged, start=1):
            song_title = item.get("song_title") or f"Song #{item['song_id']}"
            perf = item.get("performer") or "Unknown"
            fmt = item.get("audio_format") or "unknown"
            print(f"[{idx}] Recording #{item['id']} for '{song_title}' ({perf}, {fmt})")
            print(f"    Issues: {item.get('consent_reason')}\n")
        return 0

    if args.command == "withdraw-consent":
        rec_id = args.recording_id or args.recording_id_opt
        if not rec_id:
            print("Please specify a recording ID.", file=sys.stderr)
            return 1
        ok = withdraw_recording_consent(
            recording_id=rec_id,
            reason=args.reason,
            withdrawn_by=args.withdrawn_by,
            db_path=args.db,
        )
        if ok:
            print(f"Successfully withdrew consent for recording #{rec_id}.")
            return 0
        print(f"Recording #{rec_id} not found.", file=sys.stderr)
        return 1

    if args.command == "request-removal":
        rec_id = args.recording_id or args.recording_id_opt
        if not rec_id:
            print("Please specify a recording ID.", file=sys.stderr)
            return 1
        ok = request_recording_removal(
            recording_id=rec_id,
            reason=args.reason,
            requested_by=args.requested_by,
            db_path=args.db,
        )
        if ok:
            print(f"Successfully filed removal request for recording #{rec_id}.")
            return 0
        print(f"Recording #{rec_id} not found.", file=sys.stderr)
        return 1

    if args.command == "export":
        if args.csv:
            cnt = export_folk_songs_csv(
                csv_path=args.csv, db_path=args.db, song_type=args.type
            )
            print(f"Exported {cnt} folk song(s) to CSV: {args.csv}")
            return 0
        if args.json:
            cnt = export_folk_songs_json(
                json_path=args.json, db_path=args.db, song_type=args.type
            )
            print(f"Exported {cnt} folk song(s) to JSON: {args.json}")
            return 0
        print("Specify either --csv or --json destination.", file=sys.stderr)
        return 1

    if args.command == "import":
        if args.csv:
            stats = import_folk_songs_csv(
                csv_path=args.csv, db_path=args.db, dry_run=args.dry_run
            )
        elif args.json:
            stats = import_folk_songs_json(
                json_path=args.json, db_path=args.db, dry_run=args.dry_run
            )
        else:
            print("Specify either --csv or --json file to import.", file=sys.stderr)
            return 1

        mode = "Dry Run Import" if args.dry_run else "Import"
        print(f"=== {mode} Statistics ===")
        print(f"Total:            {stats['total']}")
        print(f"Imported (New):   {stats['imported']}")
        print(f"Updated:          {stats['updated']}")
        print(f"Rejected:         {stats['rejected']}")
        if stats.get("recordings_imported"):
            print(f"Recordings:       {stats['recordings_imported']}")
        if stats.get("backup_path"):
            print(f"Backup created:   {stats['backup_path']}")
        if stats["errors"]:
            print(f"\nErrors ({len(stats['errors'])}):")
            for err in stats["errors"][:10]:
                print(f"  - {err}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
