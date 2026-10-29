# Data Overview & Catalog: What Data is Inside bhasha_lib

> [!IMPORTANT]
> **💡 File Insight & Purpose**:
> - **Role in Library**: Data architecture guide and dataset catalog.
> - **What is happening here**: Explains how data is organized across the two storage tiers (file-based Markdown archives and SQLite `lexicon.sqlite`), detailing 44,011 vocabulary words, 6,128 text occurrences, 14 cultural/historical notes, registered bibliography sources, and terminal/Python query recipes.
> - **Who should use it**: Users, linguists, and researchers exploring datasets, licensing terms, and querying tools.

A user-facing guide and comprehensive catalog of all linguistic datasets, cultural records, historical archives, literary collections, and lexical resources currently tracked or managed by **`bhasha_lib`**.

---

## Table of Contents

1. [Introduction & Purpose](#1-introduction--purpose)
2. [Data Summary & Statistics](#2-data-summary--statistics)
3. [Linguistic & Lexical Datasets](#3-linguistic--lexical-datasets)
   - [3.1 Modern Devanagari Vocabulary (Aksharantar)](#31-modern-devanagari-vocabulary-aksharantar)
   - [3.2 Historical Roman-Orthography Vocabulary (Anderson 1895)](#32-historical-roman-orthography-vocabulary-anderson-1895)
   - [3.3 Protected Bodo Vocabulary](#33-protected-bodo-vocabulary)
   - [3.4 Community Review & Meaning Batches](#34-community-review--meaning-batches)
4. [Cultural Knowledge Base](#4-cultural-knowledge-base)
   - [4.1 Inventory of Cultural Notes](#41-inventory-of-cultural-notes)
   - [4.2 Structure of Cultural Notes](#42-structure-of-cultural-notes)
5. [Historical Timeline & Milestones](#5-historical-timeline--milestones)
   - [5.1 Historical Notes in the Archive](#51-historical-notes-in-the-archive)
   - [5.2 Timeline Schema & Milestone Tracking](#52-timeline-schema--milestone-tracking)
6. [Literature & Oral Heritage Catalogs](#6-literature--oral-heritage-catalogs)
   - [6.1 Literature Catalog (Works, Genres, Authors)](#61-literature-catalog-works-genres-authors)
   - [6.2 Folk Songs & Oral Traditions](#62-folk-songs--oral-traditions)
   - [6.3 Audio Recordings & Ethical Safeguards](#63-audio-recordings--ethical-safeguards)
7. [Sources & Bibliography Registry](#7-sources--bibliography-registry)
8. [How Users Can Browse & Query the Data](#8-how-users-can-browse--query-the-data)
   - [8.1 Searching the Lexicon & Words](#81-searching-the-lexicon--words)
   - [8.2 Looking up Cultural Concepts](#82-looking-up-cultural-concepts)
   - [8.3 Browsing the History Timeline](#83-browsing-the-history-timeline)
   - [8.4 Searching Literature & Folk Songs](#84-searching-literature--folk-songs)
   - [8.5 Exporting Verified Data](#85-exporting-verified-data)
9. [Data Licensing, Ethics & Provenance](#9-data-licensing-ethics--provenance)

---

## 1. Introduction & Purpose

While [`LIBRARY_OVERVIEW.md`](file:///f:/bodo/LIBRARY_OVERVIEW.md) details the library's code architecture, classes, and APIs, this document explains **what data is actually stored in the library**, how it is structured, what sources it originates from, and how users, researchers, and language community members can explore it.

`bhasha_lib` organizes data into two complementary storage tiers:
1. **File-Based Archive (`data/archive/bodo/`)**: Human-readable Markdown (`.md`) files with structured YAML frontmatter for cultural and historical narratives, alongside raw source texts and community review CSVs.
2. **Relational Database (`data/lexicon.sqlite`)**: A high-performance SQLite database indexing word forms, transliterations, sentence occurrences, bibliographic citations, and metadata catalogs.

> [!TIP]
> For a complete, item-by-item inventory listing every individual book, food dish, dance, festival, and musical instrument by name and count, see **[INVENTORY.md](INVENTORY.md)**.

---

## 2. Data Summary & Statistics

Below is an overview of the data currently tracked within the library's local database and archival directories:

| Data Category | Record Count / Volume | Primary Storage Format | Status & Confidence |
| :--- | :--- | :--- | :--- |
| **Master Extracted Bodo Vocabulary** | **508,238** unique words (360,015 Devanagari + 148,223 Roman) | JSON & PDF (`bodo_complete_extracted_vocabulary`) | Complete deduplicated extraction with 100% Hindi & English meanings (6,626,933 corpus tokens) |
| **Lexicon Words** | **512,110** headwords | SQLite `words` table | `unverified` & `verified` with dual Hindi & English meanings |
| **Word Occurrences & Contexts** | **295,578** sentences/citations | SQLite `occurrences` table | Linked to source texts, songs, and folklore (1,565 duplicate occurrences removed) |
| **Folk Songs & Oral Traditions** | **35** complete songs (+ 1 template) | SQLite `folk_songs` table & Master PDF/JSON | `verified` historical / Public Domain & Classical |
| **Historical Books & Treatises** | **15** master volumes | PDF Scans + JSON + TXT (`books/`) | Public Domain & Open Access (1847–2018) |
| **Translated World Classics** | **5** monumental works (Ramayana, Mahabharata, Bible, Gita, Gitanjali) | PDF + JSON (`translated_classics/`) | Multilingual Classical Corpora |
| **Bodo Number System** | **1** complete mathematical architecture | PDF + JSON (`number_system/`) | Cardinals (0 to 1 Cr), Ordinals, Classifiers |
| **Trilingual Dictionaries** | **150+** thematic vocabulary headwords | PDF + JSON (`dictionaries/`) | 10 Semantic Domains (Bodo-English-Hindi) |
| **Oral Folklore (Proverbs & Riddles)** | **8** Proverbs + **320** Riddles | JSON (`folklore/`) + SQLite + Master PDF | `needs_check` / Bodo Sahitya Sabha (Source #31) |
| **Cultural Heritage Notes** | **22** curated topics | Markdown (`.md`) + SQLite | `needs_check` (source-attributed) |
| **Historical Milestone Notes** | **2** detailed history topics | Markdown (`.md`) + SQLite | `needs_check` (source-attributed) |
| **Bibliographic Sources** | **37** registered sources | SQLite `sources` table + CSV | Verified licenses (CC0, Public Domain, Gazettes) |
| **Protected Bodo Native Words** | **31** Roman tokens + 15 Devanagari | Plain text & Python sets | Verified native words protected from filtering |
| **Review / Annotation Batches** | **2** review CSV files | CSV in `data/` | Community annotation candidates |
| **Digitized Archive Publications** | **433 JSON + 73 PDF files** | 100% Complete Dual-Format Archive across all 16 domains (Deduplicated) | >280 MB Scanned PDFs & Compendiums |

---

## 3. Linguistic & Lexical Datasets

### 3.1 Modern Devanagari Vocabulary (Aksharantar)
- **Source**: AI4Bharat Aksharantar Bodo subset ([`ai4bharat/Aksharantar`](https://huggingface.co/datasets/ai4bharat/Aksharantar)).
- **License**: CC0 (Public Domain Dedication).
- **Format**: Ingested into `words` table via [`loaders/aksharantar.py`](file:///f:/bodo/src/bhasha_lib/loaders/aksharantar.py).
- **Contents**:
  - Contains modern standard Bodo orthography in Devanagari script along with Roman transliterations (e.g., `अनुकृति` / `onukriti`, `रंजालि` / `rongjali`, `होदरसायाव` / `hwdorsayao`).
  - Word forms include natural case inflections (genitive `-नि`, accusative `-खौ`, dative `-नो`), plural suffixes (`-फोर`), and postpositional attachments.
  - All entries are initialized with `status = 'unverified'` until reviewed by native speakers.

### 3.2 Historical Roman-Orthography Vocabulary (Anderson 1895)
- **Source**: J. D. Anderson, *A Collection of Kachári Folk-Tales and Rhymes* (1895, Assam Secretariat Press; Project Gutenberg eBook #53506).
- **License**: Public Domain.
- **Archive Path**: [`data/archive/bodo/books/anderson_kachari_folktales.txt`](file:///f:/bodo/data/archive/bodo/books/anderson_kachari_folktales.txt).
- **Contents**:
  - Provides early historical records of Bodo (Kachári) folk narratives and songs recorded in late 19th-century Roman script.
  - Includes bilingual English translations and lexical glosses.
  - Ingested occurrences link historical word usages to specific story contexts and line numbers.

### 3.3 Protected Bodo Vocabulary
Certain high-frequency native Bodo words naturally coincide with short English words or function tokens. To prevent automatic NLP pipelines or English wordlist filters from stripping them, the library maintains dedicated protection lists:
- **File Reference**: [`data/bodo_keep_list.txt`](file:///f:/bodo/data/bodo_keep_list.txt) (Roman script) and [`english.py`](file:///f:/bodo/src/bhasha_lib/english.py) (`BODO_PROTECTED_WORDS`).
- **Protected Native Words**:
  - `ai` (mother), `dui` (water), `mai` (paddy/rice), `na` (fish), `nu` (to see), `be` (this), `ha` (land), `da` (don't), `ba` (if), `bo` (also), `ma` (what).

### 3.4 Community Review & Meaning Batches
The library stores prepared CSV batches containing unannotated high-frequency words for community and linguistic evaluation:
- [`data/review_batch_1.csv`](file:///f:/bodo/data/review_batch_1.csv): High-frequency modern Devanagari words formatted with columns for English/Hindi meanings, part-of-speech (`pos`), linguistic origin, and dialect.
- [`data/review_anderson_1.csv`](file:///f:/bodo/data/review_anderson_1.csv): Candidates extracted from 19th-century colonial texts awaiting manual confirmation.

---

## 4. Cultural Knowledge Base

The cultural archive documents Bodo traditions, music, festivals, attire, cuisine, and rituals. Every item is stored as a Markdown document in [`data/archive/bodo/culture/`](file:///f:/bodo/data/archive/bodo/culture/) with YAML frontmatter citing sources.

### 4.1 Inventory of Cultural Notes

| Item Name | Category | Archive File | Region | Sourced Citations |
| :--- | :--- | :--- | :--- | :--- |
| **Bagurumba** | `dance` | [`bagurumba.md`](file:///f:/bodo/data/archive/bodo/culture/bagurumba.md) | Assam | Bodoland Tourism, Boro culture (Wikipedia), Rooftop art-wiki |
| **Bathou** | `ritual` | [`bathou.md`](file:///f:/bodo/data/archive/bodo/culture/bathou.md) | Assam | Bodoland Tourism, Boro culture (Wikipedia) |
| **Bwisagu** | `festival` | [`bwisagu.md`](file:///f:/bodo/data/archive/bodo/culture/bwisagu.md) | Assam | Bodoland Tourism, Boro culture (Wikipedia) |
| **Kherai** | `festival` | [`kherai.md`](file:///f:/bodo/data/archive/bodo/culture/kherai.md) | Assam | Bodoland Tourism, Boro culture (Wikipedia) |
| **Domashi** | `festival` | [`domashi.md`](file:///f:/bodo/data/archive/bodo/culture/domashi.md) | Assam | Bodoland Tourism |
| **Aronai** | `attire` | [`aronai.md`](file:///f:/bodo/data/archive/bodo/culture/aronai.md) | Assam | Bodoland Tourism, Boro culture (Wikipedia) |
| **Dokhona** | `attire` | [`dokhona.md`](file:///f:/bodo/data/archive/bodo/culture/dokhona.md) | Assam | Bodoland Tourism, Boro culture (Wikipedia) |
| **Kham** | `instrument` | [`kham.md`](file:///f:/bodo/data/archive/bodo/culture/kham.md) | Assam | Bodoland Tourism, Boro culture (Wikipedia), Anahad Foundation |
| **Serja** | `instrument` | [`serja.md`](file:///f:/bodo/data/archive/bodo/culture/serja.md) | Assam | Bodoland Tourism, Boro culture (Wikipedia), Anahad Foundation |
| **Siphung** | `instrument` | [`siphung.md`](file:///f:/bodo/data/archive/bodo/culture/siphung.md) | Assam | Bodoland Tourism, Boro culture (Wikipedia), Anahad Foundation |
| **Napham** | `food` | [`napham.md`](file:///f:/bodo/data/archive/bodo/culture/napham.md) | Assam | Bodoland Tourism |
| **Oma jwng narjwi** | `food` | [`oma_jwng_narjwi.md`](file:///f:/bodo/data/archive/bodo/culture/oma_jwng_narjwi.md) | Assam | Bodoland Tourism |
| **Jou & Amaw** | `food` | [`jou.md`](file:///f:/bodo/data/archive/bodo/culture/jou.md) | Assam | Sidney Endle (1911, *The Kacharis*), Bodoland Tourism |
| **Sijou** | `ritual` | [`sijou.md`](file:///f:/bodo/data/archive/bodo/culture/sijou.md) | Assam | Sidney Endle (1911, *The Kacharis*), Bathou Religious Tradition |
| **Eri Silk & Traditional Weaving** | `craft` | [`eri_silk.md`](file:///f:/bodo/data/archive/bodo/culture/eri_silk.md) | Assam | Sidney Endle (1911, *The Kacharis*), Bodoland Sericulture Dept. |
| **Gamsha** | `attire` | [`gamsha.md`](file:///f:/bodo/data/archive/bodo/culture/gamsha.md) | Assam | Bodoland Tourism, Boro culture (Wikipedia) |
| **Noh** | `architecture` | [`noh.md`](file:///f:/bodo/data/archive/bodo/culture/noh.md) | Assam | Sidney Endle (1911, *The Kacharis*), Bodoland Tourism |
| **Haba** | `custom` | [`haba.md`](file:///f:/bodo/data/archive/bodo/culture/haba.md) | Assam | Sidney Endle (1911, *The Kacharis*), Bodo Sahitya Sabha |
| **Jotha** | `instrument` | [`jotha.md`](file:///f:/bodo/data/archive/bodo/culture/jotha.md) | Assam | Bodoland Tourism, Anahad Foundation |
| **Tharkha** | `instrument` | [`tharkha.md`](file:///f:/bodo/data/archive/bodo/culture/tharkha.md) | Assam | Bodoland Tourism, ethnomusicology archives |
| **Bathra Phao (Bodo Proverbs)** | `folklore` | [`proverbs.md`](file:///f:/bodo/data/archive/bodo/culture/proverbs.md) | Assam | Bodo Folk Literature & Oral Traditions (Bodo Sahitya Sabha) |
| **Phake-sol (Bodo Riddles)** | `folklore` | [`riddles.md`](file:///f:/bodo/data/archive/bodo/culture/riddles.md) | Assam | Bodo Folk Literature & Oral Traditions (Bodo Sahitya Sabha) |

### 4.2 Structure of Cultural Notes
Each note contains structured YAML headers:
```yaml
---
category: dance
title: Bagurumba
region: Assam
source: Bodoland Tourism culture page (tourism.bodoland.gov.in); Boro culture (Wikipedia); Bagurumba (rooftopapp.com art-wiki)
confidence: needs_check
related_words: []
---
Body text describing the cultural practice, context, instruments, and season...
```

> [!NOTE]
> All current cultural notes are explicitly marked with `confidence: needs_check`. Per project rules, they are not promoted to `verified` until reviewed against primary ethnographies and verified by native community members.

---

## 5. Historical Timeline & Milestones

The library tracks major historical, literary, and political milestones related to the Bodo community and language preservation in Northeast India.

### 5.1 Historical Notes in the Archive

| Topic / Milestone | Archive File | Key Organizations / Bodies | Citations |
| :--- | :--- | :--- | :--- |
| **Bodo Sahitya Sabha** | [`bodo_sahitya_sabha.md`](file:///f:/bodo/data/archive/bodo/history/bodo_sahitya_sabha.md) | Bodo Sahitya Sabha (founded 1952, Basugaon) | Bodo Sahitya Sabha official site (`bihung.org/about`), Wikipedia |
| **Bodo Script Movement & History** | [`bodo_script_history.md`](file:///f:/bodo/data/archive/bodo/history/bodo_script_history.md) | Language conventions & accords | Boro language (Wikipedia), Grokipedia, Assam archival records |

### 5.2 Timeline Schema & Milestone Tracking
In the database (`timeline_events` table), historical events are tracked with:
- **Title & Description**: Event title and historical narrative.
- **Year Start / End**: Numerical date ranges.
- **Date Precision**: Categorized as `exact`, `decade`, `approximate`, `century`, or `unknown`.
- **Entities & Tags**: Linked lists of people, places, and organizations (e.g. Basugaon, Kokrajhar, Bodo Sahitya Sabha).
- **Verification Status**: Reviewed records record `verified_by` and `verified_on`.

---

## 6. Literature & Oral Heritage Catalogs

### 6.1 Literature Catalog (Works, Genres, Authors)
The database structure supports cataloging Bodo literature across 8 genres:
- **Genres**: `poem`, `short_story`, `novel`, `play`, `folk_tale`, `essay`, `collection`, `other`.
- **Historical Periods & Venues**:
  - Tracks pioneering publications from historical journals such as *Bibar* (1920s), *Alari*, and *Nayek*.
  - Documents author names in both Devanagari and Latin Romanization.
  - Prevents full-text copyright violations by indexing bibliographic metadata, thematic summaries, and publication records without storing unauthorized copies of complete copyrighted books.

### 6.2 Folk Songs & Oral Traditions
The catalog schema supports 9 folk song categories:
- **Types**: `traditional_folk_song`, `work_song`, `festival_song`, `lullaby`, `devotional_song`, `dance_song`, `ritual_song`, `ballad`, `other`.
- **Musical Associations**: Each song record links to traditional instruments (*Kham*, *Siphung*, *Serja*, *Jotha*, *Tharkha*) and festive seasons (e.g. *Bwisagu*).
- **Cataloged Songs (14 Historical Folk Songs)**:
  - Extracted from J. D. Anderson's 1895 public domain collection (*A Collection of Kachari Folk-Tales and Rhymes*, Source #10) and indexed in `folk_songs`.
  - Includes 3 nursery rhymes/lullabies (*Addressed to a Spoiled Child*, *To a Conceited Child*, *Nursery Rhyme of the Orange Tree*), 2 spring festival songs (*Bwisagu Courting Song*, *Reproach Song of Bwisagu*), 2 work songs (*Community Fishing Song*, *Weaver's Song*), 1 ballad (*The Lament of a Mother*), and 6 traditional folk songs (wedding songs, love songs, pastoral dialogue, and humorous household rhymes).
  - **Lyric Word Extraction**: All 200 word tokens across the lyrics were extracted, normalized, and indexed into `words` and `occurrences` tables, linking song vocabulary to full lexical query APIs.

### 6.3 Audio Recordings & Ethical Safeguards
Audio metadata is governed under strict ethical data rules:
- **No Binaries in Git**: Heavy `.mp3`, `.wav`, or `.flac` files are kept out of git repositories.
- **Consent Register**: Audio recording entries track performer permissions across 5 granular flags (`permit_recording`, `permit_publication`, `permit_attribution`, `permit_transcribe`, `permit_redistribute`).
- **Consent Statuses**: `unknown`, `pending`, `granted`, `denied`, `withdrawn`.
- **Immediate Revocation**: Community performers or families can revoke permission at any time, removing recordings from public access.

---

## 7. Sources & Bibliography Registry

Every word occurrence, cultural note, and historical event must cite a registered source in the `sources` table. Below are the primary registered sources:

| Source ID | Title | Type | License | Details / Reference |
| :---: | :--- | :--- | :--- | :--- |
| **2** | Aksharantar brx | `dataset` | **CC0** | AI4Bharat mined transliteration pairs |
| **10** | A Collection of Kachari Folk-Tales and Rhymes | `book` | **public_domain** | J. D. Anderson (1895), Project Gutenberg #53506 |
| **7** | Boro culture / Bagurumba | `culture_note` | **own_words** | Bodoland Tourism, Rooftop Art Wiki, Wikipedia |
| **12** | Bodo Sahitya Sabha | `history_note` | **own_words** | Official Sabha records (`bihung.org`), Wikipedia |
| **13** | Bodo lipi ka itihaas (Script history) | `history_note` | **own_words** | State linguistic history records |
| **14** | Aronai | `culture_note` | **own_words** | Bodoland Tourism, regional textile documentation |
| **15** | Dokhona | `culture_note` | **own_words** | Bodoland Tourism, regional textile documentation |
| **17** | Domashi | `culture_note` | **own_words** | Bodoland Tourism festival archive |
| **18** | Serja | `culture_note` | **own_words** | Bodoland Tourism, Anahad Foundation musical archives |
| **19** | Siphung | `culture_note` | **own_words** | Bodoland Tourism, Anahad Foundation musical archives |
| **20** | Kham | `culture_note` | **own_words** | Bodoland Tourism, Anahad Foundation musical archives |
| **21** | Napham / Oma jwng narjwi | `culture_note` | **own_words** | Bodoland Tourism culinary documentation |
| **22** | Outline Grammar of the Kachári (Bårå) Language | `book` | **public_domain** | Sidney Endle (1884), Assam Secretariat Press |
| **23** | The Kacháris | `book` | **public_domain** | Sidney Endle (1911), Macmillan and Co., London |

---

## 8. How Users Can Browse & Query the Data

Users do not need to write raw SQL to explore the library's contents. `bhasha_lib` provides convenient command-line and Python interfaces.

### 8.1 Searching the Lexicon & Words

#### From the Terminal:
```bash
# Look up a word, its transliteration, and usage occurrences
python -m bhasha_lib.lookup "रंजालि" --db data/lexicon.sqlite

# Check lexical annotation stats (total words, reviewed counts)
python -m bhasha_lib.meanings stats --db data/lexicon.sqlite
```

#### From Python:
```python
from bhasha_lib.db import get_connection, search_word

# Search words starting with a prefix
matches = search_word("रं", db_path="data/lexicon.sqlite")
for word in matches:
    print(f"Word: {word['word']} | Roman: {word['roman']}")

# Fetch usage contexts and sentences
with get_connection("data/lexicon.sqlite") as conn:
    cur = conn.cursor()
    cur.execute(
        "SELECT context FROM occurrences WHERE word = ? LIMIT 3", 
        ("अनुकृति",)
    )
    for row in cur.fetchall():
        print(f"Occurrence: {row['context']}")
```

---

### 8.2 Looking up Cultural Concepts

```python
import bhasha_lib as bl

# Query cultural notes and related words for a topic
result = bl.lookup_term("Bagurumba", db_path="data/lexicon.sqlite")

print("--- Matching Cultural Items ---")
for item in result["culture_items"]:
    print(f"Title: {item['title']} ({item['category']})")
    print(f"Source: {item['source']}")
    print(f"Confidence: {item['confidence']}\n")
```

---

### 8.3 Browsing the History Timeline

```bash
# View complete chronological timeline
python -m bhasha_lib.timeline --db data/lexicon.sqlite

# Filter timeline by year range
python -m bhasha_lib.timeline --from-year 1950 --to-year 2000

# Search historical events by keyword or organization
python -m bhasha_lib.timeline --search "Basugaon" --verbose
```

---

### 8.4 Searching Literature & Folk Songs

```bash
# Search literature by author or title
python -m bhasha_lib.literature --search "सतिश चन्द्र" --verbose

# Filter folk songs by festival or musical instrument
python -m bhasha_lib.folk_songs filter --type festival_song
python -m bhasha_lib.folk_songs search "Kham" --db data/lexicon.sqlite

# View audio recordings attached to a folk song
python -m bhasha_lib.folk_songs recordings 1 --db data/lexicon.sqlite
```

---

### 8.5 Exporting Verified Data

When lexical definitions have been reviewed and verified by community members, users can export clean release packages:

```bash
# Export verified lexicon to CSV, JSON, and license text
python -m bhasha_lib.export_verified --out dist_lexicon --db data/lexicon.sqlite
```

This generates:
- `dist_lexicon/lexicon_verified.csv` (UTF-8 with BOM for easy opening in Excel)
- `dist_lexicon/lexicon_verified.json` (Structured JSON)
- `dist_lexicon/DATA_LICENSE.txt` (License manifest for data attribution)

---

## 9. Data Licensing, Ethics & Provenance

Users and contributors should observe the following guidelines when handling data from `bhasha_lib`:

1. **Code vs. Data Separation**:
   The software engine in `src/bhasha_lib/` is licensed under the **MIT License**. The underlying datasets retain the licenses of their original authors or publishers (e.g. CC0 for Aksharantar, Public Domain for 19th-century texts).
2. **Strict License Enforcement**:
   Every source record in the database requires an explicit, non-empty `license`. Unlicensed or copyright-infringing datasets are strictly excluded.
3. **Indigenous Data Sovereignty & Consent**:
   Oral traditions, community songs, and traditional knowledge are governed by [`CONSENT_AND_ETHICS.md`](file:///f:/bodo/CONSENT_AND_ETHICS.md). Written consent is required for recordings, and performers retain the right to withdraw access at any point.
4. **Confidence Rating Integrity**:
   Data in the repository is transparently tagged as `unverified`, `needs_check`, or `verified`. Users should treat `needs_check` entries as working drafts that cite preliminary references pending native speaker verification.
