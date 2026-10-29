"""Tests for Bodo literature, poems, stories, and author metadata module."""

from __future__ import annotations

import csv
import datetime
import json
import sqlite3
import unicodedata
from pathlib import Path

import pytest

from bhasha_lib import (
    VALID_LITERARY_TYPES,
    add_literary_record,
    add_literature_item,
    add_source,
    export_literature_csv,
    export_literature_json,
    filter_literature,
    format_literature_item,
    get_literary_by_author,
    get_literary_record,
    get_literature_by_author,
    get_literature_missing_citations,
    get_unverified_literature,
    import_literature_csv,
    import_literature_json,
    init_db,
    search_literature,
    validate_literary_record,
)
from bhasha_lib.db import get_connection
from bhasha_lib.literature import main


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    """Create an empty, initialized test database in a temporary directory."""
    db_file = tmp_path / "test_literature.sqlite"
    init_db(db_file)
    return db_file


def test_add_literature_item_and_valid_types(test_db: Path):
    """Verify add_literature_item direct database insertion and valid types."""
    assert "poem" in VALID_LITERARY_TYPES
    assert "short_story" in VALID_LITERARY_TYPES
    assert "novel" in VALID_LITERARY_TYPES
    assert "play" in VALID_LITERARY_TYPES
    assert "folk_tale" in VALID_LITERARY_TYPES
    assert "essay" in VALID_LITERARY_TYPES
    assert "collection" in VALID_LITERARY_TYPES
    assert "other" in VALID_LITERARY_TYPES

    item_id = add_literature_item(
        title="Direct Item",
        literary_type="essay",
        year=1960,
        db_path=test_db,
    )
    rec = get_literary_record(item_id, db_path=test_db)
    assert rec is not None
    assert rec["title"] == "Direct Item"
    assert rec["literary_type"] == "essay"


def test_validate_literary_record_rules():
    """Verify schema and cultural validation rules for literary records."""
    # Valid record
    valid_payload = {
        "title": "हाबिला खावनाय",
        "literary_type": "short_story",
        "year": 1919,
        "date_precision": "exact",
        "confidence": "needs_check",
    }
    assert validate_literary_record(valid_payload) == []

    # Missing title
    res = validate_literary_record({"literary_type": "poem"})
    assert any("title" in err.lower() for err in res)

    # Missing or invalid literary_type
    res = validate_literary_record({"title": "Test Title"})
    assert any("literary_type" in err.lower() for err in res)
    res = validate_literary_record(
        {"title": "Test Title", "literary_type": "comic_strip"}
    )
    assert any("must be one of" in err.lower() for err in res)

    # Invalid year formats and out-of-range dates
    res = validate_literary_record(
        {"title": "Test", "literary_type": "poem", "year": "not_an_int"}
    )
    assert any("must be an integer" in err.lower() for err in res)
    res = validate_literary_record(
        {"title": "Test", "literary_type": "poem", "year": 3000}
    )
    assert any("out of realistic range" in err.lower() for err in res)

    # Inverted date range
    res = validate_literary_record(
        {
            "title": "Test",
            "literary_type": "collection",
            "year": 1990,
            "year_end": 1980,
        }
    )
    assert any("cannot be earlier" in err.lower() for err in res)

    # Date precision without year
    res = validate_literary_record(
        {"title": "Test", "literary_type": "poem", "date_precision": "exact"}
    )
    assert any("requires a non-null 'year'" in err.lower() for err in res)

    # Invalid confidence
    res = validate_literary_record(
        {
            "title": "Test",
            "literary_type": "poem",
            "confidence": "super_confident",
        }
    )
    assert any("confidence" in err.lower() for err in res)

    # Verified confidence requires valid, non-future verified_on date
    res = validate_literary_record(
        {"title": "Test", "literary_type": "poem", "confidence": "verified"}
    )
    assert any("requires 'verified_on' date" in err.lower() for err in res)

    future_date = (datetime.date.today() + datetime.timedelta(days=365)).isoformat()
    res = validate_literary_record(
        {
            "title": "Test",
            "literary_type": "poem",
            "confidence": "verified",
            "verified_on": future_date,
        }
    )
    assert any("future" in err.lower() for err in res)

    res = validate_literary_record(
        {
            "title": "Test",
            "literary_type": "poem",
            "confidence": "verified",
            "verified_on": "01-01-2020",
        }
    )
    assert any("YYYY-MM-DD" in err for err in res)

    # Excessively long description safety check
    res = validate_literary_record(
        {
            "title": "Test",
            "literary_type": "poem",
            "description": "X" * 3000,
        }
    )
    assert any("excessively long" in err.lower() for err in res)


