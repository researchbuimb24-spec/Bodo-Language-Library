import sqlite3
from datetime import date, timedelta

import pytest

from bhasha_lib.culture import load_culture_dir
from bhasha_lib.db import add_culture_item, add_source, get_connection, init_db
from bhasha_lib.timeline import (
    add_historical_event,
    filter_events,
    format_year_range,
    get_event,
    get_events_missing_citations,
    get_historical_event,
    get_timeline,
    get_unverified_events,
    main,
    print_timeline,
    search_events,
    validate_historical_event,
)


def test_timeline_loads_and_sorts_chronologically(tmp_path):
    """Verify get_timeline returns only items with year_start sorted chronologically."""
    db_file = tmp_path / "timeline_test.sqlite"
    init_db(db_file)

    add_culture_item(
        category="history",
        title="Script Accord",
        description="Agreement to adopt Devanagari script.",
        year_start=1975,
        confidence="verified",
        db_path=db_file,
    )
    add_culture_item(
        category="history",
        title="Sabha Foundation",
        description="Bodo Sahitya Sabha was founded in Basugaon.",
        year_start=1952,
        confidence="needs_check",
        db_path=db_file,
    )
    add_culture_item(
        category="history",
        title="Primary Medium",
        description="Bodo introduced as primary medium of instruction.",
        year_start=1963,
        confidence="verified",
        db_path=db_file,
    )
    add_culture_item(
        category="dance",
        title="Bagurumba",
        description="Traditional folk dance without specific historical year.",
        year_start=None,
        db_path=db_file,
    )

    events = get_timeline(db_file)
    assert len(events) == 3

    years = [e["year_start"] for e in events]
    titles = [e["title"] for e in events]

    assert years == [1952, 1963, 1975]
    assert titles == ["Sabha Foundation", "Primary Medium", "Script Accord"]
    assert events[0]["confidence"] == "needs_check"
    assert events[1]["confidence"] == "verified"


def test_timeline_same_year_sorting(tmp_path):
    """Verify events in the same year are properly ordered and formatted."""
    db_file = tmp_path / "same_year.sqlite"
    init_db(db_file)

    add_culture_item(
        category="history",
        title="Bodo lipi ka itihaas",
        description="Script evolution overview.",
        year_start=1952,
        year_end=1975,
        confidence="needs_check",
        db_path=db_file,
    )
    add_culture_item(
        category="history",
        title="Bodo Sahitya Sabha",
        description="Foundation in Basugaon.",
        year_start=1952,
        year_end=None,
        confidence="needs_check",
        db_path=db_file,
    )

    events = get_timeline(db_file)
    assert len(events) == 2

    assert events[0]["title"] == "Bodo Sahitya Sabha"
    assert events[0]["year_start"] == 1952
    assert events[0]["year_end"] is None

    assert events[1]["title"] == "Bodo lipi ka itihaas"
    assert events[1]["year_start"] == 1952
    assert events[1]["year_end"] == 1975

    assert format_year_range(1952, None) == "1952"
    assert format_year_range(1952, 1975) == "1952 - 1975"


def test_timeline_filters_by_category_and_year_range(tmp_path):
    """Verify filtering by category, from_year, and to_year."""
    db_file = tmp_path / "filter_test.sqlite"
    init_db(db_file)

    add_culture_item(
        category="history",
        title="Event 1952",
        year_start=1952,
        db_path=db_file,
    )
    add_culture_item(
        category="history",
        title="Event 1963",
        year_start=1963,
        db_path=db_file,
    )
    add_culture_item(
        category="festival",
        title="Festival 1963",
        year_start=1963,
        db_path=db_file,
    )
    add_culture_item(
        category="history",
        title="Event 1975",
        year_start=1975,
        db_path=db_file,
    )

    # Filter by category
    hist_only = get_timeline(db_file, category="history")
    assert len(hist_only) == 3

    # Filter by year range using filter_events and get_timeline
    range_events = filter_events(db_file, from_year=1960, to_year=1970)
    assert len(range_events) == 2
    assert {e["title"] for e in range_events} == {"Event 1963", "Festival 1963"}


