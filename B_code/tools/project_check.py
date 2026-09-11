#!/usr/bin/env python3
"""只读检查项目关键目录和文件是否存在。"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

REQUIRED_DIRECTORIES = [
    "00_official",
    "00_official/problem_statement",
    "00_official/simulator_docs",
    "01_team",
    "03_results",
    "03_results/practice/q3",
    "03_results/practice/q4",
    "03_results/stress_test/q3",
    "03_results/stress_test/q4",
    "03_results/ablation",
    "03_results/sensitivity",
    "03_results/formal/q3",
    "03_results/formal/q4",
    "03_results/plot_data",
    "04_paper",
    "04_paper/figures",
    "04_paper/tables",
    "04_paper/references",
    "04_paper/drafts",
    "05_submission",
    "05_submission/source",
    "05_submission/logs",
    "05_submission/results",
    "06_backup",
    "B_code",
    "B_code/frozen",
    "B_code/development",
    "B_code/tests",
    "B_code/tools",
]

REQUIRED_FILES = [
    "01_team/TEAM_STATUS.md",
    "01_team/SOURCE_OF_TRUTH.md",
    "01_team/MODEL_SPEC.md",
    "01_team/CODE_SPEC.md",
    "01_team/CHANGELOG.md",
    "01_team/HANDOFF_LOG.md",
    "01_team/ISSUES.md",
    "01_team/DECISIONS.md",
    "01_team/LITERATURE_TRACKER.xlsx",
    "03_results/RESULTS_MASTER.xlsx",
    "04_paper/paper_material.md",
    "05_submission/README.txt",
    "README_PROJECT.md",
    "B_code/tools/project_check.py",
    "B_code/tools/create_backup.py",
    ".gitignore",
]


def check_path(relative_path: str, expected: str) -> str:
    path = ROOT / relative_path
    if not path.exists():
        return f"[MISSING] {relative_path}"
    if expected == "directory" and not path.is_dir():
        return f"[WARNING] {relative_path} 存在，但不是目录"
    if expected == "file" and not path.is_file():
        return f"[WARNING] {relative_path} 存在，但不是文件"
    return f"[OK] {relative_path}"


def main() -> int:
    results = [check_path(item, "directory") for item in REQUIRED_DIRECTORIES]
    results.extend(check_path(item, "file") for item in REQUIRED_FILES)

    git_path = ROOT / ".git"
    if git_path.is_dir():
        results.append("[OK] Git 仓库已初始化")
    elif git_path.exists():
        results.append("[WARNING] .git 存在，但不是目录")
    else:
        results.append("[WARNING] Git 仓库尚未初始化")

    for result in results:
        print(result)

    missing_count = sum(line.startswith("[MISSING]") for line in results)
    warning_count = sum(line.startswith("[WARNING]") for line in results)
    ok_count = sum(line.startswith("[OK]") for line in results)
    print(f"\n检查汇总：OK={ok_count}, WARNING={warning_count}, MISSING={missing_count}")
    return 1 if missing_count else 0


if __name__ == "__main__":
    raise SystemExit(main())

