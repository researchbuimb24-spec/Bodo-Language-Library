# bhasha_lib

> [!IMPORTANT]
> **💡 File Insight & Purpose**:
> - **Role in Library**: Primary landing page, project overview & quick-start guide.
> - **What is happening here**: Introduces `bhasha_lib`, provides installation instructions, command-line usage examples (`bodo-translate`), Python API quick-starts, project layout, and contribution guidelines.
> - **Who should use it**: Anyone discovering or getting started with the `bhasha_lib` library.

`bhasha_lib` is an open-source Python library designed to document, process, and preserve endangered and regional languages. It provides standardized tools for managing language configurations, lexicons, script-aware tokenizers, corpus extraction pipelines, and cultural archives.

The first supported language is **Bodo (`brx`)**.

> [!TIP]
> - **Code & Architecture Guide**: See [LIBRARY_OVERVIEW.md](LIBRARY_OVERVIEW.md) for module catalogs, system architecture, database schema, and developer APIs.
> - **Data Catalog & Archives**: See [DATA_OVERVIEW.md](DATA_OVERVIEW.md) to explore all linguistic datasets, cultural knowledge notes, historical timelines, and lexical resources inside the library.
> - **Item Inventory (Counts & Names)**: See [INVENTORY.md](INVENTORY.md) for the exact item-by-item directory of all books, foods, dances, festivals, instruments, and attire.

---

## Installation

Install the library in editable mode:

```bash
git clone https://github.com/<YOUR-USERNAME>/bhasha-lib.git
cd bhasha-lib
pip install -e .
```

To install development dependencies (`pytest`, `ruff`):

```bash
pip install -e ".[dev]"
```

---

## Quick Start

### Python API

