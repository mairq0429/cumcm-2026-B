"""Q2 robust second-station selection, model Q2-robust-selection-v2.1.

This first implementation slice covers milestones M1--M3.  All convex
clipping, polygon cleanup, region classification, diameter, MEC and geometry
tolerances are imported from the verified Q1 implementation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Iterable, Mapping, Optional, Sequence

from q1_localization import (
    DEFAULT_TOLERANCES,
    EPS_MEC,
    NumericalTolerances,
    analyze_convex_region,
    circumscribed_circle_polygon,
    classify_region,
    half_plane_clip,
    point_in_convex_region,
    polygon_area,
    wedge_halfplanes,
)


Point = tuple[float, float]
SOURCE_RADIUS_M = 1800.0
FIRST_RECEIVE_MAX_M = 1500.0
RECEIVE_FLOOR_M = 1000.0
NEAR_RADIUS_M = 5.0
BEARING_ERROR_DEG = 1.0
SPEED_MPS = 5.0
MEASURE_TIME_S = 5.0
OFFICIAL_CLEAR_RADIUS_M = 20.0
OPERATIONAL_CLEAR_RADIUS_M = 17.0


@dataclass(frozen=True)
class Q2Config:
    circle_sides: int = 1440
    omega_move: Optional[Sequence[Point]] = None
    lmin_m: float = 50.0
    eps_rec_m: float = DEFAULT_TOLERANCES.eps_geo
    error_step_deg: float = 0.1
    source_step_m: float = 20.0
    candidate_steps_m: tuple[float, ...] = (50.0, 20.0, 5.0)
    certificate_max_depth: int = 24
    certificate_max_cells: int = 200_000
    tolerances: NumericalTolerances = field(default=DEFAULT_TOLERANCES)

    def __post_init__(self) -> None:
        if self.circle_sides < 12:
            raise ValueError("circle_sides must be at least 12")
        if self.lmin_m < 0 or self.eps_rec_m < 0:
            raise ValueError("lmin_m and eps_rec_m must be nonnegative")
        if self.error_step_deg <= 0 or self.source_step_m <= 0:
            raise ValueError("sampling steps must be positive")


@dataclass(frozen=True)
class SourceScenario:
    G: Point
    e2_deg: Optional[float] = None
    weight_m2: float = 0.0
    sample_set: str = "Gext"


@dataclass(frozen=True)
class WorstScenario:
    metric: str
    value: float
    G: Point
    e2_deg: Optional[float]
    status: str


@dataclass
class CandidateResult:
    S2: Point
    strict_receive: bool
    certificate: dict
    T2: float
    JD: Optional[float]
    JR: Optional[float]
    JA: Optional[float]
    official20: bool
    operational17: bool
    worst_scenarios: dict[str, WorstScenario]
    HFIM: Optional[float] = None
    robust_guarantee: bool = True

    def to_dict(self) -> dict:
        result = asdict(self)
        result["S2"] = list(self.S2)
        return result


@dataclass
class Q2Result:
    status: str
    model_version: str
    P1: dict
    selected_strict: Optional[CandidateResult]
    diagnostics: dict

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "model_version": self.model_version,
            "P1": self.P1,
            "selected_strict": None if self.selected_strict is None else self.selected_strict.to_dict(),
            "diagnostics": self.diagnostics,
        }


def _point(value: Sequence[float], name: str = "point") -> Point:
    if len(value) != 2:
        raise ValueError(f"{name} must have two coordinates")
    result = (float(value[0]), float(value[1]))
    if not all(math.isfinite(v) for v in result):
        raise ValueError(f"{name} coordinates must be finite")
    return result


def _distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _translated(polygon: Sequence[Point], center: Point) -> list[Point]:
    return [(x + center[0], y + center[1]) for x, y in polygon]


def _inscribed_circle_polygon(radius_m: float, sides: int, center: Point = (0.0, 0.0)) -> list[Point]:
    if radius_m <= 0 or sides < 3:
        raise ValueError("invalid circle polygon")
    step = 2.0 * math.pi / sides
    return [
        (center[0] + radius_m * math.cos(k * step), center[1] + radius_m * math.sin(k * step))
        for k in range(sides)
    ]


def _outer_circle_polygon(radius_m: float, sides: int, center: Point = (0.0, 0.0)) -> list[Point]:
    return _translated(circumscribed_circle_polygon(radius_m, sides), center)


def _clip_by_convex(
    subject: Sequence[Point], clipper: Sequence[Point], tolerances: NumericalTolerances
) -> list[Point]:
    """Intersect two CCW convex polygons using Q1's verified clipper."""

    result = list(subject)
    for index, a in enumerate(clipper):
        b = clipper[(index + 1) % len(clipper)]
        # left of a->b: cross(b-a, p-a)>=0
        hp_a = b[1] - a[1]
        hp_b = a[0] - b[0]
        hp_c = hp_a * a[0] + hp_b * a[1]
        result = half_plane_clip(result, hp_a, hp_b, hp_c, tolerances)
        if not result:
            break
    return result


