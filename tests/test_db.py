import sqlite3
import unicodedata
from pathlib import Path

import pytest

from bhasha_lib.db import (
    DEFAULT_DB_PATH,
    VALID_ORIGINS,
    VALID_STATUSES,
    add_culture_item,
    add_occurrence,
    add_source,
    add_word,
    backup_db,
    get_connection,
    init_db,
    search_word,
    update_word_meaning,
)


def test_create_db_insert_and_search(tmp_path):
    db_file = tmp_path / "lexicon.sqlite"
    init_db(db_file)

    source_id = add_source(
        title="Bodo Grammar & Usage",
        type="book",
        author="Bodo Sahitya Sabha",
        year=2020,
        license="CC-BY-4.0",
        contributor="Archive Contributor",
        url="https://example.org/bodo-grammar",
        file_path="data/archive/bodo/books/grammar.pdf",
        db_path=db_file,
    )
    assert isinstance(source_id, int)
    assert source_id > 0

    add_word(
        word="बर'",
        roman="Boro",
        meaning_hi="बोडो भाषा/लोग",
        meaning_en="Bodo language or ethnic group",
        pos="noun",
        tone="high",
        dialect="Standard",
        freq=1,
        db_path=db_file,
    )

    result = search_word("बर'", db_path=db_file)
    assert result is not None
    assert result["word"] == "बर'"
    assert result["roman"] == "Boro"
    assert result["meaning_en"] == "Bodo language or ethnic group"
    assert result["freq"] == 1


def test_empty_license_raises_value_error(tmp_path):
    db_file = tmp_path / "lexicon.sqlite"
    init_db(db_file)

    with pytest.raises(ValueError, match="license"):
        add_source(title="Untitled", license="", db_path=db_file)

    with pytest.raises(ValueError, match="license"):
        add_source(title="Untitled", license="   ", db_path=db_file)

    with pytest.raises(ValueError, match="license"):
        add_source(title="Untitled", license=None, db_path=db_file)


def test_adding_same_word_twice_increases_freq(tmp_path):
    db_file = tmp_path / "lexicon.sqlite"
    init_db(db_file)

    add_word("अंखा", meaning_en="star", freq=1, db_path=db_file)
    res1 = search_word("अंखा", db_path=db_file)
    assert res1 is not None
    assert res1["freq"] == 1

    # Adding the word again must increase freq
    add_word("अंखा", freq=1, db_path=db_file)
    res2 = search_word("अंखा", db_path=db_file)
    assert res2 is not None
    assert res2["freq"] == 2

    # Adding with a specific frequency increment
    add_word("अंखा", freq=3, db_path=db_file)
    res3 = search_word("अंखा", db_path=db_file)
    assert res3 is not None
    assert res3["freq"] == 5


def test_nfc_normalization(tmp_path):
    db_file = tmp_path / "lexicon.sqlite"
    init_db(db_file)

    # Decomposed form (NFD)
    word_nfd = unicodedata.normalize("NFD", "बड़ो")
    word_nfc = unicodedata.normalize("NFC", "बड़ो")

    add_word(word_nfd, meaning_en="Bodo", db_path=db_file)

    # Search with composed (NFC)
    found_nfc = search_word(word_nfc, db_path=db_file)
    assert found_nfc is not None
    assert found_nfc["word"] == word_nfc

    # Search with decomposed (NFD)
    found_nfd = search_word(word_nfd, db_path=db_file)
    assert found_nfd is not None
    assert found_nfd["word"] == word_nfc


def test_occurrences_and_culture_items(tmp_path):
    db_file = tmp_path / "lexicon.sqlite"
    init_db(db_file)

    s_id = add_source(
        title="Folk Songs of Bodos", license="Public Domain", db_path=db_file
    )
    add_word("बैसागु", meaning_en="Bwisagu Spring Festival", db_path=db_file)

    add_occurrence(
        word="बैसागु",
        source_id=s_id,
        line_no=42,
        context="बैसागु सान बेलाव...",
        db_path=db_file,
    )

    c_id = add_culture_item(
        category="festivals",
        title="Bwisagu",
        description="Spring festival celebrated during Bwisagu month",
        region="Bodoland",
        related_words="बैसागु,बागुरुम्बा",
        source_id=s_id,
        media_path="data/archive/bodo/culture/bwisagu.jpg",
        db_path=db_file,
    )
    assert isinstance(c_id, int)
    assert c_id > 0


def test_search_word_not_found(tmp_path):
    db_file = tmp_path / "lexicon.sqlite"
    init_db(db_file)

    assert search_word("nonexistent_word", db_path=db_file) is None
    assert search_word("", db_path=db_file) is None


def test_foreign_key_enforcement(tmp_path):
    """PRAGMA foreign_keys is enforced on all connections."""
    db_file = tmp_path / "fk_test.sqlite"
    init_db(db_file)

    with get_connection(db_file) as conn:
        fk_status = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        assert fk_status == 1

    # Attempting to add occurrence for non-existent word must fail
    with pytest.raises(sqlite3.IntegrityError):
        add_occurrence(word="nonexistent_word", line_no=1, db_path=db_file)

    # Attempting to add occurrence with non-existent source_id must fail
    add_word("बर'", db_path=db_file)
    with pytest.raises(sqlite3.IntegrityError):
        add_occurrence(word="बर'", source_id=9999, line_no=1, db_path=db_file)