```python
from bhasha_lib import (
    add_source,
    detect,
    extract_file,
    init_db,
    load_aksharantar,
    load_culture_dir,
    related,
    tokenize,
    tokenize_roman,
    translate,
    translate_batch,
)

# 0. Translate Any Language into Bodo (Assam Region)
# Online multi-engine with automatic offline SQLite fallback
bodo_text = translate("Welcome to Assam")
print(bodo_text)

# Translate offline using local lexicon & morphology
print(translate("water", offline=True))  # Output: दै

# Translate Bodo back to English or Hindi
print(translate("दै", target="en"))  # Output: water

# Detect language code
print(detect("मानसिफोर गामआव दं"))  # Output: brx

# 1. Initialize Database
init_db("data/lexicon.sqlite")

# 2. Add a Source Record
source_id = add_source(
    title="Example Corpus",
    type="book",
    license="public_domain",
    db_path="data/lexicon.sqlite",
)

# 3. Extract Words from Text
# Devanagari script (default)
extract_file(
    "path/to/bodo_text.txt",
    db_path="data/lexicon.sqlite",
    source_id=source_id,
    license="public_domain",
)

# Latin script (for historical books)
extract_file(
    "path/to/latin_text.txt",
    db_path="data/lexicon.sqlite",
    source_id=source_id,
    license="public_domain",
    script="latin",
)

# 4. Load Aksharantar Dataset
load_aksharantar(
    "data/archive/bodo/datasets/brx.zip",
    db_path="data/lexicon.sqlite",
    license="CC0",
)

# 5. Load Culture Markdown Notes
load_culture_dir(
    "data/archive/bodo/culture",
    db_path="data/lexicon.sqlite",
)

# 6. Query Related Terms & Culture Items
res = related("Bagurumba", db_path="data/lexicon.sqlite")
print(res["culture_items"])

# 7. Query Chronological History & Cultural Timeline
from bhasha_lib.timeline import add_historical_event, get_timeline, search_events

events = get_timeline(db_path="data/lexicon.sqlite")
for event in events:
    print(event)

# Search historical events by entities, places, or keywords
sabha_events = search_events("Joy Bhadra", db_path="data/lexicon.sqlite")

# 8. Query and Manage Bodo Literature (Poems, Stories, Plays, Novels)
from bhasha_lib import (
    add_literary_record,
    filter_literature,
    get_literature_by_author,
    search_literature,
)

# Add source-backed literary metadata
rec_id = add_literary_record(
    title="हाबिला खावनाय",
    literary_type="short_story",
    title_en="Habila Khaonay",
    author="सतिश चन्द्र बसुमतारी",
    year=1919,
    date_precision="exact",
    book_title="बिबार (Bibar Magazine)",
    description="Pioneering modern Bodo short story published in Bibar.",
    literary_movement="Bibar Era",
    source_title="Bodo Sahitya Sabha Archival Records",
    confidence="verified",
    verified_by="Archival Review Board",
    verified_on="2024-01-15",
    db_path="data/lexicon.sqlite",
)

# Search literature by title, author, or keyword
works = search_literature("हाबिला", db_path="data/lexicon.sqlite")

# Retrieve works by author
author_works = get_literature_by_author(
    "सतिश चन्द्र बसुमतारी", db_path="data/lexicon.sqlite"
)

# Filter by genre and date range
poems = filter_literature(
    literary_type="poem",
    from_year=1920,
    to_year=1960,
    db_path="data/lexicon.sqlite",
)

# 9. Catalog and Govern Bodo Folk Songs & Audio Recordings
from bhasha_lib import (
    add_folk_song,
    add_song_recording,
    filter_folk_songs,
    get_folk_song,
    get_recordings,
    search_folk_songs,
    withdraw_recording_consent,
    request_recording_removal,
)

# Add normalized, source-backed folk song metadata
song_id = add_folk_song(
    title="खाम सिफुं दामनानै",
    roman_title="Kham Siphung Damnanwi",
    title_en="Playing the Drum and Flute",
    song_type="festival_song",
    composer="Traditional",
    lyricist="Traditional",
    performer="Community Elders",
    community="Bodo",
    region="Kokrajhar",
    description="Traditional Bwisagu festival song welcoming the spring season.",
    cultural_context="Sung during Bwisagu festivities accompanied by Kham and Siphung.",
    festivals=["Bwisagu"],
    instruments=["Kham", "Siphung", "Serja", "Tharkha"],
    places=["Kokrajhar", "Dotma"],
    source_title="Folk Songs of the Bodos (Mohini Mohan Brahma, 1960)",
    license="CC-BY-NC-SA-4.0",
    confidence="verified",
    verified_by="Archival Researcher",
    verified_on="2026-10-22",
    db_path="data/lexicon.sqlite",
)

# Attach an audio recording with explicit ethical consent tracking
rec_id = add_song_recording(
    song_id=song_id,
    performer="Bodo Troupe",
    recording_date="2015-04-14",
    audio_format="wav",
    duration_seconds=185,
    location="Dotma, Kokrajhar",
    source_title="Field Audio Archive",
    license="CC-BY-NC-4.0",
    consent_status="granted",
    consent_document_ref="consents/2015_01.pdf",
    permit_attribution=True,
    permit_transcribe=True,
    permit_redistribute=True,
    db_path="data/lexicon.sqlite",
)

# Search and filter songs
results = search_folk_songs("Kham", db_path="data/lexicon.sqlite")
festival_songs = filter_folk_songs(song_type="festival_song", db_path="data/lexicon.sqlite")
```

### Command Line Tools

