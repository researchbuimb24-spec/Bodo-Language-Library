import pytest

from bhasha_lib.db import init_db, search_word
from bhasha_lib.loaders.archive_org import (
    HISTORICAL_BOOKS,
    BookPreset,
    download_book_text,
    load_historical_book,
)


def test_historical_books_presets():
    assert "anderson_1895" in HISTORICAL_BOOKS
    assert "endle_1884" in HISTORICAL_BOOKS
    assert "endle_1911" in HISTORICAL_BOOKS

    anderson = HISTORICAL_BOOKS["anderson_1895"]
    assert anderson.author == "J. D. Anderson"
    assert anderson.year == 1895
    assert anderson.license == "public_domain"
    assert "archive.org/download" in anderson.download_url

    endle = HISTORICAL_BOOKS["endle_1884"]
    assert endle.author == "Sidney Endle"
    assert endle.year == 1884
    assert endle.license == "public_domain"

    endle_1911 = HISTORICAL_BOOKS["endle_1911"]
    assert endle_1911.author == "Sidney Endle"
    assert endle_1911.year == 1911
    assert endle_1911.license == "public_domain"


def test_download_book_text_invalid():
    with pytest.raises(ValueError, match="Unknown book preset"):
        download_book_text("invalid_preset")


def test_load_historical_book_local_preset(tmp_path):
    """Test loading a mock historical book preset using a local text file."""
    mock_txt = tmp_path / "mock_historical.txt"
    mock_txt.write_text(
        "Kachari folk stories by Anderson. Gaham mosa in Darrang.\n",
        encoding="utf-8",
    )

    preset = BookPreset(
        preset_id="mock_historical",
        title="Mock Historical Collection",
        author="Mock Author",
        year=1890,
        license="public_domain",
        identifier="mock_identifier",
        text_filename="mock_historical.txt",
        url="https://archive.org/details/mock_identifier",
    )

    db_path = tmp_path / "hist_test.sqlite"
    init_db(db_path)

    # Pre-save text so no internet download is required during test
    source_id, stats = load_historical_book(
        preset_or_id=preset,
        db_path=db_path,
        target_dir=tmp_path,
        mark_english=True,
        filter_english=False,
    )

    assert source_id > 0
    assert "stories" in stats
    assert "gaham" in stats

    # English word is marked
    w_stories = search_word("stories", db_path=db_path)
    assert w_stories is not None
    assert w_stories["dialect"] == "english"

    # Bodo word is not marked as English
    w_gaham = search_word("gaham", db_path=db_path)
    assert w_gaham is not None
    assert w_gaham["dialect"] != "english"
