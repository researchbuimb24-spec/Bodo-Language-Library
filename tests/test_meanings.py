import csv

import pytest

from bhasha_lib.db import (
    add_occurrence,
    add_word,
    get_connection,
    init_db,
    search_word,
)
from bhasha_lib.meanings import (
    CONTEXT_1_COL,
    CONTEXT_2_COL,
    CSV_FIELDNAMES,
    REQUIRED_CSV_FIELDS,
    export_for_review,
    get_meanings_stats,
    get_progress_stats,
    import_meanings,
    import_reviewed_csv,
    main,
    print_progress,
    print_stats,
    validate_review_csv,
)


def test_export_writes_empty_meanings_and_correct_columns(tmp_path):
    db_file = tmp_path / "export_test.sqlite"
    init_db(db_file)

    # Word 1: no meaning (should be exported)
    add_word(word="बर'", roman="boro", freq=5, db_path=db_file)
    # Word 2: has Hindi meaning (should NOT be exported)
    add_word(
        word="गाहाम",
        roman="gaham",
        meaning_hi="अच्छा",
        freq=3,
        db_path=db_file,
    )
    # Word 3: has English meaning (should NOT be exported)
    add_word(
        word="राव",
        roman="rao",
        meaning_en="language",
        freq=2,
        db_path=db_file,
    )
    # Word 4: no meaning (should be exported)
    add_word(word="आफा", roman="afa", freq=1, db_path=db_file)

    csv_out = tmp_path / "review_out.csv"
    count = export_for_review(db_file, csv_out, limit=500, only_empty=True)

    assert count == 2
    assert csv_out.is_file()

    with open(csv_out, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == CSV_FIELDNAMES
        rows = list(reader)

    exported_words = {r["word"] for r in rows}
    assert exported_words == {"बर'", "आफा"}
    assert "गाहाम" not in exported_words
    assert "राव" not in exported_words


def test_import_updates_meanings_and_sets_status_and_verified_by(tmp_path):
    db_file = tmp_path / "import_test.sqlite"
    init_db(db_file)

    add_word(word="बर'", roman="boro", freq=5, db_path=db_file)
    w_initial = search_word("बर'", db_path=db_file)
    assert w_initial["status"] == "unverified"
    assert w_initial["verified_by"] is None

    # Prepare review CSV
    csv_file = tmp_path / "review_filled.csv"
    with open(csv_file, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerow(
            {
                "word": "बर'",
                "roman": "boro",
                "meaning_hi": "बोडो (भाषा/समुदाय)",
                "meaning_en": "Bodo language and people",
                "pos": "noun",
                "origin": "bodo",
                "dialect": "standard",
                "verified_by": "Dr. Brahma",
                "notes": "Verified native term",
            }
        )

    res = import_meanings(csv_file, db_file)
    assert res["updated"] == 1
    assert res["rejected"] == 0
    assert res["conflicts"] == 0

    w_after = search_word("बर'", db_path=db_file)
    assert w_after["meaning_hi"] == "बोडो (भाषा/समुदाय)"
    assert w_after["meaning_en"] == "Bodo language and people"
    assert w_after["origin"] == "bodo"
    assert w_after["status"] == "community"
    assert w_after["verified_by"] == "Dr. Brahma"
    assert w_after["freq"] == 5  # Word frequency must remain untouched


def test_empty_verified_by_is_rejected(tmp_path):
    db_file = tmp_path / "reject_test.sqlite"
    init_db(db_file)

    add_word(word="राव", roman="rao", db_path=db_file)

    csv_file = tmp_path / "no_verifier.csv"
    with open(csv_file, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        # meaning is provided but verified_by is empty
        writer.writerow(
            {
                "word": "राव",
                "roman": "rao",
                "meaning_hi": "भाषा",
                "meaning_en": "language",
                "origin": "bodo",
                "verified_by": "",
            }
        )

    res = import_meanings(csv_file, db_file)
    assert res["rejected"] == 1
    assert res["updated"] == 0

    # Ensure database record was NOT updated
    w = search_word("राव", db_path=db_file)
    assert w["meaning_hi"] is None
    assert w["status"] == "unverified"


def test_invalid_origin_is_rejected(tmp_path):
    db_file = tmp_path / "origin_test.sqlite"
    init_db(db_file)

    add_word(word="सम्पर्क", db_path=db_file)

    csv_file = tmp_path / "bad_origin.csv"
    with open(csv_file, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerow(
            {
                "word": "सम्पर्क",
                "meaning_hi": "संपर्क",
                "origin": "sanskrit_derived",  # Invalid, must be bodo, loan, or unsure
                "verified_by": "Linguist",
            }
        )

    res = import_meanings(csv_file, db_file)
    assert res["rejected"] == 1
    assert res["updated"] == 0


def test_existing_meaning_is_not_overwritten_and_conflicts(tmp_path):
    db_file = tmp_path / "conflict_test.sqlite"
    init_db(db_file)

    # Word already has an established meaning
    add_word(
        word="गाहाम",
        roman="gaham",
        meaning_hi="अच्छा, शुभ",
        meaning_en="good",
        db_path=db_file,
    )

    csv_file = tmp_path / "conflict.csv"
    with open(csv_file, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        # Incoming row gives conflicting Hindi meaning
        writer.writerow(
            {
                "word": "गाहाम",
                "meaning_hi": "खराब",
                "meaning_en": "good",
                "origin": "bodo",
                "verified_by": "Conflicting Contributor",
            }
        )

    res = import_meanings(csv_file, db_file)
    assert res["conflicts"] == 1
    assert res["updated"] == 0

    # Ensure original meaning in database was preserved
    w = search_word("गाहाम", db_path=db_file)
    assert w["meaning_hi"] == "अच्छा, शुभ"


def test_devanagari_round_trip_unchanged(tmp_path):
    db_file = tmp_path / "roundtrip_test.sqlite"
    init_db(db_file)

    original_word = "बर' राव"
    add_word(word=original_word, db_path=db_file)

    csv_file = tmp_path / "roundtrip.csv"
    export_for_review(db_file, csv_file, limit=10)

    # Read and fill in meaning while keeping word string intact
    with open(csv_file, encoding="utf-8-sig", newline="") as f:
        reader = list(csv.DictReader(f))

    assert reader[0]["word"] == original_word

    with open(csv_file, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerow(
            {
                "word": original_word,
                "roman": "boro rao",
                "meaning_hi": "बोडो भाषा",
                "meaning_en": "Bodo language",
                "origin": "bodo",
                "verified_by": "Native Speaker",
            }
        )

    import_meanings(csv_file, db_file)

    # Direct query to ensure exact Unicode character preservation
    with get_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT word, meaning_hi FROM words WHERE word = ?", (original_word,)
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == original_word
        assert row[1] == "बोडो भाषा"


def test_stats_and_cli(tmp_path):
    db_file = tmp_path / "cli_test.sqlite"
    init_db(db_file)

    add_word(word="word1", db_path=db_file)
    add_word(word="word2", db_path=db_file)

    # Stats initially
    stats = get_meanings_stats(db_file)
    assert stats["total_words"] == 2
    assert stats["words_with_meaning"] == 0
    assert stats["status_counts"]["unverified"] == 2
    printed = print_stats(db_file)
    assert printed["total_words"] == 2

    # CLI stats
    assert main(["stats", "--db", str(db_file)]) == 0

    # CLI export
    csv_file = tmp_path / "cli_out.csv"
    assert (
        main(
            [
                "export",
                str(csv_file),
                "--batch-name",
                "cli_batch",
                "--limit",
                "10",
                "--db",
                str(db_file),
            ]
        )
        == 0
    )
    assert csv_file.is_file()

    # CLI import
    assert main(["import", str(csv_file), "--db", str(db_file)]) == 0


def test_export_source_id_filtering(tmp_path):
    """Verify --source-id filters only words with occurrences from that source."""
    db_file = tmp_path / "source_filter.sqlite"
    init_db(db_file)
    with get_connection(db_file) as conn:
        conn.execute(
            """
            INSERT INTO sources (id, title, license)
            VALUES (10, 'Source 10', 'CC-BY'), (2, 'Source 2', 'CC-BY')
            """
        )

    add_word(word="word_source_10", db_path=db_file)
    add_occurrence(
        word="word_source_10",
        source_id=10,
        line_no=1,
        context="Story line 1",
        db_path=db_file,
    )

    add_word(word="word_source_2", db_path=db_file)
    add_occurrence(
        word="word_source_2",
        source_id=2,
        line_no=5,
        context="Aksharantar line",
        db_path=db_file,
    )

    add_word(word="word_no_occ", db_path=db_file)

    csv_file = tmp_path / "src_10.csv"
    count = export_for_review(db_file, csv_file, source_id=10)
    assert count == 1

    with open(csv_file, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["word"] == "word_source_10"


def test_export_with_context_columns(tmp_path):
    """Verify context columns are filled from occurrences and empty when none exist."""
    db_file = tmp_path / "context_test.sqlite"
    init_db(db_file)
    with get_connection(db_file) as conn:
        conn.execute(
            "INSERT INTO sources (id, title, license) VALUES (10, 'Source 10', 'CC-BY')"
        )

    add_word(word="word_with_ctx", db_path=db_file)
    add_occurrence(
        word="word_with_ctx",
        source_id=10,
        line_no=10,
        context="First snippet",
        db_path=db_file,
    )
    add_occurrence(
        word="word_with_ctx",
        source_id=10,
        line_no=20,
        context="Second snippet",
        db_path=db_file,
    )
    add_occurrence(
        word="word_with_ctx",
        source_id=10,
        line_no=30,
        context="Third snippet",
        db_path=db_file,
    )

    add_word(word="word_zero_ctx", db_path=db_file)

    csv_file = tmp_path / "with_ctx.csv"
    count = export_for_review(db_file, csv_file, with_context=True)
    assert count == 2

    with open(csv_file, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        assert CONTEXT_1_COL in reader.fieldnames
        assert CONTEXT_2_COL in reader.fieldnames
        rows = {r["word"]: r for r in reader}

    assert rows["word_with_ctx"][CONTEXT_1_COL] == "First snippet"
    assert rows["word_with_ctx"][CONTEXT_2_COL] == "Second snippet"
    assert rows["word_zero_ctx"][CONTEXT_1_COL] == ""
    assert rows["word_zero_ctx"][CONTEXT_2_COL] == ""


def test_export_min_freq_order_and_exclude_hyphen(tmp_path):
    """Verify --min-freq, --order freq, and --exclude-hyphen."""
    db_file = tmp_path / "freq_filter.sqlite"
    init_db(db_file)

    add_word(word="rare_word", freq=1, db_path=db_file)
    add_word(word="common_word", freq=15, db_path=db_file)
    add_word(word="mid_word", freq=5, db_path=db_file)
    add_word(word="hyphen-word", freq=25, db_path=db_file)

    csv_file = tmp_path / "freq_out.csv"
    count = export_for_review(
        db_file,
        csv_file,
        min_freq=3,
        order="freq",
        exclude_hyphen=True,
    )
    # rare_word (freq 1 < 3) and hyphen-word (contains '-') are excluded
    assert count == 2

    with open(csv_file, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    # Must be ordered by freq descending: common_word (15) before mid_word (5)
    assert [r["word"] for r in rows] == ["common_word", "mid_word"]


def test_import_with_context_columns_and_old_layout(tmp_path):
    """Verify import ignores context columns and old layout still imports cleanly."""
    db_file = tmp_path / "import_compat.sqlite"
    init_db(db_file)
    with get_connection(db_file) as conn:
        conn.execute(
            "INSERT INTO sources (id, title, license) VALUES (10, 'Source 10', 'CC-BY')"
        )

    add_word(word="word_ctx_test", db_path=db_file)
    add_occurrence(
        word="word_ctx_test",
        source_id=10,
        line_no=1,
        context="Permanent context",
        db_path=db_file,
    )

    # 1. Export with context columns
    csv_file = tmp_path / "compat_out.csv"
    export_for_review(db_file, csv_file, with_context=True)

    # 2. Fill in meaning in the exported CSV
    with open(csv_file, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    rows[0]["meaning_hi"] = "अर्थ"
    rows[0]["meaning_en"] = "meaning"
    rows[0]["origin"] = "bodo"
    rows[0]["verified_by"] = "Verifier A"
    # Even if someone modifies the read-only context columns:
    rows[0][CONTEXT_1_COL] = "Modified context in CSV"

    with open(csv_file, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    res = import_meanings(csv_file, db_file)
    assert res["updated"] == 1

    # Word meaning in DB is updated
    w = search_word("word_ctx_test", db_path=db_file)
    assert w["meaning_hi"] == "अर्थ"
    assert w["status"] == "community"

    # Context in DB occurrences table was NOT changed or corrupted
    with get_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT context FROM occurrences WHERE word = 'word_ctx_test'")
        db_context = cursor.fetchone()[0]
        assert db_context == "Permanent context"

    # 3. Test old layout CSV (without context columns) still imports seamlessly
    old_csv = tmp_path / "old_layout.csv"
    add_word(word="old_layout_word", db_path=db_file)
    with open(old_csv, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerow(
            {
                "word": "old_layout_word",
                "meaning_hi": "पुराना",
                "origin": "bodo",
                "verified_by": "Verifier Old",
            }
        )
    res_old = import_meanings(old_csv, db_file)
    assert res_old["updated"] == 1
    w_old = search_word("old_layout_word", db_path=db_file)
    assert w_old["meaning_hi"] == "पुराना"


def test_batch_name_must_be_unique(tmp_path):
    """Batch name must be unique; fails if the name already exists."""
    db_file = tmp_path / "batch_unique.sqlite"
    init_db(db_file)

    add_word(word="w1", db_path=db_file)
    add_word(word="w2", db_path=db_file)

    csv_1 = tmp_path / "batch_1.csv"
    count = export_for_review(db_file, csv_1, batch_name="batch_alpha")
    assert count == 2
    assert csv_1.is_file()

    # Verify review_batches and review_batch_words records
    with get_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM review_batches WHERE batch_name = 'batch_alpha'")
        row = cursor.fetchone()
        assert row is not None
        assert row["words_count"] == 2
        assert row["imported_at"] is None

        cursor.execute(
            "SELECT word FROM review_batch_words "
            "WHERE batch_name = 'batch_alpha' ORDER BY word"
        )
        words = [r["word"] for r in cursor.fetchall()]
        assert words == ["w1", "w2"]

    # Re-exporting with identical batch name must raise ValueError
    csv_2 = tmp_path / "batch_2.csv"
    with pytest.raises(ValueError, match="already exists"):
        export_for_review(db_file, csv_2, batch_name="batch_alpha")

    # CSV_2 should not have been created
    assert not csv_2.exists()

    # CLI export with duplicate batch name exits with non-zero (1)
    cli_code = main(
        [
            "export",
            str(csv_2),
            "--batch-name",
            "batch_alpha",
            "--db",
            str(db_file),
        ]
    )
    assert cli_code == 1


def test_words_file_exports_only_matching_words(tmp_path):
    """--words-file exports only matching words present in the file."""
    db_file = tmp_path / "words_file_test.sqlite"
    init_db(db_file)

    add_word(word="w1", db_path=db_file)
    add_word(word="w2", db_path=db_file)
    add_word(word="w3", db_path=db_file)
    add_word(word="w4", db_path=db_file)

    words_file = tmp_path / "keep.txt"
    words_file.write_text("w2\nw4\nw999\n", encoding="utf-8")

    csv_out = tmp_path / "words_file_out.csv"
    count = export_for_review(
        db_file,
        csv_out,
        batch_name="words_file_batch",
        words_file=words_file,
    )
    assert count == 2

    with open(csv_out, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    exported = {r["word"] for r in rows}
    assert exported == {"w2", "w4"}


def test_skip_exported_skips_earlier_batches(tmp_path):
    """--skip-exported skips words already recorded in any earlier batch."""
    db_file = tmp_path / "skip_exp.sqlite"
    init_db(db_file)

    add_word(word="w1", freq=10, db_path=db_file)
    add_word(word="w2", freq=8, db_path=db_file)
    add_word(word="w3", freq=6, db_path=db_file)
    add_word(word="w4", freq=4, db_path=db_file)

    # Batch 1 exports w1 and w2 (limit 2, order freq)
    csv_1 = tmp_path / "b1.csv"
    c1 = export_for_review(
        db_file,
        csv_1,
        batch_name="batch_1",
        limit=2,
        order="freq",
    )
    assert c1 == 2

    # Batch 2 with skip_exported=True must skip w1 and w2
    csv_2 = tmp_path / "b2.csv"
    c2 = export_for_review(
        db_file,
        csv_2,
        batch_name="batch_2",
        skip_exported=True,
        order="freq",
    )
    assert c2 == 2

    with open(csv_2, encoding="utf-8-sig", newline="") as f:
        rows_b2 = list(csv.DictReader(f))
    assert [r["word"] for r in rows_b2] == ["w3", "w4"]


def test_only_without_occurrences_and_exclude_origin(tmp_path):
    """Verify --only-without-occurrences and --exclude-origin options."""
    db_file = tmp_path / "filters.sqlite"
    init_db(db_file)
    with get_connection(db_file) as conn:
        conn.execute(
            "INSERT INTO sources (id, title, license) VALUES (1, 'Source 1', 'CC-BY')"
        )

    add_word(word="has_occ", origin="bodo", db_path=db_file)
    add_occurrence(
        word="has_occ",
        source_id=1,
        line_no=1,
        context="ctx",
        db_path=db_file,
    )

    add_word(word="no_occ_loan", origin="loan", db_path=db_file)
    add_word(word="no_occ_bodo", origin="bodo", db_path=db_file)

    csv_out = tmp_path / "filtered.csv"
    count = export_for_review(
        db_file,
        csv_out,
        batch_name="filter_batch",
        only_without_occurrences=True,
        exclude_origin="loan",
    )
    assert count == 1

    with open(csv_out, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["word"] == "no_occ_bodo"


def test_import_dry_run_changes_nothing(tmp_path, capsys):
    """--dry-run prints changes but writes NOTHING to database."""
    db_file = tmp_path / "dry_run.sqlite"
    init_db(db_file)

    add_word(word="word_dry", roman="wd", db_path=db_file)
    # Create batch
    csv_exp = tmp_path / "exp.csv"
    export_for_review(db_file, csv_exp, batch_name="dry_batch")

    # Prepare review CSV with valid meaning
    csv_in = tmp_path / "dry_in.csv"
    with open(csv_in, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerow(
            {
                "word": "word_dry",
                "meaning_hi": "सूखा",
                "meaning_en": "dry",
                "origin": "bodo",
                "verified_by": "Tester",
            }
        )
        writer.writerow(
            {
                "word": "empty_meanings_word",
                "meaning_hi": "",
                "meaning_en": "",
                "verified_by": "",
            }
        )
        writer.writerow(
            {
                "word": "rejected_word",
                "meaning_hi": "खारिज",
                "verified_by": "",  # Missing verified_by -> rejected
            }
        )

    # 1. Run with dry_run=True
    res_dry = import_meanings(
        csv_in,
        db_file,
        batch_name="dry_batch",
        dry_run=True,
    )
    assert res_dry["updated"] == 1
    assert res_dry["skipped"] == 1
    assert res_dry["rejected"] == 1

    # Verify that database was NOT modified at all
    w = search_word("word_dry", db_path=db_file)
    assert w["meaning_hi"] is None
    assert w["status"] == "unverified"

    with get_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT imported_at FROM review_batches WHERE batch_name = 'dry_batch'"
        )
        row = cursor.fetchone()
        assert row["imported_at"] is None

    # Check output prints
    out = capsys.readouterr().out
    assert "Would update" in out
    assert "Rejected" in out
    assert "Summary: 1 updated, 1 skipped, 1 rejected, 0 conflicts." in out

    # 2. Run without dry_run (normal import)
    res_real = import_meanings(
        csv_in,
        db_file,
        batch_name="dry_batch",
        dry_run=False,
    )
    assert res_real["updated"] == 1

    w_after = search_word("word_dry", db_path=db_file)
    assert w_after["meaning_hi"] == "सूखा"
    assert w_after["status"] == "community"

    with get_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT imported_at FROM review_batches WHERE batch_name = 'dry_batch'"
        )
        row = cursor.fetchone()
        assert row["imported_at"] is not None


def test_progress_counts_are_right(tmp_path, capsys):
    """progress command reports accurate batch counts and overall totals."""
    db_file = tmp_path / "progress.sqlite"
    init_db(db_file)

    add_word(word="w1", origin="bodo", db_path=db_file)
    add_word(word="w2", origin="loan", db_path=db_file)
    add_word(word="w3", db_path=db_file)

    # Batch 1
    csv_1 = tmp_path / "batch1.csv"
    export_for_review(db_file, csv_1, batch_name="batch_1")

    # Check progress before import
    stats1 = get_progress_stats(db_file)
    assert len(stats1["batches"]) == 1
    assert stats1["batches"][0]["batch_name"] == "batch_1"
    assert stats1["batches"][0]["words_exported"] == 3
    assert stats1["batches"][0]["words_with_meaning"] == 0
    assert stats1["batches"][0]["imported_at"] is None
    assert stats1["totals"]["words_with_meaning"] == 0
    assert stats1["totals"]["status_counts"]["unverified"] == 3

    # Import meaning for w1
    csv_done = tmp_path / "b1_done.csv"
    with open(csv_done, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerow(
            {
                "word": "w1",
                "meaning_hi": "अर्थ1",
                "meaning_en": "meaning1",
                "origin": "bodo",
                "verified_by": "Dr. Brahma",
            }
        )

    import_meanings(csv_done, db_file, batch_name="batch_1")

    # Check progress after import
    stats2 = get_progress_stats(db_file)
    assert stats2["batches"][0]["words_with_meaning"] == 1
    assert stats2["batches"][0]["imported_at"] is not None
    assert stats2["totals"]["words_with_meaning"] == 1
    assert stats2["totals"]["status_counts"]["community"] == 1
    assert stats2["totals"]["status_counts"]["unverified"] == 2
    assert stats2["totals"]["origin_counts"]["bodo"] == 1
    assert stats2["totals"]["origin_counts"]["loan"] == 1
    assert stats2["totals"]["origin_counts"]["unset"] == 1

    # Verify print_progress and CLI
    print_progress(db_file)
    out = capsys.readouterr().out
    assert "Batch: batch_1" in out
    assert "Words exported: 3" in out
    assert "Words with meaning: 1" in out
    assert "Words with a meaning: 1" in out

    # CLI progress command
    cli_code = main(["progress", "--db", str(db_file)])
    assert cli_code == 0


def test_validate_review_csv(tmp_path):
    """Validation of review CSV headers and file existence."""
    # File not found
    with pytest.raises(FileNotFoundError):
        validate_review_csv(tmp_path / "nonexistent.csv")

    # Missing required header
    bad_csv = tmp_path / "bad.csv"
    with open(bad_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["word", "meaning_hi"])
        writer.writeheader()
    with pytest.raises(ValueError, match="Missing required CSV headers"):
        validate_review_csv(bad_csv)

    # Valid CSV headers
    good_csv = tmp_path / "good.csv"
    with open(good_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(REQUIRED_CSV_FIELDS))
        writer.writeheader()
    assert validate_review_csv(good_csv) is True


def test_import_reviewed_csv_workflow_and_preservation(tmp_path):
    """Review CSV import validates approvals, dry run writes nothing,
    and preserves original file.
    """
    db_file = tmp_path / "review_flow.sqlite"
    init_db(db_file)

    add_word(word="word1", db_path=db_file)
    add_word(word="word2", db_path=db_file)

    csv_file = tmp_path / "review_input.csv"
    with open(csv_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[*CSV_FIELDNAMES, "status"])
        writer.writeheader()
        # Row 1: Valid approved review
        writer.writerow(
            {
                "word": "word1",
                "meaning_hi": "अर्थ1",
                "meaning_en": "meaning1",
                "status": "community",
                "origin": "bodo",
                "verified_by": "Reviewer Alice",
            }
        )
        # Row 2: Incomplete (no meaning, no reviewer) -> should be skipped
        writer.writerow(
            {
                "word": "word2",
                "meaning_hi": "",
                "meaning_en": "",
                "status": "unverified",
                "verified_by": "",
            }
        )
        # Row 3: Has meaning but lacks verified_by -> must be rejected
        writer.writerow(
            {
                "word": "word_unreviewed",
                "meaning_hi": "अनधिकृत",
                "meaning_en": "unreviewed",
                "verified_by": "",
            }
        )

    # Read original file bytes to ensure strict preservation
    original_bytes = csv_file.read_bytes()

    # 1. Dry run
    res_dry = import_reviewed_csv(csv_file, db_file, dry_run=True)
    assert res_dry["would_update"] == 1
    assert res_dry["skipped"] == 1
    assert res_dry["rejected"] == 1
    assert res_dry["conflicts"] == 0

    # Ensure DB was not modified
    w1_before = search_word("word1", db_path=db_file)
    assert w1_before["meaning_hi"] is None
    assert w1_before["status"] == "unverified"

    # Ensure CSV was not modified or deleted
    assert csv_file.read_bytes() == original_bytes

    # 2. Approved import
    res_import = import_reviewed_csv(csv_file, db_file, dry_run=False)
    assert res_import["updated"] == 1
    assert res_import["skipped"] == 1
    assert res_import["rejected"] == 1

    # Verify word1 is now updated
    w1_after = search_word("word1", db_path=db_file)
    assert w1_after["meaning_hi"] == "अर्थ1"
    assert w1_after["meaning_en"] == "meaning1"
    assert w1_after["status"] == "community"
    assert w1_after["origin"] == "bodo"

    # word2 remains unchanged
    w2 = search_word("word2", db_path=db_file)
    assert w2["meaning_hi"] is None
    assert w2["status"] == "unverified"

    # CSV remains untouched
    assert csv_file.read_bytes() == original_bytes