```bash
# Translate any text to Bodo (Assam region)
bodo-translate "Welcome to Assam"
python -m bhasha_lib "Hello world"

# Translate offline using local lexicon & Bodo morphological rules
bodo-translate "water" --offline

# Detect language of text
bodo-translate "मानसिफोर गामआव दं" --detect

# Extract words from text (Devanagari)
python -m bhasha_lib.extract document.txt --source-id 1 --license public_domain

# Extract words from text (Latin script with English marking or filtering)
python -m bhasha_lib.extract latin_book.txt --source-id 2 --license public_domain --script latin --mark-english
python -m bhasha_lib.extract latin_book.txt --source-id 2 --license public_domain --script latin --filter-english

# Ingest historical books directly from archive.org (Anderson 1895, Endle 1884)
python -m bhasha_lib.loaders.archive_org --list
python -m bhasha_lib.loaders.archive_org --book anderson_1895 --db data/lexicon.sqlite

# Load Aksharantar dataset zip directly into database
python -m bhasha_lib.loaders.aksharantar path/to/brx.zip --license "CC0" --db data/lexicon.sqlite

# Ingest culture markdown notes
python -m bhasha_lib.culture data/archive/bodo/culture --db data/lexicon.sqlite

# View chronological history timeline
python -m bhasha_lib.timeline --db data/lexicon.sqlite

# Filter timeline by category and year interval
python -m bhasha_lib.timeline --category history --from-year 1950 --to-year 2000

# Search historical events and view detailed entity/citation metadata
python -m bhasha_lib.timeline --search "Basugaon" --verbose

# Audit historical citations and view records needing verification
python -m bhasha_lib.timeline --missing-citations
python -m bhasha_lib.timeline --unverified

# Query, search, and filter literature records
python -m bhasha_lib.literature --db data/lexicon.sqlite
python -m bhasha_lib.literature --search "सतिश चन्द्र" --verbose
python -m bhasha_lib.literature --type poem --from-year 1920 --to-year 1960
python -m bhasha_lib.literature --author "सतिश चन्द्र बसुमतारी"

# Audit literature citations and view unverified records
python -m bhasha_lib.literature --missing-citations
python -m bhasha_lib.literature --unverified

# Export and import literature records (CSV and JSON)
python -m bhasha_lib.literature --export-csv literature.csv --type poem
python -m bhasha_lib.literature --export-json literature.json
python -m bhasha_lib.literature --import-csv new_works.csv --dry-run
python -m bhasha_lib.literature --import-csv new_works.csv
python -m bhasha_lib.literature --import-json new_works.json

# Import bibliography sources from CSV
python -m bhasha_lib.sources_import sources.csv --db data/lexicon.sqlite

# Manage lexical meanings & community annotation
python -m bhasha_lib.meanings stats --db data/lexicon.sqlite
python -m bhasha_lib.meanings export unannotated.csv --min-freq 2 --limit 500 --db data/lexicon.sqlite
python -m bhasha_lib.meanings import completed_meanings.csv --db data/lexicon.sqlite
python -m bhasha_lib.meanings bootstrap --db data/lexicon.sqlite

# Catalog, search, and filter folk songs
python -m bhasha_lib.folk_songs search "Kham" --db data/lexicon.sqlite
python -m bhasha_lib.folk_songs filter --type festival_song --region Kokrajhar
python -m bhasha_lib.folk_songs recordings 1 --db data/lexicon.sqlite

# Audit folk song citations and unverified records
python -m bhasha_lib.folk_songs missing-citations --db data/lexicon.sqlite
python -m bhasha_lib.folk_songs unverified --db data/lexicon.sqlite

# Audit audio recordings missing consent or evidence
python -m bhasha_lib.folk_songs missing-consent --db data/lexicon.sqlite

# Withdraw consent or register cultural removal request
python -m bhasha_lib.folk_songs withdraw-consent 1 --reason "Performer requested withdrawal"
python -m bhasha_lib.folk_songs request-removal 1 --reason "Sacred ritual restriction"

# Export and import folk songs metadata (CSV and JSON)
python -m bhasha_lib.folk_songs export --csv songs.csv --type festival_song
python -m bhasha_lib.folk_songs export --json songs.json
python -m bhasha_lib.folk_songs import --csv new_songs.csv --dry-run
python -m bhasha_lib.folk_songs import --csv new_songs.csv
python -m bhasha_lib.folk_songs import --json new_songs.json

# Legacy markdown folk song verification and ingestion
python -m bhasha_lib.folk_songs verify data/archive/bodo/folk_songs
python -m bhasha_lib.folk_songs load data/archive/bodo/folk_songs --db data/lexicon.sqlite
```

---

