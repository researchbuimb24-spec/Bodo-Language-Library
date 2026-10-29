"""bhasha_lib - Python library for Indian language processing and linguistic data.

💡 FILE INSIGHT & PURPOSE:
Top-level package initializer and public API export gateway.
Exports primary functions (translate, tokenize, init_db, lookup_term, etc.)
and implements PEP-562 lazy loading via `__getattr__` to ensure fast imports
without circular dependencies or early database connections.
"""

from __future__ import annotations

from typing import Any

from bhasha_lib.archive import (
    ARCHIVE_CATEGORIES,
    get_archive_base_dir,
    get_archive_path,
    list_archive_files,
    verify_archive_structure,
)
from bhasha_lib.config import (
    LanguageConfig,
    find_default_config,
    get_bodo_config,
    load_config,
)
from bhasha_lib.consent import (
    ConsentError,
    ConsentRecord,
    ConsentStatus,
    validate_consent_dict,
)
from bhasha_lib.db import (
    DEFAULT_DB_PATH,
    DEFAULT_TIMEOUT,
    VALID_AUDIO_FORMATS,
    VALID_CONFIDENCE_LEVELS,
    VALID_CONSENT_STATES,
    VALID_DATE_PRECISIONS,
    VALID_LITERARY_TYPES,
    VALID_ORIGINS,
    VALID_SONG_TYPES,
    VALID_STATUSES,
    add_culture_item,
    add_folk_song_item,
    add_literature_item,
    add_occurrence,
    add_song_recording_item,
    add_source,
    add_word,
    backup_db,
    init_db,
    search_word,
    update_word_meaning,
)
from bhasha_lib.english import BODO_PROTECTED_WORDS, is_english_word
from bhasha_lib.tokenizer import normalize, tokenize, tokenize_roman
from bhasha_lib.translator import (
    BodoTranslator,
    detect,
    translate,
    translate_batch,
)
from bhasha_lib.unicode import (
    calculate_coverage,
    filter_devanagari,
    is_char_in_range,
    is_devanagari,
    parse_unicode_range,
)

__version__ = "0.1.0"


