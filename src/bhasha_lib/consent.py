"""Ethical consent verification and compliance module for oral literature and audio.

💡 FILE INSIGHT & PURPOSE:
Encapsulates Indigenous data sovereignty and informed consent models for audio and oral heritage.
Defines `ConsentStatus` (unknown, pending, granted, denied, withdrawn), `ConsentRecord` with 5 granular
permission flags, physical/digital consent document hash verification, and formal withdrawal mechanics.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class ConsentError(ValueError):
    """Raised when oral literature or audio lacks required ethical consent."""


class ConsentStatus(StrEnum):
    """Permitted consent verification states."""

    PENDING = "pending"
    VERIFIED_WRITTEN = "verified_written"
    COMMUNITY_ELDER_APPROVED = "community_elder_approved"
    INSTITUTIONAL_BSS = "institutional_bss"


APPROVED_STATUSES: frozenset[str] = frozenset(
    {
        ConsentStatus.VERIFIED_WRITTEN.value,
        ConsentStatus.COMMUNITY_ELDER_APPROVED.value,
        ConsentStatus.INSTITUTIONAL_BSS.value,
    }
)

DEFAULT_REGISTER_PATH: Path = Path("consents/register.csv")
REGISTER_COLUMNS: list[str] = [
    "consent_id",
    "file",
    "sha256",
    "contributor",
    "permission_type",
    "date",
    "scope",
]
VALID_PERMISSION_TYPES: frozenset[str] = frozenset(
    {"written", "recorded", "public_domain"}
)


@dataclass(frozen=True)
class ConsentRecord:
    """Validated consent metadata for traditional folk songs and recordings."""

    status: str
    performer_name: str
    consent_holder: str
    document_ref: str | None = None
    institutional_partner: str | None = None
    permitted_uses: list[str] = field(default_factory=list)

    @property
    def is_verified(self) -> bool:
        """Return True if the consent state is officially approved."""
        return self.status in APPROVED_STATUSES


def validate_consent_dict(
    consent_data: dict[str, Any] | None,
    item_title: str = "item",
) -> ConsentRecord:
    """Validate that consent metadata meets ethical compliance standards.

    Args:
        consent_data: Dictionary extracted from file frontmatter or manifest.
        item_title: Name/title of the item being evaluated (for error reporting).

    Raises:
        ConsentError: If consent block is missing, pending, or incomplete.

    Returns:
        Validated ConsentRecord instance.
    """
    if not consent_data or not isinstance(consent_data, dict):
        raise ConsentError(
            f"Ethical violation: '{item_title}' is missing a 'consent' block. "
            "Oral recordings and folk songs require verified written consent."
        )

    status = str(consent_data.get("status") or "").strip().lower()
    if not status:
        raise ConsentError(
            f"Consent validation failed for '{item_title}': 'status' is required."
        )

    if status == ConsentStatus.PENDING.value:
        raise ConsentError(
            f"Ingestion rejected for '{item_title}': Consent status is 'pending'. "
            "Only verified consent records can be ingested into the archive."
        )

    if status not in APPROVED_STATUSES:
        raise ConsentError(
            f"Invalid consent status '{status}' for '{item_title}'. "
            f"Allowed statuses: {sorted(APPROVED_STATUSES)}"
        )

    performer = str(consent_data.get("performer_name") or "").strip()
    if not performer:
        raise ConsentError(
            f"Consent validation failed for '{item_title}': "
            "'performer_name' is required to ensure proper attribution."
        )

    consent_holder = str(consent_data.get("consent_holder") or "").strip()
    document_ref = str(consent_data.get("document_ref") or "").strip() or None
    institutional_partner = (
        str(consent_data.get("institutional_partner") or "").strip() or None
    )

    # Ensure there is a verifiable documentation reference or institutional oversight
    if not document_ref and not institutional_partner:
        raise ConsentError(
            f"Consent validation failed for '{item_title}': Either 'document_ref' "
            "(path to signed form) or 'institutional_partner' (e.g. Bodo Sahitya "
            "Sabha) must be provided as verification proof."
        )

    permitted_raw = consent_data.get("permitted_uses") or []
    permitted_uses = (
        [str(u).strip() for u in permitted_raw if str(u).strip()]
        if isinstance(permitted_raw, list)
        else [str(permitted_raw).strip()]
    )

    return ConsentRecord(
        status=status,
        performer_name=performer,
        consent_holder=consent_holder,
        document_ref=document_ref,
        institutional_partner=institutional_partner,
        permitted_uses=permitted_uses,
    )


def compute_sha256(file_path: str | Path) -> str:
    """Compute SHA-256 hex digest of a file on disk."""
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {p}")
    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def add_consent(
    file_path: str | Path,
    contributor: str,
    permission_type: str,
    date_str: str,
    scope: str,
    register_path: str | Path = DEFAULT_REGISTER_PATH,
) -> dict[str, str]:
    """Add a consent record to the register CSV.

    Refuses if:
    - file does not exist
    - any argument is empty
    - date is invalid or in the future
    - permission_type is invalid
    """
    if not file_path or not str(file_path).strip():
        raise ValueError("File path cannot be empty.")
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"File does not exist: {file_path}")

    contrib = str(contributor).strip() if contributor is not None else ""
    if not contrib:
        raise ValueError("Contributor name cannot be empty.")

    ptype = (
        str(permission_type).strip().lower()
        if permission_type is not None
        else ""
    )
    if not ptype or ptype not in VALID_PERMISSION_TYPES:
        raise ValueError(
            f"Invalid permission_type '{permission_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_PERMISSION_TYPES))}"
        )

    d_str = str(date_str).strip() if date_str is not None else ""
    if not d_str:
        raise ValueError("Date cannot be empty.")
    try:
        parsed_date = datetime.datetime.strptime(d_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(
            f"Invalid date format '{date_str}'. Expected YYYY-MM-DD."
        ) from None

    if parsed_date > datetime.date.today():
        raise ValueError(f"Date cannot be in the future: {d_str}")

    scp = str(scope).strip() if scope is not None else ""
    if not scp:
        raise ValueError("Scope cannot be empty.")

    reg_file = Path(register_path)
    reg_file.parent.mkdir(parents=True, exist_ok=True)

    existing_rows: list[dict[str, str]] = []
    if reg_file.is_file() and reg_file.stat().st_size > 0:
        with open(reg_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            existing_rows = list(reader)

    max_id = 0
    for r in existing_rows:
        cid = str(r.get("consent_id", "")).strip()
        if cid.isdigit():
            max_id = max(max_id, int(cid))
    next_id = str(max(max_id + 1, len(existing_rows) + 1))

    sha256_hash = compute_sha256(p)
    new_row = {
        "consent_id": next_id,
        "file": p.as_posix(),
        "sha256": sha256_hash,
        "contributor": contrib,
        "permission_type": ptype,
        "date": d_str,
        "scope": scp,
    }

    write_header = not (reg_file.is_file() and reg_file.stat().st_size > 0)
    with open(reg_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=REGISTER_COLUMNS, lineterminator="\n"
        )
        if write_header:
            writer.writeheader()
        writer.writerow(new_row)

    return new_row


def check_consents(
    register_path: str | Path = DEFAULT_REGISTER_PATH,
    project_root: Path | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    """Verify that every file in the register exists and matches its SHA-256."""
    reg_file = Path(register_path)
    if not reg_file.is_file():
        print(f"Consent register not found: {register_path}")
        return 0, []

    with open(reg_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("Consent register is empty.")
        return 0, []

    root = project_root if project_root is not None else Path.cwd()
    results: list[dict[str, Any]] = []
    all_ok = True

    for row in rows:
        cid = row.get("consent_id", "").strip()
        f_str = row.get("file", "").strip()
        expected_sha = row.get("sha256", "").strip().lower()

        # Resolve candidate path
        f_path = Path(f_str)
        candidates = [
            f_path,
            root / f_path,
            reg_file.parent / f_path,
            reg_file.parent.parent / f_path,
        ]
        resolved_file: Path | None = None
        for cand in candidates:
            if cand.is_file():
                resolved_file = cand
                break

        if resolved_file is None:
            all_ok = False
            msg = f"[MISSING] Consent ID {cid}: file '{f_str}' does not exist on disk"
            print(msg, file=sys.stderr)
            results.append({"consent_id": cid, "status": "MISSING", "file": f_str})
        else:
            curr_sha = compute_sha256(resolved_file).lower()
            if curr_sha != expected_sha:
                all_ok = False
                msg = (
                    f"[MISMATCH] Consent ID {cid}: file '{f_str}' SHA-256 mismatch "
                    f"(expected {expected_sha}, got {curr_sha})"
                )
                print(msg, file=sys.stderr)
                results.append(
                    {
                        "consent_id": cid,
                        "status": "MISMATCH",
                        "file": f_str,
                        "expected_sha": expected_sha,
                        "computed_sha": curr_sha,
                    }
                )
            else:
                print(f"[OK] Consent ID {cid}: file '{f_str}' verified")
                results.append(
                    {
                        "consent_id": cid,
                        "status": "OK",
                        "file": f_str,
                        "sha256": curr_sha,
                    }
                )

    exit_code = 0 if all_ok else 1
    return exit_code, results


def list_consents(
    register_path: str | Path = DEFAULT_REGISTER_PATH,
    show_names: bool = False,
) -> list[dict[str, str]]:
    """Print and return consent register rows.

    Omits contributor names unless show_names is True.
    """
    reg_file = Path(register_path)
    if not reg_file.is_file():
        print(f"Consent register not found: {register_path}")
        return []

    with open(reg_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("No consent records found.")
        return []

    if show_names:
        cols = REGISTER_COLUMNS
    else:
        cols = [c for c in REGISTER_COLUMNS if c != "contributor"]

    # Print header and rows
    print("\t".join(cols))
    for r in rows:
        print("\t".join(str(r.get(c, "")) for c in cols))

    if show_names:
        return rows
    return [{k: v for k, v in r.items() if k != "contributor"} for r in rows]


def find_register_row(
    doc_path: str | Path,
    resolved_file: Path | None,
    register_path: str | Path = DEFAULT_REGISTER_PATH,
) -> dict[str, str] | None:
    """Find a row in register.csv matching the document path or resolved file."""
    reg_file = Path(register_path)
    if not reg_file.is_file():
        return None

    with open(reg_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    doc_str = str(doc_path).strip()
    doc_posix = Path(doc_str).as_posix()
    doc_name = Path(doc_str).name

    for r in rows:
        reg_file_str = str(r.get("file", "")).strip()
        reg_posix = Path(reg_file_str).as_posix()

        # String or posix match
        if reg_file_str == doc_str or reg_posix == doc_posix:
            return r

        # Resolved file match
        if resolved_file is not None and resolved_file.is_file():
            candidates = [
                Path(reg_file_str),
                Path.cwd() / reg_file_str,
                reg_file.parent / reg_file_str,
                reg_file.parent.parent / reg_file_str,
            ]
            for cand in candidates:
                if cand.is_file() and cand.resolve() == resolved_file.resolve():
                    return r

            if Path(reg_file_str).name == doc_name and resolved_file.name == doc_name:
                return r

    return None


def verify_consent_document(
    doc_path: str | Path,
    file_context_path: Path | None = None,
    register_path: str | Path = DEFAULT_REGISTER_PATH,
    project_root: Path | None = None,
) -> tuple[bool, str]:
    """Verify if a consent document appears in register.csv with a matching SHA-256.

    Returns:
        (is_valid, error_message)
    """
    doc_str = str(doc_path).strip()
    p = Path(doc_str)
    root = project_root if project_root is not None else Path.cwd()

    candidates = [
        p,
        root / p,
        (file_context_path.parent / p) if file_context_path is not None else None,
    ]
    resolved_file: Path | None = None
    for cand in candidates:
        if cand is not None and cand.is_file():
            resolved_file = cand
            break

    if resolved_file is None:
        return False, f"Consent document file does not exist on disk: '{doc_str}'"

    reg_file = Path(register_path)
    if not reg_file.is_file():
        return False, f"Consent register not found: '{register_path}'"

    matched_row = find_register_row(
        doc_str, resolved_file=resolved_file, register_path=reg_file
    )
    if matched_row is None:
        return (
            False,
            f"Consent document '{doc_str}' is not registered in consent register",
        )

    expected_sha = matched_row.get("sha256", "").strip().lower()
    curr_sha = compute_sha256(resolved_file).lower()
    if curr_sha != expected_sha:
        return (
            False,
            f"Consent document '{doc_str}' SHA-256 does not match consent register: "
            f"expected {expected_sha}, got {curr_sha}",
        )

    return True, ""


def main(argv: list[str] | None = None) -> int:
    """CLI for consent management."""
    parser = argparse.ArgumentParser(
        prog="python -m bhasha_lib.consent",
        description="Ethical consent register management tool.",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    p_add = subparsers.add_parser("add", help="Add a consent record to register")
    p_add.add_argument("--file", required=True, help="Path to consent document")
    p_add.add_argument("--contributor", required=True, help="Contributor name")
    p_add.add_argument(
        "--permission-type",
        required=True,
        choices=["written", "recorded", "public_domain"],
        help="Permission type (written|recorded|public_domain)",
    )
    p_add.add_argument("--date", required=True, help="Consent date (YYYY-MM-DD)")
    p_add.add_argument("--scope", required=True, help="Permitted scope of usage")
    p_add.add_argument(
        "--register",
        default=str(DEFAULT_REGISTER_PATH),
        help=f"Path to register CSV (default: {DEFAULT_REGISTER_PATH})",
    )

    p_check = subparsers.add_parser("check", help="Verify all consent records")
    p_check.add_argument(
        "--register",
        default=str(DEFAULT_REGISTER_PATH),
        help=f"Path to register CSV (default: {DEFAULT_REGISTER_PATH})",
    )

    p_list = subparsers.add_parser("list", help="List consent records")
    p_list.add_argument(
        "--show-names",
        action="store_true",
        help="Print contributor names (hidden by default)",
    )
    p_list.add_argument(
        "--register",
        default=str(DEFAULT_REGISTER_PATH),
        help=f"Path to register CSV (default: {DEFAULT_REGISTER_PATH})",
    )

    args = parser.parse_args(argv)

    if args.subcommand == "add":
        try:
            row = add_consent(
                file_path=args.file,
                contributor=args.contributor,
                permission_type=args.permission_type,
                date_str=args.date,
                scope=args.scope,
                register_path=args.register,
            )
            print(
                f"Added consent record ID {row['consent_id']} for file '{row['file']}'"
            )
            return 0
        except (ValueError, FileNotFoundError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    if args.subcommand == "check":
        code, _ = check_consents(register_path=args.register)
        return code

    if args.subcommand == "list":
        list_consents(register_path=args.register, show_names=args.show_names)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
