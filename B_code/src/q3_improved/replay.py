"""Replay the explicitly printed subset of historical Q3 console evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .protocol import ActionKind, ClearResult, normalize_response


CLEAR_PATTERN = re.compile(r"\bresult=(success|no_target_in_range)\b")


@dataclass(frozen=True)
class ConsoleReplaySummary:
    evidence_source: str
    success_count: int
    no_target_in_range_count: int
    request_ids: str = "NOT_CHECKABLE"
    raw_response_completeness: str = "NOT_CHECKABLE"
    duplicate_commit_semantics: str = "NOT_CHECKABLE"


def replay_console_files(paths: list[Path]) -> ConsoleReplaySummary:
    success = 0
    no_target = 0
    for path in paths:
        for raw_value in CLEAR_PATTERN.findall(path.read_text(encoding="utf-8")):
            response = normalize_response(
                ActionKind.CLEAR,
                {"accepted": True, "virtual_time_s": 0.0, "clear_result": raw_value},
            )
            success += response.clear_result == ClearResult.SUCCESS
            no_target += response.clear_result == ClearResult.NO_TARGET_IN_RANGE
    return ConsoleReplaySummary(
        evidence_source="console_output.txt selective printed fields (not raw wire responses)",
        success_count=success,
        no_target_in_range_count=no_target,
    )
