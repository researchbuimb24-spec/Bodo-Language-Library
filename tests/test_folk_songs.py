import csv
import json
import sqlite3
import unicodedata
from pathlib import Path

import pytest

from bhasha_lib import (
    VALID_AUDIO_FORMATS,
    VALID_CONSENT_STATES,
    VALID_SONG_TYPES,
    add_folk_song,
    add_folk_song_item,
    add_song_recording,
    add_song_recording_item,
    add_source,
    export_folk_songs_csv,
    export_folk_songs_json,
    filter_folk_songs,
    format_folk_song_item,
    get_folk_song,
    get_folk_songs_missing_citations,
    get_recording,
    get_recordings,
    get_recordings_missing_consent,
    get_unverified_folk_songs,
    import_folk_songs_csv,
    import_folk_songs_json,
    init_db,
    request_recording_removal,
    search_folk_songs,
    validate_folk_song,
    validate_song_recording,
    withdraw_recording_consent,
)
from bhasha_lib.consent import (
    ConsentError,
    ConsentRecord,
    ConsentStatus,
    validate_consent_dict,
)
from bhasha_lib.db import get_connection, search_word
from bhasha_lib.folk_songs import (
    CSV_FOLK_SONG_COLUMNS,
    load_folk_song_file,
    load_folk_songs_dir,
    main,
    verify_folk_songs_dir,
)


def test_validate_consent_valid():
    data = {
        "status": "verified_written",
        "performer_name": "Traditional Performer",
        "consent_holder": "Cultural Archivist",
        "document_ref": "docs/consents/001.pdf",
        "permitted_uses": ["preservation", "research"],
    }
    record = validate_consent_dict(data, item_title="Test Song")
    assert isinstance(record, ConsentRecord)
    assert record.is_verified is True
    assert record.status == ConsentStatus.VERIFIED_WRITTEN.value
    assert record.performer_name == "Traditional Performer"


def test_validate_consent_institutional_bss():
    data = {
        "status": "institutional_bss",
        "performer_name": "Bodo Community Elders",
        "consent_holder": "BSS Kokrajhar",
        "institutional_partner": "Bodo Sahitya Sabha",
    }
    record = validate_consent_dict(data, item_title="BSS Song")
    assert record.is_verified is True
    assert record.institutional_partner == "Bodo Sahitya Sabha"


def test_validate_consent_pending_rejected():
    data = {
        "status": "pending",
        "performer_name": "Singer Name",
        "document_ref": "pending.pdf",
    }
    with pytest.raises(ConsentError, match="Consent status is 'pending'"):
        validate_consent_dict(data, item_title="Pending Song")


def test_validate_consent_missing_performer():
    data = {
        "status": "verified_written",
        "document_ref": "docs/form.pdf",
    }
    with pytest.raises(ConsentError, match="'performer_name' is required"):
        validate_consent_dict(data, item_title="No Performer Song")


def test_validate_consent_missing_verification_proof():
    data = {
        "status": "verified_written",
        "performer_name": "Singer",
    }
    with pytest.raises(ConsentError, match="Either 'document_ref' .* must be provided"):
        validate_consent_dict(data, item_title="Unverified Song")


def test_load_folk_song_file_success(tmp_path):
    db_file = tmp_path / "song_test.sqlite"
    init_db(db_file)

    song_file = tmp_path / "bwisagu_song.md"
    song_file.write_text(
        "---\n"
        "title: 'Bwisagu Test Song'\n"
        "category: 'folk_song'\n"
        "genre: 'Bwisagu'\n"
        "region: 'Kokrajhar, Assam'\n"
        "instruments: ['Kham', 'Siphung']\n"
        "consent:\n"
        "  status: 'verified_written'\n"
        "  performer_name: 'Bodo Singer'\n"
        "  consent_holder: 'Archive Project'\n"
        "  document_ref: 'consents/01.pdf'\n"
        "license: 'CC-BY-NC-SA-4.0'\n"
        "lyrics_script: 'devanagari'\n"
        "---\n"
        "बैसागु फैबाय आदा गाहाम फैबाय\n"
        "खाम सिफुं दामनानै\n",
        encoding="utf-8",
    )

    item_id = load_folk_song_file(song_file, db_path=db_file)
    assert item_id > 0

    # Verify culture item inserted
    with get_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT title, category, related_words FROM culture_items WHERE id = ?",
            (item_id,),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "Bwisagu Test Song"
        assert row[1] == "folk_song"
        assert "Kham" in row[2]
        assert "Siphung" in row[2]

        # Verify source inserted
        cursor.execute(
            "SELECT type, author, license FROM sources "
            "WHERE title = 'Bwisagu Test Song'"
        )
        s_row = cursor.fetchone()
        assert s_row is not None
        assert s_row[0] == "folk_song"
        assert s_row[1] == "Bodo Singer"
        assert s_row[2] == "CC-BY-NC-SA-4.0"

    # Verify words tokenized from lyrics into lexicon
    w_bwisagu = search_word("बैसागु", db_path=db_file)
    assert w_bwisagu is not None


