"""SQLite database layer for bhasha_lib.

💡 FILE INSIGHT & PURPOSE:
Core persistence engine managing the relational SQLite database (`data/lexicon.sqlite`).
Defines schemas for 8 tables (sources, words, occurrences, culture_items, timeline_events,
literature_items, folk_songs, song_recordings), transaction context manager `get_connection()`,
automated backups (`backup_db()`), and thread-safe CRUD operations with constraint validation.
"""

from __future__ import annotations

import sqlite3
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH: str = "data/lexicon.sqlite"
DEFAULT_TIMEOUT: float = 30.0

VALID_STATUSES: frozenset[str] = frozenset({"unverified", "community", "expert"})
VALID_ORIGINS: frozenset[str] = frozenset({"bodo", "loan", "unsure"})
VALID_DATE_PRECISIONS: frozenset[str] = frozenset(
    {"exact", "approximate", "range", "unknown"}
)
VALID_CONFIDENCE_LEVELS: frozenset[str] = frozenset(
    {"unverified", "needs_check", "community", "expert", "disputed", "verified"}
)
VALID_LITERARY_TYPES: frozenset[str] = frozenset(
    {
        "poem",
        "short_story",
        "novel",
        "play",
        "folk_tale",
        "essay",
        "collection",
        "other",
    }
)
VALID_SONG_TYPES: frozenset[str] = frozenset(
    {
        "traditional_folk_song",
        "traditional_folk",
        "work_song",
        "festival_song",
        "lullaby",
        "devotional_song",
        "devotional",
        "dance_song",
        "ritual_song",
        "ballad",
        "other",
    }
)
VALID_CONSENT_STATES: frozenset[str] = frozenset(
    {"unknown", "pending", "granted", "denied", "withdrawn"}
)
VALID_AUDIO_FORMATS: frozenset[str] = frozenset(
    {
        "mp3",
        "wav",
        "flac",
        "ogg",
        "aac",
        "m4a",
        "wma",
        "opus",
        "aiff",
        "unknown",
    }
)

INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_occurrences_word ON occurrences(word);
CREATE INDEX IF NOT EXISTS idx_occurrences_source ON occurrences(source_id);
CREATE INDEX IF NOT EXISTS idx_words_status ON words(status);
CREATE INDEX IF NOT EXISTS idx_words_freq ON words(freq DESC);
CREATE INDEX IF NOT EXISTS idx_culture_items_year ON culture_items(year_start);
CREATE INDEX IF NOT EXISTS idx_sources_title ON sources(title);
CREATE INDEX IF NOT EXISTS idx_culture_items_category ON culture_items(category);
CREATE INDEX IF NOT EXISTS idx_culture_items_confidence ON culture_items(confidence);
CREATE INDEX IF NOT EXISTS idx_literature_title ON literature_items(title);
CREATE INDEX IF NOT EXISTS idx_literature_author ON literature_items(author);
CREATE INDEX IF NOT EXISTS idx_literature_type ON literature_items(literary_type);
CREATE INDEX IF NOT EXISTS idx_literature_year ON literature_items(year);
CREATE INDEX IF NOT EXISTS idx_literature_confidence ON literature_items(confidence);
CREATE INDEX IF NOT EXISTS idx_literature_source ON literature_items(source_id);
CREATE INDEX IF NOT EXISTS idx_folk_songs_title ON folk_songs(title);
CREATE INDEX IF NOT EXISTS idx_folk_songs_type ON folk_songs(song_type);
CREATE INDEX IF NOT EXISTS idx_folk_songs_community ON folk_songs(community);
CREATE INDEX IF NOT EXISTS idx_folk_songs_region ON folk_songs(region);
CREATE INDEX IF NOT EXISTS idx_folk_songs_confidence ON folk_songs(confidence);
CREATE INDEX IF NOT EXISTS idx_folk_songs_source ON folk_songs(source_id);
CREATE INDEX IF NOT EXISTS idx_song_recordings_song ON song_recordings(song_id);
CREATE INDEX IF NOT EXISTS idx_recordings_consent ON song_recordings(consent_status);
CREATE INDEX IF NOT EXISTS idx_song_recordings_performer ON song_recordings(performer);
CREATE INDEX IF NOT EXISTS idx_song_recordings_source ON song_recordings(source_id);
"""

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    type TEXT,
    author TEXT,
    year INTEGER,
    license TEXT NOT NULL,
    contributor TEXT,
    url TEXT,
    file_path TEXT
);

CREATE TABLE IF NOT EXISTS words (
    word TEXT PRIMARY KEY,
    roman TEXT,
    meaning_hi TEXT,
    meaning_en TEXT,
    pos TEXT,
    tone TEXT,
    dialect TEXT,
    freq INTEGER DEFAULT 0,
    origin TEXT,
    status TEXT DEFAULT 'unverified',
    verified_by TEXT
);

CREATE TABLE IF NOT EXISTS occurrences (
    word TEXT,
    source_id INTEGER,
    line_no INTEGER,
    context TEXT,
    FOREIGN KEY (word) REFERENCES words(word),
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS culture_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT,
    title TEXT,
    description TEXT,
    region TEXT,
    related_words TEXT,
    source_id INTEGER,
    media_path TEXT,
    year_start INTEGER,
    year_end INTEGER,
    confidence TEXT DEFAULT 'needs_check',
    verified_on TEXT,
    date_precision TEXT DEFAULT 'exact',
    people TEXT,
    places TEXT,
    organizations TEXT,
    books TEXT,
    primary_sources TEXT,
    secondary_sources TEXT,
    source_url TEXT,
    license TEXT,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS literature_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    title_en TEXT,
    roman_title TEXT,
    literary_type TEXT NOT NULL,
    author TEXT,
    translator TEXT,
    editor TEXT,
    contributor TEXT,
    original_language TEXT DEFAULT 'brx',
    translation_languages TEXT,
    year INTEGER,
    year_end INTEGER,
    date_precision TEXT DEFAULT 'exact',
    book_title TEXT,
    publisher TEXT,
    edition TEXT,
    description TEXT,
    people TEXT,
    places TEXT,
    literary_movement TEXT,
    source_id INTEGER,
    primary_sources TEXT,
    secondary_sources TEXT,
    source_url TEXT,
    license TEXT DEFAULT 'own_words',
    confidence TEXT DEFAULT 'needs_check',
    verified_by TEXT,
    verified_on TEXT,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS folk_songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    title_en TEXT,
    roman_title TEXT,
    song_type TEXT NOT NULL DEFAULT 'traditional_folk_song',
    composer TEXT,
    lyricist TEXT,
    performer TEXT,
    singer TEXT,
    community TEXT,
    region TEXT,
    language TEXT DEFAULT 'brx',
    dialect TEXT,
    description TEXT,
    cultural_context TEXT,
    festivals TEXT,
    ceremonies TEXT,
    dances TEXT,
    instruments TEXT,
    places TEXT,
    year INTEGER,
    year_end INTEGER,
    date_precision TEXT DEFAULT 'unknown',
    source_id INTEGER,
    source_title TEXT,
    primary_sources TEXT,
    secondary_sources TEXT,
    source_url TEXT,
    license TEXT DEFAULT 'metadata_only',
    confidence TEXT DEFAULT 'needs_check',
    verified_by TEXT,
    verified_on TEXT,
    consent_status TEXT DEFAULT 'unknown',
    consent_document_ref TEXT,
    cultural_restrictions TEXT,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS song_recordings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id INTEGER NOT NULL,
    recording_title TEXT,
    performer TEXT,
    singer TEXT,
    musicians TEXT,
    recorder TEXT,
    recording_date TEXT,
    year INTEGER,
    date_precision TEXT DEFAULT 'unknown',
    location TEXT,
    duration INTEGER,
    audio_format TEXT DEFAULT 'unknown',
    sample_rate INTEGER,
    file_path TEXT,
    audio_url TEXT,
    source_id INTEGER,
    source_title TEXT,
    license TEXT DEFAULT 'all_rights_reserved',
    consent_status TEXT DEFAULT 'unknown',
    consent_recording TEXT DEFAULT 'unknown',
    consent_publication TEXT DEFAULT 'unknown',
    consent_attribution TEXT DEFAULT 'unknown',
    consent_transcription TEXT DEFAULT 'unknown',
    consent_redistribution TEXT DEFAULT 'unknown',
    consent_document_ref TEXT,
    consent_notes TEXT,
    removal_requested INTEGER DEFAULT 0,
    removal_reason TEXT,
    confidence TEXT DEFAULT 'needs_check',
    verified_by TEXT,
    verified_on TEXT,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (song_id) REFERENCES folk_songs(id) ON DELETE CASCADE,
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS review_batches (
    batch_name TEXT PRIMARY KEY,
    created_at TEXT,
    csv_path TEXT,
    words_count INTEGER,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS review_batch_words (
    batch_name TEXT,
    word TEXT
);

{INDEXES_SQL}
"""


