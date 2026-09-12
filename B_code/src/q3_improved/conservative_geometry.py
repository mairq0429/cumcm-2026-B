"""Conservative adaptive-box OUTER for Q3 omnidirectional sources.

Retained boxes mean only ``not proven impossible``. They are never certified
feasible boxes. All geometry can be rebuilt from immutable observations.
"""

from __future__ import annotations

import math
from collections import Counter, deque
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional, Tuple

from q1_localization import wedge_halfplanes

from .config import ARENA_R, BEARING_ALPHA_DEG, CLEAR_R, NEAR_R, RX_MAX, RX_MIN
from .observations import (
    ClearNoTargetObservation, DirectionObservation, NearObservation,
    NoSignalObservation, ObservationHistory,
)


Point = Tuple[float, float]
ULP_FACTOR = 16


def _comparison_slack(*values: float) -> float:
    finite = [abs(value) for value in values if math.isfinite(value)] or [1.0]
    scale = max(1.0, *finite)
    return ULP_FACTOR * math.ulp(scale)


def _proven_gt(left: float, right: float) -> bool:
    return left > right and left - right > _comparison_slack(left, right)


def _proven_le(left: float, right: float) -> bool:
    return left == right or (
        left < right and right - left > _comparison_slack(left, right)
    )


def _proven_ge(left: float, right: float) -> bool:
    return left == right or (
        left > right and left - right > _comparison_slack(left, right)
    )


@dataclass(frozen=True, order=True)
class Box:
    xmin: float
    xmax: float
    ymin: float
    ymax: float

    def __post_init__(self) -> None:
        if not all(math.isfinite(value) for value in (self.xmin, self.xmax, self.ymin, self.ymax)):
            raise ValueError("box coordinates must be finite")
        if self.xmin > self.xmax or self.ymin > self.ymax:
            raise ValueError("box bounds are reversed")

    @property
    def width(self) -> float:
        return self.xmax - self.xmin

    @property
    def height(self) -> float:
        return self.ymax - self.ymin

    @property
    def center(self) -> Point:
        return ((self.xmin + self.xmax) * 0.5, (self.ymin + self.ymax) * 0.5)

    @property
    def corners(self) -> tuple[Point, Point, Point, Point]:
        return (
            (self.xmin, self.ymin), (self.xmin, self.ymax),
            (self.xmax, self.ymin), (self.xmax, self.ymax),
        )

    def split4(self) -> tuple["Box", "Box", "Box", "Box"]:
        cx, cy = self.center
        return (
            Box(self.xmin, cx, self.ymin, cy),
            Box(self.xmin, cx, cy, self.ymax),
            Box(cx, self.xmax, self.ymin, cy),
            Box(cx, self.xmax, cy, self.ymax),
        )

    def contains(self, point: Point) -> bool:
        return self.xmin <= point[0] <= self.xmax and self.ymin <= point[1] <= self.ymax


def dist_lo(box: Box, point: Point) -> float:
    dx = max(box.xmin - point[0], 0.0, point[0] - box.xmax)
    dy = max(box.ymin - point[1], 0.0, point[1] - box.ymax)
    return math.hypot(dx, dy)


def dist_hi(box: Box, point: Point) -> float:
    return max(math.dist(corner, point) for corner in box.corners)


@dataclass(frozen=True)
class FixedRadiusInterval:
    lower: float
    negative_distance_limit: float
    feasible: bool


def fixed_radius_interval_at_point(
    point: Point, observations: ObservationHistory,
) -> FixedRadiusInterval:
    """Return the shared-radius constraints at one candidate source point.

    NEAR reception distances are at most 5 m, so including them cannot raise
    ``max(1000, positive distances)`` and does not change this interval.
    """

    positive_distances = [math.dist(point, item.position) for item in observations.directions]
    lower = max([RX_MIN, *positive_distances])
    negative_limit = min(
        (math.dist(point, item.position) for item in observations.no_signals),
        default=math.inf,
    )
    feasible = lower <= RX_MAX and lower < negative_limit
    return FixedRadiusInterval(lower, negative_limit, feasible)


class ExclusionReason(str, Enum):
    OUTSIDE_ARENA = "OUTSIDE_ARENA"
    DIRECTION_TOO_FAR = "DIRECTION_TOO_FAR"
    DIRECTION_TOO_NEAR = "DIRECTION_TOO_NEAR"
    DIRECTION_WEDGE = "DIRECTION_WEDGE"
    NO_SIGNAL_MIN_RX = "NO_SIGNAL_MIN_RX"
    NEAR_MISS = "NEAR_MISS"
    CLEAR_DISTANCE = "CLEAR_DISTANCE"
    FIXED_R_INCONSISTENT = "FIXED_R_INCONSISTENT"


class BoxStatus(str, Enum):
    EXCLUDED = "EXCLUDED"
    RETAINED_UNCERTAIN = "RETAINED_UNCERTAIN"


@dataclass(frozen=True)
class BoxClassification:
    status: BoxStatus
    reason: Optional[ExclusionReason] = None


def _whole_box_violates_halfplane(box: Box, halfplane: tuple[float, float, float]) -> bool:
    a, b, c = halfplane
    minimum_residual = min(a * x + b * y - c for x, y in box.corners)
    return _proven_gt(minimum_residual, 0.0)