def __getattr__(name: str) -> Any:
    """Lazy-load modules to avoid runpy warnings when running modules with -m."""
    if name == "extract_file":
        from bhasha_lib.extract import extract_file

        return extract_file
    if name == "strip_gutenberg":
        from bhasha_lib.extract import strip_gutenberg

        return strip_gutenberg
    if name == "is_english_inflection":
        from bhasha_lib.extract import is_english_inflection

        return is_english_inflection
    if name == "load_aksharantar":
        from bhasha_lib.loaders.aksharantar import load_aksharantar

        return load_aksharantar
    if name == "load_culture_dir":
        from bhasha_lib.culture import load_culture_dir

        return load_culture_dir
    if name == "related":
        from bhasha_lib.culture import related

        return related
    if name == "import_sources_csv":
        from bhasha_lib.sources_import import import_sources_csv

        return import_sources_csv
    if name == "load_historical_book":
        from bhasha_lib.loaders.archive_org import load_historical_book

        return load_historical_book
    if name == "export_for_review":
        from bhasha_lib.meanings import export_for_review

        return export_for_review
    if name == "export_meanings_csv":
        from bhasha_lib.meanings import export_meanings_csv

        return export_meanings_csv
    if name == "import_meanings":
        from bhasha_lib.meanings import import_meanings

        return import_meanings
    if name == "import_meanings_csv":
        from bhasha_lib.meanings import import_meanings_csv

        return import_meanings_csv
    if name == "bootstrap_seed_meanings":
        from bhasha_lib.meanings import bootstrap_seed_meanings

        return bootstrap_seed_meanings
    if name == "import_reviewed_csv":
        from bhasha_lib.meanings import import_reviewed_csv

        return import_reviewed_csv
    if name == "validate_review_csv":
        from bhasha_lib.meanings import validate_review_csv

        return validate_review_csv
    if name == "get_meanings_stats":
        from bhasha_lib.meanings import get_meanings_stats

        return get_meanings_stats
    if name == "load_folk_song_file":
        from bhasha_lib.folk_songs import load_folk_song_file

        return load_folk_song_file
    if name == "load_folk_songs_dir":
        from bhasha_lib.folk_songs import load_folk_songs_dir

        return load_folk_songs_dir
    if name == "verify_folk_songs_dir":
        from bhasha_lib.folk_songs import verify_folk_songs_dir

        return verify_folk_songs_dir
    if name == "lookup_term":
        from bhasha_lib.lookup import lookup_term

        return lookup_term
    if name == "export_verified":
        from bhasha_lib.export_verified import export_verified

        return export_verified
    if name == "get_timeline":
        from bhasha_lib.timeline import get_timeline

        return get_timeline
    if name in ("add_historical_event", "add_event"):
        from bhasha_lib.timeline import add_historical_event

        return add_historical_event
    if name in ("get_historical_event", "get_event"):
        from bhasha_lib.timeline import get_historical_event

        return get_historical_event
    if name == "search_events":
        from bhasha_lib.timeline import search_events

        return search_events
    if name == "filter_events":
        from bhasha_lib.timeline import filter_events

        return filter_events
    if name == "get_events_missing_citations":
        from bhasha_lib.timeline import get_events_missing_citations

        return get_events_missing_citations
    if name == "get_unverified_events":
        from bhasha_lib.timeline import get_unverified_events

        return get_unverified_events
    if name == "validate_historical_event":
        from bhasha_lib.timeline import validate_historical_event

        return validate_historical_event
    if name == "format_year_range":
        from bhasha_lib.timeline import format_year_range

        return format_year_range
    if name == "print_timeline":
        from bhasha_lib.timeline import print_timeline

        return print_timeline
    if name == "reset_confidence":
        from bhasha_lib.culture import reset_confidence

        return reset_confidence
    if name == "audit_culture_and_history":
        from bhasha_lib.audit import audit_culture_and_history

        return audit_culture_and_history
    if name == "validate_folk_song_header":
        from bhasha_lib.culture import validate_folk_song_header

        return validate_folk_song_header
    if name == "validate_literary_record":
        from bhasha_lib.literature import validate_literary_record

        return validate_literary_record
    if name == "add_literary_record":
        from bhasha_lib.literature import add_literary_record

        return add_literary_record
    if name == "get_literary_record":
        from bhasha_lib.literature import get_literary_record

        return get_literary_record
    if name == "search_literature":
        from bhasha_lib.literature import search_literature

        return search_literature
    if name == "filter_literature":
        from bhasha_lib.literature import filter_literature

        return filter_literature
    if name in ("get_literature_by_author", "get_literary_by_author"):
        from bhasha_lib.literature import get_literature_by_author

        return get_literature_by_author
    if name == "get_literature_missing_citations":
        from bhasha_lib.literature import get_literature_missing_citations

        return get_literature_missing_citations
    if name == "get_unverified_literature":
        from bhasha_lib.literature import get_unverified_literature

        return get_unverified_literature
    if name == "export_literature_csv":
        from bhasha_lib.literature import export_literature_csv

        return export_literature_csv
    if name == "export_literature_json":
        from bhasha_lib.literature import export_literature_json

        return export_literature_json
    if name == "import_literature_csv":
        from bhasha_lib.literature import import_literature_csv

        return import_literature_csv
    if name == "import_literature_json":
        from bhasha_lib.literature import import_literature_json

        return import_literature_json
    if name == "format_literature_item":
        from bhasha_lib.literature import format_literature_item

        return format_literature_item
    if name == "print_literature":
        from bhasha_lib.literature import print_literature

        return print_literature
    if name == "validate_folk_song":
        from bhasha_lib.folk_songs import validate_folk_song

        return validate_folk_song
    if name == "validate_song_recording":
        from bhasha_lib.folk_songs import validate_song_recording

        return validate_song_recording
    if name == "add_folk_song":
        from bhasha_lib.folk_songs import add_folk_song

        return add_folk_song
    if name == "add_song_recording":
        from bhasha_lib.folk_songs import add_song_recording

        return add_song_recording
    if name == "get_folk_song":
        from bhasha_lib.folk_songs import get_folk_song

        return get_folk_song
    if name == "get_recordings":
        from bhasha_lib.folk_songs import get_recordings

        return get_recordings
    if name == "get_recording":
        from bhasha_lib.folk_songs import get_recording

        return get_recording
    if name == "search_folk_songs":
        from bhasha_lib.folk_songs import search_folk_songs

        return search_folk_songs
    if name == "filter_folk_songs":
        from bhasha_lib.folk_songs import filter_folk_songs

        return filter_folk_songs
    if name == "get_folk_songs_missing_citations":
        from bhasha_lib.folk_songs import get_folk_songs_missing_citations

        return get_folk_songs_missing_citations
    if name == "get_unverified_folk_songs":
        from bhasha_lib.folk_songs import get_unverified_folk_songs

        return get_unverified_folk_songs
    if name == "get_recordings_missing_consent":
        from bhasha_lib.folk_songs import get_recordings_missing_consent

        return get_recordings_missing_consent
    if name == "withdraw_recording_consent":
        from bhasha_lib.folk_songs import withdraw_recording_consent

        return withdraw_recording_consent
    if name == "request_recording_removal":
        from bhasha_lib.folk_songs import request_recording_removal

        return request_recording_removal
    if name == "export_folk_songs_csv":
        from bhasha_lib.folk_songs import export_folk_songs_csv

        return export_folk_songs_csv
    if name == "export_folk_songs_json":
        from bhasha_lib.folk_songs import export_folk_songs_json

        return export_folk_songs_json
    if name == "import_folk_songs_csv":
        from bhasha_lib.folk_songs import import_folk_songs_csv

        return import_folk_songs_csv
    if name == "import_folk_songs_json":
        from bhasha_lib.folk_songs import import_folk_songs_json

        return import_folk_songs_json
    if name == "format_folk_song_item":
        from bhasha_lib.folk_songs import format_folk_song_item

        return format_folk_song_item
    if name == "print_folk_songs":
        from bhasha_lib.folk_songs import print_folk_songs

        return print_folk_songs
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ARCHIVE_CATEGORIES",
    "BODO_PROTECTED_WORDS",
    "BodoTranslator",
    "ConsentError",
    "ConsentRecord",
    "ConsentStatus",
    "DEFAULT_DB_PATH",
    "DEFAULT_TIMEOUT",
    "LanguageConfig",
    "VALID_AUDIO_FORMATS",
    "VALID_CONFIDENCE_LEVELS",
    "VALID_CONSENT_STATES",
    "VALID_DATE_PRECISIONS",
    "VALID_LITERARY_TYPES",
    "VALID_ORIGINS",
    "VALID_SONG_TYPES",
    "VALID_STATUSES",
    "__version__",
    "add_culture_item",
    "add_event",
    "add_folk_song",
    "add_folk_song_item",
    "add_historical_event",
    "add_literary_record",
    "add_literature_item",
    "add_occurrence",
    "add_song_recording",
    "add_song_recording_item",
    "add_source",
    "add_word",
    "audit_culture_and_history",
    "backup_db",
    "bootstrap_seed_meanings",
    "calculate_coverage",
    "detect",
    "export_folk_songs_csv",
    "export_folk_songs_json",
    "export_for_review",
    "export_literature_csv",
    "export_literature_json",
    "export_meanings_csv",
    "export_verified",
    "extract_file",
    "filter_devanagari",
    "filter_events",
    "filter_folk_songs",
    "filter_literature",
    "find_default_config",
    "format_folk_song_item",
    "format_literature_item",
    "format_year_range",
    "get_archive_base_dir",
    "get_archive_path",
    "get_bodo_config",
    "get_event",
    "get_events_missing_citations",
    "get_folk_song",
    "get_folk_songs_missing_citations",
    "get_historical_event",
    "get_literary_by_author",
    "get_literary_record",
    "get_literature_by_author",
    "get_literature_missing_citations",
    "get_meanings_stats",
    "get_recording",
    "get_recordings",
    "get_recordings_missing_consent",
    "get_timeline",
    "get_unverified_events",
    "get_unverified_folk_songs",
    "get_unverified_literature",
    "import_folk_songs_csv",
    "import_folk_songs_json",
    "import_literature_csv",
    "import_literature_json",
    "import_meanings",
    "import_meanings_csv",
    "import_reviewed_csv",
    "import_sources_csv",
    "init_db",
    "is_char_in_range",
    "is_devanagari",
    "is_english_inflection",
    "is_english_word",
    "list_archive_files",
    "load_aksharantar",
    "load_config",
    "load_culture_dir",
    "load_folk_song_file",
    "load_folk_songs_dir",
    "load_historical_book",
    "lookup_term",
    "normalize",
    "parse_unicode_range",
    "print_folk_songs",
    "print_literature",
    "print_timeline",
    "related",
    "request_recording_removal",
    "reset_confidence",
    "search_events",
    "search_folk_songs",
    "search_literature",
    "search_word",
    "strip_gutenberg",
    "tokenize",
    "tokenize_roman",
    "translate",
    "translate_batch",
    "update_word_meaning",
    "validate_consent_dict",
    "validate_folk_song",
    "validate_folk_song_header",
    "validate_historical_event",
    "validate_literary_record",
    "validate_review_csv",
    "validate_song_recording",
    "verify_archive_structure",
    "verify_folk_songs_dir",
    "withdraw_recording_consent",
]