def bearing(S: Sequence[float], G: Sequence[float]) -> float:
    station, source = _point(S, "S"), _point(G, "G")
    return math.degrees(math.atan2(source[1] - station[1], source[0] - station[0]))


def wrap_pi(angle_rad: float) -> float:
    if not math.isfinite(angle_rad):
        raise ValueError("angle must be finite")
    wrapped = (angle_rad + math.pi) % (2.0 * math.pi) - math.pi
    return 0.0 if abs(wrapped) <= 1.0e-15 else wrapped


def build_P1_bound(
    S1: Sequence[float],
    theta1_hat_deg: float,
    config: Optional[Q2Config] = None,
) -> dict:
    """Build conservative P1_out and lower P1_in circle approximations."""

    cfg = config or Q2Config()
    s1 = _point(S1, "S1")
    theta = float(theta1_hat_deg)
    if not math.isfinite(theta):
        raise ValueError("theta1_hat_deg must be finite")

    outer = _outer_circle_polygon(SOURCE_RADIUS_M, cfg.circle_sides)
    inner = _inscribed_circle_polygon(SOURCE_RADIUS_M, cfg.circle_sides)
    for hp in wedge_halfplanes(s1[0], s1[1], theta, BEARING_ERROR_DEG):
        outer = half_plane_clip(outer, *hp, cfg.tolerances)
        inner = half_plane_clip(inner, *hp, cfg.tolerances)
    outer = _clip_by_convex(
        outer, _outer_circle_polygon(FIRST_RECEIVE_MAX_M, cfg.circle_sides, s1), cfg.tolerances
    )
    inner = _clip_by_convex(
        inner, _inscribed_circle_polygon(FIRST_RECEIVE_MAX_M, cfg.circle_sides, s1), cfg.tolerances
    )
    outer_kind, outer, outer_area = classify_region(outer, cfg.tolerances)
    inner_kind, inner, inner_area = classify_region(inner, cfg.tolerances)
    if outer_kind == "EMPTY":
        raise ValueError("P1_bound is empty under the confirmed first observation")
    xs, ys = [p[0] for p in outer], [p[1] for p in outer]
    bbox = [min(xs), min(ys), max(xs), max(ys)]
    search_box = [bbox[0] - 1500.0, bbox[1] - 1500.0, bbox[2] + 1500.0, bbox[3] + 1500.0]
    return {
        "S1": s1,
        "theta1_hat_deg": theta,
        "circle_sides": cfg.circle_sides,
        "P1_out": outer,
        "P1_in": inner,
        "P1_out_region_type": outer_kind,
        "P1_in_region_type": inner_kind,
        "P1_out_area_m2": outer_area,
        "P1_in_area_m2": inner_area,
        "area_bracket_m2": [inner_area, outer_area],
        "area_discretization_gap_m2": max(0.0, outer_area - inner_area),
        "bbox": bbox,
        "search_box": search_box,
        "omega_move": None if cfg.omega_move is None else list(cfg.omega_move),
        "formal_polygon": "P1_out",
    }