def _clean_str(val: Any) -> str | None:
    """Normalize string using Unicode NFC and strip leading/trailing whitespace."""
    if val is None:
        return None
    cleaned = unicodedata.normalize("NFC", str(val).strip())
    return cleaned if cleaned else None


@contextmanager
def get_connection(
    db_path: str | Path = DEFAULT_DB_PATH,
    timeout: float = DEFAULT_TIMEOUT,
) -> Iterator[sqlite3.Connection]:
    """Provide a transactional database connection that closes automatically.

    Ensures parent directories exist when a file path is provided.
    Enables foreign key enforcement (PRAGMA foreign_keys = ON) and sets busy timeout.
    """
    if str(db_path) != ":memory:":
        path_obj = Path(db_path)
        if path_obj.parent and not path_obj.parent.exists():
            path_obj.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def backup_db(
    db_path: str | Path = DEFAULT_DB_PATH,
    backup_dir: str | Path | None = None,
) -> Path:
    """Create a consistent, timestamped backup copy of the SQLite database.

    Uses SQLite online backup API to ensure complete ACID consistency without locking.

    Args:
        db_path: Path to the source database.
        backup_dir: Optional destination directory (defaults to 'data/backups'
            or sibling directory of db_path).

    Returns:
        Path to the newly created backup file.
    """
    source_path = Path(db_path)
    if not source_path.is_file():
        raise FileNotFoundError(f"Database file not found: {source_path}")

    if backup_dir is not None:
        target_dir = Path(backup_dir)
    else:
        target_dir = source_path.parent / "backups"

    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    stem = source_path.stem
    backup_file = target_dir / f"{stem}_backup_{timestamp}.sqlite"

    with sqlite3.connect(str(source_path), timeout=DEFAULT_TIMEOUT) as src_conn:
        with sqlite3.connect(str(backup_file), timeout=DEFAULT_TIMEOUT) as dst_conn:
            src_conn.backup(dst_conn)

    return backup_file


