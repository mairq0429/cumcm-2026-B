#!/usr/bin/env python3
"""创建不覆盖已有内容的时间戳备份。"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKUP_ROOT = ROOT / "06_backup"
SOURCES = ["01_team", "B_code", "03_results", "04_paper", "05_submission"]


def main() -> int:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    destination = BACKUP_ROOT / timestamp

    if destination.exists():
        print(f"备份未创建：目标已存在，禁止覆盖：{destination}")
        return 1

    missing = [name for name in SOURCES if not (ROOT / name).is_dir()]
    if missing:
        print("备份未创建：以下源目录不存在：" + ", ".join(missing))
        return 1

    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    destination.mkdir()

    try:
        for name in SOURCES:
            shutil.copytree(
                ROOT / name,
                destination / name,
                ignore=shutil.ignore_patterns("__pycache__", ".git"),
            )
    except Exception:
        print(f"备份过程中发生错误。已保留未完成目录以避免隐藏问题：{destination}")
        raise

    print(f"备份创建成功：{destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