def physical_filter(
    G: Sequence[float] | Iterable[Sequence[float]],
    S1: Sequence[float],
    *,
    tolerance: float = 0.0,
) -> bool | list[Point]:
    """Apply the exact physical source inequalities, independent of P1_out."""

    s1 = _point(S1, "S1")

    def legal(item: Sequence[float]) -> bool:
        point = _point(item, "G")
        d0, d1 = _distance(point, (0.0, 0.0)), _distance(point, s1)
        return d0 <= SOURCE_RADIUS_M + tolerance and d1 > NEAR_RADIUS_M and d1 <= FIRST_RECEIVE_MAX_M + tolerance

    if isinstance(G, Sequence) and len(G) == 2 and all(isinstance(v, (int, float)) for v in G):
        return legal(G)
    return [_point(item, "G") for item in G if legal(item)]


def receive_floor(G: Sequence[float], S1: Sequence[float]) -> float:
    return max(RECEIVE_FLOOR_M, _distance(_point(G, "G"), _point(S1, "S1")))


def receive_violation(S2: Sequence[float], G: Sequence[float], S1: Sequence[float]) -> float:
    """Return f(G)=||G-S2||-max(1000,||G-S1||), in metres."""

    return _distance(_point(G, "G"), _point(S2, "S2")) - receive_floor(G, S1)


def _point_segment_distance(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    denom = dx * dx + dy * dy
    if denom == 0.0:
        return _distance(p, a)
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / denom))
    return _distance(p, (a[0] + t * dx, a[1] + t * dy))


def _min_distance_polygon(p: Point, polygon: Sequence[Point]) -> float:
    kind, canonical, _ = classify_region(polygon, DEFAULT_TOLERANCES)
    if point_in_convex_region(p, canonical, kind, DEFAULT_TOLERANCES):
        return 0.0
    if len(canonical) == 1:
        return _distance(p, canonical[0])
    return min(_point_segment_distance(p, canonical[i], canonical[(i + 1) % len(canonical)]) for i in range(len(canonical)))


def _physical_intersection_possible(polygon: Sequence[Point], S1: Point) -> bool:
    if not polygon:
        return False
    if _min_distance_polygon((0.0, 0.0), polygon) > SOURCE_RADIUS_M:
        return False
    if _min_distance_polygon(S1, polygon) > FIRST_RECEIVE_MAX_M:
        return False
    if max(_distance(S1, p) for p in polygon) <= NEAR_RADIUS_M:
        return False
    return True


def _triangle_children(triangle: Sequence[Point]) -> tuple[list[Point], list[Point]]:
    edges = [(0, 1), (1, 2), (2, 0)]
    i, j = max(edges, key=lambda pair: _distance(triangle[pair[0]], triangle[pair[1]]))
    k = ({0, 1, 2} - {i, j}).pop()
    midpoint = ((triangle[i][0] + triangle[j][0]) / 2.0, (triangle[i][1] + triangle[j][1]) / 2.0)
    return [triangle[i], midpoint, triangle[k]], [midpoint, triangle[j], triangle[k]]


