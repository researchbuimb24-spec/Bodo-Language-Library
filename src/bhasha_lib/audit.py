"""Audit tool for verifying culture and history notes.

💡 FILE INSIGHT & PURPOSE:
Quality control and ethical audit engine for the repository.
Scans cultural drafts, timeline events, literature, and folk songs for vague citations
(e.g., bare domain names like wikipedia.org), unverified claims, missing consent files,
and possible unauthorized lyrics/verse copies, producing comprehensive verification reports.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from bhasha_lib.consent import DEFAULT_REGISTER_PATH, verify_consent_document
from bhasha_lib.culture import parse_culture_markdown
from bhasha_lib.db import DEFAULT_DB_PATH, get_connection, init_db

VAGUE_SITE_PATTERNS: frozenset[str] = frozenset(
    {
        "wikipedia",
        "google",
        "bing",
        "yahoo",
        "youtube",
        "facebook",
        "internet",
        "online",
        "web",
        "wikimedia",
    }
)

GENERIC_CITATION_SITES: frozenset[str] = frozenset(
    {
        "wikipedia",
        "google",
        "youtube",
        "blog",
        "wordpress",
        "blogspot",
    }
)

VALID_PERMISSION_TYPES: frozenset[str] = frozenset(
    {
        "written",
        "recorded",
        "public_domain",
    }
)


def is_vague_source(source: str | None) -> bool:
    """Return True if source is only a site name without identifying details."""
    if not source:
        return False
    clean = source.strip().lower()
    clean = re.sub(r"^https?://", "", clean)
    clean = re.sub(r"^www\.", "", clean)
    clean = re.sub(r"\.(org|com|net|gov|edu|io)(/.*)?$", "", clean)
    clean = clean.strip(" ./:;,-")
    return clean in VAGUE_SITE_PATTERNS


def parse_permission_date(val: Any) -> tuple[datetime.date | None, bool]:
    """Parse permission date.

    Returns:
        (date_object, is_valid_format_bool)
    """
    if isinstance(val, datetime.date):
        return val, True
    if isinstance(val, datetime.datetime):
        return val.date(), True
    if not val or not str(val).strip():
        return None, False
    try:
        dt = datetime.datetime.strptime(str(val).strip(), "%Y-%m-%d")
        return dt.date(), True
    except ValueError:
        return None, False


def check_source_equals_title(source: str | None, title: str | None) -> bool:
    """Return True if source text equals item title or contains only title."""
    if not source or not title:
        return False
    s_clean = re.sub(r"[^\w]", "", source.lower())
    t_clean = re.sub(r"[^\w]", "", title.lower())
    return bool(s_clean and t_clean and s_clean == t_clean)


def check_possible_lyrics(text: str | None) -> bool:
    """Detect if text resembles verse or lyrics structure."""
    if not text:
        return False
    clean = text.strip()
    if len(clean) > 400:
        return True
    lines = [line.strip() for line in clean.splitlines() if line.strip()]
    if len(lines) > 5:
        return True
    short_lines = [line for line in lines if len(line) < 60]
    if len(short_lines) > 3:
        lengths = [len(line) for line in short_lines]
        if max(lengths) - min(lengths) <= 25:
            return True
    return False


def check_needs_citation_detail(source: str | None) -> bool:
    """Check if source contains only generic site names without details."""
    if not source:
        return False
    source_lower = source.lower()
    has_generic = any(site in source_lower for site in GENERIC_CITATION_SITES)
    if not has_generic:
        return False

    parts = [p.strip() for p in source.split(";") if p.strip()]
    if len(parts) <= 1:
        return True

    non_generic_parts = [
        p
        for p in parts
        if not any(site in p.lower() for site in GENERIC_CITATION_SITES)
    ]
    return len(non_generic_parts) == 0


def scan_markdown_files(
    dir_path: str | Path,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Scan directory recursively for culture/history markdown files.

    Returns mapping of (title, category) -> {'path': Path, 'header': dict, 'body': str}.
    """
    directory = Path(dir_path)
    if not directory.is_dir():
        return {}

    mapping: dict[tuple[str, str], dict[str, Any]] = {}
    for file_path in directory.rglob("*.md"):
        try:
            content = file_path.read_text(encoding="utf-8")
            header, body = parse_culture_markdown(
                content, file_name=file_path.name
            )
            title = str(header.get("title") or "").strip()
            category = str(header.get("category") or "").strip()
            if title and category:
                mapping[(title, category)] = {
                    "path": file_path,
                    "header": header,
                    "body": body,
                }
        except (ValueError, UnicodeDecodeError):
            continue

    return mapping