def test_add_and_get_literary_record(test_db: Path):
    """Insert and retrieve a complete literary record with foreign keys."""
    source_id = add_source(
        title="Bodo Sahitya Sabha Archival Record",
        type="archive",
        license="CC-BY-4.0",
        db_path=test_db,
    )

    rec_id = add_literary_record(
        title="हाबिला खावनाय",
        literary_type="short_story",
        title_en="Habila Khaonay",
        roman_title="Habila Khaonai",
        author="सतिश चन्द्र बसुमतारी",
        year=1919,
        date_precision="exact",
        original_language="brx",
        translation_languages=["as", "en"],
        book_title="बिबार (Bibar Magazine)",
        publisher="Bodo Chhatra Sanmilani",
        description="Regarded as the first modern Bodo short story.",
        literary_movement="Bibar Era",
        source_id=source_id,
        primary_sources=["Bibar Magazine, Inaugural Issue, 1919"],
        confidence="verified",
        verified_by="Archival Committee",
        verified_on="2024-01-15",
        db_path=test_db,
    )

    item = get_literary_record(rec_id, db_path=test_db)
    assert item is not None
    assert item["id"] == rec_id
    assert item["title"] == "हाबिला खावनाय"
    assert item["title_en"] == "Habila Khaonay"
    assert item["literary_type"] == "short_story"
    assert item["author"] == "सतिश चन्द्र बसुमतारी"
    assert item["year"] == 1919
    assert item["date_precision"] == "exact"
    assert item["original_language"] == "brx"
    assert "en" in item["translation_languages"]
    assert item["book_title"] == "बिबार (Bibar Magazine)"
    assert item["literary_movement"] == "Bibar Era"
    assert item["source_id"] == source_id
    assert item["source_title"] == "Bodo Sahitya Sabha Archival Record"
    assert item["source_license"] == "CC-BY-4.0"
    assert item["confidence"] == "verified"
    assert item["verified_by"] == "Archival Committee"
    assert item["verified_on"] == "2024-01-15"

    # Non-existent ID returns None
    assert get_literary_record(99999, db_path=test_db) is None


def test_unicode_nfc_normalization(test_db: Path):
    """Verify all text fields are normalized to Unicode NFC upon insertion."""
    # Create decomposed NFD strings (combining accent marks)
    nfd_title = unicodedata.normalize("NFD", "Hàbila Kháwnay (हाबिला खावनाय)")
    nfd_author = unicodedata.normalize("NFD", "Satísh Chándra Basumatary (सतिश चन्द्र)")
    assert not unicodedata.is_normalized("NFC", nfd_title)
    assert not unicodedata.is_normalized("NFC", nfd_author)

    rec_id = add_literary_record(
        title=nfd_title,
        literary_type="poem",
        author=nfd_author,
        year=1935,
        db_path=test_db,
    )

    item = get_literary_record(rec_id, db_path=test_db)
    assert item is not None
    assert unicodedata.is_normalized("NFC", item["title"])
    assert unicodedata.is_normalized("NFC", item["author"])
    assert item["title"] == unicodedata.normalize("NFC", nfd_title)
    assert item["author"] == unicodedata.normalize("NFC", nfd_author)