def certified_strict(
    S2: Sequence[float],
    P1_bound: Sequence[Point] | Mapping[str, object],
    S1: Sequence[float],
    config: Optional[Q2Config] = None,
) -> dict:
    """Certify strict reception over the continuous physical set.

    Active triangles use the mandated 2-Lipschitz upper bound
    ``f(Gc)+2*h``.  Physical-invalid cells are skipped only when the entire
    clipped cell is provably invalid; partially intersecting cells subdivide.
    """

    cfg = config or Q2Config()
    s1, s2 = _point(S1, "S1"), _point(S2, "S2")
    polygon = list(P1_bound["P1_out"] if isinstance(P1_bound, Mapping) else P1_bound)
    if _distance(s1, s2) <= cfg.tolerances.eps_geo:
        return {
            "strict_receive": True,
            "certified": True,
            "method": "analytic_identity_plus_physical_domain",
            "upper_bound_m": 0.0,
            "eps_rec_m": cfg.eps_rec_m,
            "cells_examined": 0,
            "boundary_uncertainty_m": 0.0,
            "counterexample": None,
        }
    xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
    lo_x, hi_x, lo_y, hi_y = min(xs), max(xs), min(ys), max(ys)
    queue: list[tuple[list[Point], int]] = [
        ([(lo_x, lo_y), (hi_x, lo_y), (hi_x, hi_y)], 0),
        ([(lo_x, lo_y), (hi_x, hi_y), (lo_x, hi_y)], 0),
    ]
    examined = 0
    certified_leaf_upper = -math.inf
    certified_leaf_h = 0.0
    while queue:
        triangle, depth = queue.pop()
        examined += 1
        if examined > cfg.certificate_max_cells:
            return {
                "strict_receive": False, "certified": False, "method": "triangle_cell_2_lipschitz",
                "upper_bound_m": None, "eps_rec_m": cfg.eps_rec_m,
                "cells_examined": examined, "boundary_uncertainty_m": None,
                "counterexample": None, "reason": "certificate_cell_budget_exhausted",
            }
        clipped = _clip_by_convex(triangle, polygon, cfg.tolerances)
        if not _physical_intersection_possible(clipped, s1):
            continue
        center = (
            sum(p[0] for p in clipped) / len(clipped),
            sum(p[1] for p in clipped) / len(clipped),
        )
        h = max(_distance(center, p) for p in clipped)
        upper = receive_violation(s2, center, s1) + 2.0 * h
        samples = list(clipped) + [center]
        for point in samples:
            if physical_filter(point, s1) and receive_violation(s2, point, s1) > cfg.eps_rec_m:
                return {
                    "strict_receive": False, "certified": True, "method": "triangle_cell_2_lipschitz",
                    "upper_bound_m": upper, "eps_rec_m": cfg.eps_rec_m,
                    "cells_examined": examined, "boundary_uncertainty_m": h,
                    "counterexample": point, "reason": "physical_counterexample",
                }
        if upper <= cfg.eps_rec_m:
            certified_leaf_upper = max(certified_leaf_upper, upper)
            certified_leaf_h = max(certified_leaf_h, h)
            continue
        if depth >= cfg.certificate_max_depth:
            return {
                "strict_receive": False, "certified": False, "method": "triangle_cell_2_lipschitz",
                "upper_bound_m": upper, "eps_rec_m": cfg.eps_rec_m,
                "cells_examined": examined, "boundary_uncertainty_m": h,
                "counterexample": None, "reason": "max_depth_with_active_physical_cell",
            }
        first, second = _triangle_children(triangle)
        queue.append((first, depth + 1))
        queue.append((second, depth + 1))
    return {
        "strict_receive": True,
        "certified": True,
        "method": "triangle_cell_2_lipschitz",
        "upper_bound_m": certified_leaf_upper if math.isfinite(certified_leaf_upper) else None,
        "eps_rec_m": cfg.eps_rec_m,
        "cells_examined": examined,
        "boundary_uncertainty_m": certified_leaf_h,
        "counterexample": None,
    }


def make_P2(
    P1_bound: Sequence[Point] | Mapping[str, object],
    S2: Sequence[float],
    G: Sequence[float],
    e2_deg: float = 0.0,
    *,
    rho: Optional[float] = None,
    config: Optional[Q2Config] = None,
) -> dict:
    """Evaluate one physical second-observation scenario."""

    cfg = config or Q2Config()
    polygon = list(P1_bound["P1_out"] if isinstance(P1_bound, Mapping) else P1_bound)
    s2, source = _point(S2, "S2"), _point(G, "G")
    distance = _distance(source, s2)
    if rho is not None and distance > float(rho):
        raw, status, measured = polygon, "NO_SIGNAL", None
    elif distance <= NEAR_RADIUS_M + cfg.tolerances.eps_geo:
        raw = _clip_by_convex(
            polygon, _outer_circle_polygon(NEAR_RADIUS_M, cfg.circle_sides, s2), cfg.tolerances
        )
        status, measured = "NEAR_TERMINAL", None
    else:
        measured = bearing(s2, source) + float(e2_deg)
        raw = polygon
        for hp in wedge_halfplanes(s2[0], s2[1], measured, BEARING_ERROR_DEG):
            raw = half_plane_clip(raw, *hp, cfg.tolerances)
        status = "BEARING"
    analysis = analyze_convex_region(raw, cfg.tolerances)
    diameter, radius = analysis["diameter"], analysis["mec_radius"]
    if diameter is not None and radius is not None:
        analysis.update({
            "mec_lower_bound_ok": radius + cfg.tolerances.eps_mec >= diameter / 2.0,
            "mec_jung_upper_ok": radius <= diameter / math.sqrt(3.0) + cfg.tolerances.eps_mec,
            "cover_by_diameter_circle": abs(2.0 * radius - diameter) <= 2.0 * cfg.tolerances.eps_mec,
            "diameter_circle_gap_tolerance_m": 2.0 * cfg.tolerances.eps_mec,
            "gap_m": 2.0 * radius - diameter,
        })
    analysis.update({
        "status": status,
        "near_terminal": status == "NEAR_TERMINAL",
        "theta2_hat_deg": measured,
        "G": source,
        "S2": s2,
        "distance_G_S2_m": distance,
        "rho_m": rho,
    })
    if status == "NEAR_TERMINAL" and (diameter is None or radius is None or diameter > 10.0 + cfg.tolerances.eps_cover or radius > 5.0 + cfg.tolerances.eps_mec):
        analysis["diagnostics"].setdefault("validation_failures", []).append("near_geometry_bound_failed")
    return analysis