def test_load_folk_song_unconsented_rejected(tmp_path):
    db_file = tmp_path / "song_reject.sqlite"
    init_db(db_file)

    bad_song = tmp_path / "unconsented_song.md"
    bad_song.write_text(
        "---\n"
        "title: 'Unauthorized Song'\n"
        "category: 'folk_song'\n"
        "genre: 'Folk'\n"
        "lyrics_script: 'devanagari'\n"
        "---\n"
        "Lyrics without consent.\n",
        encoding="utf-8",
    )

    with pytest.raises(ConsentError, match="missing a 'consent' block"):
        load_folk_song_file(bad_song, db_path=db_file)


def test_verify_folk_songs_dir(tmp_path):
    # Create valid song
    valid_song = tmp_path / "valid.md"
    valid_song.write_text(
        "---\n"
        "title: 'Valid'\n"
        "consent:\n"
        "  status: 'verified_written'\n"
        "  performer_name: 'Singer'\n"
        "  document_ref: 'ref.pdf'\n"
        "---\n"
        "Lyrics\n",
        encoding="utf-8",
    )

    # Create pending song
    pending_song = tmp_path / "pending.md"
    pending_song.write_text(
        "---\n"
        "title: 'Pending'\n"
        "consent:\n"
        "  status: 'pending'\n"
        "  performer_name: 'Singer'\n"
        "  document_ref: 'ref.pdf'\n"
        "---\n"
        "Lyrics\n",
        encoding="utf-8",
    )

    # Create invalid song
    invalid_song = tmp_path / "invalid.md"
    invalid_song.write_text(
        "---\ntitle: 'Invalid'\n---\nLyrics\n",
        encoding="utf-8",
    )

    report = verify_folk_songs_dir(tmp_path)
    assert "valid.md" in report["valid"]
    assert "pending.md" in report["pending"]
    assert "invalid.md" in report["invalid"]


def test_load_folk_songs_dir(tmp_path):
    db_file = tmp_path / "dir_test.sqlite"
    init_db(db_file)

    song_dir = tmp_path / "songs"
    song_dir.mkdir()

    s1 = song_dir / "s1.md"
    s1.write_text(
        "---\n"
        "title: 'Song 1'\n"
        "consent:\n"
        "  status: 'institutional_bss'\n"
        "  performer_name: 'Artist'\n"
        "  institutional_partner: 'BSS'\n"
        "---\n"
        "Lyrics 1\n",
        encoding="utf-8",
    )

    loaded = load_folk_songs_dir(song_dir, db_path=db_file)
    assert len(loaded) == 1


def test_folk_songs_cli(tmp_path):
    db_file = tmp_path / "cli_test.sqlite"
    init_db(db_file)

    song_file = tmp_path / "cli_song.md"
    song_file.write_text(
        "---\n"
        "title: 'CLI Song'\n"
        "consent:\n"
        "  status: 'institutional_bss'\n"
        "  performer_name: 'Artist'\n"
        "  institutional_partner: 'BSS'\n"
        "---\n"
        "Lyrics\n",
        encoding="utf-8",
    )

    # CLI verify
    assert main(["verify", str(tmp_path)]) == 0

    # CLI load
    assert main(["load", str(tmp_path), "--db", str(db_file)]) == 0


