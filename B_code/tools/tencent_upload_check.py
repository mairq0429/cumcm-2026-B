"""Read-only checks for the local Tencent Docs upload staging directory."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_ROOT = PROJECT_ROOT / "07_tencent_docs_upload"


def report(status: str, label: str, path: Path, detail: str = "") -> None:
    suffix = f" - {detail}" if detail else ""
    print(f"[{status}] {label}: {path}{suffix}")


def check_file(label: str, path: Path) -> None:
    if path.is_file():
        report("OK", label, path)
    else:
        report("MISSING", label, path)


def check_directory(label: str, path: Path, warn_if_empty: bool = False) -> None:
    if not path.is_dir():
        report("MISSING", label, path)
        return
    if warn_if_empty and not any(path.iterdir()):
        report("WARNING", label, path, "directory exists but is empty")
        return
    report("OK", label, path)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    check_directory("Upload preparation directory", UPLOAD_ROOT)
    check_file(
        "RESULTS_MASTER",
        UPLOAD_ROOT / "01_RESULTS" / "RESULTS_MASTER.xlsx",
    )
    check_file(
        "LITERATURE_TRACKER",
        UPLOAD_ROOT / "03_LITERATURE" / "LITERATURE_TRACKER.xlsx",
    )
    check_file(
        "Paper MASTER",
        UPLOAD_ROOT / "02_PAPER" / "B题论文_MASTER.docx",
    )
    check_directory(
        "Figures",
        UPLOAD_ROOT / "02_PAPER" / "Figures",
        warn_if_empty=True,
    )
    check_directory(
        "Formal Logs",
        UPLOAD_ROOT / "04_LOGS" / "Formal",
        warn_if_empty=True,
    )

    submission_root = UPLOAD_ROOT / "06_SUBMISSION"
    check_directory("Submission", submission_root)
    for name in ("Paper", "Supporting_Materials", "Final_Backup"):
        check_directory(f"Submission/{name}", submission_root / name)


if __name__ == "__main__":
    main()