def test_index_creation_and_idempotence(tmp_path):
    """Indexes are created properly and init_db is fully idempotent."""
    db_file = tmp_path / "index_test.sqlite"
    init_db(db_file)

    expected_indexes = {
        "idx_occurrences_word",
        "idx_occurrences_source",
        "idx_words_status",
        "idx_words_freq",
        "idx_culture_items_year",
        "idx_sources_title",
    }
    with get_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        found = {row[0] for row in cursor.fetchall()}
        for idx in expected_indexes:
            assert idx in found

    # Repeated initialization should be idempotent and not raise errors
    init_db(db_file)
    init_db(db_file)


def test_backup_db_creates_consistent_snapshot(tmp_path):
    """backup_db creates a valid, readable SQLite backup with identical content."""
    db_file = tmp_path / "source.sqlite"
    backup_dir = tmp_path / "backups"
    init_db(db_file)

    s_id = add_source("Test Source", license="CC0", db_path=db_file)
    add_word("खोन्थाय", meaning_en="poem", db_path=db_file)
    add_occurrence(word="खोन्थाय", source_id=s_id, line_no=10, db_path=db_file)

    backup_path = backup_db(db_file, backup_dir=backup_dir)
    assert backup_path.exists()
    assert backup_path.parent == backup_dir

    # Backup should contain the same records
    res = search_word("खोन्थाय", db_path=backup_path)
    assert res is not None
    assert res["meaning_en"] == "poem"

    # Non-existent DB raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        backup_db(tmp_path / "missing.sqlite", backup_dir=backup_dir)


def test_word_validation_and_status_origin(tmp_path):
    """Validation checks for word string, status, origin, and duplicate handling."""
    db_file = tmp_path / "validation.sqlite"
    init_db(db_file)

    # Empty or whitespace-only words must raise ValueError
    with pytest.raises(ValueError, match="cannot be empty"):
        add_word("", db_path=db_file)
    with pytest.raises(ValueError, match="cannot be empty"):
        add_word("   ", db_path=db_file)

    # Invalid status raises ValueError
    with pytest.raises(ValueError, match="Invalid status"):
        add_word("थाव", status="invalid_status", db_path=db_file)

    # Valid statuses are accepted
    for st in VALID_STATUSES:
        add_word(f"word_{st}", status=st, db_path=db_file)
        w = search_word(f"word_{st}", db_path=db_file)
        assert w["status"] == st

    # Invalid origin raises ValueError
    with pytest.raises(ValueError, match="Invalid origin"):
        add_word("थाव", origin="alien", db_path=db_file)

    # Valid origins are accepted
    for orig in VALID_ORIGINS:
        add_word(f"word_{orig}", origin=orig, db_path=db_file)
        w = search_word(f"word_{orig}", db_path=db_file)
        assert w["origin"] == orig

    # Duplicate word handling with raise_on_duplicate
    add_word("गाहाम", db_path=db_file)
    with pytest.raises(ValueError, match="already exists"):
        add_word("गाहाम", raise_on_duplicate=True, db_path=db_file)

    # update_word_meaning validation
    with pytest.raises(ValueError, match="Invalid status"):
        update_word_meaning("गाहाम", status="bogus", db_path=db_file)
    with pytest.raises(ValueError, match="Invalid origin"):
        update_word_meaning("गाहाम", origin="bogus", db_path=db_file)


def test_production_database_integrity_and_indexes():
    """Verify production database records and indexes are preserved intact."""
    if not Path(DEFAULT_DB_PATH).exists():
        pytest.skip("Default database not found at data/lexicon.sqlite")

    with get_connection(DEFAULT_DB_PATH) as conn:
        cursor = conn.cursor()

        # Word count must be at least 44,011 baseline (expanded with Endle 1884/1911)
        cursor.execute("SELECT count(*) FROM words")
        assert cursor.fetchone()[0] >= 44011

        # Sources count must be at least 12 baseline
        cursor.execute("SELECT count(*) FROM sources")
        assert cursor.fetchone()[0] >= 12

        # Occurrences count must be at least 6,128 baseline
        cursor.execute("SELECT count(*) FROM occurrences")
        assert cursor.fetchone()[0] >= 6128

        # Culture items count must be at least 14 baseline
        cursor.execute("SELECT count(*) FROM culture_items")
        assert cursor.fetchone()[0] >= 14

        # All words must still have unverified status
        cursor.execute("SELECT count(*) FROM words WHERE status != 'unverified'")
        assert cursor.fetchone()[0] == 0

        # All words must have origin IS NULL
        cursor.execute("SELECT count(*) FROM words WHERE origin IS NOT NULL")
        assert cursor.fetchone()[0] == 0

        # Verify all 6 required indexes exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        existing_indexes = {row[0] for row in cursor.fetchall()}
        expected = {
            "idx_occurrences_word",
            "idx_occurrences_source",
            "idx_words_status",
            "idx_words_freq",
            "idx_culture_items_year",
            "idx_sources_title",
        }
        for idx in expected:
            assert idx in existing_indexes