def get_file_git_origins(
    files: list[Path],
    repo_root: Path | None = None,
) -> tuple[dict[str, str], bool]:
    """Get the initial commit that added each markdown file using git log.

    Returns:
        (dict of file_rel_path -> commit_info, git_available_bool)
    """
    if shutil.which("git") is None:
        return {}, False

    cwd = str(repo_root) if repo_root else None
    results: dict[str, str] = {}

    for file_path in files:
        rel_str = str(file_path).replace("\\", "/")
        try:
            cmd = [
                "git",
                "log",
                "--diff-filter=A",
                "--format=%h %ad %s",
                "--date=short",
                "--",
                str(file_path),
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
                check=False,
            )
            out = proc.stdout.strip()
            if proc.returncode == 0 and out:
                results[rel_str] = out.splitlines()[-1]
            else:
                results[rel_str] = "(uncommitted / excluded from git)"
        except (FileNotFoundError, subprocess.SubprocessError):
            return results, False

    return results, True


def get_file_creation_commit_msg(
    file_path: Path,
    repo_root: Path | None = None,
) -> str:
    """Return subject line of git commit that created file, or '' if uncommitted."""
    if shutil.which("git") is None:
        return ""
    cwd = str(repo_root) if repo_root else None
    try:
        cmd = [
            "git",
            "log",
            "--diff-filter=A",
            "--format=%s",
            "--",
            str(file_path),
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            check=False,
        )
        out = proc.stdout.strip()
        if proc.returncode == 0 and out:
            return out.splitlines()[-1]
        cmd2 = [
            "git",
            "log",
            "--reverse",
            "--format=%s",
            "-n",
            "1",
            "--",
            str(file_path),
        ]
        proc2 = subprocess.run(
            cmd2,
            capture_output=True,
            text=True,
            cwd=cwd,
            check=False,
        )
        out2 = proc2.stdout.strip()
        if proc2.returncode == 0 and out2:
            return out2.splitlines()[0]
        return ""
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""


def get_file_first_commit(
    file_path: Path,
    repo_root: Path | None = None,
) -> str:
    """Return first git commit that added file, or 'uncommitted'."""
    if shutil.which("git") is None:
        return "uncommitted"
    cwd = str(repo_root) if repo_root else None
    try:
        cmd = [
            "git",
            "log",
            "--diff-filter=A",
            "--format=%h %ad %s",
            "--date=short",
            "--",
            str(file_path),
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            check=False,
        )
        out = proc.stdout.strip()
        if proc.returncode == 0 and out:
            return out.splitlines()[-1]
        cmd2 = [
            "git",
            "log",
            "--reverse",
            "--format=%h %ad %s",
            "--date=short",
            "-n",
            "1",
            "--",
            str(file_path),
        ]
        proc2 = subprocess.run(
            cmd2,
            capture_output=True,
            text=True,
            cwd=cwd,
            check=False,
        )
        out2 = proc2.stdout.strip()
        if proc2.returncode == 0 and out2:
            return out2.splitlines()[0]
        return "uncommitted"
    except (FileNotFoundError, subprocess.SubprocessError):
        return "uncommitted"