def test_search_literature(test_db: Path):
    """Search works by title, author, description, movement, or linked source."""
    add_literary_record(
        title="खामफ्लं",
        literary_type="poem",
        author="कमल कुमार ब्रह्म",
        year=1940,
        description="Philosophical poem examining nature and heritage.",
        literary_movement="Bibha Movement",
        db_path=test_db,
    )
    add_literary_record(
        title="बर' हारिनि गिबि फावथाय",
        literary_type="play",
        author="सतिश चन्द्र बसुमतारी",
        year=1923,
        description="Early Bodo stage drama performed in Goalpara.",
        db_path=test_db,
    )
    add_literary_record(
        title="गाबख्रेबनाय",
        literary_type="novel",
        author="चित्तरंजन मुशाहारी",
        year=1977,
        description="Social realism novel reflecting agrarian life.",
        db_path=test_db,
    )

    # Search by title keyword
    res = search_literature("खामफ्लं", db_path=test_db)
    assert len(res) == 1
    assert res[0]["title"] == "खामफ्लं"

    # Search by author keyword
    res = search_literature("मुशाहारी", db_path=test_db)
    assert len(res) == 1
    assert res[0]["author"] == "चित्तरंजन मुशाहारी"

    # Search by movement
    res = search_literature("Bibha", db_path=test_db)
    assert len(res) == 1
    assert res[0]["literary_movement"] == "Bibha Movement"

    # Filter search by type
    res = search_literature("सतिश", db_path=test_db, literary_type="play")
    assert len(res) == 1
    assert res[0]["literary_type"] == "play"

    res = search_literature("सतिश", db_path=test_db, literary_type="poem")
    assert len(res) == 0

    # Wildcard escaping safety
    res = search_literature("%", db_path=test_db)
    assert len(res) == 0

    # Empty search returns empty list
    assert search_literature("", db_path=test_db) == []
    assert search_literature("   ", db_path=test_db) == []


def test_filter_literature(test_db: Path):
    """Filter literature items by type, author, date range, and confidence."""
    add_literary_record(
        title="Work A",
        literary_type="poem",
        author="Author 1",
        year=1920,
        confidence="verified",
        verified_on="2020-01-01",
        db_path=test_db,
    )
    add_literary_record(
        title="Work B",
        literary_type="poem",
        author="Author 1",
        year=1930,
        confidence="needs_check",
        db_path=test_db,
    )
    add_literary_record(
        title="Work C",
        literary_type="novel",
        author="Author 2",
        year=1950,
        confidence="verified",
        verified_on="2021-05-10",
        db_path=test_db,
    )
    add_literary_record(
        title="Work D",
        literary_type="folk_tale",
        author=None,
        year=None,
        date_precision="unknown",
        confidence="needs_check",
        db_path=test_db,
    )

    # Filter by literary_type
    poems = filter_literature(db_path=test_db, literary_type="poem")
    assert len(poems) == 2
    assert all(p["literary_type"] == "poem" for p in poems)

    # Filter by author
    a1_works = filter_literature(db_path=test_db, author="Author 1")
    assert len(a1_works) == 2

    # Filter by date range
    range_works = filter_literature(db_path=test_db, from_year=1925, to_year=1960)
    assert len(range_works) == 2
    assert [w["title"] for w in range_works] == ["Work B", "Work C"]

    # Filter by confidence
    verified = filter_literature(db_path=test_db, confidence="verified")
    assert len(verified) == 2
    assert all(v["confidence"] == "verified" for v in verified)

    # Unknown dates excluded by default, included when requested
    without_unknown = filter_literature(db_path=test_db)
    assert len(without_unknown) == 3
    with_unknown = filter_literature(db_path=test_db, include_unknown_dates=True)
    assert len(with_unknown) == 4

    # Sort order
    desc_works = filter_literature(
        db_path=test_db, include_unknown_dates=False, sort_order="desc"
    )
    years = [w["year"] for w in desc_works]
    assert years == [1950, 1930, 1920]


