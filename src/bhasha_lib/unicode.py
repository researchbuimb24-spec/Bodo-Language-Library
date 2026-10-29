"""Unicode range and script processing utilities for bhasha_lib.

💡 FILE INSIGHT & PURPOSE:
Validates and processes Unicode script boundaries for Indian languages.
Includes hex range parsing (`0900-097F` for Devanagari), Devanagari character verification,
script coverage calculation, and filtering to ensure linguistic corpus data integrity.
"""

from __future__ import annotations


def parse_unicode_range(unicode_range: str) -> tuple[int, int]:
    """Parse a unicode range string such as '0900-097F' into start and end integers."""
    parts = unicode_range.strip().split("-")
    if len(parts) != 2:
        raise ValueError(
            f"Invalid unicode range format: '{unicode_range}'. Expected 'START-END'."
        )
    start_hex, end_hex = parts[0].strip(), parts[1].strip()
    return int(start_hex, 16), int(end_hex, 16)


def is_char_in_range(char: str, unicode_range: str = "0900-097F") -> bool:
    """Check if a character falls within the specified hexadecimal range."""
    if not char:
        return False
    start, end = parse_unicode_range(unicode_range)
    return start <= ord(char[0]) <= end


def is_devanagari(text: str) -> bool:
    """Check if all alphabetic characters are in Devanagari block (0900-097F)."""
    alpha_chars = [c for c in text if c.isalpha()]
    if not alpha_chars:
        return False
    return all(is_char_in_range(c, "0900-097F") for c in alpha_chars)


TONE_MARKERS: tuple[str, ...] = ("'", "’", "\u02c8", "\u02ca", "\u02cb")


def filter_devanagari(
    text: str, keep_whitespace: bool = True, allow_tone_markers: bool = True
) -> str:
    """Extract Devanagari characters, optional whitespace, and tone markers."""
    filtered = []
    for c in text:
        if is_char_in_range(c, "0900-097F"):
            filtered.append(c)
        elif allow_tone_markers and c in TONE_MARKERS:
            filtered.append(c)
        elif keep_whitespace and c.isspace():
            filtered.append(c)
    return "".join(filtered)


def calculate_coverage(text: str, unicode_range: str = "0900-097F") -> float:
    """Calculate the fraction of non-whitespace characters that belong to the range."""
    non_ws = [c for c in text if not c.isspace()]
    if not non_ws:
        return 0.0
    matching = sum(1 for c in non_ws if is_char_in_range(c, unicode_range))
    return matching / len(non_ws)
