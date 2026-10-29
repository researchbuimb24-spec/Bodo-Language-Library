"""Word lookup and cultural context search module for bhasha_lib.

💡 FILE INSIGHT & PURPOSE:
Unified multi-table lookup engine (`lookup_term`).
Given any query string, searches words by exact match and prefix match, fetches up to 3 sentence
usage contexts with bibliographic source titles from `occurrences`, and aggregates matching cultural articles.
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path
from typing import Any

from bhasha_lib.culture import related
from bhasha_lib.db import DEFAULT_DB_PATH, get_connection, init_db


def _escape_like(text: str, escape_char: str = "\\") -> str:
    """Escape special pattern characters (%, _, and escape_char) for SQLite LIKE."""
    escaped = text.replace(escape_char, escape_char + escape_char)
    escaped = escaped.replace("%", escape_char + "%")
    return escaped.replace("_", escape_char + "_")


def lookup_term(
    term: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    limit: int = 20,
) -> dict[str, Any]:
    """Look up a term in the lexicon and culture metadata.

    Searches words by exact match first, then by prefix match, up to `limit`
    total results. Normalizes the search term using Unicode NFC.
    Fetches up to 3 context occurrences and source title for each matching word.
    Also fetches related culture items using related().

    Returns:
        dict with keys:
            'term': normalized search term
            'words': list of matching word dicts (with 'occurrences' list)
            'culture_items': list of related culture item dicts
    """
    clean_term = term.strip() if term else ""
    if not clean_term:
        return {"term": "", "words": [], "culture_items": []}

    normalized_term = unicodedata.normalize("NFC", clean_term)
    init_db(db_path)

    words: list[dict[str, Any]] = []

    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Exact match
        cursor.execute(
            """
            SELECT word, roman, meaning_hi, meaning_en, pos, origin, dialect,
                   status, verified_by
            FROM words
            WHERE word = ?
            """,
            (normalized_term,),
        )
        exact_row = cursor.fetchone()
        if exact_row is not None:
            words.append(dict(exact_row))

        # 2. Prefix match
        remaining = limit - len(words)
        if remaining > 0:
            escaped_term = _escape_like(normalized_term)
            prefix_pattern = f"{escaped_term}%"
            cursor.execute(
                """
                SELECT word, roman, meaning_hi, meaning_en, pos, origin, dialect,
                       status, verified_by
                FROM words
                WHERE word LIKE ? ESCAPE '\\'
                  AND word != ?
                ORDER BY word ASC
                LIMIT ?
                """,
                (prefix_pattern, normalized_term, remaining),
            )
            for row in cursor.fetchall():
                words.append(dict(row))

        # 3. Occurrences for each word (up to 3 snippets with source title)
        for w in words:
            cursor.execute(
                """
                SELECT o.context, s.title
                FROM occurrences o
                LEFT JOIN sources s ON o.source_id = s.id
                WHERE o.word = ?
                ORDER BY o.rowid ASC
                LIMIT 3
                """,
                (w["word"],),
            )
            snippets = [
                {
                    "context": row["context"] or "",
                    "title": row["title"] or "Unknown source",
                }
                for row in cursor.fetchall()
            ]
            w["occurrences"] = snippets

    # 4. Related culture items via existing related() function
    culture_res = related(normalized_term, db_path=db_path)
    culture_items = list(culture_res.get("culture_items", []))

    # Also check culture items for exact word match if different from query term
    if not culture_items and words:
        first_word = words[0].get("word")
        if first_word and first_word != normalized_term:
            extra = related(first_word, db_path=db_path).get("culture_items", [])
            culture_items.extend(extra)

    return {
        "term": normalized_term,
        "words": words,
        "culture_items": culture_items,
    }


def print_lookup_results(results: dict[str, Any]) -> None:
    """Format and print lookup results to standard output."""
    term = results.get("term", "")
    words = results.get("words", [])
    culture_items = results.get("culture_items", [])

    if not words and not culture_items:
        print(f"No results found for '{term}' (not found).")
        return

    if words:
        print(f"Found {len(words)} word result(s) for '{term}':\n")
        for idx, w in enumerate(words, start=1):
            print(f"[{idx}] Word: {w.get('word')}")
            print(f"    Roman: {w.get('roman') or '-'}")
            print(f"    Meaning (HI): {w.get('meaning_hi') or '-'}")
            print(f"    Meaning (EN): {w.get('meaning_en') or '-'}")
            print(f"    POS: {w.get('pos') or '-'}")
            print(f"    Origin: {w.get('origin') or '-'}")
            print(f"    Status: {w.get('status') or '-'}")
            print(f"    Verified by: {w.get('verified_by') or '-'}")

            occurrences = w.get("occurrences", [])
            if occurrences:
                print(f"    Occurrences ({len(occurrences)}):")
                for occ in occurrences:
                    print(f"      - [{occ['title']}]: {occ['context']}")
            else:
                print("    Occurrences: (none)")
            print()

    if culture_items:
        print(f"Related Culture Items ({len(culture_items)}):")
        for item in culture_items:
            cat = item.get("category") or "general"
            title = item.get("title") or "Untitled"
            desc = item.get("description") or ""
            print(f"  - [{cat}] {title}")
            if desc:
                first_para = desc.split("\n\n")[0].replace("\n", " ").strip()
                print(f"    {first_para}")
        print()


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for lexicon lookup."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Lookup words and cultural notes in the lexicon database."
    )
    parser.add_argument("term", type=str, help="Word or term to search")
    parser.add_argument(
        "--db",
        type=str,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    args = parser.parse_args(argv)

    results = lookup_term(args.term, db_path=args.db)
    print_lookup_results(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
