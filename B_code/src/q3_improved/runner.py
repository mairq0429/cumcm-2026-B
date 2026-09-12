"""Minimal P0 online action loop; truth-blind and fail-closed."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from .clear_certificate import bind_clear_certificate, certificate_from_outer
from .fallback import build_fallback_candidates
from .protocol import ActionKind, ClearResult, ExecutionStatus, NormalizedResponse
from .scheduler import Action, ActionType, CoverageScheduler
from .state import ChannelStatus, Q3State


def _jsonable(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: _jsonable(val) for key, val in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


class P0Runner:
    def __init__(self, adapter: Any, *, journal_path: Optional[str | Path] = None, max_actions: int = 10000):
        self.adapter = adapter
        self.state = Q3State()
        self.scheduler = CoverageScheduler()
        self.max_actions = max_actions
        self.journal_path = Path(journal_path) if journal_path else None
        self.journal: list[dict[str, Any]] = []

    def _record(self, sequence: int, action: Action, response: NormalizedResponse, before: dict[str, Any]) -> None:
        self.journal.append({
            "sequence": sequence, "action_type": action.action_type.value,
            "position": action.position, "channel": action.channel,
            "coverage_node": action.coverage_node, "provenance": action.provenance,
            "fallback_cell_id": action.fallback_cell_id,
            "accepted": response.accepted, "raw_response": response.raw_response,
            "raw_result": response.raw_result,
            "normalized_result": (response.measure_result or response.clear_result),
            "virtual_time": response.virtual_time,
            "channel_state_before": before["status"],
            "channel_state_after": self.state.channels[action.channel].status.value,
            "recovery_reason": self.state.channels[action.channel].recovery_history[-1].get("status") if self.state.channels[action.channel].recovery_history else None,
        })

    def _rebuild_channel(self, channel: int) -> None:
        from .conservative_geometry import rebuild_outer_from_observations
        from .clear_certificate import certificate_from_outer
        state = self.state.channels[channel]
        outer = rebuild_outer_from_observations(state.geometry_history)
        state.outer = outer
        cert = certificate_from_outer(outer)
        if state.status == ChannelStatus.DETECTED and cert.operational_clearable:
            bind_clear_certificate(self.state, channel, cert)
        state.fallback_candidates = build_fallback_candidates(outer.boxes, current_position=self.state.position)

    def _execute(self, action: Action) -> NormalizedResponse:
        if action.action_type == ActionType.MEASURE:
            return self.adapter.measure(*action.position, action.channel)
        return self.adapter.clear(*action.position, action.channel)

    def run(self) -> Q3State:
        enter = self.adapter.enter()
        if enter.execution != ExecutionStatus.ACCEPTED:
            return self.state
        for sequence in range(self.max_actions):
            if self.state.terminal() or any(s.status == ChannelStatus.RECOVERY for s in self.state.channels.values()):
                break
            action = self.scheduler.next_action(self.state)
            if action is None:
                # No pending action with a detected channel and no untried
                # intersecting cell is a safety contradiction, never success.
                for channel_state in self.state.channels.values():
                    if channel_state.status == ChannelStatus.DETECTED and channel_state.outer is not None:
                        candidates = build_fallback_candidates(channel_state.outer.boxes, current_position=self.state.position)
                        if candidates and all(c.cell_id in channel_state.attempted_cell_ids for c in candidates):
                            channel_state.status = ChannelStatus.RECOVERY
                            channel_state.recovery_history.append({"status": "FALLBACK_GUARANTEE_CONTRADICTION"})
                break
            before = {"status": self.state.channels[action.channel].status.value}
            response = self._execute(action)
            if response.execution == ExecutionStatus.UNKNOWN_EXECUTION_STATE:
                if action.action_type == ActionType.MEASURE:
                    self.state.apply_measure(response, action.coverage_node)
                else:
                    self.state.apply_clear(response, provenance=action.provenance)
            elif action.action_type == ActionType.MEASURE:
                self.state.apply_measure(response, action.coverage_node)
                if response.accepted and response.channel:
                    self._rebuild_channel(response.channel)
            else:
                if action.provenance == "FALLBACK_CLEAR" and action.fallback_cell_id is not None:
                    self.state.channels[action.channel].attempted_cell_ids.add(action.fallback_cell_id)
                    self.state.channels[action.channel].attempted_centers.append(action.position)
                    self.state.channels[action.channel].fallback_responses.append(response)
                self.state.apply_clear(response, provenance=action.provenance)
                if response.accepted and response.channel and response.clear_result == ClearResult.NO_TARGET_IN_RANGE and action.provenance == "FALLBACK_CLEAR":
                    channel_state = self.state.channels[response.channel]
                    if self.state.may_add_clear_distance_exclusion(response):
                        channel_state.status = ChannelStatus.DETECTED
                        self._rebuild_channel(response.channel)
            self._record(sequence, action, response, before)
        self.adapter.exit()
        if self.journal_path:
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
            with self.journal_path.open("w", encoding="utf-8") as handle:
                for item in self.journal:
                    handle.write(json.dumps(_jsonable(item), sort_keys=True) + "\n")
        return self.state