def test_get_literature_by_author(test_db: Path):
    """Retrieve all works by a specific author (including unknown years)."""
    add_literary_record(
        title="Poem 1",
        literary_type="poem",
        author="ईशान चन्द्र मुशाहारी",
        year=1935,
        db_path=test_db,
    )
    add_literary_record(
        title="Poem 2",
        literary_type="poem",
        author="ईशान चन्द्र मुशाहारी",
        year=None,
        db_path=test_db,
    )
    add_literary_record(
        title="Other Poem",
        literary_type="poem",
        author="अन्ये लेखका",
        year=1940,
        db_path=test_db,
    )

    works = get_literature_by_author("ईशान चन्द्र मुशाहारी", db_path=test_db)
    assert len(works) == 2
    titles = {w["title"] for w in works}
    assert titles == {"Poem 1", "Poem 2"}

    # Also test alias get_literary_by_author
    works_alias = get_literary_by_author("ईशान चन्द्र मुशाहारी", db_path=test_db)
    assert len(works_alias) == 2

    # Non-existent author
    assert get_literature_by_author("Nobody", db_path=test_db) == []
    # Empty author
    assert get_literature_by_author("", db_path=test_db) == []


def test_approximate_and_unknown_dates(test_db: Path):
    """Handle approximate dates, date ranges, and unknown publication years."""
    id_approx = add_literary_record(
        title="Folklore Collection",
        literary_type="folk_tale",
        year=1920,
        date_precision="approximate",
        db_path=test_db,
    )
    id_range = add_literary_record(
        title="Poetry Anthology",
        literary_type="collection",
        year=1952,
        year_end=1955,
        date_precision="range",
        db_path=test_db,
    )
    id_unknown = add_literary_record(
        title="Ancient Mythological Song",
        literary_type="folk_tale",
        year=None,
        date_precision="unknown",
        db_path=test_db,
    )

    rec_approx = get_literary_record(id_approx, db_path=test_db)
    rec_range = get_literary_record(id_range, db_path=test_db)
    rec_unknown = get_literary_record(id_unknown, db_path=test_db)

    assert rec_approx["date_precision"] == "approximate"
    assert rec_range["year"] == 1952
    assert rec_range["year_end"] == 1955
    assert rec_range["date_precision"] == "range"
    assert rec_unknown["year"] is None
    assert rec_unknown["date_precision"] == "unknown"

    fmt_approx = format_literature_item(rec_approx)
    assert "c. 1920" in fmt_approx

    fmt_range = format_literature_item(rec_range)
    assert "1952 - 1955" in fmt_range

    fmt_unknown = format_literature_item(rec_unknown)
    assert "Unknown Year" in fmt_unknown


def test_duplicate_detection_and_conflict_handling(test_db: Path):
    """Prevent duplicate insertions when disallowed, update cleanly when allowed."""
    id1 = add_literary_record(
        title="अंखाया",
        literary_type="poem",
        author="रुपनाथ ब्रह्म",
        year=1924,
        description="First description",
        db_path=test_db,
    )

    # With raise_on_duplicate=True: raises ValueError
    with pytest.raises(ValueError, match="already exists"):
        add_literary_record(
            title="अंखाया",
            literary_type="poem",
            author="रुपनाथ ब्रह्म",
            year=1924,
            db_path=test_db,
            raise_on_duplicate=True,
        )

    # With raise_on_duplicate=False (default): updates existing record
    id2 = add_literary_record(
        title="अंखाया",
        literary_type="poem",
        author="रुपनाथ ब्रह्म",
        book_title="बिबार",
        description="Updated extended description",
        db_path=test_db,
        raise_on_duplicate=False,
    )
    assert id1 == id2

    updated = get_literary_record(id1, db_path=test_db)
    assert updated["book_title"] == "बिबार"
    assert updated["description"] == "Updated extended description"
    assert updated["year"] == 1924