def test_folk_song_constants():
    """Verify standard types, audio formats, and consent states."""
    assert "traditional_folk" in VALID_SONG_TYPES
    assert "festival_song" in VALID_SONG_TYPES
    assert "work_song" in VALID_SONG_TYPES
    assert "lullaby" in VALID_SONG_TYPES
    assert "dance_song" in VALID_SONG_TYPES
    assert "devotional" in VALID_SONG_TYPES

    assert "mp3" in VALID_AUDIO_FORMATS
    assert "wav" in VALID_AUDIO_FORMATS
    assert "flac" in VALID_AUDIO_FORMATS
    assert "ogg" in VALID_AUDIO_FORMATS

    assert "unknown" in VALID_CONSENT_STATES
    assert "pending" in VALID_CONSENT_STATES
    assert "granted" in VALID_CONSENT_STATES
    assert "denied" in VALID_CONSENT_STATES
    assert "withdrawn" in VALID_CONSENT_STATES


def test_validate_folk_song_rules():
    """Verify validation rules for folk song metadata."""
    valid_payload = {
        "title": "हाबिला मेथाय",
        "song_type": "festival_song",
        "year": 1950,
        "confidence": "expert",
    }
    assert validate_folk_song(valid_payload) == []

    # Missing title
    res = validate_folk_song({"song_type": "lullaby"})
    assert any("title" in err.lower() for err in res)

    # Blank title
    res = validate_folk_song({"title": "   ", "song_type": "lullaby"})
    assert any("title" in err.lower() for err in res)

    # Missing song_type
    res = validate_folk_song({"title": "Test Song"})
    assert any("song_type" in err.lower() for err in res)

    # Invalid song_type
    res = validate_folk_song({"title": "Test", "song_type": "techno_pop"})
    assert any("must be one of" in err.lower() for err in res)

    # Long description
    res = validate_folk_song(
        {
            "title": "Test",
            "song_type": "traditional_folk",
            "description": "x" * 10001,
        }
    )
    assert any("10,000" in err for err in res)

    # Out of range year
    res = validate_folk_song(
        {
            "title": "Test",
            "song_type": "traditional_folk",
            "year": 3000,
        }
    )
    assert any("year" in err.lower() for err in res)

    res = validate_folk_song(
        {
            "title": "Test",
            "song_type": "traditional_folk",
            "year": -6000,
        }
    )
    assert any("year" in err.lower() for err in res)

    # Invalid confidence
    res = validate_folk_song(
        {
            "title": "Test",
            "song_type": "traditional_folk",
            "confidence": "guessed",
        }
    )
    assert any("confidence" in err.lower() for err in res)


def test_validate_song_recording_rules():
    """Verify validation rules for audio recording metadata."""
    valid_payload = {
        "song_id": 1,
        "recording_id": 10,
        "audio_format": "wav",
        "consent_status": "granted",
        "consent_document_ref": "docs/consents/rec_001.pdf",
    }
    assert validate_song_recording(valid_payload) == []

    # Missing song_id
    res = validate_song_recording(
        {
            "audio_format": "mp3",
            "consent_status": "unknown",
        }
    )
    assert any("song_id" in err.lower() for err in res)

    # Invalid audio format
    res = validate_song_recording(
        {
            "song_id": 1,
            "audio_format": "exe",
            "consent_status": "unknown",
        }
    )
    assert any("audio_format" in err.lower() for err in res)

    # Negative duration
    res = validate_song_recording(
        {
            "song_id": 1,
            "duration_seconds": -15,
            "consent_status": "unknown",
        }
    )
    assert any("duration_seconds" in err.lower() for err in res)

    # Invalid consent status
    res = validate_song_recording(
        {
            "song_id": 1,
            "consent_status": "assumed",
        }
    )
    assert any("consent_status" in err.lower() for err in res)

    # Granted without consent document reference
    res = validate_song_recording(
        {
            "song_id": 1,
            "consent_status": "granted",
        }
    )
    assert any("consent_document_ref" in err.lower() for err in res)

    # Permission granted without consent document reference
    res = validate_song_recording(
        {
            "song_id": 1,
            "consent_status": "pending",
            "permit_redistribute": True,
        }
    )
    assert any("consent_document_ref" in err.lower() for err in res)