def list_archive_files(
    dir_path: str | Path = "data/archive/bodo",
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    """List all files in dir_path with size, last modified time, and first git commit.

    Sorted by modified time, newest first.
    """
    directory = Path(dir_path)
    if not directory.exists():
        return []

    files_info: list[dict[str, Any]] = []
    all_files = [p for p in directory.rglob("*") if p.is_file()]

    for f in all_files:
        st = f.stat()
        mtime = datetime.datetime.fromtimestamp(st.st_mtime)
        first_commit = get_file_first_commit(f, repo_root=repo_root)

        try:
            rel = f.relative_to(Path.cwd())
            path_display = str(rel).replace("\\", "/")
        except ValueError:
            try:
                rel = f.relative_to(directory)
                path_display = str(rel).replace("\\", "/")
            except ValueError:
                path_display = str(f).replace("\\", "/")

        files_info.append(
            {
                "path": f,
                "path_display": path_display,
                "size": st.st_size,
                "mtime": mtime,
                "mtime_display": mtime.strftime("%Y-%m-%d %H:%M:%S"),
                "first_commit": first_commit,
            }
        )

    files_info.sort(key=lambda x: x["mtime"], reverse=True)
    return files_info


def print_archive_files(files: list[dict[str, Any]]) -> None:
    """Print table of archive files sorted newest first."""
    print("Archive Files (sorted by modified time, newest first):")
    path_len = max(
        [len("File Path")]
        + [len(item["path_display"]) for item in files]
        + [45]
    )
    col_widths = [path_len, 12, 20, 32]
    headers = ["File Path", "Size", "Modified Time", "First Git Commit"]
    total_w = sum(col_widths) + 3 * (len(col_widths) - 1)
    print("=" * total_w)
    header_line = " | ".join(
        h.ljust(w) for h, w in zip(headers, col_widths, strict=False)
    )
    print(header_line)
    print("-+-".join("-" * w for w in col_widths))

    for item in files:
        fp = item["path_display"].ljust(col_widths[0])
        sz = f"{item['size']} B".ljust(col_widths[1])
        mt = item["mtime_display"].ljust(col_widths[2])
        fc = item["first_commit"][: col_widths[3]].ljust(col_widths[3])
        print(f"{fp} | {sz} | {mt} | {fc}")
    print("=" * total_w)
    print(f"Total files: {len(files)}\n")


def remove_culture_item(
    item_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
    prompt_input: Callable[[str], str] | None = None,
) -> bool:
    """Delete one culture_items row (not the file) after confirmation."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title, category FROM culture_items WHERE id = ?",
            (item_id,),
        )
        row = cursor.fetchone()
        if row is None:
            print(f"Error: culture_items row with ID {item_id} not found.")
            return False

        title = str(row["title"])
        category = str(row["category"])

        prompt_fn = prompt_input if prompt_input is not None else input
        confirmation = prompt_fn(
            f"Type the exact title '{title}' to confirm deletion: "
        )

        if confirmation.strip() != title.strip():
            print("Confirmation failed: Title did not match. Deletion cancelled.")
            return False

        cursor.execute("DELETE FROM culture_items WHERE id = ?", (item_id,))
        print(f"Successfully deleted culture item #{item_id} '{title}' ({category}).")
        return True


def audit_culture_and_history(
    db_path: str | Path = DEFAULT_DB_PATH,
    dir_path: str | Path = "data/archive/bodo",
    register_path: str | Path | None = None,
) -> dict[str, Any]:
    """Audit culture_items rows against repository markdown files.

    Performs read-only validation and reports:
    - NO FILE: database row has no matching markdown file in dir_path
    - NO SOURCE: source is empty or shorter than 15 characters
    - VAGUE SOURCE: source is only a site name (e.g. Wikipedia, Google)
    - SOURCE EQUALS TITLE: source text equals item title or contains only title
    - FOLK SONG WITHOUT CONSENT: missing contributor, permission_type, or date
    - POSSIBLE LYRICS: verse structure or lyrics in folk_song description/body
    - NEEDS CITATION DETAIL: generic site name without page title or 2nd source
    - DUPLICATE TITLE: same title appears in multiple distinct categories
    - VERIFIED WITHOUT NOTE: confidence is 'verified' without 'verified_by' key
    - CONSENT HASH MISMATCH: consent document SHA-256 does not match consent register

    Never modifies database or files.
    """
    init_db(db_path)
    file_map = scan_markdown_files(dir_path)

    # 1. Fetch culture_items rows and source information
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                ci.id,
                ci.category,
                ci.title,
                ci.description,
                ci.year_start,
                ci.confidence,
                s.title AS source_title
            FROM culture_items ci
            LEFT JOIN sources s ON ci.source_id = s.id
            ORDER BY ci.id ASC
            """
        )
        db_rows = [dict(r) for r in cursor.fetchall()]

    # Check title duplicates across categories
    title_categories: dict[str, set[str]] = {}
    for r in db_rows:
        t = str(r["title"] or "").strip()
        c = str(r["category"] or "").strip()
        title_categories.setdefault(t, set()).add(c)

    duplicate_titles = {
        t for t, cats in title_categories.items() if len(cats) > 1
    }

    audit_rows: list[dict[str, Any]] = []
    flagged_problems: list[dict[str, Any]] = []

    cat_counts: dict[str, int] = {}
    conf_counts: dict[str, int] = {}
    flag_counts: dict[str, int] = {
        "NO FILE": 0,
        "NO SOURCE": 0,
        "VAGUE SOURCE": 0,
        "SOURCE EQUALS TITLE": 0,
        "FOLK SONG WITHOUT CONSENT": 0,
        "POSSIBLE LYRICS": 0,
        "NEEDS CITATION DETAIL": 0,
        "DUPLICATE TITLE": 0,
        "VERIFIED WITHOUT NOTE": 0,
        "CONSENT FILE MISSING": 0,
        "FUTURE OR INVALID DATE": 0,
        "UNTRACKED DATA FILE": 0,
    }

    matched_files: list[Path] = []

    for r in db_rows:
        row_id = r["id"]
        cat = str(r["category"] or "").strip()
        title = str(r["title"] or "").strip()
        desc = str(r["description"] or "").strip()
        year = r["year_start"]
        conf = str(r["confidence"] or "needs_check").strip()
        source_title = (r["source_title"] or "").strip()

        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        conf_counts[conf] = conf_counts.get(conf, 0) + 1

        # Match markdown file
        file_info = file_map.get((title, cat))
        if file_info:
            file_path = file_info["path"]
            file_header = file_info["header"]
            file_body = file_info.get("body", "")
            file_display = str(file_path).replace("\\", "/")
            matched_files.append(file_path)
        else:
            file_path = None
            file_header = None
            file_body = ""
            file_display = "NO FILE"

        row_flags: list[str] = []

        # Flag: NO FILE
        if file_path is None:
            row_flags.append("NO FILE")
            flagged_problems.append(
                {
                    "flag": "NO FILE",
                    "row_id": row_id,
                    "title": title,
                    "category": cat,
                    "message": f"No matching markdown file in {dir_path}",
                }
            )

        # Flag: SOURCE EQUALS TITLE
        if check_source_equals_title(source_title, title):
            row_flags.append("SOURCE EQUALS TITLE")
            flagged_problems.append(
                {
                    "flag": "SOURCE EQUALS TITLE",
                    "row_id": row_id,
                    "title": title,
                    "category": cat,
                    "message": (
                        f"Source text '{source_title}' equals the item title"
                    ),
                }
            )

        # Flag: VAGUE SOURCE or NO SOURCE
        if is_vague_source(source_title):
            row_flags.append("VAGUE SOURCE")
            flagged_problems.append(
                {
                    "flag": "VAGUE SOURCE",
                    "row_id": row_id,
                    "title": title,
                    "category": cat,
                    "message": f"Source is only a vague site name: '{source_title}'",
                }
            )
        elif not source_title or len(source_title) < 15:
            row_flags.append("NO SOURCE")
            flagged_problems.append(
                {
                    "flag": "NO SOURCE",
                    "row_id": row_id,
                    "title": title,
                    "category": cat,
                    "message": (
                        f"Source is empty or shorter than 15 chars: '{source_title}'"
                    ),
                }
            )

        # Flag: NEEDS CITATION DETAIL
        if check_needs_citation_detail(source_title):
            row_flags.append("NEEDS CITATION DETAIL")
            flagged_problems.append(
                {
                    "flag": "NEEDS CITATION DETAIL",
                    "row_id": row_id,
                    "title": title,
                    "category": cat,
                    "message": (
                        f"Source '{source_title}' has generic site without 2nd source"
                    ),
                }
            )

        # Flag: FOLK SONG WITHOUT CONSENT
        is_folk_song = (cat == "folk_song") or (
            file_path is not None and "folk_songs" in file_path.parts
        )
        if is_folk_song:
            contributor = (
                file_header.get("contributor") if file_header else None
            )
            perm_type = (
                file_header.get("permission_type") if file_header else None
            )
            perm_date = (
                file_header.get("permission_date") if file_header else None
            )

            has_contrib = bool(contributor and str(contributor).strip())
            has_valid_perm = bool(
                perm_type
                and str(perm_type).strip().lower() in VALID_PERMISSION_TYPES
            )
            has_date = bool(perm_date and str(perm_date).strip())

            if not (has_contrib and has_valid_perm and has_date):
                row_flags.append("FOLK SONG WITHOUT CONSENT")
                flagged_problems.append(
                    {
                        "flag": "FOLK SONG WITHOUT CONSENT",
                        "row_id": row_id,
                        "title": title,
                        "category": cat,
                        "message": (
                            "Folk song missing contributor, valid permission_type "
                            "(written/recorded/public_domain), or permission_date"
                        ),
                    }
                )

            # Flag: CONSENT FILE MISSING
            consent_doc = (
                file_header.get("consent_document") if file_header else None
            )
            consent_file_ok = False
            if consent_doc and str(consent_doc).strip():
                c_path = Path(str(consent_doc).strip())
                if (
                    c_path.is_file()
                    or (Path.cwd() / c_path).is_file()
                    or (
                        file_path is not None
                        and (file_path.parent / c_path).is_file()
                    )
                ):
                    consent_file_ok = True

            if not consent_file_ok:
                row_flags.append("CONSENT FILE MISSING")
                flagged_problems.append(
                    {
                        "flag": "CONSENT FILE MISSING",
                        "row_id": row_id,
                        "title": title,
                        "category": cat,
                        "message": (
                            "Consent document missing or path does not exist on disk: "
                            f"'{consent_doc}'"
                        ),
                    }
                )
            else:
                # Flag: CONSENT HASH MISMATCH
                reg_file = register_path
                if reg_file is None:
                    env_reg = os.environ.get("BHASHA_CONSENT_REGISTER")
                    if env_reg:
                        reg_file = Path(env_reg)
                    else:
                        reg_file = DEFAULT_REGISTER_PATH

                if Path(reg_file).is_file():
                    valid_consent, consent_err = verify_consent_document(
                        doc_path=str(consent_doc).strip(),
                        file_context_path=file_path,
                        register_path=reg_file,
                        project_root=Path(dir_path) if dir_path else None,
                    )
                    if not valid_consent:
                        row_flags.append("CONSENT HASH MISMATCH")
                        flagged_problems.append(
                            {
                                "flag": "CONSENT HASH MISMATCH",
                                "row_id": row_id,
                                "title": title,
                                "category": cat,
                                "message": (
                                    "Folk song consent verification failed: "
                                    f"{consent_err}"
                                ),
                            }
                        )

            # Flag: FUTURE OR INVALID DATE
            parsed_d, is_valid_fmt = parse_permission_date(perm_date)
            is_bad_date = False
            if not is_valid_fmt or parsed_d is None:
                is_bad_date = True
            elif parsed_d > datetime.date.today():
                is_bad_date = True

            if is_bad_date:
                row_flags.append("FUTURE OR INVALID DATE")
                flagged_problems.append(
                    {
                        "flag": "FUTURE OR INVALID DATE",
                        "row_id": row_id,
                        "title": title,
                        "category": cat,
                        "message": (
                            "Folk song permission_date is invalid or in the future: "
                            f"'{perm_date}'"
                        ),
                    }
                )

        # Flag: POSSIBLE LYRICS
        if is_folk_song and (
            check_possible_lyrics(desc) or check_possible_lyrics(file_body)
        ):
            row_flags.append("POSSIBLE LYRICS")
            flagged_problems.append(
                {
                    "flag": "POSSIBLE LYRICS",
                    "row_id": row_id,
                    "title": title,
                    "category": cat,
                    "message": "Description or body text resembles song lyrics",
                }
            )

        # Flag: DUPLICATE TITLE
        if title in duplicate_titles:
            row_flags.append("DUPLICATE TITLE")
            all_cats = sorted(title_categories[title])
            flagged_problems.append(
                {
                    "flag": "DUPLICATE TITLE",
                    "row_id": row_id,
                    "title": title,
                    "category": cat,
                    "message": f"Title appears in multiple categories: {all_cats}",
                }
            )

        # Flag: VERIFIED WITHOUT NOTE
        if conf == "verified":
            verified_by = (
                file_header.get("verified_by") if file_header else None
            )
            if not verified_by or not str(verified_by).strip():
                row_flags.append("VERIFIED WITHOUT NOTE")
                flagged_problems.append(
                    {
                        "flag": "VERIFIED WITHOUT NOTE",
                        "row_id": row_id,
                        "title": title,
                        "category": cat,
                        "message": (
                            "Confidence is 'verified' but file lacks 'verified_by' key"
                        ),
                    }
                )

        for f in row_flags:
            flag_counts[f] = flag_counts.get(f, 0) + 1

        audit_rows.append(
            {
                "id": row_id,
                "category": cat,
                "title": title,
                "year_start": year,
                "confidence": conf,
                "source_title": source_title or "-",
                "file_path": file_display,
                "flags": row_flags,
            }
        )

    # Check for UNTRACKED DATA FILE: any .md file under dir_path not in DB
    # and not created by a commit message containing "culture" or "history"
    archive_dir = Path(dir_path)
    all_md_files = (
        sorted(archive_dir.rglob("*.md")) if archive_dir.is_dir() else []
    )
    matched_set = {f.resolve() for f in matched_files}

    for md_file in all_md_files:
        if md_file.resolve() not in matched_set:
            creation_commit = get_file_creation_commit_msg(md_file)
            c_msg_lower = creation_commit.lower()
            is_culture_or_history_commit = (
                "culture" in c_msg_lower or "history" in c_msg_lower
            )
            if not is_culture_or_history_commit:
                flag_counts["UNTRACKED DATA FILE"] = (
                    flag_counts.get("UNTRACKED DATA FILE", 0) + 1
                )
                rel_path = str(md_file).replace("\\", "/")
                flagged_problems.append(
                    {
                        "flag": "UNTRACKED DATA FILE",
                        "row_id": "-",
                        "title": md_file.stem,
                        "category": "-",
                        "message": (
                            f"Markdown file '{rel_path}' is not in database and was "
                            "not created in a culture/history commit "
                            f"('{creation_commit or 'uncommitted'}')"
                        ),
                    }
                )

    # Git origins for scanned markdown files
    all_scanned_files = sorted({info["path"] for info in file_map.values()})
    git_origins, git_available = get_file_git_origins(all_scanned_files)

    return {
        "rows": audit_rows,
        "problems": flagged_problems,
        "summary": {
            "total_rows": len(db_rows),
            "rows_per_category": cat_counts,
            "rows_per_confidence": conf_counts,
            "flag_counts": flag_counts,
        },
        "git_origins": git_origins,
        "git_available": git_available,
    }


