"""P0 channel state machine and confirmed-state commit rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Tuple

from .config import N_CHANNELS
from .coverage import CoverageMatrix
from .observations import ObservationHistory
from .protocol import ClearResult, ExecutionStatus, MeasureResult, NormalizedResponse


Point = Tuple[float, float]


class ChannelStatus(str, Enum):
    UNKNOWN = "unknown"
    DETECTED = "detected"
    CLEAR_READY = "clear_ready"
    CLEARED = "cleared"
    ABSENT_CERTIFIED = "absent_certified"
    RECOVERY = "recovery"


@dataclass
class ChannelState:
    status: ChannelStatus = ChannelStatus.UNKNOWN
    positive_evidence: bool = False
    observations: list[NormalizedResponse] = field(default_factory=list)
    geometry_history: ObservationHistory = field(default_factory=ObservationHistory)
    geometry_revision: Optional[str] = None
    certificate_revision: Optional[str] = None
    clear_target: Optional[Point] = None
    clear_certificate: Optional[Any] = None
    certificate_outer_snapshot: Optional[Any] = None
    recovery_history: list[dict[str, Any]] = field(default_factory=list)
    outer: Optional[Any] = None
    fallback_candidates: list[Any] = field(default_factory=list)
    attempted_cell_ids: set[tuple[int, int]] = field(default_factory=set)
    attempted_centers: list[Point] = field(default_factory=list)
    fallback_responses: list[Any] = field(default_factory=list)


@dataclass
class Q3State:
    position: Point = (0.0, 0.0)
    receiver_channel: int = 1
    virtual_time: float = 0.0
    coverage: CoverageMatrix = field(default_factory=CoverageMatrix)
    channels: dict[int, ChannelState] = field(
        default_factory=lambda: {channel: ChannelState() for channel in range(1, N_CHANNELS + 1)}
    )
    same_point_clear_pending: Optional[int] = None

    def apply_measure(self, response: NormalizedResponse, coverage_node: Optional[int] = None) -> bool:
        channel = response.channel
        if channel is None or channel not in self.channels:
            raise ValueError("measure response needs a valid channel")
        state = self.channels[channel]
        if response.execution == ExecutionStatus.UNKNOWN_EXECUTION_STATE:
            self._invalidate_certificate(state)
            if state.status != ChannelStatus.CLEARED:
                state.status = ChannelStatus.RECOVERY
            return False
        if response.accepted is not True or response.measure_result not in {
            MeasureResult.NO_SIGNAL, MeasureResult.DIRECTION, MeasureResult.NEAR,
        } or response.virtual_time is None:
            if response.accepted is True and state.status != ChannelStatus.CLEARED:
                state.status = ChannelStatus.RECOVERY
            return False

        self._invalidate_certificate(state)
        if response.position is not None:
            self.position = response.position
        self.receiver_channel = channel
        if response.virtual_time is not None:
            self.virtual_time = response.virtual_time
        state.observations.append(response)
        state.geometry_history = state.geometry_history.commit_measure(response)
        if coverage_node is not None:
            self.coverage.commit(channel, coverage_node, response)

        if response.measure_result == MeasureResult.DIRECTION:
            state.positive_evidence = True
            if state.status not in {ChannelStatus.CLEARED, ChannelStatus.CLEAR_READY}:
                state.status = ChannelStatus.DETECTED
        elif response.measure_result == MeasureResult.NEAR:
            state.positive_evidence = True
            if state.status != ChannelStatus.CLEARED:
                state.status = ChannelStatus.CLEAR_READY
                self.same_point_clear_pending = channel

        self._refresh_absence(channel)
        return True

    def apply_clear(self, response: NormalizedResponse, *, provenance: Optional[str] = None) -> bool:
        channel = response.channel
        if channel is None or channel not in self.channels:
            raise ValueError("clear response needs a valid channel")
        state = self.channels[channel]
        if response.execution == ExecutionStatus.UNKNOWN_EXECUTION_STATE:
            self._invalidate_certificate(state)
            if state.status != ChannelStatus.CLEARED:
                state.status = ChannelStatus.RECOVERY
            return False
        if (
            response.accepted is not True
            or response.clear_result in {None, ClearResult.UNKNOWN}
            or response.virtual_time is None
        ):
            if response.accepted is True and state.status != ChannelStatus.CLEARED:
                state.status = ChannelStatus.RECOVERY
            return False
        if response.position is not None:
            self.position = response.position
        if response.virtual_time is not None:
            self.virtual_time = response.virtual_time
        certified_contradiction = bool(
            response.clear_result == ClearResult.NO_TARGET_IN_RANGE
            and state.certificate_revision is not None
            and state.clear_certificate is not None
            and getattr(state.clear_certificate, "operational_clearable", False)
            and getattr(state.clear_certificate, "observation_revision", None) == state.geometry_history.revision
        )
        if certified_contradiction:
            state.recovery_history.append({
                "status": "CERTIFIED_CLEAR_CONTRADICTION",
                "certificate": state.clear_certificate,
                "outer": state.certificate_outer_snapshot,
                "observations": state.geometry_history,
                "response": response,
            })
        if response.clear_result == ClearResult.NO_TARGET_IN_RANGE and provenance == "NEAR_CLEAR":
            state.recovery_history.append({
                "status": "NEAR_CLEAR_CONTRADICTION", "response": response,
            })

        if response.clear_result == ClearResult.SUCCESS:
            state.positive_evidence = True
            state.status = ChannelStatus.CLEARED
            if self.same_point_clear_pending == channel:
                self.same_point_clear_pending = None
        elif response.clear_result in {ClearResult.NO_TARGET_IN_RANGE, ClearResult.OTHER_FAILURE}:
            if provenance == "FALLBACK_CLEAR":
                if response.position is not None:
                    state.attempted_centers.append(response.position)
                state.fallback_responses.append(response)
            if response.clear_result == ClearResult.NO_TARGET_IN_RANGE and provenance in {None, "FALLBACK_CLEAR"}:
                state.geometry_history = state.geometry_history.commit_clear_no_target(self, response)
            state.status = ChannelStatus.RECOVERY
            if self.same_point_clear_pending == channel:
                self.same_point_clear_pending = None
        return True

    @staticmethod
    def _invalidate_certificate(state: ChannelState) -> None:
        had_mec_ready = state.certificate_revision is not None
        state.geometry_revision = None
        state.certificate_revision = None
        state.clear_target = None
        state.clear_certificate = None
        state.certificate_outer_snapshot = None
        if had_mec_ready and state.status == ChannelStatus.CLEAR_READY:
            state.status = ChannelStatus.DETECTED

    def may_add_clear_distance_exclusion(self, response: NormalizedResponse) -> bool:
        return bool(
            response.accepted is True
            and response.clear_result == ClearResult.NO_TARGET_IN_RANGE
            and response.channel in self.channels
            and self.channels[response.channel].positive_evidence
        )

    def absent_certified(self, channel: int) -> bool:
        state = self.channels[channel]
        records = self.coverage.records_for(channel)
        return bool(
            not state.positive_evidence
            and all(record.accepted and record.completed and record.result == MeasureResult.NO_SIGNAL for record in records)
        )

    def _refresh_absence(self, channel: int) -> None:
        state = self.channels[channel]
        if state.status != ChannelStatus.CLEARED and self.absent_certified(channel):
            state.status = ChannelStatus.ABSENT_CERTIFIED

    def terminal(self) -> bool:
        cleared = sum(state.status == ChannelStatus.CLEARED for state in self.channels.values())
        return cleared == 16 or all(
            state.status in {ChannelStatus.CLEARED, ChannelStatus.ABSENT_CERTIFIED}
            for state in self.channels.values()
        )