def test_unicode_nfc_normalization(tmp_path: Path):
    """Verify Unicode NFC normalization for folk songs and recordings."""
    db_file = tmp_path / "nfc_test.sqlite"
    init_db(db_file)

    # Note: Using decomposed combining accent 'e\u0301' ensures true NFD status
    nfd_title = unicodedata.normalize("NFD", "Bwisagu Me\u0301thai (बैसागु मेथाय)")
    assert not unicodedata.is_normalized("NFC", nfd_title)

    nfd_composer = unicodedata.normalize("NFD", "Sule\u0301kha Basumatary (सुलेखा)")
    assert not unicodedata.is_normalized("NFC", nfd_composer)

    song_id = add_folk_song(
        title=nfd_title,
        song_type="festival_song",
        composer=nfd_composer,
        db_path=db_file,
    )

    retrieved = get_folk_song(song_id, db_path=db_file)
    assert retrieved is not None
    assert unicodedata.is_normalized("NFC", retrieved["title"])
    assert unicodedata.is_normalized("NFC", retrieved["composer"])

    # Recording normalization
    nfd_performer = unicodedata.normalize("NFD", "Gobi\u0301nd Fouji (गोबिन्द)")
    assert not unicodedata.is_normalized("NFC", nfd_performer)
    rec_id = add_song_recording(
        song_id=song_id,
        performer=nfd_performer,
        audio_format="flac",
        consent_status="unknown",
        db_path=db_file,
    )

    rec = get_recording(rec_id, db_path=db_file)
    assert rec is not None
    assert unicodedata.is_normalized("NFC", rec["performer"])


def test_add_and_get_folk_song(tmp_path: Path):
    """Test full metadata insertion and retrieval for folk songs."""
    db_file = tmp_path / "song_full.sqlite"
    init_db(db_file)

    src_id = add_source(
        title="Folk Songs of the Bodos",
        author="Mohini Mohan Brahma",
        year=1960,
        type="book",
        license="CC-BY-NC-SA-4.0",
        db_path=db_file,
    )

    song_id = add_folk_song(
        title="खाम सिफुं दामनानै",
        roman_title="Kham Siphung Damnanwi",
        title_en="Playing the Drum and Flute",
        song_type="festival_song",
        composer="Traditional",
        lyricist="Traditional",
        performer="Community Elders",
        singer="Community Choir",
        community="Bodo",
        region="Kokrajhar",
        language="Bodo",
        dialect="Western",
        description="A traditional Bwisagu festival song welcoming spring.",
        cultural_context="Sung during the Bwisagu new year festivities.",
        festivals=["Bwisagu"],
        ceremonies=["Spring Welcoming"],
        dances=["Bagurumba"],
        instruments=["Kham", "Siphung", "Serja", "Tharkha"],
        places=["Kokrajhar", "Dotma"],
        source_id=src_id,
        license="CC-BY-NC-SA-4.0",
        confidence="verified",
        verified_by="Researcher",
        verified_on="2026-10-22",
        db_path=db_file,
    )

    item = get_folk_song(song_id, db_path=db_file)
    assert item is not None
    assert item["id"] == song_id
    assert item["title"] == "खाम सिफुं दामनानै"
    assert item["roman_title"] == "Kham Siphung Damnanwi"
    assert item["title_en"] == "Playing the Drum and Flute"
    assert item["song_type"] == "festival_song"
    assert "Bwisagu" in item["festivals"]
    assert "Spring Welcoming" in item["ceremonies"]
    assert "Bagurumba" in item["dances"]
    assert "Kham" in item["instruments"]
    assert "Kokrajhar" in item["places"]
    assert item["source_title"] == "Folk Songs of the Bodos"
    assert item["confidence"] == "verified"

    # Formatting helper test
    formatted = format_folk_song_item(item)
    assert "खाम सिफुं दामनानै" in formatted
    assert "festival_song" in formatted
    assert "Kham" in formatted