def init_db(path: str | Path = DEFAULT_DB_PATH) -> Path:
    """Initialize database tables, apply migrations, and create indexes idempotently."""
    with get_connection(path) as conn:
        cursor = conn.cursor()
        cursor.executescript(SCHEMA)

        # Migration: add origin, status, verified_by to words table if missing
        cursor.execute("PRAGMA table_info(words)")
        existing_cols = {row["name"] for row in cursor.fetchall()}

        if "origin" not in existing_cols:
            cursor.execute("ALTER TABLE words ADD COLUMN origin TEXT")
        if "status" not in existing_cols:
            cursor.execute(
                "ALTER TABLE words ADD COLUMN status TEXT DEFAULT 'unverified'"
            )
        if "verified_by" not in existing_cols:
            cursor.execute("ALTER TABLE words ADD COLUMN verified_by TEXT")

        # Migration: add optional columns to sources table if missing
        cursor.execute("PRAGMA table_info(sources)")
        source_cols = {row["name"] for row in cursor.fetchall()}
        for col, col_type in (
            ("type", "TEXT"),
            ("author", "TEXT"),
            ("year", "INTEGER"),
            ("contributor", "TEXT"),
            ("url", "TEXT"),
            ("file_path", "TEXT"),
        ):
            if col not in source_cols:
                cursor.execute(f"ALTER TABLE sources ADD COLUMN {col} {col_type}")

        # Migration: add year_start, year_end, confidence to culture_items if missing
        cursor.execute("PRAGMA table_info(culture_items)")
        culture_cols = {row["name"] for row in cursor.fetchall()}

        if "year_start" not in culture_cols:
            cursor.execute("ALTER TABLE culture_items ADD COLUMN year_start INTEGER")
        if "year_end" not in culture_cols:
            cursor.execute("ALTER TABLE culture_items ADD COLUMN year_end INTEGER")
        if "confidence" not in culture_cols:
            cursor.execute(
                "ALTER TABLE culture_items "
                "ADD COLUMN confidence TEXT DEFAULT 'needs_check'"
            )
        if "verified_on" not in culture_cols:
            cursor.execute("ALTER TABLE culture_items ADD COLUMN verified_on TEXT")
        if "date_precision" not in culture_cols:
            cursor.execute(
                "ALTER TABLE culture_items "
                "ADD COLUMN date_precision TEXT DEFAULT 'exact'"
            )
        if "people" not in culture_cols:
            cursor.execute("ALTER TABLE culture_items ADD COLUMN people TEXT")
        if "places" not in culture_cols:
            cursor.execute("ALTER TABLE culture_items ADD COLUMN places TEXT")
        if "organizations" not in culture_cols:
            cursor.execute("ALTER TABLE culture_items ADD COLUMN organizations TEXT")
        if "books" not in culture_cols:
            cursor.execute("ALTER TABLE culture_items ADD COLUMN books TEXT")
        if "primary_sources" not in culture_cols:
            cursor.execute("ALTER TABLE culture_items ADD COLUMN primary_sources TEXT")
        if "secondary_sources" not in culture_cols:
            cursor.execute(
                "ALTER TABLE culture_items ADD COLUMN secondary_sources TEXT"
            )
        if "source_url" not in culture_cols:
            cursor.execute("ALTER TABLE culture_items ADD COLUMN source_url TEXT")
        if "license" not in culture_cols:
            cursor.execute("ALTER TABLE culture_items ADD COLUMN license TEXT")
        if "created_at" not in culture_cols:
            cursor.execute("ALTER TABLE culture_items ADD COLUMN created_at TEXT")
        if "updated_at" not in culture_cols:
            cursor.execute("ALTER TABLE culture_items ADD COLUMN updated_at TEXT")

        # Safe migration: set confidence = 'needs_check'
        # for rows where confidence IS NULL
        cursor.execute(
            "UPDATE culture_items SET confidence = 'needs_check' "
            "WHERE confidence IS NULL"
        )
        cursor.execute(
            "UPDATE culture_items SET date_precision = 'exact' "
            "WHERE date_precision IS NULL"
        )

        # Migration: ensure all columns exist in literature_items if table
        # already existed
        cursor.execute("PRAGMA table_info(literature_items)")
        lit_cols = {row["name"] for row in cursor.fetchall()}
        if lit_cols:
            lit_col_defs = [
                ("title_en", "TEXT", None),
                ("roman_title", "TEXT", None),
                ("literary_type", "TEXT", "'other'"),
                ("author", "TEXT", None),
                ("translator", "TEXT", None),
                ("editor", "TEXT", None),
                ("contributor", "TEXT", None),
                ("original_language", "TEXT", "'brx'"),
                ("translation_languages", "TEXT", None),
                ("year", "INTEGER", None),
                ("year_end", "INTEGER", None),
                ("date_precision", "TEXT", "'exact'"),
                ("book_title", "TEXT", None),
                ("publisher", "TEXT", None),
                ("edition", "TEXT", None),
                ("description", "TEXT", None),
                ("people", "TEXT", None),
                ("places", "TEXT", None),
                ("literary_movement", "TEXT", None),
                ("source_id", "INTEGER", None),
                ("primary_sources", "TEXT", None),
                ("secondary_sources", "TEXT", None),
                ("source_url", "TEXT", None),
                ("license", "TEXT", "'own_words'"),
                ("confidence", "TEXT", "'needs_check'"),
                ("verified_by", "TEXT", None),
                ("verified_on", "TEXT", None),
                ("created_at", "TEXT", None),
                ("updated_at", "TEXT", None),
            ]
            for col, ctype, default in lit_col_defs:
                if col not in lit_cols:
                    def_clause = f" DEFAULT {default}" if default else ""
                    cursor.execute(
                        f"ALTER TABLE literature_items ADD COLUMN "
                        f"{col} {ctype}{def_clause}"
                    )

        cursor.execute(
            "UPDATE literature_items SET confidence = 'needs_check' "
            "WHERE confidence IS NULL"
        )
        cursor.execute(
            "UPDATE literature_items SET date_precision = 'exact' "
            "WHERE date_precision IS NULL"
        )

        # Migration: ensure all columns exist in folk_songs if table already existed
        cursor.execute("PRAGMA table_info(folk_songs)")
        fs_cols = {row["name"] for row in cursor.fetchall()}
        if fs_cols:
            fs_col_defs = [
                ("title_en", "TEXT", None),
                ("roman_title", "TEXT", None),
                ("song_type", "TEXT", "'traditional_folk_song'"),
                ("composer", "TEXT", None),
                ("lyricist", "TEXT", None),
                ("performer", "TEXT", None),
                ("singer", "TEXT", None),
                ("community", "TEXT", None),
                ("region", "TEXT", None),
                ("language", "TEXT", "'brx'"),
                ("dialect", "TEXT", None),
                ("description", "TEXT", None),
                ("cultural_context", "TEXT", None),
                ("festivals", "TEXT", None),
                ("ceremonies", "TEXT", None),
                ("dances", "TEXT", None),
                ("instruments", "TEXT", None),
                ("places", "TEXT", None),
                ("year", "INTEGER", None),
                ("year_end", "INTEGER", None),
                ("date_precision", "TEXT", "'unknown'"),
                ("source_id", "INTEGER", None),
                ("source_title", "TEXT", None),
                ("primary_sources", "TEXT", None),
                ("secondary_sources", "TEXT", None),
                ("source_url", "TEXT", None),
                ("license", "TEXT", "'metadata_only'"),
                ("confidence", "TEXT", "'needs_check'"),
                ("verified_by", "TEXT", None),
                ("verified_on", "TEXT", None),
                ("consent_status", "TEXT", "'unknown'"),
                ("consent_document_ref", "TEXT", None),
                ("cultural_restrictions", "TEXT", None),
                ("created_at", "TEXT", None),
                ("updated_at", "TEXT", None),
            ]
            for col, ctype, default in fs_col_defs:
                if col not in fs_cols:
                    def_clause = f" DEFAULT {default}" if default else ""
                    cursor.execute(
                        f"ALTER TABLE folk_songs ADD COLUMN "
                        f"{col} {ctype}{def_clause}"
                    )

        cursor.execute(
            "UPDATE folk_songs SET confidence = 'needs_check' "
            "WHERE confidence IS NULL"
        )
        cursor.execute(
            "UPDATE folk_songs SET date_precision = 'unknown' "
            "WHERE date_precision IS NULL"
        )

        # Migration: ensure all columns exist in song_recordings if table existed
        cursor.execute("PRAGMA table_info(song_recordings)")
        rec_cols = {row["name"] for row in cursor.fetchall()}
        if rec_cols:
            rec_col_defs = [
                ("recording_title", "TEXT", None),
                ("performer", "TEXT", None),
                ("singer", "TEXT", None),
                ("musicians", "TEXT", None),
                ("recorder", "TEXT", None),
                ("recording_date", "TEXT", None),
                ("year", "INTEGER", None),
                ("date_precision", "TEXT", "'unknown'"),
                ("location", "TEXT", None),
                ("duration", "INTEGER", None),
                ("audio_format", "TEXT", "'unknown'"),
                ("sample_rate", "INTEGER", None),
                ("file_path", "TEXT", None),
                ("audio_url", "TEXT", None),
                ("source_id", "INTEGER", None),
                ("source_title", "TEXT", None),
                ("license", "TEXT", "'all_rights_reserved'"),
                ("consent_status", "TEXT", "'unknown'"),
                ("consent_recording", "TEXT", "'unknown'"),
                ("consent_publication", "TEXT", "'unknown'"),
                ("consent_attribution", "TEXT", "'unknown'"),
                ("consent_transcription", "TEXT", "'unknown'"),
                ("consent_redistribution", "TEXT", "'unknown'"),
                ("consent_document_ref", "TEXT", None),
                ("consent_notes", "TEXT", None),
                ("removal_requested", "INTEGER", "0"),
                ("removal_reason", "TEXT", None),
                ("confidence", "TEXT", "'needs_check'"),
                ("verified_by", "TEXT", None),
                ("verified_on", "TEXT", None),
                ("created_at", "TEXT", None),
                ("updated_at", "TEXT", None),
            ]
            for col, ctype, default in rec_col_defs:
                if col not in rec_cols:
                    def_clause = f" DEFAULT {default}" if default else ""
                    cursor.execute(
                        f"ALTER TABLE song_recordings ADD COLUMN "
                        f"{col} {ctype}{def_clause}"
                    )

        cursor.execute(
            "UPDATE song_recordings SET confidence = 'needs_check' "
            "WHERE confidence IS NULL"
        )
        cursor.execute(
            "UPDATE song_recordings SET consent_status = 'unknown' "
            "WHERE consent_status IS NULL"
        )

        # Idempotent index creation
        cursor.executescript(INDEXES_SQL)

    return Path(path)


