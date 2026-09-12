"""Normalize simulator responses without losing raw protocol evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional, Tuple


Point = Tuple[float, float]


class ActionKind(str, Enum):
    ENTER = "enter"
    MEASURE = "measure"
    CLEAR = "clear"
    EXIT = "exit"


class ExecutionStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNKNOWN_EXECUTION_STATE = "unknown_execution_state"


class MeasureResult(str, Enum):
    NO_SIGNAL = "no_signal"
    DIRECTION = "direction"
    NEAR = "near"
    UNKNOWN = "unknown"


class ClearResult(str, Enum):
    SUCCESS = "success"
    NO_TARGET_IN_RANGE = "no_target_in_range"
    OTHER_FAILURE = "other_failure"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class NormalizedResponse:
    action: ActionKind
    execution: ExecutionStatus
    accepted: Optional[bool]
    raw_response: Optional[Mapping[str, Any]]
    raw_result: Optional[str]
    measure_result: Optional[MeasureResult]
    clear_result: Optional[ClearResult]
    virtual_time: Optional[float]
    channel: Optional[int]
    position: Optional[Point]
    direction_deg: Optional[float]
    request_id: Optional[str] = None
    error: Optional[str] = None


def unknown_response(
    action: ActionKind,
    *,
    channel: Optional[int] = None,
    position: Optional[Point] = None,
    request_id: Optional[str] = None,
    error: Optional[str] = None,
) -> NormalizedResponse:
    return NormalizedResponse(
        action=action,
        execution=ExecutionStatus.UNKNOWN_EXECUTION_STATE,
        accepted=None,
        raw_response=None,
        raw_result=None,
        measure_result=MeasureResult.UNKNOWN if action == ActionKind.MEASURE else None,
        clear_result=ClearResult.UNKNOWN if action == ActionKind.CLEAR else None,
        virtual_time=None,
        channel=channel,
        position=position,
        direction_deg=None,
        request_id=request_id,
        error=error,
    )


def normalize_response(
    action: ActionKind,
    raw_response: Mapping[str, Any],
    *,
    channel: Optional[int] = None,
    position: Optional[Point] = None,
    request_id: Optional[str] = None,
) -> NormalizedResponse:
    """Normalize one complete JSON response while preserving its raw mapping."""

    raw = dict(raw_response)
    accepted_value = raw.get("accepted")
    accepted = accepted_value if isinstance(accepted_value, bool) else None
    if accepted is not True:
        execution = (
            ExecutionStatus.REJECTED
            if accepted is False
            else ExecutionStatus.UNKNOWN_EXECUTION_STATE
        )
        return NormalizedResponse(
            action=action,
            execution=execution,
            accepted=accepted,
            raw_response=raw,
            raw_result=None,
            measure_result=MeasureResult.UNKNOWN if action == ActionKind.MEASURE else None,
            clear_result=ClearResult.UNKNOWN if action == ActionKind.CLEAR else None,
            virtual_time=None,
            channel=channel,
            position=position,
            direction_deg=None,
            request_id=request_id,
            error=None if accepted is False else "missing or invalid accepted field",
        )

    virtual_time = raw.get("virtual_time_s")
    committed_time = float(virtual_time) if isinstance(virtual_time, (int, float)) else None
    raw_result: Optional[str] = None
    measure_result: Optional[MeasureResult] = None
    clear_result: Optional[ClearResult] = None
    direction: Optional[float] = None

    if action == ActionKind.MEASURE:
        value = raw.get("measure_result")
        raw_result = value if isinstance(value, str) else None
        try:
            measure_result = MeasureResult(raw_result)
        except (TypeError, ValueError):
            measure_result = MeasureResult.UNKNOWN
        if measure_result == MeasureResult.DIRECTION and isinstance(raw.get("svd_deg"), (int, float)):
            direction = float(raw["svd_deg"])
    elif action == ActionKind.CLEAR:
        value = raw.get("clear_result")
        raw_result = value if isinstance(value, str) else None
        if raw_result == ClearResult.SUCCESS.value:
            clear_result = ClearResult.SUCCESS
        elif raw_result == ClearResult.NO_TARGET_IN_RANGE.value:
            clear_result = ClearResult.NO_TARGET_IN_RANGE
        elif raw_result is None:
            clear_result = ClearResult.UNKNOWN
        else:
            clear_result = ClearResult.OTHER_FAILURE

    return NormalizedResponse(
        action=action,
        execution=ExecutionStatus.ACCEPTED,
        accepted=True,
        raw_response=raw,
        raw_result=raw_result,
        measure_result=measure_result,
        clear_result=clear_result,
        virtual_time=committed_time,
        channel=channel,
        position=position,
        direction_deg=direction,
        request_id=request_id,
    )