def _error_values(step_deg: float) -> list[float]:
    count = int(math.ceil(BEARING_ERROR_DEG / step_deg))
    values = {-BEARING_ERROR_DEG, 0.0, BEARING_ERROR_DEG}
    values.update(max(-1.0, min(1.0, -1.0 + k * step_deg)) for k in range(2 * count + 1))
    return sorted(values)


def fim_order_score(S1: Sequence[float], S2: Sequence[float], sources: Iterable[Sequence[float]]) -> Optional[float]:
    values = []
    s1, s2 = _point(S1), _point(S2)
    for source_value in sources:
        source = _point(source_value)
        a = math.radians(bearing(source, s1))
        b = math.radians(bearing(source, s2))
        values.append(math.sin(wrap_pi(a - b)) ** 2)
    if not values:
        return None
    values.sort()
    return values[int(math.floor(0.05 * (len(values) - 1)))]


def evaluate_candidate(
    S2: Sequence[float],
    S1: Sequence[float],
    P1_bound: Sequence[Point] | Mapping[str, object],
    Gext: Iterable[Sequence[float] | SourceScenario],
    config: Optional[Q2Config] = None,
) -> CandidateResult:
    cfg = config or Q2Config()
    s1, s2 = _point(S1, "S1"), _point(S2, "S2")
    certificate = certified_strict(s2, P1_bound, s1, cfg)
    worst: dict[str, WorstScenario] = {}
    source_points: list[Point] = []
    for item in Gext:
        source = item.G if isinstance(item, SourceScenario) else _point(item, "G")
        if not physical_filter(source, s1):
            continue
        source_points.append(source)
        errors: Iterable[Optional[float]] = [None] if _distance(source, s2) <= NEAR_RADIUS_M + cfg.tolerances.eps_geo else _error_values(cfg.error_step_deg)
        for error in errors:
            result = make_P2(P1_bound, s2, source, 0.0 if error is None else error, config=cfg)
            for metric, field_name in (("JD", "diameter"), ("JR", "mec_radius"), ("JA", "area")):
                value = result[field_name]
                if value is not None and (metric not in worst or value > worst[metric].value):
                    worst[metric] = WorstScenario(metric, value, source, error, result["status"])
    JD, JR, JA = (worst[name].value if name in worst else None for name in ("JD", "JR", "JA"))
    return CandidateResult(
        S2=s2,
        strict_receive=bool(certificate["strict_receive"]),
        certificate=certificate,
        T2=_distance(s1, s2) / SPEED_MPS,
        JD=JD,
        JR=JR,
        JA=JA,
        official20=JR is not None and JR + EPS_MEC <= OFFICIAL_CLEAR_RADIUS_M,
        operational17=JR is not None and JR + EPS_MEC <= OPERATIONAL_CLEAR_RADIUS_M,
        worst_scenarios=worst,
        HFIM=fim_order_score(s1, s2, source_points),
    )