def test_source_foreign_key_and_citation_checks(test_db: Path):
    """Enforce foreign key constraints and identify insufficient citations."""
    # Invalid source_id raises sqlite3.IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        add_literary_record(
            title="Invalid Source Poem",
            literary_type="poem",
            source_id=88888,
            db_path=test_db,
        )

    # Auto-source creation when source_title is provided
    rec_id = add_literary_record(
        title="Auto Sourced Poem",
        literary_type="poem",
        source_title="Gauhati University Journal of Humanities",
        source_url="https://example.org/gujh",
        db_path=test_db,
    )
    rec = get_literary_record(rec_id, db_path=test_db)
    assert rec["source_id"] is not None
    assert rec["source_title"] == "Gauhati University Journal of Humanities"

    # Item with no citations
    add_literary_record(
        title="Unreferenced Story",
        literary_type="short_story",
        author="Unknown",
        db_path=test_db,
    )

    # Item with vague citation
    vague_src_id = add_source(
        title="wikipedia.org", license="CC-BY-SA", db_path=test_db
    )
    add_literary_record(
        title="Vaguely Cited Play",
        literary_type="play",
        source_id=vague_src_id,
        db_path=test_db,
    )

    flagged = get_literature_missing_citations(db_path=test_db)
    assert len(flagged) >= 2
    flagged_titles = {f["title"] for f in flagged}
    assert "Unreferenced Story" in flagged_titles
    assert "Vaguely Cited Play" in flagged_titles


def test_get_unverified_literature(test_db: Path):
    """Retrieve only unverified or needs_check literary works."""
    add_literary_record(
        title="Verified Work",
        literary_type="poem",
        confidence="verified",
        verified_on="2023-10-10",
        db_path=test_db,
    )
    add_literary_record(
        title="Needs Check Work",
        literary_type="poem",
        confidence="needs_check",
        db_path=test_db,
    )
    add_literary_record(
        title="Unverified Work",
        literary_type="novel",
        confidence="unverified",
        db_path=test_db,
    )

    unverified = get_unverified_literature(db_path=test_db)
    titles = [item["title"] for item in unverified]
    assert "Verified Work" not in titles
    assert "Needs Check Work" in titles
    assert "Unverified Work" in titles