def test_search_and_filter_folk_songs(tmp_path: Path):
    """Test searching and filtering folk songs."""
    db_file = tmp_path / "search_filter.sqlite"
    init_db(db_file)

    s1 = add_folk_song(
        title="बैसागु मेथाय",
        roman_title="Bwisagu Methai",
        song_type="festival_song",
        region="Kokrajhar",
        community="Bodo",
        instruments=["Kham", "Siphung"],
        dances=["Bagurumba"],
        confidence="verified",
        verified_by="Researcher",
        verified_on="2026-10-22",
        db_path=db_file,
    )
    s2 = add_folk_song(
        title="हाबिला मेथाय",
        roman_title="Habila Methai",
        song_type="work_song",
        region="Udalguri",
        community="Bodo",
        instruments=["Siphung"],
        confidence="needs_check",
        db_path=db_file,
    )
    s3 = add_folk_song(
        title="गथ' उन्दुनाय मेथाय",
        roman_title="Gotho Undunay Methai",
        title_en="Lullaby",
        song_type="lullaby",
        region="Chirang",
        community="Bodo",
        confidence="verified",
        verified_by="Researcher",
        verified_on="2026-10-22",
        db_path=db_file,
    )

    # Search by title query
    res = search_folk_songs("बैसागु", db_path=db_file)
    assert len(res) == 1
    assert res[0]["id"] == s1

    # Search by roman query
    res = search_folk_songs("Habila", db_path=db_file)
    assert len(res) == 1
    assert res[0]["id"] == s2

    # Search by instrument
    res = search_folk_songs("Kham", db_path=db_file)
    assert len(res) == 1
    assert res[0]["id"] == s1

    # Filter by song_type
    res = filter_folk_songs(song_type="festival_song", db_path=db_file)
    assert len(res) == 1
    assert res[0]["id"] == s1

    # Filter by region
    res = filter_folk_songs(region="Udalguri", db_path=db_file)
    assert len(res) == 1
    assert res[0]["id"] == s2

    # Filter by verified_only
    res = filter_folk_songs(verified_only=True, db_path=db_file)
    ids = [r["id"] for r in res]
    assert s1 in ids
    assert s3 in ids
    assert s2 not in ids

    # Filter by confidence
    res = filter_folk_songs(confidence="needs_check", db_path=db_file)
    assert len(res) == 1
    assert res[0]["id"] == s2

    # Filter has_recording_only
    res = filter_folk_songs(has_recording_only=True, db_path=db_file)
    assert len(res) == 0

    # Add recording to s1 and re-check
    add_song_recording(
        song_id=s1,
        audio_format="mp3",
        consent_status="unknown",
        db_path=db_file,
    )
    res = filter_folk_songs(has_recording_only=True, db_path=db_file)
    assert len(res) == 1
    assert res[0]["id"] == s1


def test_song_recordings_relationship_and_fks(tmp_path: Path):
    """Test linking recordings to songs and foreign key enforcement."""
    db_file = tmp_path / "rec_fk.sqlite"
    init_db(db_file)

    src_id = add_source(
        title="Field Audio Archive",
        year=2015,
        type="audio_archive",
        license="CC-BY-NC-4.0",
        db_path=db_file,
    )

    song_id = add_folk_song(
        title="दामनानै मेथाय",
        song_type="dance_song",
        db_path=db_file,
    )

    rec_id = add_song_recording(
        song_id=song_id,
        performer="Bodo Troupe",
        recording_date="2015-04-14",
        audio_format="wav",
        duration_seconds=185,
        location="Dotma, Kokrajhar",
        source_id=src_id,
        consent_status="granted",
        consent_document_ref="consents/2015_01.pdf",
        permit_attribution=True,
        permit_transcribe=True,
        permit_redistribute=True,
        db_path=db_file,
    )

    recs = get_recordings(song_id, db_path=db_file)
    assert len(recs) == 1
    assert recs[0]["id"] == rec_id
    assert recs[0]["performer"] == "Bodo Troupe"
    assert recs[0]["duration_seconds"] == 185
    assert recs[0]["permit_redistribute"] == 1
    assert recs[0]["source_title"] == "Field Audio Archive"

    single = get_recording(rec_id, db_path=db_file)
    assert single is not None
    assert single["song_title"] == "दामनानै मेथाय"

    # Foreign key check on non-existent song_id
    with pytest.raises((sqlite3.IntegrityError, ValueError)):
        add_song_recording(
            song_id=99999,
            audio_format="mp3",
            consent_status="unknown",
            db_path=db_file,
        )

    # Foreign key check on non-existent source_id
    with pytest.raises((sqlite3.IntegrityError, ValueError)):
        add_folk_song(
            title="Non-existent Source Song",
            song_type="work_song",
            source_id=88888,
            db_path=db_file,
        )