def add_source(
    title: str | None = None,
    type: str | None = None,
    author: str | None = None,
    year: int | None = None,
    license: str | None = None,
    contributor: str | None = None,
    url: str | None = None,
    file_path: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """Insert a source record.

    Raises:
        ValueError: If license is None or an empty string.
    """
    if license is None or not str(license).strip():
        raise ValueError("The 'license' field is required and cannot be empty.")

    clean_title = _clean_str(title)
    clean_type = _clean_str(type)
    clean_author = _clean_str(author)
    clean_license = str(license).strip()
    clean_contributor = _clean_str(contributor)
    clean_url = _clean_str(url)
    clean_file_path = _clean_str(file_path)

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sources (
                title, type, author, year, license, contributor, url, file_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clean_title,
                clean_type,
                clean_author,
                year,
                clean_license,
                clean_contributor,
                clean_url,
                clean_file_path,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("Failed to insert source record.")
        return int(cursor.lastrowid)


def add_word(
    word: str,
    roman: str | None = None,
    meaning_hi: str | None = None,
    meaning_en: str | None = None,
    pos: str | None = None,
    tone: str | None = None,
    dialect: str | None = None,
    origin: str | None = None,
    status: str = "unverified",
    verified_by: str | None = None,
    freq: int = 1,
    db_path: str | Path = DEFAULT_DB_PATH,
    raise_on_duplicate: bool = False,
) -> None:
    """Insert or update a word record with robust validation.

    Normalizes the word to Unicode NFC format.
    Validates word, status, origin, and metadata.
    If the word already exists, increments its freq count
    unless raise_on_duplicate is True.
    """
    if word is None or not str(word).strip():
        raise ValueError("Word cannot be empty or whitespace-only.")

    normalized_word = unicodedata.normalize("NFC", str(word).strip())
    if not normalized_word:
        raise ValueError("Word cannot be empty after Unicode NFC normalization.")

    clean_status = str(status).strip().lower() if status is not None else "unverified"
    if clean_status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Must be one of: {sorted(VALID_STATUSES)}"
        )

    clean_origin = (
        str(origin).strip().lower()
        if origin is not None and str(origin).strip()
        else None
    )
    if clean_origin is not None and clean_origin not in VALID_ORIGINS:
        raise ValueError(
            f"Invalid origin '{origin}'. Must be one of: {sorted(VALID_ORIGINS)}"
        )

    clean_roman = _clean_str(roman)
    clean_meaning_hi = _clean_str(meaning_hi)
    clean_meaning_en = _clean_str(meaning_en)
    clean_pos = _clean_str(pos)
    clean_tone = _clean_str(tone)
    clean_dialect = _clean_str(dialect)
    clean_verified_by = _clean_str(verified_by)
    freq_increment = freq if freq > 0 else 1

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if raise_on_duplicate:
            cursor.execute("SELECT 1 FROM words WHERE word = ?", (normalized_word,))
            if cursor.fetchone() is not None:
                raise ValueError(
                    f"Word '{normalized_word}' already exists in database."
                )

        cursor.execute(
            """
            INSERT INTO words (
                word, roman, meaning_hi, meaning_en, pos, tone, dialect,
                origin, status, verified_by, freq
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(word) DO UPDATE SET
                freq = words.freq + excluded.freq,
                roman = COALESCE(excluded.roman, words.roman),
                meaning_hi = COALESCE(excluded.meaning_hi, words.meaning_hi),
                meaning_en = COALESCE(excluded.meaning_en, words.meaning_en),
                pos = COALESCE(excluded.pos, words.pos),
                tone = COALESCE(excluded.tone, words.tone),
                dialect = COALESCE(excluded.dialect, words.dialect),
                origin = COALESCE(excluded.origin, words.origin),
                status = COALESCE(excluded.status, words.status),
                verified_by = COALESCE(excluded.verified_by, words.verified_by)
            """,
            (
                normalized_word,
                clean_roman,
                clean_meaning_hi,
                clean_meaning_en,
                clean_pos,
                clean_tone,
                clean_dialect,
                clean_origin,
                clean_status,
                clean_verified_by,
                freq_increment,
            ),
        )


def update_word_meaning(
    word: str,
    meaning_hi: str | None = None,
    meaning_en: str | None = None,
    roman: str | None = None,
    pos: str | None = None,
    tone: str | None = None,
    dialect: str | None = None,
    origin: str | None = None,
    status: str | None = None,
    verified_by: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> bool:
    """Update meaning, POS, tone, origin, status, or verified_by of an existing word.

    Normalizes word and text metadata using Unicode NFC.
    Validates status and origin if provided.
    Does not modify the word's frequency counter.

    Returns:
        True if the word was found and updated, False otherwise.
    """
    if word is None or not str(word).strip():
        raise ValueError("Word cannot be empty or whitespace-only.")

    normalized_word = unicodedata.normalize("NFC", str(word).strip())

    clean_status = (
        str(status).strip().lower()
        if status is not None and str(status).strip()
        else None
    )
    if clean_status is not None and clean_status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Must be one of: {sorted(VALID_STATUSES)}"
        )

    clean_origin = (
        str(origin).strip().lower()
        if origin is not None and str(origin).strip()
        else None
    )
    if clean_origin is not None and clean_origin not in VALID_ORIGINS:
        raise ValueError(
            f"Invalid origin '{origin}'. Must be one of: {sorted(VALID_ORIGINS)}"
        )

    clean_hi = _clean_str(meaning_hi)
    clean_en = _clean_str(meaning_en)
    clean_roman = _clean_str(roman)
    clean_pos = _clean_str(pos)
    clean_tone = _clean_str(tone)
    clean_dialect = _clean_str(dialect)
    clean_verified_by = _clean_str(verified_by)

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE words SET
                meaning_hi = COALESCE(?, meaning_hi),
                meaning_en = COALESCE(?, meaning_en),
                roman = COALESCE(?, roman),
                pos = COALESCE(?, pos),
                tone = COALESCE(?, tone),
                dialect = COALESCE(?, dialect),
                origin = COALESCE(?, origin),
                status = COALESCE(?, status),
                verified_by = COALESCE(?, verified_by)
            WHERE word = ?
            """,
            (
                clean_hi,
                clean_en,
                clean_roman,
                clean_pos,
                clean_tone,
                clean_dialect,
                clean_origin,
                clean_status,
                clean_verified_by,
                normalized_word,
            ),
        )
        return cursor.rowcount > 0


def add_occurrence(
    word: str,
    source_id: int | None = None,
    line_no: int | None = None,
    context: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    """Insert a word occurrence record.

    Normalizes the word to Unicode NFC format.
    Enforces foreign key relationships (word must exist in words table;
    source_id if provided must exist in sources table).
    """
    if word is None or not str(word).strip():
        raise ValueError("Word cannot be empty or whitespace-only.")

    normalized_word = unicodedata.normalize("NFC", str(word).strip())
    clean_context = _clean_str(context)

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO occurrences (word, source_id, line_no, context)
            VALUES (?, ?, ?, ?)
            """,
            (normalized_word, source_id, line_no, clean_context),
        )