## Project Structure

```
bhasha-lib/
├── LICENSE                            # MIT License (for CODE only)
├── CONSENT_AND_ETHICS.md              # Ethical archiving protocol & consent template
├── DATA_OVERVIEW.md                   # Data catalog: vocabulary, culture, history & sources
├── INVENTORY.md                       # Item-by-item directory: books, foods, dances, instruments
├── LIBRARY_OVERVIEW.md                # Architecture, module catalog & developer guide
├── pyproject.toml                     # Package dependencies and tool settings
├── bodo.yaml                          # Bodo language specification
├── configs/
│   └── bodo.yaml                      # Secondary config reference
├── data/
│   └── archive/
│       └── bodo/
│           ├── culture/               # Cultural markdown drafts (.md tracked)
│           │   ├── bagurumba.md
│           │   ├── bathou.md
│           │   ├── bwisagu.md
│           │   └── kherai.md
│           ├── folk_songs/            # Folk songs & audio (excluded by .gitignore)
│           ├── history/               # Historical notes (.md tracked)
│           ├── books/                 # Raw texts & books (excluded by .gitignore)
│           └── datasets/              # External dataset archives (excluded by .gitignore)
├── examples/
│   └── folk_song_template.md          # Sample folk song template with consent schema
├── src/
│   └── bhasha_lib/
│       ├── __init__.py                # Package exports & lazy loaders
│       ├── archive.py                 # Archive path resolution
│       ├── config.py                  # YAML LanguageConfig loader
│       ├── consent.py                 # Ethical consent verification & compliance
│       ├── culture.py                 # Markdown frontmatter parser & related() query
│       ├── db.py                      # SQLite database operations & context manager
│       ├── english.py                 # English detection & Bodo protected vocabulary
│       ├── extract.py                 # Text extraction & frequency pipeline
│       ├── folk_songs.py              # Folk songs ingestion & consent enforcement
│       ├── loaders/
│       │   ├── __init__.py
│       │   ├── aksharantar.py         # AI4Bharat Aksharantar zip loader
│       │   └── archive_org.py         # Archive.org historical books loader
│       ├── literature.py              # Literature metadata, search, and import/export
│       ├── meanings.py                # Lexical meanings export/import & seed vocabulary
│       ├── resources/
│       │   └── english_words.txt      # Curated English vocabulary list
│       ├── py.typed                   # PEP 561 type annotation marker
│       ├── sources_import.py          # CSV bibliography importer
│       ├── timeline.py                # Chronological timeline & milestone records
│       ├── tokenizer.py               # Devanagari & Latin tokenizers
│       └── unicode.py                 # Unicode script validation
└── tests/                             # Pytest test suite
```

---

## Data and Licensing

- **Code License**: The codebase is licensed under the **MIT License**.
- **Data License**: Data retains the license of each individual source.
- **Mandatory License Field**: Every source entered into the database (`sources` table) must have a non-empty `license` field. This rule is strictly enforced by the software layer.
- **Excluded Data**: Raw books, dataset archives, audio files, and local database files (`lexicon.sqlite`) are **NOT included in the repository** and are excluded by `.gitignore`.

---

## Where to Get Data