def test_unknown_and_approximate_dates(tmp_path: Path):
    """Verify unknown and approximate dates remain unknown without guessing."""
    db_file = tmp_path / "dates.sqlite"
    init_db(db_file)

    song_id = add_folk_song(
        title="Traditional Ancient Lullaby",
        song_type="lullaby",
        year=None,
        date_precision="approximate",
        db_path=db_file,
    )
    rec_id = add_song_recording(
        song_id=song_id,
        audio_format="mp3",
        recording_date=None,
        duration_seconds=None,
        consent_status="unknown",
        db_path=db_file,
    )

    song = get_folk_song(song_id, db_path=db_file)
    assert song["year"] is None
    assert song["date_precision"] == "approximate"

    recording = get_recording(rec_id, db_path=db_file)
    assert recording["recording_date"] is None
    assert recording["duration_seconds"] is None


def test_duplicate_detection_and_conflict_handling(tmp_path: Path):
    """Test duplicate detection for folk songs and recordings."""
    db_file = tmp_path / "dup_test.sqlite"
    init_db(db_file)

    add_folk_song_item(
        song_id=101,
        title="Unique Song",
        song_type="festival_song",
        db_path=db_file,
    )

    # Duplicate song_id with raise_on_duplicate=True
    with pytest.raises(ValueError, match="already exists"):
        add_folk_song(
            song_id=101,
            title="Duplicate Song",
            song_type="work_song",
            raise_on_duplicate=True,
            db_path=db_file,
        )

    # Duplicate song_id with raise_on_duplicate=False
    res = add_folk_song(
        song_id=101,
        title="Duplicate Song",
        song_type="work_song",
        raise_on_duplicate=False,
        db_path=db_file,
    )
    assert res is None

    # Duplicate recording_id
    add_song_recording_item(
        recording_id=201,
        song_id=101,
        audio_format="mp3",
        consent_status="unknown",
        db_path=db_file,
    )

    with pytest.raises(ValueError, match="already exists"):
        add_song_recording(
            recording_id=201,
            song_id=101,
            audio_format="wav",
            consent_status="unknown",
            raise_on_duplicate=True,
            db_path=db_file,
        )


def test_citation_auditing_and_unverified(tmp_path: Path):
    """Test auditing of missing citations and unverified songs."""
    db_file = tmp_path / "audit_test.sqlite"
    init_db(db_file)

    src_id = add_source(
        title="Authentic Bodo Folk Documentation",
        author="Academic Press",
        year=2000,
        type="monograph",
        license="CC-BY-4.0",
        db_path=db_file,
    )

    # Song with no citation
    s_no_cite = add_folk_song(
        title="Uncited Song",
        song_type="work_song",
        source_id=None,
        confidence="needs_check",
        db_path=db_file,
    )

    # Song with valid citation
    s_cited = add_folk_song(
        title="Cited Song",
        song_type="dance_song",
        source_id=src_id,
        confidence="verified",
        verified_by="Researcher",
        verified_on="2026-10-22",
        db_path=db_file,
    )

    missing = get_folk_songs_missing_citations(db_path=db_file)
    assert len(missing) == 1
    assert missing[0]["id"] == s_no_cite
    assert "No source_id" in missing[0]["missing_reason"]
    assert s_cited not in [m["id"] for m in missing]

    unverified = get_unverified_folk_songs(db_path=db_file)
    assert len(unverified) == 1
    assert unverified[0]["id"] == s_no_cite


def test_consent_states_and_auditing(tmp_path: Path):
    """Test auditing recordings lacking ethical consent."""
    db_file = tmp_path / "consent_audit.sqlite"
    init_db(db_file)

    song_id = add_folk_song(
        title="Consent Test Song",
        song_type="lullaby",
        db_path=db_file,
    )

    # Unknown consent
    r_unk = add_song_recording(
        song_id=song_id,
        audio_format="mp3",
        consent_status="unknown",
        db_path=db_file,
    )
    # Pending consent
    r_pend = add_song_recording(
        song_id=song_id,
        audio_format="mp3",
        consent_status="pending",
        db_path=db_file,
    )
    # Denied consent
    r_den = add_song_recording(
        song_id=song_id,
        audio_format="mp3",
        consent_status="denied",
        db_path=db_file,
    )
    # Granted consent
    r_grant = add_song_recording(
        song_id=song_id,
        audio_format="wav",
        consent_status="granted",
        consent_document_ref="docs/grant.pdf",
        db_path=db_file,
    )

    flagged = get_recordings_missing_consent(db_path=db_file)
    flagged_ids = [f["id"] for f in flagged]
    assert r_unk in flagged_ids
    assert r_pend in flagged_ids
    assert r_den in flagged_ids
    assert r_grant not in flagged_ids


