# Ethical Archiving & Community Consent Protocol

> [!IMPORTANT]
> **💡 File Insight & Purpose**:
> - **Role in Library**: Governance charter for indigenous data sovereignty & ethical archiving.
> - **What is happening here**: Defines legal and moral guidelines for preserving Bodo oral traditions, mandating prior written consent, tracking 5 granular permission scopes, forbidding unauthorized audio distribution, and providing standard consent verification forms.
> - **Who should use it**: Community archivists, researchers, ethnomusicologists, and contributors collecting oral literature or audio recordings.

Preserving traditional folk songs (*lok-geet*), oral lore, ritual chants, and spoken audio recordings requires the highest level of cultural sensitivity, legal respect, and community custodianship. 

Traditional cultural expressions belong to the communities that nurtured them. This protocol establishes mandatory requirements for archiving Bodo oral heritage within `bhasha_lib`.

---

## 1. Core Principles

1. **Prior Informed Consent (PIC)**: No audio recording, traditional song lyrics, or sacred chant may be ingested into the archive or database without verifiable, documented written consent from the singer, performer, or community custodians.
2. **Community Ownership & Custodianship**: The Bodo community retains moral and cultural ownership over traditional expressions. Archiving serves preservation, linguistic study, and community revitalization—never commercial exploitation.
3. **Institutional Partnership with Bodo Sahitya Sabha**:
   - The **Bodo Sahitya Sabha (Kokrajhar)** is the apex literary and cultural organization of the Bodo people.
   - Field collection of oral literature and audio recordings should be conducted in consultation with or under the guidance of Bodo Sahitya Sabha representatives, village elders (*Gao-bura*), and local cultural committees.
4. **Right to Withdraw**: Performers and community elders retain the perpetual right to request removal, restriction, or redaction of any sensitive or sacred recording.

---

## 2. Consent Manifest in Song Files

Every folk song markdown file placed in `data/archive/<language>/folk_songs/` must include a verified `consent` section in its YAML frontmatter:

```yaml
---
title: "Bwisagu Folk Song (Habao Fwinailai)"
category: folk_song
genre: "Bwisagu Geeth"
region: "Kokrajhar, Bodoland, Assam"
performer: "Traditional / Performer Name"
recorded_by: "Collector Name"
recording_date: "2026-04-14"
instruments:
  - "Kham"
  - "Siphung"
  - "Serja"
consent:
  status: "verified_written" # Must be 'verified_written' or 'institutional_bss'
  performer_name: "Performer Name"
  consent_holder: "Collector Name / Institution"
  document_ref: "docs/consents/BSS_KOK_2026_001.pdf"
  institutional_partner: "Bodo Sahitya Sabha (Kokrajhar)"
  permitted_uses:
    - "academic_linguistic_research"
    - "cultural_preservation"
    - "educational_non_commercial"
license: "CC-BY-NC-SA-4.0"
---
[Bodo Song Lyrics in Devanagari or Roman script]
```

Any file lacking a valid, verified consent block will be **strictly rejected** by `bhasha_lib.folk_songs`.

---

## 3. Standard Informed Consent Form Template

Field workers and contributors must print and execute this form prior to recording traditional songs or oral histories:

```
================================================================================
                    BODOLAND ORAL HERITAGE ARCHIVE
                 INDEPENDENT & COMMUNITY CONSENT FORM
================================================================================

1. INFORMANT / PERFORMER DETAILS:
   - Full Name: ___________________________________________________________
   - Clan / Mahari: _______________________________________________________
   - Village / Para: ______________________________________________________
   - Post Office & District: _____________________________________________
   - Contact (Phone / Elder): _____________________________________________

2. RECORDING / PERFORMANCE DETAILS:
   - Title / Description of Song/Story: __________________________________
   - Genre (Bwisagu / Kherai / Hagramay / Lullaby): ________________________
   - Primary Instruments: ________________________________________________
   - Language / Dialect: Bodo (brx) / _____________________________________

3. COLLECTOR / ARCHIVIST DETAILS:
   - Name of Collector: __________________________________________________
   - Affiliated Institution / Committee: __________________________________
   - Reference / Identification Code: _____________________________________

4. DECLARATION OF CONSENT:
   I hereby confirm that I have willingly shared this performance / recording
   for the purpose of language preservation, documentation, and academic
   study within the Bhasha Library.

   Permitted uses:
   [X] Linguistic preservation and lexicon development
   [X] Open educational research and academic citation
   [X] Non-commercial cultural education
   [ ] Audio broadcast / public dissemination (Specify: __________________)

5. SIGNATURES & VERIFICATION:

   Performer / Custodian Signature / Thumbprint: __________________________
   Date: ________________________   Place: _______________________________

   Witness / Village Elder (Gao-bura / BSS Representative):
   Name: __________________________________________________________________
   Designation / Village: ________________________________________________
   Signature: __________________________________ Date: ___________________
================================================================================
```

---

## 4. Contact & Institutional Oversight

For queries regarding ethical archiving, community partnerships, or permission verification:
- **Apex Literary Body**: Bodo Sahitya Sabha (Central Office: Kokrajhar, BTR, Assam)
- **Academic Collaborators**: Department of Bodo, Bodoland University (Debargaon, Kokrajhar)