- **AI4Bharat Aksharantar**: Available on Hugging Face at [`ai4bharat/Aksharantar`](https://huggingface.co/datasets/ai4bharat/Aksharantar). Always review its license terms on the dataset page before use (mined data subsets are released under CC0; the manual benchmark is under CC-BY).
- **Public Domain Books**: Available on [archive.org](https://archive.org) (e.g. historical Bodo language works by Rev. Sidney Endle, J. D. Anderson).
- **Bodo-Dimasa Archive**: [bododimasaarchive.org](https://bododimasaarchive.org) provides reference material, oral traditions, and cultural heritage documentation.

---

## Known Limitations

- **Inflected Forms & Loanwords**: Datasets like Aksharantar contain inflected grammatical word-forms (with case and plural suffixes such as `-नि` or `-फोरखौ`) rather than lemmatized dictionary headwords, as well as transliterated loanwords (such as English terms written in Bodo script).
- **Empty Meanings**: Current vocabulary imports provide word forms and transliterations; definition fields (`meaning_hi`, `meaning_en`) are mostly empty and require future lexical annotation.
- **Latin-Script Verification**: Words extracted from older Latin-script books may include English words from bilingual sections or older non-standard spellings, requiring manual verification before being considered authoritative.

---

## Contributing

Cultural notes and folk songs need a real source and, for folk songs, a real consent document, and the project does not accept entries without them.

We welcome community contributions to expand regional language preservation.

### Adding a Culture Note
1. Create a markdown file in `data/archive/<language>/culture/<item_name>.md`.
2. Include the required YAML frontmatter:
   ```markdown
   ---
   category: dance
   title: Bagurumba
   region: Assam
   source: Verified source reference
   related_words: []
   ---
   Description text goes here...
   ```
3. Run the culture loader to ingest:
   ```bash
   python -m bhasha_lib.culture data/archive/<language>/culture
   ```

### Adding a Historical Event
1. Create a markdown file in `data/archive/<language>/history/<event_name>.md`.
2. Include the required YAML frontmatter with date precision and source attribution:
   ```markdown
   ---
   category: history
   title: Bodo Sahitya Sabha Foundation
   region: Assam
   year_start: 1952
   date_precision: exact
   confidence: needs_check
   people:
     - Joy Bhadra Hagjer
     - Sonaram Thaosen
   places:
     - Basugaon
     - Kokrajhar
   organizations:
     - Bodo Sahitya Sabha
   source: Archival Records of Bodo Sahitya Sabha; Assam State Gazette
   related_words: []
   ---
   Historical event description...
   ```
3. Load the history directory into the database:
   ```bash
   python -m bhasha_lib.culture data/archive/<language>/history
   ```
   Or add via the Python API:
   ```python
   from bhasha_lib.timeline import add_historical_event

   add_historical_event(
       title="Primary Medium Accord",
       description="Declaration of Bodo as primary medium in Kokrajhar.",
       year_start=1963,
       date_precision="exact",
       category="history",
       confidence="needs_check",
       source_title="Government of Assam Declaration 1963",
   )
   ```

### Adding Literary Records (Poems, Stories, Plays, Novels)
The project supports normalized, source-backed documentation for Bodo literature across poems, short stories, novels, plays, folk tales, essays, and periodicals.

#### Supported Literary Record Types
- `poem` — Individual poems, lyrics, and verses
- `short_story` — Short stories and novellas
- `novel` — Full-length novels and serialized fiction
- `play` — Stage plays, dramas, and performance scripts
- `folk_tale` — Traditional folklore, legends, and oral stories
- `essay` — Critical, historical, and cultural essays
- `collection` — Literary anthologies, magazine issues (e.g. *Bibar*, *Alari*), and edited volumes
- `other` — Miscellaneous and unclassified literary works

#### Attribution, Copyright & Verification Rules
- **No Copyright Infringement**: Never copy full poems, short stories, or book chapters into the database without explicit licensing or public-domain status. Store only short factual metadata, publication details, and objective summaries.
- **Unicode & Script Integrity**: Preserve authentic Bodo spelling in Devanagari or Latin script; all textual fields are normalized and verified in Unicode NFC format.
- **Bibliographic Sourcing**: Every entry must cite a verifiable source (periodical, book, journal, or library archive). Generic domains (e.g., "Wikipedia") are flagged by `get_literature_missing_citations()`.
- **Verification Workflow**: Newly submitted records default to `needs_check` or `unverified`. An entry reaches `verified` only with an identified `verified_by` reviewer and non-future `verified_on` date.
- **Dry Run & Backup Safety**: Bulk imports via CSV or JSON support `--dry-run` to inspect validation issues and automatically generate a timestamped database backup before any modifications are committed.

### Cataloging Bodo Folk Songs & Audio Recordings (Step 5)
The library provides a normalized, source-backed, and ethically governed catalog for Bodo folk songs and associated audio recordings.

#### Supported Song Types
- `traditional_folk_song` (`traditional_folk`) — Ancient or community oral folk songs
- `work_song` — Agricultural, weaving, or manual labor songs
- `festival_song` — Seasonal and festive songs (e.g. *Bwisagu Methai*)
- `lullaby` — Traditional cradle songs and lullabies
- `devotional_song` (`devotional`) — Songs of worship, Bathou hymns, and chants
- `dance_song` — Songs accompanying folk dances such as *Bagurumba*
- `ritual_song` — Ceremonial and sacred rituals (e.g. *Kherai* rites)
- `ballad` — Narrative or historical ballads
- `other` — Miscellaneous folk songs

#### Ethical Consent Governance & Audio Safeguards
1. **Consent States**:
   - `unknown` — Default for unconfirmed historical or legacy materials.
   - `pending` — Consent request submitted to performers or custodians; awaiting formal approval.
   - `granted` — Explicit written consent on record. **Strictly requires `consent_document_ref`** referencing verified documentation.
   - `denied` — Permission explicitly denied.
   - `withdrawn` — Performer, family, or community custodian revoked earlier consent.
2. **Granular Consent Scopes**:
   Consent is tracked separately across 5 distinct permissions:
   - `consent_recording` — Permission to make or retain the recording.
   - `consent_publication` — Permission to catalog and display recording metadata.
   - `consent_attribution` — Preferred credit and attribution details.
   - `consent_transcription` — Permission to transcribe lyrical excerpts.
   - `consent_redistribution` — Permission to share or redistribute audio references.
3. **Audio Integrity & Safe Storage**:
   - Audio binary data is never embedded inside CSV or JSON metadata exports; exports store metadata and file/URL references only.
   - Supported audio formats: `mp3`, `wav`, `flac`, `ogg`, `aac`.
   - Never assume traditional or author-unknown songs are public domain without evidence.
4. **Correction, Withdrawal & Removal Protocol**:
   - **Withdraw Consent**: Maintainers or community members can withdraw consent via `withdraw_recording_consent(recording_id, reason=...)` or CLI `python -m bhasha_lib.folk_songs withdraw-consent <id> --reason "..."`.
   - **Removal Requests**: For sacred, ritual, or community-restricted audio, a formal removal request is registered with `request_recording_removal(recording_id, reason=...)` or CLI `python -m bhasha_lib.folk_songs request-removal <id> --reason "..."`.
   - Withdrawn recordings are excluded from public listings when `include_withdrawn=False`.

### Attribution & Citation Standards
- **Evidence-Backed**: Never fabricate events, years, quotations, or committee resolutions.
- **Secondary vs Primary Sources**: Generic website names (such as "Wikipedia" alone) are insufficient. Include specific article titles, publication volumes, archival gazettes, or official reports.
- **Unsupported Claims**: Historical claims that cannot be corroborated must be preserved with `confidence: needs_check` or `unverified`.

### Requesting Community or Expert Review
- All community-submitted historical notes enter the repository as `needs_check`.
- Contributors can request peer review from native Bodo historians, language scholars, and community elders.
- An entry is upgraded to `verified` only when primary or corroborating secondary documentation has been reviewed and recorded with `verified_by` and `verified_on`.

### Adding a Source
- Use `add_source()` in Python or import via CSV using `python -m bhasha_lib.sources_import sources.csv`.
- An explicit, valid license is mandatory for all sources.

### Community Consent Policy
Community contributors must provide **written consent** from language speakers and cultural custodians for any traditional folk songs, oral stories, or audio recordings contributed to the archive.

---

## Roadmap

- **More Regional Languages**: Extend language configurations and tokenizers to additional endangered and regional Indian languages.
- **Audio Integration**: Ingest spoken audio, phoneme alignments, and pronunciation recordings.
- **Meanings & Lexical Annotation**: Add Hindi and English meanings, parts of speech, and root lemma relationships to the vocabulary.
