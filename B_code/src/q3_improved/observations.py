"""Immutable geometric observations committed from normalized protocol events."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from typing import Optional, Tuple, TYPE_CHECKING, Union

from .protocol import ClearResult, MeasureResult, NormalizedResponse

if TYPE_CHECKING:
    from .state import Q3State


Point = Tuple[float, float]


@dataclass(frozen=True)
class DirectionObservation:
    position: Point
    bearing_deg: float
    request_id: Optional[str] = None


@dataclass(frozen=True)
class NoSignalObservation:
    position: Point
    request_id: Optional[str] = None


@dataclass(frozen=True)
class NearObservation:
    position: Point
    request_id: Optional[str] = None


_CLEAR_GUARD_TOKEN = object()


@dataclass(frozen=True, init=False)
class ClearNoTargetObservation:
    position: Point
    request_id: Optional[str]

    def __init__(
        self, position: Point, request_id: Optional[str] = None, *,
        _guard_token: object = None,
    ) -> None:
        if _guard_token is not _CLEAR_GUARD_TOKEN:
            raise ValueError("clear-distance observation requires the Q3I-02 geometry guard")
        object.__setattr__(self, "position", position)
        object.__setattr__(self, "request_id", request_id)


GeometricObservation = Union[
    DirectionObservation, NoSignalObservation, NearObservation,
    ClearNoTargetObservation,
]


@dataclass(frozen=True)
class ObservationHistory:
    records: tuple[GeometricObservation, ...] = ()

    @property
    def revision(self) -> str:
        """Stable content revision used to invalidate geometry certificates."""

        payload = "|".join(repr(record) for record in self.records).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def commit_measure(self, response: NormalizedResponse) -> "ObservationHistory":
        if response.accepted is not True or response.position is None:
            return self
        if response.measure_result == MeasureResult.DIRECTION:
            if response.direction_deg is None:
                return self
            record: GeometricObservation = DirectionObservation(
                response.position, response.direction_deg, response.request_id,
            )
        elif response.measure_result == MeasureResult.NO_SIGNAL:
            record = NoSignalObservation(response.position, response.request_id)
        elif response.measure_result == MeasureResult.NEAR:
            record = NearObservation(response.position, response.request_id)
        else:
            return self
        return replace(self, records=self.records + (record,))

    def commit_clear_no_target(
        self, state: "Q3State", response: NormalizedResponse,
    ) -> "ObservationHistory":
        if (
            response.position is None
            or response.clear_result != ClearResult.NO_TARGET_IN_RANGE
            or not state.may_add_clear_distance_exclusion(response)
        ):
            return self
        record = ClearNoTargetObservation(
            response.position, response.request_id, _guard_token=_CLEAR_GUARD_TOKEN,
        )
        return replace(self, records=self.records + (record,))

    @property
    def directions(self) -> tuple[DirectionObservation, ...]:
        return tuple(item for item in self.records if isinstance(item, DirectionObservation))

    @property
    def no_signals(self) -> tuple[NoSignalObservation, ...]:
        return tuple(item for item in self.records if isinstance(item, NoSignalObservation))

    @property
    def nears(self) -> tuple[NearObservation, ...]:
        return tuple(item for item in self.records if isinstance(item, NearObservation))

    @property
    def clear_no_targets(self) -> tuple[ClearNoTargetObservation, ...]:
        return tuple(item for item in self.records if isinstance(item, ClearNoTargetObservation))
