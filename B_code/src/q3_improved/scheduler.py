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


def ordered_pending_channels(pending: list[int], current_channel: int, node_index: int) -> list[int]:
    """Deterministic serpentine order with current receiver first when pending."""

    ordered = sorted(pending, reverse=bool(node_index % 2))
    if current_channel in ordered:
        ordered.remove(current_channel)
        ordered.insert(0, current_channel)
    return ordered


class CoverageScheduler:
    def next_action(self, state: Q3State) -> Optional[Action]:
        if state.same_point_clear_pending is not None:
            channel = state.same_point_clear_pending
            if state.channels[channel].status == ChannelStatus.CLEAR_READY:
                return Action(ActionType.CLEAR, state.position, channel)

        # MEC clears are permitted only for a certificate bound to the exact
        # current observation and geometry revisions. Physical-only <=20 m
        # diagnostics never authorize an automatic clear.
        from .clear_certificate import certificate_is_current
        for channel in range(1, N_CHANNELS + 1):
            if certificate_is_current(state, channel):
                target = state.channels[channel].clear_target
                assert target is not None
                return Action(ActionType.CLEAR, target, channel)

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
        return None
