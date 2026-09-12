"""Deterministic seven-node coverage scheduler; no active localization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from .config import N_CHANNELS, N_COVERAGE_NODES
from .coverage import coverage_nodes
from .state import ChannelStatus, Q3State


Point = Tuple[float, float]


class ActionType(str, Enum):
    MEASURE = "measure"
    CLEAR = "clear"


@dataclass(frozen=True)
class Action:
    action_type: ActionType
    position: Point
    channel: int
    coverage_node: Optional[int] = None
    provenance: Optional[str] = None
    fallback_cell_id: Optional[tuple[int, int]] = None


def ordered_pending_channels(pending: list[int], current_channel: int, node_index: int) -> list[int]:
    """Deterministic serpentine order with current receiver first when pending."""

    ordered = sorted(pending, reverse=bool(node_index % 2))
    if current_channel in ordered:
        ordered.remove(current_channel)
        ordered.insert(0, current_channel)
    return ordered


class CoverageScheduler:
    def next_action(self, state: Q3State) -> Optional[Action]:
        if any(item.status == ChannelStatus.RECOVERY for item in state.channels.values()):
            return None
        if state.same_point_clear_pending is not None:
            channel = state.same_point_clear_pending
            if state.channels[channel].status == ChannelStatus.CLEAR_READY:
                return Action(ActionType.CLEAR, state.position, channel, provenance="NEAR_CLEAR")

        # MEC clears are permitted only for a certificate bound to the exact
        # current observation and geometry revisions. Physical-only <=20 m
        # diagnostics never authorize an automatic clear.
        from .clear_certificate import certificate_is_current
        for channel in range(1, N_CHANNELS + 1):
            if certificate_is_current(state, channel):
                target = state.channels[channel].clear_target
                assert target is not None
                return Action(ActionType.CLEAR, target, channel, provenance="MEC_CERTIFIED_CLEAR")

        nodes = coverage_nodes()
        for node in range(N_COVERAGE_NODES):
            pending = [
                channel for channel in range(1, N_CHANNELS + 1)
                if state.channels[channel].status not in {ChannelStatus.CLEARED, ChannelStatus.ABSENT_CERTIFIED}
                and not state.coverage.get(channel, node).completed
            ]
            if pending:
                channel = ordered_pending_channels(pending, state.receiver_channel, node)[0]
                return Action(ActionType.MEASURE, nodes[node], channel, coverage_node=node)
        # Fallback is considered only after all mandatory coverage is complete.
        from .fallback import build_fallback_candidates
        for channel in range(1, N_CHANNELS + 1):
            channel_state = state.channels[channel]
            if channel_state.status != ChannelStatus.DETECTED or not channel_state.positive_evidence:
                continue
            candidates = build_fallback_candidates(
                getattr(channel_state, "outer", None).boxes if getattr(channel_state, "outer", None) else (),
                current_position=state.position,
            )
            attempted = getattr(channel_state, "attempted_cell_ids", set())
            for candidate in candidates:
                if candidate.cell_id not in attempted:
                    return Action(ActionType.CLEAR, candidate.center, channel, provenance="FALLBACK_CLEAR", fallback_cell_id=candidate.cell_id)
        return None
