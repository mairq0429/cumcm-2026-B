"""Deterministic Q3 MEC wrapper with documented Q1 provenance.

Production geometry reuses the verified public Q1 implementation at
``B_code/src/q1_localization.py:minimum_enclosing_circle``. That implementation
uses a private fixed seed and recomputes the returned radius from its centre
over every input point. ``EPS_MEC=1.8e-4 m`` is the frozen Q1 numerical
certificate tolerance recorded in MODEL_SPEC, CODE_SPEC and SOURCE_OF_TRUTH.
The independent Q1 report compared 105 finite sets with a brute-force oracle
(maximum observed radius error 1.4210854715202004e-14 m); Q3 adds a separate
500-set oracle. EPS_MEC is a numerical certification bound, not a physical or
localization margin.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

from q1_localization import EPS_MEC, minimum_enclosing_circle as q1_minimum_enclosing_circle


Point = Tuple[float, float]
MEC_IMPLEMENTATION_PROVENANCE = "Q1-localization-v1 verified public minimum_enclosing_circle"
MEC_EPS_PROVENANCE = (
    "Q1 EPS_MEC frozen in MODEL_SPEC/CODE_SPEC/SOURCE_OF_TRUTH; "
    "105-set independent oracle max radius error 1.4210854715202004e-14 m"
)


@dataclass(frozen=True)
class MECCircle:
    center: Point
    radius: float


def minimum_enclosing_circle(points: Iterable[Point]) -> Optional[MECCircle]:
    unique = tuple(sorted(set((float(x), float(y)) for x, y in points)))
    if not unique:
        return None
    if not all(math.isfinite(value) for point in unique for value in point):
        raise ValueError("MEC points must be finite")
    center, radius = q1_minimum_enclosing_circle(unique)
    if center is None or radius is None or not all(math.isfinite(value) for value in (*center, radius)):
        return None
    return MECCircle((float(center[0]), float(center[1])), float(radius))


__all__ = [
    "EPS_MEC", "MECCircle", "MEC_EPS_PROVENANCE",
    "MEC_IMPLEMENTATION_PROVENANCE", "minimum_enclosing_circle",
]