def fixed_radius_box_bounds(
    box: Box, observations: ObservationHistory,
) -> tuple[float, float]:
    lower_min = max(
        [RX_MIN, *(dist_lo(box, item.position) for item in observations.directions)]
    )
    negative_max = min(
        (dist_hi(box, item.position) for item in observations.no_signals),
        default=math.inf,
    )
    return lower_min, negative_max


def classify_box(box: Box, observations: ObservationHistory) -> BoxClassification:
    if _proven_gt(dist_lo(box, (0.0, 0.0)), ARENA_R):
        return BoxClassification(BoxStatus.EXCLUDED, ExclusionReason.OUTSIDE_ARENA)

    for item in observations.directions:
        if _proven_gt(dist_lo(box, item.position), RX_MAX):
            return BoxClassification(BoxStatus.EXCLUDED, ExclusionReason.DIRECTION_TOO_FAR)
        if _proven_le(dist_hi(box, item.position), NEAR_R):
            return BoxClassification(BoxStatus.EXCLUDED, ExclusionReason.DIRECTION_TOO_NEAR)
        if any(
            _whole_box_violates_halfplane(box, halfplane)
            for halfplane in wedge_halfplanes(
                item.position[0], item.position[1], item.bearing_deg,
                BEARING_ALPHA_DEG,
            )
        ):
            return BoxClassification(BoxStatus.EXCLUDED, ExclusionReason.DIRECTION_WEDGE)

    for item in observations.no_signals:
        if _proven_le(dist_hi(box, item.position), RX_MIN):
            return BoxClassification(BoxStatus.EXCLUDED, ExclusionReason.NO_SIGNAL_MIN_RX)

    for item in observations.nears:
        if _proven_gt(dist_lo(box, item.position), NEAR_R):
            return BoxClassification(BoxStatus.EXCLUDED, ExclusionReason.NEAR_MISS)

    for item in observations.clear_no_targets:
        if _proven_le(dist_hi(box, item.position), CLEAR_R):
            return BoxClassification(BoxStatus.EXCLUDED, ExclusionReason.CLEAR_DISTANCE)

    lower_min, negative_max = fixed_radius_box_bounds(box, observations)
    if _proven_gt(lower_min, RX_MAX) or _proven_ge(lower_min, negative_max):
        return BoxClassification(BoxStatus.EXCLUDED, ExclusionReason.FIXED_R_INCONSISTENT)
    return BoxClassification(BoxStatus.RETAINED_UNCERTAIN)


@dataclass(frozen=True)
class OuterDiagnostics:
    retained_box_count: int
    excluded_box_count: int
    split_count: int
    max_depth_reached: int
    budget_exhausted: bool
    exclusion_reason_counts: dict[str, int]


@dataclass(frozen=True)
class OuterResult:
    boxes: tuple[Box, ...]
    diagnostics: OuterDiagnostics

    def contains(self, point: Point) -> bool:
        return any(box.contains(point) for box in self.boxes)


def rebuild_outer_from_observations(
    observations: ObservationHistory,
    *,
    max_depth: int = 6,
    max_boxes: int = 20000,
    split_budget: int = 20000,
    target_box_size: Optional[float] = None,
) -> OuterResult:
    if max_depth < 0 or max_boxes < 1 or split_budget < 0:
        raise ValueError("invalid refinement budget")
    if target_box_size is not None and target_box_size <= 0.0:
        raise ValueError("target_box_size must be positive")

    queue = deque([(Box(-ARENA_R, ARENA_R, -ARENA_R, ARENA_R), 0)])
    retained: list[Box] = []
    excluded = 0
    splits = 0
    maximum_depth = 0
    budget_exhausted = False
    reasons: Counter[str] = Counter()

    while queue:
        box, depth = queue.popleft()
        maximum_depth = max(maximum_depth, depth)
        classification = classify_box(box, observations)
        if classification.status == BoxStatus.EXCLUDED:
            excluded += 1
            assert classification.reason is not None
            reasons[classification.reason.value] += 1
            continue

        size_reached = target_box_size is not None and max(box.width, box.height) <= target_box_size
        depth_reached = depth >= max_depth
        live_count = len(retained) + len(queue) + 1
        can_split = (
            not size_reached
            and not depth_reached
            and splits < split_budget
            and live_count + 3 <= max_boxes
        )
        if can_split:
            queue.extend((child, depth + 1) for child in box.split4())
            splits += 1
        else:
            retained.append(box)
            if not size_reached and not depth_reached and (
                splits >= split_budget or live_count + 3 > max_boxes
            ):
                budget_exhausted = True

    return OuterResult(
        tuple(retained),
        OuterDiagnostics(
            retained_box_count=len(retained),
            excluded_box_count=excluded,
            split_count=splits,
            max_depth_reached=maximum_depth,
            budget_exhausted=budget_exhausted,
            exclusion_reason_counts=dict(sorted(reasons.items())),
        ),
    )


rebuild_outer = rebuild_outer_from_observations


__all__ = [
    "Box", "BoxClassification", "BoxStatus", "ExclusionReason",
    "FixedRadiusInterval", "OuterDiagnostics", "OuterResult", "classify_box",
    "dist_hi", "dist_lo", "fixed_radius_box_bounds",
    "fixed_radius_interval_at_point", "rebuild_outer",
    "rebuild_outer_from_observations",
]