def test_idempotent_migrations_legacy_database(tmp_path: Path):
    """Ensure init_db adds literature_items safely to an existing legacy DB."""
    legacy_db = tmp_path / "legacy.sqlite"
    # Create legacy schema without literature_items
    with sqlite3.connect(legacy_db) as conn:
        conn.execute(
            """
            CREATE TABLE sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                license TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO sources (title, license) VALUES ('Old Source', 'MIT')"
        )
        conn.commit()

    # Apply migrations
    init_db(legacy_db)

    # Verify literature_items exists and old sources row is intact
    with get_connection(legacy_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM sources")
        assert cursor.fetchone()[0] == 1

        cursor.execute(
            "SELECT count(*) FROM sqlite_master "
            "WHERE type='table' AND name='literature_items'"
        )
        assert cursor.fetchone()[0] == 1

    # Insert literature record into newly migrated legacy DB
    rec_id = add_literary_record(
        title="Migrated Story",
        literary_type="short_story",
        source_id=1,
        db_path=legacy_db,
    )
    assert rec_id > 0

    # Running init_db multiple times must be completely idempotent
    init_db(legacy_db)
    init_db(legacy_db)

    rec = get_literary_record(rec_id, db_path=legacy_db)
    assert rec is not None
    assert rec["title"] == "Migrated Story"


def test_csv_and_json_export_and_import(tmp_path: Path):
    """Round-trip export and import of CSV and JSON with dry-run and backup checks."""
    db_file = tmp_path / "lexicon_roundtrip.sqlite"
    init_db(db_file)

    add_literary_record(
        title="हाबिला खावनाय",
        literary_type="short_story",
        author="सतिश चन्द्र बसुमतारी",
        year=1919,
        description="First Bodo modern story.",
        db_path=db_file,
    )
    add_literary_record(
        title="अंखाया",
        literary_type="poem",
        author="रुपनाथ ब्रह्म",
        year=1924,
        description="Pioneering poetry in Bibar magazine.",
        db_path=db_file,
    )

    csv_path = tmp_path / "export.csv"
    json_path = tmp_path / "export.json"

    # Export to CSV
    exported_csv_count = export_literature_csv(csv_path, db_path=db_file)
    assert exported_csv_count == 2
    assert csv_path.is_file()

    # Export to JSON
    exported_json_count = export_literature_json(json_path, db_path=db_file)
    assert exported_json_count == 2
    assert json_path.is_file()
    with open(json_path, encoding="utf-8") as f:
        loaded_data = json.load(f)
        assert len(loaded_data) == 2
        assert loaded_data[0]["title"] in ("हाबिला खावनाय", "अंखाया")

    # Create new target database for import
    target_db = tmp_path / "target.sqlite"
    init_db(target_db)

    # Dry-run import from CSV
    dry_stats = import_literature_csv(csv_path, db_path=target_db, dry_run=True)
    assert dry_stats["dry_run"] is True
    assert dry_stats["imported"] == 2
    # Verify no records were actually written in dry run
    assert len(filter_literature(db_path=target_db, include_unknown_dates=True)) == 0

    # Actual import from CSV
    real_stats = import_literature_csv(csv_path, db_path=target_db, dry_run=False)
    assert real_stats["dry_run"] is False
    assert real_stats["imported"] == 2
    assert real_stats["backup_path"] is not None
    assert len(filter_literature(db_path=target_db, include_unknown_dates=True)) == 2

    # Malformed CSV import: should report errors clearly without crashing
    bad_csv = tmp_path / "bad.csv"
    with open(bad_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["title", "literary_type", "year"])
        writer.writerow(["Valid Poem", "poem", "1930"])
        writer.writerow(["", "poem", "1930"])  # Missing title
        writer.writerow(["Bad Type", "unknown_genre", "1930"])  # Bad type
        writer.writerow(["Bad Year", "novel", "not_a_year"])  # Bad year

    bad_stats = import_literature_csv(bad_csv, db_path=target_db, dry_run=False)
    assert bad_stats["total"] == 4
    assert bad_stats["imported"] == 1
    assert bad_stats["rejected"] == 3
    assert len(bad_stats["errors"]) == 3

    # JSON import into a third clean database
    json_db = tmp_path / "json_target.sqlite"
    init_db(json_db)
    json_stats = import_literature_json(json_path, db_path=json_db, dry_run=False)
    assert json_stats["imported"] == 2
    assert len(filter_literature(db_path=json_db, include_unknown_dates=True)) == 2


def test_cli_literature_execution(test_db: Path, capsys: pytest.CaptureFixture[str]):
    """Test CLI commands for search, filter, author query, citations, and export."""
    add_literary_record(
        title="CLI Test Poem",
        literary_type="poem",
        author="CLI Author",
        year=1945,
        description="Sample poem for CLI verification.",
        db_path=test_db,
    )

    # Test search via CLI
    code = main(["--db", str(test_db), "--search", "CLI Test"])
    assert code == 0
    out = capsys.readouterr().out
    assert "CLI Test Poem" in out
    assert "CLI Author" in out

    # Test author filter via CLI
    code = main(["--db", str(test_db), "--author", "CLI Author"])
    assert code == 0
    out = capsys.readouterr().out
    assert "CLI Test Poem" in out

    # Test type filter via CLI
    code = main(["--db", str(test_db), "--type", "poem"])
    assert code == 0
    out = capsys.readouterr().out
    assert "CLI Test Poem" in out

    # Test unverified listing via CLI
    code = main(["--db", str(test_db), "--unverified"])
    assert code == 0
    out = capsys.readouterr().out
    assert "CLI Test Poem" in out

    # Test missing citations listing via CLI
    code = main(["--db", str(test_db), "--missing-citations"])
    assert code == 0
    out = capsys.readouterr().out
    assert "CLI Test Poem" in out

    # Test export CSV via CLI
    csv_out = test_db.parent / "cli_export.csv"
    code = main(["--db", str(test_db), "--export-csv", str(csv_out)])
    assert code == 0
    assert csv_out.is_file()
