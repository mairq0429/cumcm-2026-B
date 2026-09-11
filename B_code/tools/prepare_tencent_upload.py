"""Prepare local files for later manual upload to Tencent Docs.

This script only copies local files. It never uploads, moves, or deletes data.
Existing destination files are never overwritten.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_ROOT = PROJECT_ROOT / "07_tencent_docs_upload"

EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "06_backup",
}
SENSITIVE_NAME_PARTS = {
    "credential",
    "credentials",
    "token",
    "password",
    "passwd",
    "cookie",
    "secret",
    "clash",
    "private_account",
}
SENSITIVE_SUFFIXES = {".key", ".pem", ".p12", ".pfx"}


def is_excluded(path: Path) -> bool:
    """Return True for paths that must never enter the upload staging area."""
    lowered_parts = [part.casefold() for part in path.parts]
    if any(part in EXCLUDED_DIR_NAMES for part in lowered_parts):
        return True
    if any("simulator" in part for part in lowered_parts):
        return True

    name = path.name.casefold()
    if name == ".env" or name.startswith(".env."):
        return True
    if path.suffix.casefold() in SENSITIVE_SUFFIXES:
        return True
    return any(fragment in name for fragment in SENSITIVE_NAME_PARTS)


def copy_file(source: Path, destination: Path) -> None:
    if is_excluded(source):
        print(f"[SKIP] excluded: {source}")
        return
    if not source.is_file():
        print(f"[WARNING] source file missing: {source}")
        return
    if destination.exists():
        print(f"[SKIP] destination exists; not overwritten: {destination}")
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source.open("rb") as source_stream:
            with destination.open("xb") as destination_stream:
                shutil.copyfileobj(source_stream, destination_stream)
    except FileExistsError:
        print(f"[SKIP] destination exists; not overwritten: {destination}")
        return
    shutil.copystat(source, destination)
    print(f"[COPY] {source} -> {destination}")


def copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        print(f"[WARNING] source directory missing: {source}")
        return

    found_file = False
    for current_root, dir_names, file_names in os.walk(source, topdown=True):
        current = Path(current_root)
        dir_names[:] = [
            name for name in dir_names if not is_excluded(current / name)
        ]
        for file_name in file_names:
            source_file = current / file_name
            if is_excluded(source_file):
                print(f"[SKIP] excluded: {source_file}")
                continue
            found_file = True
            relative = source_file.relative_to(source)
            copy_file(source_file, destination / relative)

    if not found_file:
        print(f"[WARNING] no eligible files found: {source}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("Tencent Docs local upload preparation (no network upload)")

    file_mappings = [
        (
            PROJECT_ROOT / "03_results" / "RESULTS_MASTER.xlsx",
            UPLOAD_ROOT / "01_RESULTS" / "RESULTS_MASTER.xlsx",
        ),
        (
            PROJECT_ROOT / "01_team" / "LITERATURE_TRACKER.xlsx",
            UPLOAD_ROOT / "03_LITERATURE" / "LITERATURE_TRACKER.xlsx",
        ),
    ]
    tree_mappings = [
        (
            PROJECT_ROOT / "04_paper" / "figures",
            UPLOAD_ROOT / "02_PAPER" / "Figures",
        ),
        (
            PROJECT_ROOT / "04_paper" / "tables",
            UPLOAD_ROOT / "02_PAPER" / "Tables",
        ),
        (
            PROJECT_ROOT / "05_submission",
            UPLOAD_ROOT / "06_SUBMISSION",
        ),
        (
            PROJECT_ROOT / "03_results" / "formal",
            UPLOAD_ROOT / "04_LOGS" / "Formal" / "03_results_formal",
        ),
        (
            PROJECT_ROOT / "05_submission" / "logs",
            UPLOAD_ROOT / "04_LOGS" / "Formal" / "05_submission_logs",
        ),
        (
            PROJECT_ROOT / "B_code" / "logs",
            UPLOAD_ROOT / "04_LOGS" / "Formal" / "B_code_logs",
        ),
    ]

    for source, destination in file_mappings:
        copy_file(source, destination)
    for source, destination in tree_mappings:
        copy_tree(source, destination)


if __name__ == "__main__":
    main()