def test_consent_withdrawal_and_removal_request(tmp_path: Path):
    """Test consent withdrawal and immediate removal request workflows."""
    db_file = tmp_path / "withdrawal.sqlite"
    init_db(db_file)

    song_id = add_folk_song(
        title="Revocation Song",
        song_type="traditional_folk",
        db_path=db_file,
    )

    r1 = add_song_recording(
        song_id=song_id,
        performer="Elder Troupe",
        audio_format="flac",
        consent_status="granted",
        consent_document_ref="docs/troupe.pdf",
        permit_redistribute=True,
        permit_transcribe=True,
        db_path=db_file,
    )
    r2 = add_song_recording(
        song_id=song_id,
        performer="Sacred Priest",
        audio_format="wav",
        consent_status="granted",
        consent_document_ref="docs/priest.pdf",
        permit_redistribute=True,
        db_path=db_file,
    )

    # Withdraw consent for r1
    ok = withdraw_recording_consent(
        recording_id=r1,
        reason="Artist requested revocation",
        withdrawn_by="Field Archivist",
        db_path=db_file,
    )
    assert ok is True

    rec1 = get_recording(r1, db_path=db_file)
    assert rec1["consent_status"] == "withdrawn"
    assert rec1["permit_redistribute"] == 0
    assert rec1["consent_withdrawn_at"] is not None
    assert "Artist requested revocation" in rec1["consent_notes"]

    # Removal request for r2
    ok2 = request_recording_removal(
        recording_id=r2,
        reason="Sacred ritual restriction",
        requested_by="Village Council",
        db_path=db_file,
    )
    assert ok2 is True

    rec2 = get_recording(r2, db_path=db_file)
    assert rec2["removal_requested"] == 1
    assert rec2["consent_status"] == "withdrawn"
    assert rec2["permit_redistribute"] == 0
    assert "Sacred ritual restriction" in rec2["removal_reason"]

    # When querying recordings with include_withdrawn=False, both are filtered out
    assert len(get_recordings(song_id, db_path=db_file, include_withdrawn=False)) == 0
    # When include_withdrawn=True, both are returned
    assert len(get_recordings(song_id, db_path=db_file, include_withdrawn=True)) == 2


def test_idempotent_migrations(tmp_path: Path):
    """Verify running init_db multiple times does not corrupt existing data."""
    db_file = tmp_path / "idempotent.sqlite"
    init_db(db_file)

    song_id = add_folk_song(
        title="Migration Preservation Song",
        song_type="festival_song",
        db_path=db_file,
    )
    rec_id = add_song_recording(
        song_id=song_id,
        audio_format="mp3",
        consent_status="unknown",
        db_path=db_file,
    )

    # Run init_db multiple times
    init_db(db_file)
    init_db(db_file)
    init_db(db_file)

    song = get_folk_song(song_id, db_path=db_file)
    assert song is not None
    assert song["title"] == "Migration Preservation Song"

    rec = get_recording(rec_id, db_path=db_file)
    assert rec is not None
    assert rec["song_id"] == song_id