def test_load_history_files_with_timeline_keys(tmp_path):
    """Verify load_culture_dir parses year_start, year_end, and confidence."""
    history_dir = tmp_path / "history"
    history_dir.mkdir()

    md_content = """---
category: history
title: Kokrajhar Medium Accord
region: Assam
year_start: 1963
confidence: needs_check
source: Historical Records
related_words: []
---
Bodo language medium declaration at Kokrajhar.
"""
    (history_dir / "medium.md").write_text(md_content, encoding="utf-8")

    db_file = tmp_path / "history_parse.sqlite"
    init_db(db_file)

    loaded = load_culture_dir(history_dir, db_path=db_file)
    assert len(loaded) == 1

    with get_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT category, title, year_start, year_end, confidence
            FROM culture_items
            WHERE id = ?
            """,
            (loaded[0],),
        )
        row = cursor.fetchone()
        assert row["category"] == "history"
        assert row["title"] == "Kokrajhar Medium Accord"
        assert row["year_start"] == 1963
        assert row["year_end"] is None
        assert row["confidence"] == "needs_check"


def test_timeline_cli_and_printing(tmp_path, capsys):
    """Verify timeline CLI output formatting."""
    db_file = tmp_path / "cli_timeline.sqlite"
    init_db(db_file)

    add_culture_item(
        category="history",
        title="Bodo Sahitya Sabha",
        description="Foundation in Basugaon.",
        region="Assam",
        year_start=1952,
        confidence="needs_check",
        db_path=db_file,
    )

    exit_code = main(["--db", str(db_file)])
    assert exit_code == 0

    out = capsys.readouterr().out
    assert "1952: Bodo Sahitya Sabha (Assam) - history [needs_check]" in out
    assert "Foundation in Basugaon." in out

    # Empty timeline output
    empty_db = tmp_path / "empty.sqlite"
    init_db(empty_db)
    print_timeline([])
    empty_out = capsys.readouterr().out
    assert "No timeline events found." in empty_out


def test_historical_event_creation_and_retrieval(tmp_path):
    """Verify creation and retrieval of rich historical event records."""
    db_file = tmp_path / "event_create.sqlite"
    init_db(db_file)

    event_id = add_historical_event(
        title="Bodo Sahitya Sabha Foundation",
        description="Founded on 16 November 1952 at Basugaon.",
        year_start=1952,
        date_precision="exact",
        category="history",
        people=["Joy Bhadra Hagjer", "Sonaram Thaosen"],
        places=["Basugaon", "Kokrajhar", "Assam"],
        organizations=["Bodo Sahitya Sabha"],
        primary_sources=["Sabha Resolution 1952"],
        secondary_sources=["Bodo Sahitya Sabha Official Chronicle"],
        source_title="Sabha Foundation Archival Dossier",
        source_url="https://bihung.org/history",
        license="CC-BY-SA-4.0",
        confidence="needs_check",
        db_path=db_file,
    )
    assert isinstance(event_id, int)
    assert event_id > 0

    event = get_historical_event(event_id, db_path=db_file)
    assert event is not None
    assert event["title"] == "Bodo Sahitya Sabha Foundation"
    assert event["year_start"] == 1952
    assert event["year_end"] is None
    assert event["date_precision"] == "exact"
    assert "Joy Bhadra Hagjer" in event["people"]
    assert "Sonaram Thaosen" in event["people"]
    assert "Basugaon" in event["places"]
    assert "Bodo Sahitya Sabha" in event["organizations"]
    assert event["source_title"] == "Sabha Foundation Archival Dossier"
    assert event["source_license"] == "CC-BY-SA-4.0"
    assert event["confidence"] == "needs_check"

    # Alias get_event
    alias_event = get_event(event_id, db_path=db_file)
    assert alias_event == event

    # Non-existent ID returns None
    assert get_historical_event(999999, db_path=db_file) is None


def test_chronological_sorting_directions(tmp_path):
    """Verify chronological ordering in ASC and DESC directions."""
    db_file = tmp_path / "sort_test.sqlite"
    init_db(db_file)

    add_historical_event(
        title="Eighth Schedule Inclusion",
        description="Bodo added to 8th Schedule of Indian Constitution.",
        year_start=2003,
        db_path=db_file,
    )
    add_historical_event(
        title="Anderson Folktales Publication",
        description="J. D. Anderson published Kachari Folk-Tales and Rhymes.",
        year_start=1895,
        db_path=db_file,
    )
    add_historical_event(
        title="Primary Education Accord",
        description="Introduction of Bodo as primary medium.",
        year_start=1963,
        db_path=db_file,
    )

    asc_events = get_timeline(db_file, sort_order="asc")
    assert [e["year_start"] for e in asc_events] == [1895, 1963, 2003]

    desc_events = get_timeline(db_file, sort_order="desc")
    assert [e["year_start"] for e in desc_events] == [2003, 1963, 1895]


def test_approximate_and_unknown_dates(tmp_path):
    """Verify safe handling of approximate and unknown dates."""
    db_file = tmp_path / "approx_dates.sqlite"
    init_db(db_file)

    # Event with approximate single year
    add_historical_event(
        title="Early Oral Epic Traditions",
        description="Origins of oral narratives passed down across generations.",
        year_start=1880,
        date_precision="approximate",
        db_path=db_file,
    )
    # Event with approximate year range
    add_historical_event(
        title="Folk Song Transcriptions Era",
        description="Earliest missionary efforts to collect Kachari rhymes.",
        year_start=1885,
        year_end=1895,
        date_precision="approximate",
        db_path=db_file,
    )
    # Event with unknown date
    add_historical_event(
        title="Ancient Kherai Chant Origins",
        description="Traditional Bathou ritual chants of undetermined antiquity.",
        year_start=None,
        date_precision="unknown",
        db_path=db_file,
    )

    # Exclude unknown dates by default
    known_events = get_timeline(db_file, include_unknown_dates=False)
    assert len(known_events) == 2
    assert all(e["year_start"] is not None for e in known_events)

    # Include unknown dates (placed safely at the end)
    all_events = get_timeline(db_file, include_unknown_dates=True)
    assert len(all_events) == 3
    assert all_events[-1]["title"] == "Ancient Kherai Chant Origins"
    assert all_events[-1]["year_start"] is None

    # Format year range checks
    assert (
        format_year_range(1880, None, precision="approximate") == "c. 1880"
    )
    assert (
        format_year_range(1885, 1895, precision="approximate")
        == "c. 1885 - 1895"
    )
    assert format_year_range(None, None, precision="unknown") == "Unknown"
    assert format_year_range(1950, None, precision="exact") == "1950"


def test_invalid_date_ranges_and_metadata_validation(tmp_path):
    """Verify validation logic rejects invalid date intervals and malformed metadata."""
    db_file = tmp_path / "invalid_data.sqlite"
    init_db(db_file)

    # End year earlier than start year
    with pytest.raises(ValueError, match="cannot be earlier than start year"):
        add_historical_event(
            title="Inverted Interval Event",
            description="Testing inverted years.",
            year_start=1975,
            year_end=1952,
            db_path=db_file,
        )

    # Missing title
    with pytest.raises(ValueError, match="title"):
        add_historical_event(
            title="",
            description="Missing title event.",
            year_start=1952,
            db_path=db_file,
        )

    # Missing description
    with pytest.raises(ValueError, match="description"):
        add_historical_event(
            title="Valid Title",
            description="",
            year_start=1952,
            db_path=db_file,
        )

    # Invalid precision type
    with pytest.raises(ValueError, match="date_precision"):
        add_historical_event(
            title="Bad Precision",
            description="Invalid precision test.",
            year_start=1952,
            date_precision="unsupported_precision",
            db_path=db_file,
        )

    # Invalid confidence status
    with pytest.raises(ValueError, match="confidence"):
        add_historical_event(
            title="Bad Confidence",
            description="Invalid confidence status test.",
            year_start=1952,
            confidence="totally_true",
            db_path=db_file,
        )

    # 'verified' requires verified_on date
    with pytest.raises(ValueError, match="verified_on"):
        add_historical_event(
            title="Verified Without Date",
            description="Missing verified_on date.",
            year_start=1952,
            confidence="verified",
            verified_on=None,
            db_path=db_file,
        )

    # 'verified' with future date is rejected
    future_date = (date.today() + timedelta(days=5)).isoformat()
    with pytest.raises(ValueError, match="future"):
        add_historical_event(
            title="Verified Future",
            description="Future verification date.",
            year_start=1952,
            confidence="verified",
            verified_on=future_date,
            db_path=db_file,
        )

    # validate_historical_event standalone checks
    errs = validate_historical_event(
        {"title": "Test", "description": "Desc", "year_start": "not_an_int"}
    )
    assert any("year_start" in e for e in errs)


def test_missing_citations_detection(tmp_path):
    """Verify detection of events lacking sufficient or verified citations."""
    db_file = tmp_path / "citations_test.sqlite"
    init_db(db_file)

    # 1. Event with no source or citations
    add_historical_event(
        title="Uncited Folklore Milestone",
        description="Unsubstantiated claim with zero references.",
        year_start=1920,
        db_path=db_file,
    )

    # 2. Event with only generic/vague source
    add_historical_event(
        title="Generic Domain Cited Event",
        description="Referenced solely to Wikipedia without article title.",
        year_start=1960,
        source_title="Wikipedia",
        db_path=db_file,
    )

    # 3. Event with short source title (< 15 chars)
    add_historical_event(
        title="Short Cited Event",
        description="Source is too short to be descriptive.",
        year_start=1970,
        source_title="Book Note",
        db_path=db_file,
    )

    # 4. Event with well-formed citation
    add_historical_event(
        title="Fully Sourced Historical Milestone",
        description="Comprehensive citations and archival references.",
        year_start=1952,
        source_title="Assam Government Gazette Notification No. 142/1952",
        primary_sources=["Official Gazette 1952"],
        secondary_sources=["Bodo Sahitya Sabha Golden Jubilee Commemorative Volume"],
        license="public_domain",
        db_path=db_file,
    )

    missing = get_events_missing_citations(db_path=db_file)
    assert len(missing) == 3

    flagged_titles = {e["title"] for e in missing}
    assert flagged_titles == {
        "Uncited Folklore Milestone",
        "Generic Domain Cited Event",
        "Short Cited Event",
    }
    assert "Fully Sourced Historical Milestone" not in flagged_titles

    for event in missing:
        assert "missing_reason" in event
        assert len(event["missing_reason"]) > 0


def test_verification_status_and_unverified_events(tmp_path):
    """Verify categorization of verified, disputed, and unverified records."""
    db_file = tmp_path / "verification_test.sqlite"
    init_db(db_file)

    add_historical_event(
        title="Verified Event",
        description="Officially corroborated historical event.",
        year_start=1952,
        confidence="verified",
        verified_on=date.today().isoformat(),
        source_title="Verified State Gazette Vol. 12",
        db_path=db_file,
    )
    add_historical_event(
        title="Needs Check Event",
        description="Preliminary entry awaiting archival confirmation.",
        year_start=1963,
        confidence="needs_check",
        db_path=db_file,
    )
    add_historical_event(
        title="Disputed Event",
        description="Contested date or attribution under scholarly debate.",
        year_start=1970,
        confidence="disputed",
        db_path=db_file,
    )
    add_historical_event(
        title="Unverified Event",
        description="Unverified community submission.",
        year_start=1975,
        confidence="unverified",
        db_path=db_file,
    )

    unverified_list = get_unverified_events(db_path=db_file)
    assert len(unverified_list) == 3

    unverified_titles = [e["title"] for e in unverified_list]
    assert "Verified Event" not in unverified_titles
    assert "Needs Check Event" in unverified_titles
    assert "Disputed Event" in unverified_titles
    assert "Unverified Event" in unverified_titles


def test_duplicate_handling(tmp_path):
    """Verify duplicate handling with raise_on_duplicate flag."""
    db_file = tmp_path / "duplicate_test.sqlite"
    init_db(db_file)

    id1 = add_historical_event(
        title="Tripartite Bodo Accord",
        description="Initial accord summary.",
        year_start=1993,
        category="history",
        db_path=db_file,
    )

    # With raise_on_duplicate=True: raises ValueError
    with pytest.raises(ValueError, match="already exists"):
        add_historical_event(
            title="Tripartite Bodo Accord",
            description="Duplicate attempt.",
            year_start=1993,
            category="history",
            raise_on_duplicate=True,
            db_path=db_file,
        )

    # With raise_on_duplicate=False (default): updates existing record
    id2 = add_historical_event(
        title="Tripartite Bodo Accord",
        description="Updated accord details with Bodoland Autonomous Council.",
        year_start=1993,
        category="history",
        places=["Kokrajhar", "Guwahati"],
        raise_on_duplicate=False,
        db_path=db_file,
    )
    assert id1 == id2

    event = get_historical_event(id1, db_path=db_file)
    assert (
        event["description"]
        == "Updated accord details with Bodoland Autonomous Council."
    )
    assert event["places"] == "Kokrajhar, Guwahati"


def test_sqlite_foreign_key_enforcement(tmp_path):
    """Verify foreign-key integrity prevents invalid source_id linking."""
    db_file = tmp_path / "fk_enforce.sqlite"
    init_db(db_file)

    valid_src_id = add_source(
        title="Authenticated Archival Monograph",
        license="CC-BY-4.0",
        db_path=db_file,
    )

    # Valid source_id succeeds
    ev_id = add_historical_event(
        title="Valid Source Event",
        description="Linked to valid source record.",
        year_start=1952,
        source_id=valid_src_id,
        db_path=db_file,
    )
    assert ev_id > 0

    # Non-existent source_id fails with sqlite3.IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        add_historical_event(
            title="Broken FK Event",
            description="Linked to invalid source record.",
            year_start=1963,
            source_id=9876543,
            db_path=db_file,
        )


def test_search_events(tmp_path):
    """Verify searching across titles, descriptions, people, places, and orgs."""
    db_file = tmp_path / "search_test.sqlite"
    init_db(db_file)

    add_historical_event(
        title="Formation of Bodo Sahitya Sabha",
        description="First conference held in Basugaon.",
        year_start=1952,
        people=["Joy Bhadra Hagjer", "Sonaram Thaosen"],
        places=["Basugaon", "Kokrajhar"],
        organizations=["Bodo Sahitya Sabha"],
        db_path=db_file,
    )
    add_historical_event(
        title="Implementation of Bodo Medium",
        description=(
            "Assam CM Bimala Prasad Chaliha introduced Bodo in primary schools."
        ),
        year_start=1963,
        people=["Bimala Prasad Chaliha"],
        places=["Kokrajhar"],
        db_path=db_file,
    )

    # Search by person name
    by_person = search_events("Joy Bhadra", db_path=db_file)
    assert len(by_person) == 1
    assert by_person[0]["title"] == "Formation of Bodo Sahitya Sabha"

    # Search by organization
    by_org = search_events("Bodo Sahitya Sabha", db_path=db_file)
    assert len(by_org) == 1

    # Search by place matching multiple
    by_place = search_events("Kokrajhar", db_path=db_file)
    assert len(by_place) == 2

    # Search by wildcard/special characters (safe escaping)
    assert search_events("%", db_path=db_file) == []
    assert search_events("", db_path=db_file) == []


def test_database_migrations_and_existing_record_preservation(tmp_path):
    """Verify database schema migrations add new columns without data loss."""
    legacy_db = tmp_path / "legacy.sqlite"

    # Build a legacy database simulating Step 1 schema without Step 3 columns
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
            """
            CREATE TABLE culture_items (
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
                confidence TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO sources (id, title, license)
            VALUES (1, 'Legacy Source Document', 'public_domain');
            """
        )
        conn.execute(
            """
            INSERT INTO culture_items (
                id, category, title, description, year_start, source_id, confidence
            )
            VALUES (
                1, 'history', 'Pre-existing Event', 'Legacy description.',
                1952, 1, 'needs_check'
            );
            """
        )
        conn.commit()

    # Apply idempotent init_db migration
    init_db(legacy_db)

    # Verify legacy item is intact with newly added columns
    event = get_historical_event(1, db_path=legacy_db)
    assert event is not None
    assert event["title"] == "Pre-existing Event"
    assert event["year_start"] == 1952
    assert event["confidence"] == "needs_check"
    assert event["date_precision"] == "exact"
    assert event["source_title"] == "Legacy Source Document"

    # Add a new Step 3 event with extended columns
    new_id = add_historical_event(
        title="Migrated World Event",
        description="Testing post-migration event insertion.",
        year_start=2000,
        date_precision="range",
        year_end=2005,
        people=["Leader Name"],
        db_path=legacy_db,
    )
    assert new_id > 1

    migrated_timeline = get_timeline(legacy_db)
    assert len(migrated_timeline) == 2
    assert [e["title"] for e in migrated_timeline] == [
        "Pre-existing Event",
        "Migrated World Event",
    ]


def test_timeline_cli_additional_modes(tmp_path, capsys):
    """Verify CLI switches for unverified, citations, search, and verbose."""
    db_file = tmp_path / "cli_extended.sqlite"
    init_db(db_file)

    add_historical_event(
        title="Archival Milestone Event",
        description="Description for search and citation testing.",
        year_start=1952,
        people=["Scholar Name"],
        organizations=["Culture Society"],
        source_title="Short",
        confidence="needs_check",
        db_path=db_file,
    )

    # 1. Test --search flag
    code = main(["--db", str(db_file), "--search", "Scholar Name"])
    assert code == 0
    search_out = capsys.readouterr().out
    assert "Archival Milestone Event" in search_out

    # 2. Test --missing-citations flag
    code = main(["--db", str(db_file), "--missing-citations"])
    assert code == 0
    missing_out = capsys.readouterr().out
    assert "Events with Missing or Insufficient Citations" in missing_out
    assert "Archival Milestone Event" in missing_out

    # 3. Test --unverified flag
    code = main(["--db", str(db_file), "--unverified"])
    assert code == 0
    unverified_out = capsys.readouterr().out
    assert "[needs_check]" in unverified_out

    # 4. Test --verbose flag
    code = main(["--db", str(db_file), "--verbose"])
    assert code == 0
    verb_out = capsys.readouterr().out
    assert "People: Scholar Name" in verb_out
    assert "Organizations: Culture Society" in verb_out
