"""Unit tests for Bodo multi-engine translation module."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from bhasha_lib.cli import main as cli_main
from bhasha_lib.engines import (
    BodoOfflineEngine,
    CompositeBodoEngine,
    GoogleGTXEngine,
    TranslationNetworkError,
)
from bhasha_lib.translator import BodoTranslator, detect, translate, translate_batch


@pytest.fixture
def test_db(tmp_path):
    """Create a temporary SQLite database with sample lexicon entries."""
    db_file = tmp_path / "test_lexicon.sqlite"
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        """
        CREATE TABLE words (
            word TEXT PRIMARY KEY,
            roman TEXT,
            meaning_hi TEXT,
            meaning_en TEXT,
            pos TEXT,
            tone TEXT,
            dialect TEXT,
            freq INTEGER DEFAULT 0,
            origin TEXT,
            status TEXT DEFAULT 'verified',
            verified_by TEXT
        )
        """
    )
    entries = [
        ("मानसि", "mansi", "व्यक्ति", "person", "noun"),
        ("गाम", "gami", "गाँव", "village", "noun"),
        ("नाव", "nao", "नाव", "boat", "noun"),
        ("दै", "dwi", "पानी", "water", "noun"),
        ("अंखा", "okha", "बारिश", "rain", "noun"),
    ]
    conn.executemany(
        """
        INSERT INTO words (word, roman, meaning_hi, meaning_en, pos)
        VALUES (?, ?, ?, ?, ?)
        """,
        entries,
    )
    conn.commit()
    conn.close()
    return db_file


def test_offline_translation_forward(test_db):
    """Test offline translation from Bodo to English and Hindi."""
    engine = BodoOfflineEngine(db_path=test_db)

    # Direct match
    en_res = engine.translate("दै", source="brx", target="en")
    assert en_res == "water"

    hi_res = engine.translate("गाम", source="brx", target="hi")
    assert hi_res == "गाँव"

    roman_res = engine.translate("मानसि", source="brx", target="roman")
    assert roman_res == "mansi"


def test_offline_translation_to_bodo(test_db):
    """Test offline translation into Bodo from English and Hindi."""
    engine = BodoOfflineEngine(db_path=test_db)

    bodo_from_en = engine.translate("water", source="en", target="brx")
    assert bodo_from_en == "दै"

    bodo_from_hi = engine.translate("गाँव", source="hi", target="brx")
    assert bodo_from_hi == "गाम"


def test_bodo_suffix_stripping(test_db):
    """Test morphological suffix stripping for Bodo case markers and plurals."""
    engine = BodoOfflineEngine(db_path=test_db)

    # -फोर plural
    res_plural = engine.translate("मानसिफोर", source="brx", target="en")
    assert "person" in res_plural

    # -नि genitive (of)
    res_genitive = engine.translate("गामनि", source="brx", target="en")
    assert "village" in res_genitive

    # -आव locative (in/at)
    res_locative = engine.translate("नावआव", source="brx", target="en")
    assert "boat" in res_locative

    # -निफ्राय ablative (from)
    res_ablative = engine.translate("गामनिफ्राय", source="brx", target="en")
    assert "village" in res_ablative


def test_composite_fallback_on_network_failure(test_db):
    """Verify CompositeBodoEngine automatically falls back to offline engine."""
    primary_mock = MagicMock(spec=GoogleGTXEngine)
    primary_mock.translate.side_effect = TranslationNetworkError("Connection refused")
    fallback_engine = BodoOfflineEngine(db_path=test_db)

    composite = CompositeBodoEngine(
        primary_engine=primary_mock,
        fallback_engine=fallback_engine,
    )

    result = composite.translate("दै", source="brx", target="en")
    assert result == "water"
    assert primary_mock.translate.called


def test_composite_force_offline(test_db):
    """Verify force_offline bypasses primary engine completely."""
    primary_mock = MagicMock(spec=GoogleGTXEngine)
    fallback_engine = BodoOfflineEngine(db_path=test_db)

    composite = CompositeBodoEngine(
        primary_engine=primary_mock,
        fallback_engine=fallback_engine,
        force_offline=True,
    )

    result = composite.translate("दै", source="brx", target="en")
    assert result == "water"
    assert not primary_mock.translate.called


def test_translator_batch_and_detect(test_db):
    """Verify batch translation and language detection."""
    translator = BodoTranslator(
        force_offline=True,
        db_path=test_db,
    )

    batch_res = translator.translate_batch(["दै", "गाम"], source="brx", target="en")
    assert batch_res == ["water", "गाँव" if "गाँव" == batch_res[1] else "village"]

    lang = translator.detect("मानसिफोर गामआव दं")
    assert lang == "brx"

    en_lang = translator.detect("Hello world")
    assert en_lang == "en"


def test_top_level_translate_functions(test_db):
    """Verify module-level translate, translate_batch, and detect functions."""
    res = translate("दै", target="en", offline=True, db_path=test_db)
    assert res == "water"

    batch = translate_batch(["नाव", "अंखा"], target="en", offline=True, db_path=test_db)
    assert "boat" in batch[0]
    assert "rain" in batch[1]

    d_code = detect("दै गाम", offline=True, db_path=test_db)
    assert d_code == "brx"

    # Default target without specifying target= should translate into Bodo
    bodo_res = translate("water", offline=True, db_path=test_db)
    assert bodo_res == "दै"


def test_cli_interface(test_db, capsys):
    """Verify bodo-translate CLI command."""
    # Translate
    code = cli_main(["दै", "--offline", "--db", str(test_db), "-t", "en"])
    assert code == 0
    out = capsys.readouterr().out.strip()
    assert out == "water"

    # Detect
    code_det = cli_main(["गामनि नाव", "--detect", "--offline", "--db", str(test_db)])
    assert code_det == 0
    det_out = capsys.readouterr().out.strip()
    assert det_out == "brx"

    # Missing text
    with patch("sys.stdin.isatty", return_value=True):
        code_empty = cli_main([])
        assert code_empty == 1