def test_csv_and_json_export_and_import(tmp_path: Path):
    """Test CSV and JSON export and import with dry runs and backup."""
    db_file = tmp_path / "export_import.sqlite"
    init_db(db_file)

    add_folk_song(
        title="हाबिला फागून",
        roman_title="Habila Phagun",
        song_type="festival_song",
        region="Kokrajhar",
        community="Bodo",
        instruments=["Kham", "Siphung"],
        festivals=["Bwisagu"],
        confidence="verified",
        verified_by="Researcher",
        verified_on="2026-10-22",
        db_path=db_file,
    )
    add_folk_song(
        title="दामनानै मेथाय",
        roman_title="Damnanwi Methai",
        song_type="dance_song",
        region="Udalguri",
        community="Bodo",
        instruments=["Serja"],
        confidence="needs_check",
        db_path=db_file,
    )

    csv_file = tmp_path / "songs.csv"
    json_file = tmp_path / "songs.json"

    # Export CSV
    exported_csv_count = export_folk_songs_csv(csv_file, db_path=db_file)
    assert exported_csv_count == 2
    assert csv_file.exists()

    with csv_file.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["title"] in ("हाबिला फागून", "दामनानै मेथाय")
        assert "audio_binary" not in rows[0]
        for col in CSV_FOLK_SONG_COLUMNS:
            assert col in rows[0]

    # Export JSON
    exported_json_count = export_folk_songs_json(json_file, db_path=db_file)
    assert exported_json_count == 2
    assert json_file.exists()

    with json_file.open(encoding="utf-8") as f:
        data = json.load(f)
        assert len(data) == 2
        assert data[0]["instruments"] is not None

    # Dry-run CSV import into fresh DB
    fresh_db = tmp_path / "fresh.sqlite"
    init_db(fresh_db)

    dry_stats = import_folk_songs_csv(csv_file, db_path=fresh_db, dry_run=True)
    assert dry_stats["total"] == 2
    assert dry_stats["imported"] == 2
    assert dry_stats["rejected"] == 0
    # In dry run, DB should still be empty
    assert len(filter_folk_songs(db_path=fresh_db)) == 0

    # Real import CSV
    real_stats = import_folk_songs_csv(csv_file, db_path=fresh_db, dry_run=False)
    assert real_stats["total"] == 2
    assert real_stats["imported"] == 2
    assert len(filter_folk_songs(db_path=fresh_db)) == 2
    assert Path(real_stats["backup_path"]).exists()

    # Re-import should report duplicate conflicts
    dup_stats = import_folk_songs_csv(csv_file, db_path=fresh_db, dry_run=False)
    assert dup_stats["rejected"] == 2
    assert len(dup_stats["errors"]) == 2

    # Import with invalid row
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text(
        "title,song_type\n,festival_song\nSong with bad type,heavy_metal\n",
        encoding="utf-8",
    )
    bad_stats = import_folk_songs_csv(bad_csv, db_path=fresh_db, dry_run=False)
    assert bad_stats["rejected"] == 2
    assert any("title" in e.lower() for e in bad_stats["errors"])
    assert any("must be one of" in e.lower() for e in bad_stats["errors"])

    # JSON import into another fresh DB
    json_db = tmp_path / "json_db.sqlite"
    init_db(json_db)
    json_stats = import_folk_songs_json(json_file, db_path=json_db, dry_run=False)
    assert json_stats["imported"] == 2
    assert len(filter_folk_songs(db_path=json_db)) == 2


def test_cli_extended_subcommands(tmp_path: Path):
    """Test all new Step 5 CLI subcommands."""
    db_file = tmp_path / "cli_subcommands.sqlite"
    init_db(db_file)

    song_id = add_folk_song(
        title="बोर' मेथाय",
        roman_title="Boro Methai",
        song_type="festival_song",
        region="Kokrajhar",
        instruments=["Kham", "Siphung"],
        confidence="needs_check",
        db_path=db_file,
    )
    rec_id = add_song_recording(
        song_id=song_id,
        performer="Troupe",
        audio_format="mp3",
        consent_status="unknown",
        db_path=db_file,
    )

    # CLI search
    assert main(["search", "Boro", "--db", str(db_file)]) == 0

    # CLI filter
    assert main(["filter", "--type", "festival_song", "--db", str(db_file)]) == 0

    # CLI recordings
    assert main(["recordings", str(song_id), "--db", str(db_file)]) == 0
    assert main(["recordings", "--song-id", str(song_id), "--db", str(db_file)]) == 0

    # CLI missing-citations
    assert main(["missing-citations", "--db", str(db_file)]) == 0

    # CLI unverified
    assert main(["unverified", "--db", str(db_file)]) == 0

    # CLI missing-consent
    assert main(["missing-consent", "--db", str(db_file)]) == 0

    # CLI withdraw-consent
    assert (
        main(
            [
                "withdraw-consent",
                str(rec_id),
                "--reason",
                "Performer requested",
                "--db",
                str(db_file),
            ]
        )
        == 0
    )

    # CLI request-removal
    assert (
        main(
            [
                "request-removal",
                str(rec_id),
                "--reason",
                "Sacred restriction",
                "--db",
                str(db_file),
            ]
        )
        == 0
    )

    # CLI export
    csv_out = tmp_path / "cli_out.csv"
    assert main(["export", "--csv", str(csv_out), "--db", str(db_file)]) == 0
    assert csv_out.exists()

    # CLI import dry-run
    assert (
        main(
            [
                "import",
                "--csv",
                str(csv_out),
                "--dry-run",
                "--db",
                str(db_file),
            ]
        )
        == 0
    )