def _format_list_or_str(val: Any) -> str | None:
    """Format string or list of strings into a normalized comma-separated string."""
    if val is None:
        return None
    if isinstance(val, (list, tuple, set)):
        items = [_clean_str(item) for item in val if _clean_str(item)]
        return ", ".join(items) if items else None
    return _clean_str(val)


def add_culture_item(
    category: str | None = None,
    title: str | None = None,
    description: str | None = None,
    region: str | None = None,
    related_words: str | None = None,
    source_id: int | None = None,
    media_path: str | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    confidence: str | None = None,
    verified_on: str | None = None,
    date_precision: str | None = None,
    people: str | list[str] | None = None,
    places: str | list[str] | None = None,
    organizations: str | list[str] | None = None,
    books: str | list[str] | None = None,
    primary_sources: str | list[str] | None = None,
    secondary_sources: str | list[str] | None = None,
    source_url: str | None = None,
    license: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """Insert a cultural or historical metadata item record."""
    clean_category = _clean_str(category)
    clean_title = _clean_str(title)
    clean_desc = _clean_str(description)
    clean_region = _clean_str(region)
    clean_related = _format_list_or_str(related_words)
    clean_media = _clean_str(media_path)
    clean_confidence = _clean_str(confidence) or "needs_check"
    clean_verified_on = _clean_str(verified_on)

    clean_precision = _clean_str(date_precision) or (
        "unknown"
        if year_start is None
        else "range"
        if (year_end is not None and year_end != year_start)
        else "exact"
    )
    clean_people = _format_list_or_str(people)
    clean_places = _format_list_or_str(places)
    clean_orgs = _format_list_or_str(organizations)
    clean_books = _format_list_or_str(books)
    clean_primary = _format_list_or_str(primary_sources)
    clean_secondary = _format_list_or_str(secondary_sources)
    clean_url = _clean_str(source_url)
    clean_license = _clean_str(license)
    now_iso = datetime.now(UTC).isoformat()
    clean_created = _clean_str(created_at) or now_iso
    clean_updated = _clean_str(updated_at) or clean_created

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clean_category,
                clean_title,
                clean_desc,
                clean_region,
                clean_related,
                source_id,
                clean_media,
                year_start,
                year_end,
                clean_confidence,
                clean_verified_on,
                clean_precision,
                clean_people,
                clean_places,
                clean_orgs,
                clean_books,
                clean_primary,
                clean_secondary,
                clean_url,
                clean_license,
                clean_created,
                clean_updated,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("Failed to insert culture item.")
        return int(cursor.lastrowid)


def search_word(
    word: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any] | None:
    """Search for a word by its NFC-normalized string.

    Returns:
        A dictionary representation of the word row, or None if not found.
    """
    if word is None or not str(word).strip():
        return None

    normalized_word = unicodedata.normalize("NFC", str(word).strip())

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                word, roman, meaning_hi, meaning_en, pos, tone, dialect,
                freq, origin, status, verified_by
            FROM words
            WHERE word = ?
            """,
            (normalized_word,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)


def add_literature_item(
    title: str,
    literary_type: str,
    title_en: str | None = None,
    roman_title: str | None = None,
    author: str | None = None,
    translator: str | None = None,
    editor: str | None = None,
    contributor: str | None = None,
    original_language: str | None = "brx",
    translation_languages: str | list[str] | None = None,
    year: int | None = None,
    year_end: int | None = None,
    date_precision: str | None = None,
    book_title: str | None = None,
    publisher: str | None = None,
    edition: str | None = None,
    description: str | None = None,
    people: str | list[str] | None = None,
    places: str | list[str] | None = None,
    literary_movement: str | None = None,
    source_id: int | None = None,
    primary_sources: str | list[str] | None = None,
    secondary_sources: str | list[str] | None = None,
    source_url: str | None = None,
    license: str | None = "own_words",
    confidence: str | None = "needs_check",
    verified_by: str | None = None,
    verified_on: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """Insert a literature item record into literature_items table.

    Normalizes strings using Unicode NFC.
    Enforces foreign key relationships (source_id must exist in sources table).

    Returns:
        The integer primary key (id) of the inserted literature item.
    """
    clean_title = _clean_str(title)
    if not clean_title:
        raise ValueError("The 'title' field is required and cannot be empty.")

    clean_type = str(literary_type).strip().lower() if literary_type else ""
    if clean_type not in VALID_LITERARY_TYPES:
        raise ValueError(
            f"Invalid literary_type '{literary_type}'. Must be one of: "
            f"{sorted(VALID_LITERARY_TYPES)}"
        )

    clean_prec = _clean_str(date_precision)
    if clean_prec is not None:
        if clean_prec not in VALID_DATE_PRECISIONS:
            raise ValueError(
                f"Invalid date_precision '{date_precision}'. Must be one of: "
                f"{sorted(VALID_DATE_PRECISIONS)}"
            )
    else:
        if year is None:
            clean_prec = "unknown"
        elif year_end is not None and year_end != year:
            clean_prec = "range"
        else:
            clean_prec = "exact"

    clean_conf = _clean_str(confidence) or "needs_check"
    if clean_conf not in VALID_CONFIDENCE_LEVELS:
        raise ValueError(
            f"Invalid confidence '{confidence}'. Must be one of: "
            f"{sorted(VALID_CONFIDENCE_LEVELS)}"
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
    clean_verified_by = _clean_str(verified_by)
    clean_verified_on = _clean_str(verified_on)

    now_iso = datetime.now(UTC).isoformat()
    clean_created = _clean_str(created_at) or now_iso
    clean_updated = _clean_str(updated_at) or clean_created

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO literature_items (
                title,
                title_en,
                roman_title,
                literary_type,
                author,
                translator,
                editor,
                contributor,
                original_language,
                translation_languages,
                year,
                year_end,
                date_precision,
                book_title,
                publisher,
                edition,
                description,
                people,
                places,
                literary_movement,
                source_id,
                primary_sources,
                secondary_sources,
                source_url,
                license,
                confidence,
                verified_by,
                verified_on,
                created_at,
                updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                clean_title,
                clean_title_en,
                clean_roman_title,
                clean_type,
                clean_author,
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
                source_id,
                clean_primary,
                clean_secondary,
                clean_url,
                clean_license,
                clean_conf,
                clean_verified_by,
                clean_verified_on,
                clean_created,
                clean_updated,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("Failed to insert literature item.")
        return int(cursor.lastrowid)


def add_folk_song_item(
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
    confidence: str | None = "needs_check",
    verified_by: str | None = None,
    verified_on: str | None = None,
    consent_status: str | None = "unknown",
    consent_document_ref: str | None = None,
    cultural_restrictions: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
    song_id: int | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """Insert a folk song record into folk_songs table.

    Normalizes text strings using Unicode NFC.
    Enforces foreign key relationships (source_id must exist in sources table).

    Returns:
        The integer primary key (id) of the inserted song item.
    """
    clean_title = _clean_str(title)
    if not clean_title:
        raise ValueError("The 'title' field is required and cannot be empty.")

    clean_type = (
        str(song_type).strip().lower() if song_type else "traditional_folk_song"
    )
    if clean_type == "folk_song":
        clean_type = "traditional_folk_song"
    if clean_type not in VALID_SONG_TYPES:
        raise ValueError(
            f"Invalid song_type '{song_type}'. Must be one of: "
            f"{sorted(VALID_SONG_TYPES)}"
        )

    clean_prec = _clean_str(date_precision)
    if clean_prec is not None:
        if clean_prec not in VALID_DATE_PRECISIONS:
            raise ValueError(
                f"Invalid date_precision '{date_precision}'. Must be one of: "
                f"{sorted(VALID_DATE_PRECISIONS)}"
            )
    else:
        clean_prec = "unknown" if year is None else "exact"

    clean_conf = _clean_str(confidence) or "needs_check"
    if clean_conf not in VALID_CONFIDENCE_LEVELS:
        raise ValueError(
            f"Invalid confidence '{confidence}'. Must be one of: "
            f"{sorted(VALID_CONFIDENCE_LEVELS)}"
        )

    clean_cs = _clean_str(consent_status) or "unknown"
    if clean_cs not in VALID_CONSENT_STATES:
        raise ValueError(
            f"Invalid consent_status '{consent_status}'. Must be one of: "
            f"{sorted(VALID_CONSENT_STATES)}"
        )

    clean_title_en = _clean_str(title_en)
    clean_roman_title = _clean_str(roman_title)
    clean_composer = _clean_str(composer)
    clean_lyricist = _clean_str(lyricist)
    clean_performer = _clean_str(performer)
    clean_singer = _clean_str(singer)
    clean_community = _clean_str(community)
    clean_region = _clean_str(region)
    clean_lang = _clean_str(language) or "brx"
    clean_dialect = _clean_dialect = _clean_str(dialect)
    clean_desc = _clean_str(description)
    clean_context = _clean_str(cultural_context)
    clean_festivals = _format_list_or_str(festivals)
    clean_ceremonies = _format_list_or_str(ceremonies)
    clean_dances = _format_list_or_str(dances)
    clean_instruments = _format_list_or_str(instruments)
    clean_places = _format_list_or_str(places)
    clean_src_title = _clean_str(source_title)
    clean_primary = _format_list_or_str(primary_sources)
    clean_secondary = _format_list_or_str(secondary_sources)
    clean_url = _clean_str(source_url)
    clean_license = _clean_str(license) or "metadata_only"
    clean_vb = _clean_str(verified_by)
    clean_vo = _clean_str(verified_on)
    clean_doc_ref = _clean_str(consent_document_ref)
    clean_restrictions = _clean_str(cultural_restrictions)

    now_iso = datetime.now(UTC).isoformat()
    clean_created = _clean_str(created_at) or now_iso
    clean_updated = _clean_str(updated_at) or clean_created

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if song_id is not None:
            cursor.execute(
                """
                INSERT INTO folk_songs (
                    id, title, title_en, roman_title, song_type, composer, lyricist,
                    performer, singer, community, region, language, dialect,
                    description, cultural_context, festivals, ceremonies, dances,
                    instruments, places, year, year_end, date_precision, source_id,
                    source_title, primary_sources, secondary_sources, source_url,
                    license, confidence, verified_by, verified_on, consent_status,
                    consent_document_ref, cultural_restrictions, created_at, updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    int(song_id),
                    clean_title,
                    clean_title_en,
                    clean_roman_title,
                    clean_type,
                    clean_composer,
                    clean_lyricist,
                    clean_performer,
                    clean_singer,
                    clean_community,
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
                    source_id,
                    clean_src_title,
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
                    clean_created,
                    clean_updated,
                ),
            )
            return int(song_id)
        cursor.execute(
            """
            INSERT INTO folk_songs (
                title,
                title_en,
                roman_title,
                song_type,
                composer,
                lyricist,
                performer,
                singer,
                community,
                region,
                language,
                dialect,
                description,
                cultural_context,
                festivals,
                ceremonies,
                dances,
                instruments,
                places,
                year,
                year_end,
                date_precision,
                source_id,
                source_title,
                primary_sources,
                secondary_sources,
                source_url,
                license,
                confidence,
                verified_by,
                verified_on,
                consent_status,
                consent_document_ref,
                cultural_restrictions,
                created_at,
                updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?
            )
            """,
            (
                clean_title,
                clean_title_en,
                clean_roman_title,
                clean_type,
                clean_composer,
                clean_lyricist,
                clean_performer,
                clean_singer,
                clean_community,
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
                source_id,
                clean_src_title,
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
                clean_created,
                clean_updated,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("Failed to insert folk song item.")
        return int(cursor.lastrowid)


def add_song_recording_item(
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
    audio_format: str | None = "unknown",
    sample_rate: int | None = None,
    file_path: str | None = None,
    audio_url: str | None = None,
    source_id: int | None = None,
    source_title: str | None = None,
    license: str | None = "all_rights_reserved",
    consent_status: str | None = "unknown",
    consent_recording: str | None = "unknown",
    consent_publication: str | None = "unknown",
    consent_attribution: str | None = "unknown",
    consent_transcription: str | None = "unknown",
    consent_redistribution: str | None = "unknown",
    consent_document_ref: str | None = None,
    consent_notes: str | None = None,
    removal_requested: int | bool = 0,
    removal_reason: str | None = None,
    confidence: str | None = "needs_check",
    verified_by: str | None = None,
    verified_on: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
    recording_id: int | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """Insert a song recording record into song_recordings table.

    Normalizes text strings using Unicode NFC.
    Enforces foreign key relationships (song_id must exist in folk_songs table;
    source_id must exist in sources table if provided).

    Returns:
        The integer primary key (id) of the inserted recording item.
    """
    clean_title = _clean_str(recording_title)
    clean_performer = _clean_str(performer)
    clean_singer = _clean_str(singer)
    clean_musicians = _format_list_or_str(musicians)
    clean_recorder = _clean_str(recorder)
    clean_rec_date = _clean_str(recording_date)
    clean_location = _clean_str(location)
    clean_fmt = str(audio_format).strip().lower() if audio_format else "unknown"
    if clean_fmt not in VALID_AUDIO_FORMATS:
        clean_fmt = "unknown"

    clean_prec = _clean_str(date_precision) or (
        "unknown" if year is None else "exact"
    )
    clean_src_title = _clean_str(source_title)
    clean_license = _clean_str(license) or "all_rights_reserved"

    clean_cs = _clean_str(consent_status) or "unknown"
    if clean_cs not in VALID_CONSENT_STATES:
        raise ValueError(
            f"Invalid consent_status '{consent_status}'. Must be one of: "
            f"{sorted(VALID_CONSENT_STATES)}"
        )

    clean_rec_consent = _clean_str(consent_recording) or "unknown"
    clean_pub_consent = _clean_str(consent_publication) or "unknown"
    clean_attr_consent = _clean_str(consent_attribution) or "unknown"
    clean_tran_consent = _clean_str(consent_transcription) or "unknown"
    clean_redist_consent = _clean_str(consent_redistribution) or "unknown"
    clean_doc_ref = _clean_str(consent_document_ref)
    clean_notes = _clean_str(consent_notes)
    clean_removal_reason = _clean_str(removal_reason)
    clean_removal_flag = 1 if removal_requested else 0

    clean_conf = _clean_str(confidence) or "needs_check"
    clean_vb = _clean_str(verified_by)
    clean_vo = _clean_str(verified_on)

    now_iso = datetime.now(UTC).isoformat()
    clean_created = _clean_str(created_at) or now_iso
    clean_updated = _clean_str(updated_at) or clean_created

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if recording_id is not None:
            cursor.execute(
                """
                INSERT INTO song_recordings (
                    id,
                    song_id,
                    recording_title,
                    performer,
                    singer,
                    musicians,
                    recorder,
                    recording_date,
                    year,
                    date_precision,
                    location,
                    duration,
                    audio_format,
                    sample_rate,
                    file_path,
                    audio_url,
                    source_id,
                    source_title,
                    license,
                    consent_status,
                    consent_recording,
                    consent_publication,
                    consent_attribution,
                    consent_transcription,
                    consent_redistribution,
                    consent_document_ref,
                    consent_notes,
                    removal_requested,
                    removal_reason,
                    confidence,
                    verified_by,
                    verified_on,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?
                )
                """,
                (
                    int(recording_id),
                    int(song_id),
                    clean_title,
                    clean_performer,
                    clean_singer,
                    clean_musicians,
                    clean_recorder,
                    clean_rec_date,
                    year,
                    clean_prec,
                    clean_location,
                    duration,
                    clean_fmt,
                    sample_rate,
                    _clean_str(file_path),
                    _clean_str(audio_url),
                    source_id,
                    clean_src_title,
                    clean_license,
                    clean_cs,
                    clean_rec_consent,
                    clean_pub_consent,
                    clean_attr_consent,
                    clean_tran_consent,
                    clean_redist_consent,
                    clean_doc_ref,
                    clean_notes,
                    clean_removal_flag,
                    clean_removal_reason,
                    clean_conf,
                    clean_vb,
                    clean_vo,
                    clean_created,
                    clean_updated,
                ),
            )
            return int(recording_id)
        cursor.execute(
            """
            INSERT INTO song_recordings (
                song_id,
                recording_title,
                performer,
                singer,
                musicians,
                recorder,
                recording_date,
                year,
                date_precision,
                location,
                duration,
                audio_format,
                sample_rate,
                file_path,
                audio_url,
                source_id,
                source_title,
                license,
                consent_status,
                consent_recording,
                consent_publication,
                consent_attribution,
                consent_transcription,
                consent_redistribution,
                consent_document_ref,
                consent_notes,
                removal_requested,
                removal_reason,
                confidence,
                verified_by,
                verified_on,
                created_at,
                updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?
            )
            """,
            (
                int(song_id),
                clean_title,
                clean_performer,
                clean_singer,
                clean_musicians,
                clean_recorder,
                clean_rec_date,
                year,
                clean_prec,
                clean_location,
                duration,
                clean_fmt,
                sample_rate,
                _clean_str(file_path),
                _clean_str(audio_url),
                source_id,
                clean_src_title,
                clean_license,
                clean_cs,
                clean_rec_consent,
                clean_pub_consent,
                clean_attr_consent,
                clean_tran_consent,
                clean_redist_consent,
                clean_doc_ref,
                clean_notes,
                clean_removal_flag,
                clean_removal_reason,
                clean_conf,
                clean_vb,
                clean_vo,
                clean_created,
                clean_updated,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("Failed to insert song recording.")
        return int(cursor.lastrowid)


