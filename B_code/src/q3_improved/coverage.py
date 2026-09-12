"""Seven-node deterministic coverage definitions and bookkeeping."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from .config import COVERAGE_RING_R, N_CHANNELS, N_COVERAGE_NODES
from .protocol import MeasureResult, NormalizedResponse


Point = Tuple[float, float]


def coverage_nodes() -> tuple[Point, ...]:
    nodes: list[Point] = [(0.0, 0.0)]
    for k in range(6):
        angle = k * math.pi / 3.0
        nodes.append((COVERAGE_RING_R * math.cos(angle), COVERAGE_RING_R * math.sin(angle)))
    return tuple(nodes)


@dataclass(frozen=True)
class CoverageRecord:
    requested: bool = False
    accepted: bool = False
    completed: bool = False
    result: Optional[MeasureResult] = None
    raw_result: Optional[str] = None
    virtual_time: Optional[float] = None
    event_id: Optional[str] = None


class CoverageMatrix:
    def __init__(self) -> None:
        self._records = [
            [CoverageRecord() for _ in range(N_COVERAGE_NODES)]
            for _ in range(N_CHANNELS)
        ]

    def get(self, channel: int, node: int) -> CoverageRecord:
        self._validate(channel, node)
        return self._records[channel - 1][node]

    def commit(self, channel: int, node: int, response: NormalizedResponse) -> bool:
        """Commit only an accepted, recognized fixed-node measure."""

        self._validate(channel, node)
        if response.accepted is not True or response.measure_result not in {
            MeasureResult.NO_SIGNAL, MeasureResult.DIRECTION, MeasureResult.NEAR,
        }:
            return False
        self._records[channel - 1][node] = CoverageRecord(
            requested=True,
            accepted=True,
            completed=True,
            result=response.measure_result,
            raw_result=response.raw_result,
            virtual_time=response.virtual_time,
            event_id=response.request_id,
        )
        return True

    def records_for(self, channel: int) -> tuple[CoverageRecord, ...]:
        self._validate(channel, 0)
        return tuple(self._records[channel - 1])

    @staticmethod
    def _validate(channel: int, node: int) -> None:
        if not 1 <= channel <= N_CHANNELS:
            raise ValueError("channel must be in 1..20")
        if not 0 <= node < N_COVERAGE_NODES:
            raise ValueError("node must be in 0..6")
