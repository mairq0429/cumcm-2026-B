"""Fail-closed HTTP adapter for the official simulator protocol."""

from __future__ import annotations

import json
import socket
from typing import Any, Mapping, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .protocol import (
    ActionKind, ExecutionStatus, NormalizedResponse, normalize_response,
    unknown_response,
)


class SimulatorAdapter:
    """Send serial requests; an ambiguous transport result never implies success.

    The adapter deliberately does not retry automatically. Its returned request
    ID and payload allow a later recovery layer to replay the identical request
    under the official idempotency rule without inventing a new logical action.
    """

    def __init__(self, robot_id: str, base_url: str = "http://127.0.0.1:2026", timeout: float = 5.0):
        self.robot_id = robot_id
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._request_number = 0

    def _new_payload(self, action: ActionKind) -> dict[str, Any]:
        self._request_number += 1
        return {
            "arena_id": "default",
            "robot_id": self.robot_id,
            "request_id": f"{action.value}-{self._request_number:04d}",
        }

    def _send(
        self,
        action: ActionKind,
        payload: Mapping[str, Any],
        *,
        channel: Optional[int] = None,
        position: Optional[Tuple[float, float]] = None,
    ) -> NormalizedResponse:
        request_id = str(payload["request_id"])
        request = Request(
            self.base_url + "/" + action.value,
            data=json.dumps(dict(payload)).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = json.loads(response.read().decode("utf-8"))
                if response.status != 200:
                    return unknown_response(action, channel=channel, position=position, request_id=request_id, error=f"HTTP {response.status}")
        except HTTPError as exc:
            try:
                raw_error = json.loads(exc.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return unknown_response(action, channel=channel, position=position, request_id=request_id, error=f"HTTP {exc.code}")
            normalized = normalize_response(
                action, raw_error, channel=channel, position=position,
                request_id=request_id,
            )
            if normalized.execution == ExecutionStatus.UNKNOWN_EXECUTION_STATE:
                return unknown_response(action, channel=channel, position=position, request_id=request_id, error=f"HTTP {exc.code}: indeterminate body")
            return normalized
        except (URLError, socket.timeout, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return unknown_response(action, channel=channel, position=position, request_id=request_id, error=str(exc))
        return normalize_response(action, raw, channel=channel, position=position, request_id=request_id)

    def enter(self) -> NormalizedResponse:
        payload = self._new_payload(ActionKind.ENTER)
        return self._send(ActionKind.ENTER, payload)

    def measure(self, x: float, y: float, channel: int) -> NormalizedResponse:
        payload = self._new_payload(ActionKind.MEASURE)
        payload.update({"position": {"x": x, "y": y}, "channel": channel})
        return self._send(ActionKind.MEASURE, payload, channel=channel, position=(x, y))

    def clear(self, x: float, y: float, channel: int) -> NormalizedResponse:
        payload = self._new_payload(ActionKind.CLEAR)
        payload.update({"position": {"x": x, "y": y}, "channel": channel})
        return self._send(ActionKind.CLEAR, payload, channel=channel, position=(x, y))

    def exit(self) -> NormalizedResponse:
        payload = self._new_payload(ActionKind.EXIT)
        return self._send(ActionKind.EXIT, payload)