def _dominates(a: CandidateResult, b: CandidateResult, epsD: float, epsR: float, epsT: float) -> bool:
    assert a.JD is not None and a.JR is not None and b.JD is not None and b.JR is not None
    tolD = max(epsD, 1.0e-3 * max(1.0, b.JD))
    tolR = max(epsR, 1.0e-3 * max(1.0, b.JR))
    tolT = max(epsT, 1.0e-3 * max(1.0, b.T2))
    no_worse = a.JR <= b.JR + tolR and a.JD <= b.JD + tolD and a.T2 <= b.T2 + tolT
    better = a.JR < b.JR - tolR or a.JD < b.JD - tolD or a.T2 < b.T2 - tolT
    return no_worse and better


def pareto_front(candidates: Iterable[CandidateResult], epsD: float = 0.0, epsR: float = 0.0, epsT: float = 0.0) -> list[CandidateResult]:
    valid = [c for c in candidates if c.strict_receive and c.JD is not None and c.JR is not None]
    return [c for c in valid if not any(_dominates(other, c, epsD, epsR, epsT) for other in valid if other is not c)]


def select_best(candidates: Iterable[CandidateResult], config: Optional[Q2Config] = None) -> Optional[CandidateResult]:
    cfg = config or Q2Config()
    strict = [c for c in candidates if c.strict_receive and _distance(c.S2, (0.0, 0.0)) < math.inf and c.T2 * SPEED_MPS + cfg.tolerances.eps_geo >= cfg.lmin_m]
    c20 = [c for c in strict if c.official20 and c.JR is not None and c.JD is not None]
    if c20:
        return min(c20, key=lambda c: (c.T2, c.JR, c.JD, c.S2[0], c.S2[1]))
    front = pareto_front(strict)
    if not front:
        return None
    return min(front, key=lambda c: (c.JR, c.JD, c.T2, c.S2[0], c.S2[1]))


def validate_solution(candidate: CandidateResult | Mapping[str, object], config: Optional[Q2Config] = None) -> dict:
    cfg = config or Q2Config()
    data = candidate.to_dict() if isinstance(candidate, CandidateResult) else dict(candidate)
    failures = []
    diameter, radius = data.get("JD"), data.get("JR")
    if diameter is not None and radius is not None:
        if radius + cfg.tolerances.eps_mec < diameter / 2.0:
            failures.append("JR_below_JD_over_2")
        if radius > diameter / math.sqrt(3.0) + cfg.tolerances.eps_mec:
            failures.append("JR_above_JD_over_sqrt3")
    if data.get("official20") != (radius is not None and radius + EPS_MEC <= 20.0):
        failures.append("official20_mismatch")
    if data.get("operational17") != (radius is not None and radius + EPS_MEC <= 17.0):
        failures.append("operational17_mismatch")
    return {"valid": not failures, "failures": failures}


def solve_q2(S1: Sequence[float], theta1_hat_deg: float, config: Optional[Q2Config] = None) -> dict:
    """Build the formal Q2 domain; M4--M6 search remains intentionally pending."""

    cfg = config or Q2Config()
    p1 = build_P1_bound(S1, theta1_hat_deg, cfg)
    return Q2Result(
        status="M1_M3_IMPLEMENTED",
        model_version="Q2-robust-selection-v2.1",
        P1=p1,
        selected_strict=None,
        diagnostics={
            "milestones_complete": ["M1", "M2", "M3"],
            "pending": ["M4", "M5", "M6"],
            "geometry_dependency": "Q1-localization-v1 VERIFIED",
            "continuous_strict_certificate": "triangle-cell 2-Lipschitz branch-and-bound",
            "worst_value_wording": "场景加密后的收敛数值最坏值",
        },
    ).to_dict()


__all__ = [
    "Q2Config", "SourceScenario", "CandidateResult", "WorstScenario", "Q2Result",
    "bearing", "wrap_pi", "build_P1_bound", "physical_filter", "receive_floor",
    "receive_violation", "certified_strict", "make_P2", "fim_order_score",
    "evaluate_candidate", "pareto_front", "select_best", "validate_solution", "solve_q2",
]
