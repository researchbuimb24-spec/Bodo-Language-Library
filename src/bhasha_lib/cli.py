"""Command-line interface for Bodo language translation.

💡 FILE INSIGHT & PURPOSE:
Implements the console command `bodo-translate` and CLI argument parser.
Allows users to translate text between Bodo and English/Hindi, detect language,
switch between online (Google GTX) and offline SQLite morphological engines,
and execute batch translations from the terminal.
"""

from __future__ import annotations

import argparse
import sys

from bhasha_lib.db import DEFAULT_DB_PATH
from bhasha_lib.translator import BodoTranslator


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser for bodo-translate CLI."""
    parser = argparse.ArgumentParser(
        prog="bodo-translate",
        description="Bodo multi-engine translation and language detection CLI.",
    )
    parser.add_argument(
        "text",
        nargs="*",
        help="Text string(s) to translate or detect (reads stdin if omitted).",
    )
    parser.add_argument(
        "-s",
        "--source",
        default="auto",
        help="Source language code (default: auto). Use 'brx' or 'bodo' for Bodo.",
    )
    parser.add_argument(
        "-t",
        "--target",
        default="brx",
        help="Target language code (default: brx for Bodo).",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Force offline rule-based translation via SQLite lexicon.",
    )
    parser.add_argument(
        "--detect",
        action="store_true",
        help="Detect language of the input text instead of translating.",
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite lexicon database (default: {DEFAULT_DB_PATH}).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute bodo-translate CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Gather input text from arguments or stdin
    raw_text = " ".join(args.text).strip() if args.text else ""
    if not raw_text and not sys.stdin.isatty():
        raw_text = sys.stdin.read().strip()

    if not raw_text:
        parser.print_help(sys.stderr)
        print("\nError: No input text provided.", file=sys.stderr)
        return 1

    translator = BodoTranslator(
        force_offline=args.offline,
        db_path=args.db,
    )

    if args.detect:
        detected_lang = translator.detect(raw_text, offline=args.offline)
        print(detected_lang)
        return 0

    translated_text = translator.translate(
        raw_text,
        source=args.source,
        target=args.target,
        offline=args.offline,
    )
    print(translated_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
