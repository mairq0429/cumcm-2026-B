"""Deterministic, conservative fallback grid for detected Q3 channels."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from .config import OPER_CLEAR_R
from .conservative_geometry import Box


GRID_H = OPER_CLEAR_R * math.sqrt(2.0)


@dataclass(frozen=True, order=True)
class FallbackCandidate:
    cell_id: tuple[int, int]
    center: tuple[float, float]


def _index_range(lo: float, hi: float) -> range:
    # Include both boundary cells: edge/corner contact is an intersection.
    eps = 8.0 * math.ulp(max(1.0, abs(lo), abs(hi), GRID_H))
    first = math.floor((lo - eps) / GRID_H)
    last = math.floor((hi + eps) / GRID_H)
    return range(first, last + 1)


def build_fallback_candidates(
    retained_boxes: Iterable[Box],
    *,
    current_position: tuple[float, float] = (0.0, 0.0),
) -> list[FallbackCandidate]:
    """Return one center per grid cell intersecting at least one retained box."""

    cells: set[tuple[int, int]] = set()
    for box in retained_boxes:
        for ix in _index_range(box.xmin, box.xmax):
            for iy in _index_range(box.ymin, box.ymax):
                cells.add((ix, iy))
    candidates = [
        FallbackCandidate((ix, iy), ((ix + 0.5) * GRID_H, (iy + 0.5) * GRID_H))
        for ix, iy in cells
    ]
    candidates.sort(key=lambda item: (math.dist(item.center, current_position), item.cell_id))
    return candidates


def candidate_distance_bound() -> float:
    return GRID_H / math.sqrt(2.0)