def print_audit_report(report: dict[str, Any]) -> None:
    """Format and print the audit table, problem list, summary, and git origins."""
    rows = report.get("rows", [])
    problems = report.get("problems", [])
    summary = report.get("summary", {})
    git_origins = report.get("git_origins", {})
    git_available = report.get("git_available", False)

    print("Culture & History Notes Audit Table")
    print("=" * 105)

    headers = [
        "ID",
        "Category",
        "Title",
        "Year",
        "Confidence",
        "Source Title",
        "File Path",
    ]
    col_widths = [4, 12, 22, 6, 12, 35, 40]

    # Print table header
    header_line = " | ".join(
        h.ljust(w) for h, w in zip(headers, col_widths, strict=False)
    )
    print(header_line)
    print("-+-".join("-" * w for w in col_widths))

    for r in rows:
        row_id = str(r["id"]).ljust(col_widths[0])
        cat = str(r["category"])[: col_widths[1]].ljust(col_widths[1])
        title = str(r["title"])[: col_widths[2]].ljust(col_widths[2])
        year = str(r["year_start"] if r["year_start"] is not None else "-").ljust(
            col_widths[3]
        )
        conf = str(r["confidence"])[: col_widths[4]].ljust(col_widths[4])
        src = str(r["source_title"])[: col_widths[5]].ljust(col_widths[5])
        fp = str(r["file_path"])[: col_widths[6]].ljust(col_widths[6])
        print(f"{row_id} | {cat} | {title} | {year} | {conf} | {src} | {fp}")

    print("\n" + "=" * 105)
    print(f"Flagged Problems ({len(problems)}):")
    print("=" * 105)
    if problems:
        for p in problems:
            print(
                f"  - [{p['flag']}] Row ID {p['row_id']}: \"{p['title']}\" "
                f"({p['category']}) - {p['message']}"
            )
    else:
        print("  (None - all items passed audit checks)")

    print("\n" + "=" * 105)
    print("Audit Summary:")
    print("=" * 105)
    print(f"  Total culture_items rows: {summary.get('total_rows', 0)}")

    print("  Rows per category:")
    for cat, count in sorted(summary.get("rows_per_category", {}).items()):
        print(f"    - {cat}: {count}")

    print("  Rows per confidence:")
    for conf, count in sorted(summary.get("rows_per_confidence", {}).items()):
        print(f"    - {conf}: {count}")

    print("  Flag counts:")
    for flag, count in sorted(summary.get("flag_counts", {}).items()):
        print(f"    - {flag}: {count}")

    print("\n" + "=" * 105)
    print("Markdown File Git Origins:")
    print("=" * 105)
    if not git_available:
        print("  Git is not available, skipping commit history.")
    elif git_origins:
        for fpath, origin in sorted(git_origins.items()):
            print(f"  - {fpath}: {origin}")
    else:
        print("  (No markdown files found)")
    print()


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for audit report or row removal."""
    parser = argparse.ArgumentParser(
        description="Audit culture and history notes in database and filesystem."
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    p_remove = subparsers.add_parser(
        "remove", help="Delete a culture_items row after confirmation"
    )
    p_remove.add_argument(
        "--id", type=int, required=True, dest="item_id", help="Row ID to remove"
    )
    p_remove.add_argument(
        "--db",
        type=str,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )

    p_files = subparsers.add_parser(
        "files", help="List archive files with size, mtime, and git commit"
    )
    p_files.add_argument(
        "--dir",
        type=str,
        default="data/archive/bodo",
        help="Root directory for archive files (default: data/archive/bodo)",
    )

    parser.add_argument(
        "--db",
        type=str,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--dir",
        type=str,
        default="data/archive/bodo",
        help="Root directory for markdown archive files (default: data/archive/bodo)",
    )
    parser.add_argument(
        "--register",
        type=str,
        default=None,
        help="Path to consent register CSV",
    )

    args = parser.parse_args(argv)

    if args.subcommand == "remove":
        success = remove_culture_item(item_id=args.item_id, db_path=args.db)
        return 0 if success else 1

    if args.subcommand == "files":
        files_data = list_archive_files(dir_path=args.dir)
        print_archive_files(files_data)
        return 0

    report = audit_culture_and_history(
        db_path=args.db, dir_path=args.dir, register_path=args.register
    )
    print_audit_report(report)
    return 1 if report.get("problems") else 0


if __name__ == "__main__":
    sys.exit(main())
