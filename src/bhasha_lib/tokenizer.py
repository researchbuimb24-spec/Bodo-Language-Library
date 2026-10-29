"""Tokenizer and text normalization utilities for Bodo and Indian languages.

💡 FILE INSIGHT & PURPOSE:
Provides language-aware tokenization and normalization for Bodo texts.
Features `tokenize()` for modern Devanagari script (preserving native high-tone markers like Bodo apostrophe / '),
`tokenize_roman()` for 19th-century Latin-script books, and `normalize()` for Unicode NFC cleaning.
"""

from __future__ import annotations

import re
import unicodedata

# Zero-width characters to strip
ZERO_WIDTH_CHARS: str = "\u200b\u200c\u200d\ufeff"

# Map apostrophe variants to standard ASCII apostrophe (')
APOSTROPHE_MAP: dict[int, str] = str.maketrans(
    {
        "\u2019": "'",  # Right single quotation mark
        "\u02bc": "'",  # Modifier letter apostrophe
        "\u2018": "'",  # Left single quotation mark
        "\u0060": "'",  # Grave accent
    }
)

# Devanagari characters excluding dandas (0964, 0965) and digits (0966-096F)
DEV_CHAR_PATTERN: str = r"[\u0900-\u0963\u0970-\u097F]"

# Matches a Devanagari word:
# - Begins with one or more Devanagari characters
# - Can contain internal apostrophes between Devanagari characters
# - Can end with an apostrophe directly after a Devanagari character
WORD_RE: re.Pattern[str] = re.compile(
    rf"{DEV_CHAR_PATTERN}+(?:'{DEV_CHAR_PATTERN}+)*'?"
)


def normalize(text: str) -> str:
    """Normalize text for linguistic processing.

    1. Applies Unicode NFC normalization.
    2. Strips zero-width characters (U+200B, U+200C, U+200D, U+FEFF).
    3. Maps apostrophe variants (U+2019, U+02BC, U+2018, U+0060) to ASCII (').
    """
    if not text:
        return ""

    # NFC normalize first
    normalized = unicodedata.normalize("NFC", text)

    # Strip zero-width characters
    for ch in ZERO_WIDTH_CHARS:
        normalized = normalized.replace(ch, "")

    # Map apostrophe variants to ASCII apostrophe (')
    normalized = normalized.translate(APOSTROPHE_MAP)

    # Re-apply NFC normalization
    return unicodedata.normalize("NFC", normalized)


def tokenize(text: str) -> list[str]:
    """Tokenize text into a list of Devanagari words.

    - Retains apostrophes within or directly after Devanagari characters.
    - Strips Devanagari digits (0966-096F) and dandas (0964, 0965).
    - Excludes standalone apostrophes or quotation marks.
    - Preserves original order, case, and letter forms.
    """
    if not text:
        return []

    # First normalize the input text
    clean_text = normalize(text)

    # Replace dandas with spaces so adjacent words are separated
    clean_text = re.sub(r"[\u0964\u0965]", " ", clean_text)

    # Remove Devanagari digits from words
    clean_text = re.sub(r"[\u0966-\u096F]", "", clean_text)

    # Extract words according to regex
    return WORD_RE.findall(clean_text)


# Matches Latin runs that may contain internal hyphens, apostrophes, or combining marks
ROMAN_WORD_RE: re.Pattern[str] = re.compile(
    r"[A-Za-z\u00C0-\u024F\u0300-\u036F0-9]+(?:[-'][A-Za-z\u00C0-\u024F\u0300-\u036F0-9]+)*"
)


def tokenize_roman(text: str) -> list[str]:
    """Tokenize Latin-script text for Bodo and historical documents.

    - Extracts runs of Latin letters, hyphens, apostrophes, and combining marks.
    - Converts words to lowercase.
    - Ignores tokens shorter than 2 letters.
    - Ignores tokens that contain digits.
    """
    if not text:
        return []

    clean_text = normalize(text)
    candidates = ROMAN_WORD_RE.findall(clean_text)

    words: list[str] = []
    for cand in candidates:
        # Ignore tokens containing digits
        if any(ch.isdigit() for ch in cand):
            continue

        clean_word = cand.strip("'-").lower()
        # Count alphabetic letters
        letters_count = sum(1 for ch in clean_word if ch.isalpha())
        if letters_count < 2:
            continue

        words.append(clean_word)

    return words
