"""Q2 robust second-station selection, model Q2-robust-selection-v2.1.

This implementation covers milestones M1--M5A.  All convex
clipping, polygon cleanup, region classification, diameter, MEC and geometry
tolerances are imported from the verified Q1 implementation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import csv
import json
import math
from pathlib import Path
import time
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
# Provisional numerical target used only while the model team has not frozen
# eps_rec.  It is deliberately independent of every Q1 geometry tolerance.
DEVELOPMENT_EPS_REC_M = 1.0e-3


@dataclass(frozen=True)
class Q2Config:
    circle_sides: int = 1440
    omega_move: Optional[Sequence[Point]] = None
    lmin_m: float = 50.0
    eps_rec_m: Optional[float] = None
    error_step_deg: float = 0.1
    source_step_m: float = 20.0
    candidate_steps_m: tuple[float, ...] = (50.0, 20.0, 5.0)
    certificate_max_depth: int = 24
    certificate_max_cells: int = 200_000
    max_error_refine_rounds: int = 4
    tolerances: NumericalTolerances = field(default=DEFAULT_TOLERANCES)

    def __post_init__(self) -> None:
        if self.circle_sides < 12:
            raise ValueError("circle_sides must be at least 12")
        if self.lmin_m < 0 or (self.eps_rec_m is not None and self.eps_rec_m < 0):
            raise ValueError("lmin_m and configured eps_rec_m must be nonnegative")
        if self.error_step_deg <= 0 or self.source_step_m <= 0:
            raise ValueError("sampling steps must be positive")
        if self.certificate_max_depth < 0 or self.certificate_max_cells < 0:
            raise ValueError("certificate limits must be nonnegative")
        if self.max_error_refine_rounds < 1:
            raise ValueError("max_error_refine_rounds must be positive")


@dataclass(frozen=True)
class SourceScenario:
    G: Point
    e2_deg: Optional[float] = None
    weight_m2: float = 0.0
    sample_set: str = "Gext"
    source_level_m: float = 0.0
    origin: str = "interior"
    near_limit_eta_m: Optional[float] = None


@dataclass(frozen=True)
class WorstScenario:
    metric: str
    value: float
    G: Point
    e2_deg: Optional[float]
    status: str
    theta2_hat_deg: Optional[float]
    diameter: float
    mec_radius: float
    area: float
    mec_center: Optional[Point]
    mec_support: tuple[Point, ...]
    source_level: float
    sample_set: str
    sample_origin: str
    near_limit_eta_m: Optional[float]
    tq3_move_from_s2_s: Optional[float]


@dataclass
class CandidateResult:
    S2: Point
    strict_receive: Optional[bool]
    certificate: dict
    T2: float
    JD: Optional[float]
    JR: Optional[float]
    JA: Optional[float]
    official20: Optional[bool]
    operational17: Optional[bool]
    worst_scenarios: dict[str, WorstScenario]
    HFIM: Optional[float] = None
    robust_guarantee: bool = False
    official20_provisional: Optional[bool] = None
    operational17_provisional: Optional[bool] = None
    source_count: int = 0
    error_count: int = 0
    scenario_count: int = 0
    error_step_deg: Optional[float] = None
    evaluation_status: str = "DEVELOPMENT"

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


@dataclass
class CandidateCell:
    cell_id: str
    level_m: float
    ix: int
    iy: int
    center: Point
    bbox: tuple[float, float, float, float]
    status: str = "UNEVALUATED"
    certificate: Optional[dict] = None
    m4_result: Optional[dict] = None
    sample_counterexample: Optional[Point] = None
    boundary_flag: bool = False
    cell_exclusion_certified: bool = False
    parent_ids: tuple[str, ...] = ()

    def to_record(self) -> dict:
        candidate = None if self.m4_result is None else self.m4_result.get("candidate")
        return {
            "cell_id": self.cell_id,
            "grid_level_m": self.level_m,
            "ix": self.ix,
            "iy": self.iy,
            "x": self.center[0],
            "y": self.center[1],
            "bbox": list(self.bbox),
            "candidate_status": self.status,
            "certificate_status": None if self.certificate is None else self.certificate.get("status"),
            "eps_rec_m": None if self.certificate is None else self.certificate.get("eps_rec_m"),
            "eps_rec_source": None if self.certificate is None else self.certificate.get("eps_rec_source"),
            "M4_status": None if self.m4_result is None else self.m4_result.get("status"),
            "official20": None if candidate is None else candidate.official20,
            "operational17": None if candidate is None else candidate.operational17,
            "JD": None if candidate is None else candidate.JD,
            "JR": None if candidate is None else candidate.JR,
            "JA": None if candidate is None else candidate.JA,
            "T2": None if candidate is None else candidate.T2,
            "boundary_flag": self.boundary_flag,
            "cell_exclusion_certified": self.cell_exclusion_certified,
            "sample_counterexample": None if self.sample_counterexample is None else list(self.sample_counterexample),
            "parent_ids": list(self.parent_ids),
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


def _certificate_epsilon(config: Q2Config) -> tuple[float, str]:
    if config.eps_rec_m is None:
        return DEVELOPMENT_EPS_REC_M, "IMPLEMENTATION_PARAMETER / NOT_MODEL_VERIFIED"
    return config.eps_rec_m, "CONFIGURED_PARAMETER / NOT_MODEL_VERIFIED"


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
    eps_rec, eps_rec_source = _certificate_epsilon(cfg)
    s1, s2 = _point(S1, "S1"), _point(S2, "S2")
    polygon = list(P1_bound["P1_out"] if isinstance(P1_bound, Mapping) else P1_bound)
    if _distance(s1, s2) <= cfg.tolerances.eps_geo:
        return {
            "status": "CERTIFIED_STRICT",
            "strict_receive": True,
            "certified": True,
            "method": "analytic_identity_plus_physical_domain",
            "upper_bound_m": 0.0,
            "eps_rec_m": eps_rec,
            "eps_rec_source": eps_rec_source,
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
                "status": "UNRESOLVED",
                "strict_receive": None, "certified": False, "method": "triangle_cell_2_lipschitz",
                "upper_bound_m": None, "eps_rec_m": eps_rec,
                "eps_rec_source": eps_rec_source,
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
            if physical_filter(point, s1) and receive_violation(s2, point, s1) > eps_rec:
                return {
                    "status": "CERTIFIED_VIOLATION",
                    "strict_receive": False, "certified": True, "method": "triangle_cell_2_lipschitz",
                    "upper_bound_m": upper, "eps_rec_m": eps_rec,
                    "eps_rec_source": eps_rec_source,
                    "cells_examined": examined, "boundary_uncertainty_m": h,
                    "counterexample": point, "reason": "physical_counterexample",
                }
        if upper <= eps_rec:
            certified_leaf_upper = max(certified_leaf_upper, upper)
            certified_leaf_h = max(certified_leaf_h, h)
            continue
        if depth >= cfg.certificate_max_depth:
            return {
                "status": "UNRESOLVED",
                "strict_receive": None, "certified": False, "method": "triangle_cell_2_lipschitz",
                "upper_bound_m": upper, "eps_rec_m": eps_rec,
                "eps_rec_source": eps_rec_source,
                "cells_examined": examined, "boundary_uncertainty_m": h,
                "counterexample": None, "reason": "max_depth_with_active_physical_cell",
            }
        first, second = _triangle_children(triangle)
        queue.append((first, depth + 1))
        queue.append((second, depth + 1))
    return {
        "status": "CERTIFIED_STRICT",
        "strict_receive": True,
        "certified": True,
        "method": "triangle_cell_2_lipschitz",
        "upper_bound_m": certified_leaf_upper if math.isfinite(certified_leaf_upper) else None,
        "eps_rec_m": eps_rec,
        "eps_rec_source": eps_rec_source,
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


def _source_key(point: Point) -> tuple[int, int]:
    """Deterministic 1e-7 m key; far tighter than any sampling level."""

    return round(point[0] * 1.0e7), round(point[1] * 1.0e7)


def _p1_polygon(P1_bound: Sequence[Point] | Mapping[str, object]) -> tuple[list[Point], str]:
    polygon = list(P1_bound["P1_out"] if isinstance(P1_bound, Mapping) else P1_bound)
    return polygon, classify_region(polygon, DEFAULT_TOLERANCES)[0]


def _add_source(
    target: dict[tuple[int, int], SourceScenario],
    point: Point,
    S1: Point,
    polygon: Sequence[Point],
    region_type: str,
    sample_set: str,
    source_level_m: float,
    origin: str,
    near_limit_eta_m: Optional[float] = None,
) -> None:
    if not physical_filter(point, S1):
        return
    if not point_in_convex_region(point, polygon, region_type, DEFAULT_TOLERANCES):
        return
    key = _source_key(point)
    if key not in target:
        target[key] = SourceScenario(
            G=point,
            sample_set=sample_set,
            source_level_m=source_level_m,
            origin=origin,
            near_limit_eta_m=near_limit_eta_m,
        )


def _point_on_circle(center: Point, radius_m: float, angle: float, keep_inside_radius: bool) -> Point:
    sample_radius = math.nextafter(radius_m, 0.0) if keep_inside_radius else radius_m
    return (
        center[0] + sample_radius * math.cos(angle),
        center[1] + sample_radius * math.sin(angle),
    )


def _circle_polygon_intersection_angles(
    center: Point, radius_m: float, polygon: Sequence[Point]
) -> list[float]:
    angles: list[float] = []
    for index, a in enumerate(polygon):
        b = polygon[(index + 1) % len(polygon)]
        ax, ay = a[0] - center[0], a[1] - center[1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        qa = dx * dx + dy * dy
        qb = 2.0 * (ax * dx + ay * dy)
        qc = ax * ax + ay * ay - radius_m * radius_m
        discriminant = qb * qb - 4.0 * qa * qc
        if qa == 0.0 or discriminant < 0.0:
            continue
        root = math.sqrt(max(0.0, discriminant))
        for t in ((-qb - root) / (2.0 * qa), (-qb + root) / (2.0 * qa)):
            if -1.0e-12 <= t <= 1.0 + 1.0e-12:
                x, y = ax + min(1.0, max(0.0, t)) * dx, ay + min(1.0, max(0.0, t)) * dy
                angles.append(math.atan2(y, x) % (2.0 * math.pi))
    return sorted({round(angle, 14) for angle in angles})


def _circle_arc_samples(
    center: Point,
    radius_m: float,
    max_arc_step_m: float,
    polygon: Sequence[Point],
    region_type: str,
    *,
    phase: float,
    keep_inside_radius: bool,
) -> list[Point]:
    """Sample every feasible circle arc, including arcs shorter than one step."""

    cuts = _circle_polygon_intersection_angles(center, radius_m, polygon)
    if not cuts:
        probe = _point_on_circle(center, radius_m, 0.0, keep_inside_radius)
        intervals = [(0.0, 2.0 * math.pi)] if point_in_convex_region(
            probe, polygon, region_type, DEFAULT_TOLERANCES
        ) else []
    else:
        intervals = []
        for index, start in enumerate(cuts):
            end = cuts[(index + 1) % len(cuts)]
            if index == len(cuts) - 1:
                end += 2.0 * math.pi
            middle = (start + end) / 2.0
            probe = _point_on_circle(center, radius_m, middle, keep_inside_radius)
            if point_in_convex_region(probe, polygon, region_type, DEFAULT_TOLERANCES):
                intervals.append((start, end))
    result: list[Point] = []
    for start, end in intervals:
        count = max(1, int(math.ceil((end - start) * radius_m / max_arc_step_m)))
        if phase == 0.0:
            fractions = [k / count for k in range(count + 1)]
        elif count == 1:
            # Two quarter-phase points keep a very short feasible arc
            # independently represented even if its midpoint is in Gext.
            fractions = [0.25, 0.75]
        else:
            fractions = [(k + phase) / count for k in range(count)]
        for fraction in fractions:
            result.append(_point_on_circle(
                center, radius_m, start + fraction * (end - start), keep_inside_radius
            ))
    return result


def _add_physical_boundaries(
    scenarios: dict[tuple[int, int], SourceScenario],
    polygon: Sequence[Point],
    region_type: str,
    S1: Point,
    step_m: float,
    *,
    sample_set: str,
    phase: float,
    verify: bool,
    excluded: Optional[set[tuple[int, int]]] = None,
) -> None:
    excluded = excluded or set()
    prefix = "verify_" if verify else "physical_boundary_"
    definitions = [
        ((0.0, 0.0), SOURCE_RADIUS_M, f"{prefix}target1800", True, None),
        (S1, FIRST_RECEIVE_MAX_M, f"{prefix}receive1500", True, None),
    ]
    # Development sampling device for the open boundary ||G-S1||>5.
    eta = 0.1 * step_m
    definitions.append((S1, NEAR_RADIUS_M + eta, f"{prefix}near_limit", False, eta))
    for center, radius, origin, keep_inside, near_eta in definitions:
        for point in _circle_arc_samples(
            center, radius, step_m, polygon, region_type,
            phase=phase, keep_inside_radius=keep_inside
        ):
            if _source_key(point) in excluded:
                continue
            _add_source(
                scenarios, point, S1, polygon, region_type, sample_set, step_m,
                origin, near_limit_eta_m=near_eta,
            )


def build_Gext(
    P1_bound: Sequence[Point] | Mapping[str, object],
    S1: Sequence[float],
    source_level_m: float,
    previous: Optional[Iterable[SourceScenario]] = None,
) -> list[SourceScenario]:
    """Build one deterministic, nested optimizer source set."""

    step = float(source_level_m)
    if not math.isfinite(step) or step <= 0.0:
        raise ValueError("source_level_m must be positive and finite")
    s1 = _point(S1, "S1")
    polygon, region_type = _p1_polygon(P1_bound)
    scenarios: dict[tuple[int, int], SourceScenario] = {}
    for scenario in previous or ():
        if scenario.sample_set != "Gext":
            raise ValueError("previous samples for build_Gext must belong to Gext")
        if physical_filter(scenario.G, s1):
            scenarios[_source_key(scenario.G)] = scenario

    for vertex in polygon:
        _add_source(scenarios, vertex, s1, polygon, region_type, "Gext", step, "vertex")
    for index, a in enumerate(polygon):
        b = polygon[(index + 1) % len(polygon)]
        length = _distance(a, b)
        for k in range(1, int(math.floor(length / step)) + 1):
            t = k * step / length
            if t < 1.0:
                point = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
                _add_source(scenarios, point, s1, polygon, region_type, "Gext", step, "boundary")

    _add_physical_boundaries(
        scenarios, polygon, region_type, s1, step,
        sample_set="Gext", phase=0.0, verify=False,
    )

    xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
    for ix in range(math.ceil(min(xs) / step), math.floor(max(xs) / step) + 1):
        x = ix * step
        for iy in range(math.ceil(min(ys) / step), math.floor(max(ys) / step) + 1):
            _add_source(scenarios, (x, iy * step), s1, polygon, region_type, "Gext", step, "interior")
    return [scenarios[key] for key in sorted(scenarios)]


def build_Gverify(
    P1_bound: Sequence[Point] | Mapping[str, object],
    S1: Sequence[float],
    final_source_step_m: float,
    exclude: Iterable[SourceScenario] = (),
) -> list[SourceScenario]:
    """Build an independent half-step, shifted deterministic verification set."""

    final_step = float(final_source_step_m)
    if not math.isfinite(final_step) or final_step <= 0.0:
        raise ValueError("final_source_step_m must be positive and finite")
    step = final_step / 2.0
    s1 = _point(S1, "S1")
    polygon, region_type = _p1_polygon(P1_bound)
    excluded = {_source_key(item.G) for item in exclude}
    scenarios: dict[tuple[int, int], SourceScenario] = {}

    def add(point: Point, origin: str) -> None:
        key = _source_key(point)
        if key not in excluded:
            _add_source(scenarios, point, s1, polygon, region_type, "Gverify", step, origin)

    for index, a in enumerate(polygon):
        b = polygon[(index + 1) % len(polygon)]
        length = _distance(a, b)
        count = max(1, int(math.ceil(length / step)))
        for k in range(count):
            t = (k + 0.5) / count
            add((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])), "verify_boundary")

    _add_physical_boundaries(
        scenarios, polygon, region_type, s1, step,
        sample_set="Gverify", phase=0.5, verify=True, excluded=excluded,
    )

    xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
    ix0, ix1 = math.floor(min(xs) / step) - 1, math.ceil(max(xs) / step) + 1
    iy0, iy1 = math.floor(min(ys) / step) - 1, math.ceil(max(ys) / step) + 1
    for ix in range(ix0, ix1 + 1):
        x = (ix + 0.5) * step
        for iy in range(iy0, iy1 + 1):
            add((x, (iy + 0.5) * step), "verify_interior")
    return [scenarios[key] for key in sorted(scenarios)]


def build_error_grid(step_deg: float) -> list[float]:
    """Build a deterministic error grid containing -1, 0 and +1 degrees."""

    step = float(step_deg)
    if not math.isfinite(step) or step <= 0.0:
        raise ValueError("step_deg must be positive and finite")
    count = int(math.floor(BEARING_ERROR_DEG / step + 1.0e-12))
    values = {-BEARING_ERROR_DEG, 0.0, BEARING_ERROR_DEG}
    values.update(round(k * step, 12) for k in range(-count, count + 1) if abs(k * step) <= 1.0 + 1.0e-12)
    return sorted(values)


def relchg(a: float, b: float) -> float:
    return abs(a - b) / max(1.0, abs(a), abs(b))


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


def _mec_support(result: Mapping[str, object], tolerances: NumericalTolerances) -> tuple[Point, ...]:
    center, radius = result.get("mec_center"), result.get("mec_radius")
    if center is None or radius is None:
        return ()
    center_point = _point(center)
    radius_value = float(radius)
    support_tolerance = max(tolerances.eps_mec, 1.0e-9 * max(1.0, radius_value))
    support = [
        _point(point) for point in result.get("polygon", [])
        if abs(_distance(_point(point), center_point) - radius_value) <= support_tolerance
    ]
    if not support and result.get("polygon"):
        support = [max((_point(p) for p in result["polygon"]), key=lambda p: _distance(p, center_point))]
    return tuple(sorted(support))


def _worst_scenario(
    metric: str,
    value: float,
    source: SourceScenario,
    error: Optional[float],
    result: Mapping[str, object],
    config: Q2Config,
    S2: Point,
) -> WorstScenario:
    center = None if result.get("mec_center") is None else _point(result["mec_center"])
    return WorstScenario(
        metric=metric,
        value=value,
        G=source.G,
        e2_deg=error,
        status=str(result["status"]),
        theta2_hat_deg=None if result.get("theta2_hat_deg") is None else float(result["theta2_hat_deg"]),
        diameter=float(result["diameter"]),
        mec_radius=float(result["mec_radius"]),
        area=float(result["area"]),
        mec_center=center,
        mec_support=_mec_support(result, config.tolerances),
        source_level=source.source_level_m,
        sample_set=source.sample_set,
        sample_origin=source.origin,
        near_limit_eta_m=source.near_limit_eta_m,
        tq3_move_from_s2_s=None if center is None else _distance(S2, center) / SPEED_MPS,
    )


def evaluate_candidate_resolution(
    S2: Sequence[float],
    S1: Sequence[float],
    P1_bound: Sequence[Point] | Mapping[str, object],
    source_scenarios: Iterable[Sequence[float] | SourceScenario],
    error_step_deg: float,
    config: Optional[Q2Config] = None,
    *,
    certificate: Optional[dict] = None,
) -> CandidateResult:
    """Evaluate one candidate at one source/error resolution."""

    cfg = config or Q2Config()
    s1, s2 = _point(S1, "S1"), _point(S2, "S2")
    certificate = certificate or certified_strict(s2, P1_bound, s1, cfg)
    worst: dict[str, WorstScenario] = {}
    source_points: list[Point] = []
    normalized: list[SourceScenario] = []
    for item in source_scenarios:
        scenario = item if isinstance(item, SourceScenario) else SourceScenario(
            G=_point(item, "G"), source_level_m=0.0, origin="interior"
        )
        if not physical_filter(scenario.G, s1):
            continue
        normalized.append(scenario)
    normalized.sort(key=lambda item: (_source_key(item.G), item.origin))
    error_grid = build_error_grid(error_step_deg)
    scenario_count = 0
    for scenario in normalized:
        source = scenario.G
        source_points.append(source)
        errors: Iterable[Optional[float]] = [None] if _distance(source, s2) <= NEAR_RADIUS_M + cfg.tolerances.eps_geo else error_grid
        for error in errors:
            scenario_count += 1
            result = make_P2(P1_bound, s2, source, 0.0 if error is None else error, config=cfg)
            for metric, field_name in (("JD", "diameter"), ("JR", "mec_radius"), ("JA", "area")):
                value = result[field_name]
                if value is not None and (metric not in worst or value > worst[metric].value):
                    worst[metric] = _worst_scenario(metric, float(value), scenario, error, result, cfg, s2)
    JD, JR, JA = (worst[name].value if name in worst else None for name in ("JD", "JR", "JA"))
    provisional20 = JR is not None and JR + EPS_MEC <= OFFICIAL_CLEAR_RADIUS_M
    provisional17 = JR is not None and JR + EPS_MEC <= OPERATIONAL_CLEAR_RADIUS_M
    return CandidateResult(
        S2=s2,
        strict_receive=certificate["strict_receive"],
        certificate=certificate,
        T2=_distance(s1, s2) / SPEED_MPS,
        JD=JD,
        JR=JR,
        JA=JA,
        official20=None,
        operational17=None,
        worst_scenarios=worst,
        HFIM=fim_order_score(s1, s2, source_points),
        robust_guarantee=certificate["status"] == "CERTIFIED_STRICT",
        official20_provisional=provisional20,
        operational17_provisional=provisional17,
        source_count=len(normalized),
        error_count=len(error_grid),
        scenario_count=scenario_count,
        error_step_deg=float(error_step_deg),
        evaluation_status=("UNRESOLVED" if certificate["status"] == "UNRESOLVED" else "RESOLUTION_EVALUATED"),
    )


def evaluate_candidate(
    S2: Sequence[float],
    S1: Sequence[float],
    P1_bound: Sequence[Point] | Mapping[str, object],
    Gext: Iterable[Sequence[float] | SourceScenario],
    config: Optional[Q2Config] = None,
) -> CandidateResult:
    """Compatibility wrapper for one configured resolution."""

    cfg = config or Q2Config()
    return evaluate_candidate_resolution(S2, S1, P1_bound, Gext, cfg.error_step_deg, cfg)


def merge_verified_worst(
    optimizer: CandidateResult,
    verify: CandidateResult,
    *,
    convergence_passed: bool,
) -> dict:
    """Merge independent verification maxima into the candidate in place."""

    optimizer_worst = dict(optimizer.worst_scenarios)
    verify_worst = dict(verify.worst_scenarios)
    validated_worst: dict[str, WorstScenario] = {}
    verify_exceeded: dict[str, bool] = {}
    for metric in ("JD", "JR", "JA"):
        left, right = optimizer_worst.get(metric), verify_worst.get(metric)
        if left is None and right is None:
            continue
        take_verify = left is None or (right is not None and right.value > left.value)
        chosen = right if take_verify else left
        assert chosen is not None
        validated_worst[metric] = chosen
        verify_exceeded[metric] = bool(take_verify and left is not None)
        setattr(optimizer, metric, chosen.value)
    optimizer.worst_scenarios = validated_worst
    optimizer.official20_provisional = optimizer.JR is not None and optimizer.JR + EPS_MEC <= OFFICIAL_CLEAR_RADIUS_M
    optimizer.operational17_provisional = optimizer.JR is not None and optimizer.JR + EPS_MEC <= OPERATIONAL_CLEAR_RADIUS_M
    if convergence_passed:
        optimizer.official20 = optimizer.official20_provisional
        optimizer.operational17 = optimizer.operational17_provisional
    else:
        optimizer.official20 = None
        optimizer.operational17 = None
    return {
        "optimizer_worst": optimizer_worst,
        "verify_worst": verify_worst,
        "validated_worst": validated_worst,
        "verify_exceeded_optimizer": verify_exceeded,
    }


def _monotone(previous: CandidateResult, current: CandidateResult) -> dict[str, bool]:
    results = {}
    for metric in ("JD", "JR", "JA"):
        before, after = getattr(previous, metric), getattr(current, metric)
        scale = max(1.0, abs(before or 0.0), abs(after or 0.0))
        results[metric] = before is None or after is None or after + 1.0e-10 * scale >= before
    return results


def replay_worst_scenario(
    worst: WorstScenario,
    P1_bound: Sequence[Point] | Mapping[str, object],
    S2: Sequence[float],
    config: Optional[Q2Config] = None,
) -> dict:
    """Replay one stored worst scenario and compare all relevant geometry."""

    cfg = config or Q2Config()
    result = make_P2(P1_bound, S2, worst.G, 0.0 if worst.e2_deg is None else worst.e2_deg, config=cfg)
    field = {"JD": "diameter", "JR": "mec_radius", "JA": "area"}[worst.metric]
    value_tolerance = {
        "JD": cfg.tolerances.eps_cover,
        "JR": cfg.tolerances.eps_mec,
        "JA": cfg.tolerances.eps_area,
    }[worst.metric]
    center_now = None if result.get("mec_center") is None else _point(result["mec_center"])
    center_ok = (worst.mec_center is None and center_now is None) or (
        worst.mec_center is not None and center_now is not None
        and _distance(worst.mec_center, center_now) <= cfg.tolerances.eps_mec
    )
    support_now = _mec_support(result, cfg.tolerances)
    checks = {
        "value": abs(float(result[field]) - worst.value) <= value_tolerance,
        "status": result["status"] == worst.status,
        "G": _distance(_point(result["G"]), worst.G) <= cfg.tolerances.eps_geo,
        "e2": result["theta2_hat_deg"] is None if worst.e2_deg is None else abs(
            float(result["theta2_hat_deg"]) - float(worst.theta2_hat_deg)
        ) <= cfg.tolerances.eps_angle_deg,
        "mec_center": center_ok,
        "mec_support": support_now == worst.mec_support,
    }
    return {
        "metric": worst.metric,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "replayed_value": result[field],
        "stored_value": worst.value,
        "tolerance": value_tolerance,
    }


def evaluate_candidate_nested(
    S2: Sequence[float],
    S1: Sequence[float],
    P1_bound: Sequence[Point] | Mapping[str, object],
    config: Optional[Q2Config] = None,
    *,
    source_levels_m: Sequence[float] = (20.0, 10.0, 5.0),
) -> dict:
    """Run the M4 source-outer/error-inner deterministic convergence engine."""

    cfg = config or Q2Config()
    s1, s2 = _point(S1, "S1"), _point(S2, "S2")
    levels = tuple(float(value) for value in source_levels_m)
    if len(levels) < 2 or any(value <= 0.0 for value in levels):
        raise ValueError("at least two positive source levels are required")
    certificate = certified_strict(s2, P1_bound, s1, cfg)
    warnings: list[str] = []
    error_history: list[dict] = []
    source_history: list[dict] = []
    previous_sources: list[SourceScenario] = []
    previous_source_result: Optional[CandidateResult] = None
    final_result: Optional[CandidateResult] = None
    final_sources: list[SourceScenario] = []
    final_error_step: Optional[float] = None
    source_status = "UNRESOLVED"
    error_status = "UNRESOLVED"
    gverify_report: Optional[dict] = None
    final_verify_result: Optional[CandidateResult] = None

    for level_index, source_level in enumerate(levels):
        sources = build_Gext(P1_bound, s1, source_level, previous_sources)
        previous_sources = sources
        previous_error_result: Optional[CandidateResult] = None
        error_status = "UNRESOLVED"
        level_error_records: list[dict] = []
        for error_round in range(cfg.max_error_refine_rounds + 1):
            error_step = cfg.error_step_deg / (2 ** error_round)
            current = evaluate_candidate_resolution(
                s2, s1, P1_bound, sources, error_step, cfg, certificate=certificate
            )
            monotone = {"JD": True, "JR": True, "JA": True}
            rel_d = rel_r = rel_a = None
            if previous_error_result is not None:
                monotone = _monotone(previous_error_result, current)
                rel_d = relchg(previous_error_result.JD, current.JD)
                rel_r = relchg(previous_error_result.JR, current.JR)
                rel_a = relchg(previous_error_result.JA, current.JA)
                if not all(monotone.values()):
                    warnings.append("NON_MONOTONE_REFINEMENT")
                if rel_d <= 1.0e-3 and rel_r <= 1.0e-3 and all(monotone.values()):
                    error_status = "PASS"
            record = {
                "source_level_m": source_level,
                "source_count": current.source_count,
                "error_step_deg": error_step,
                "error_count": current.error_count,
                "scenario_count": current.scenario_count,
                "JD": current.JD, "JR": current.JR, "JA": current.JA,
                "relchg_D": rel_d, "relchg_R": rel_r, "relchg_A": rel_a,
                "JD_monotone": monotone["JD"], "JR_monotone": monotone["JR"],
                "JA_monotone": monotone["JA"],
            }
            error_history.append(record)
            level_error_records.append(record)
            final_result, final_sources, final_error_step = current, sources, error_step
            if error_status == "PASS":
                break
            previous_error_result = current
        if error_status != "PASS":
            warnings.append("ERROR_CONVERGENCE_UNRESOLVED")
            break

        source_monotone = {"JD": True, "JR": True, "JA": True}
        rel_d = rel_r = rel_a = None
        if previous_source_result is not None:
            source_monotone = _monotone(previous_source_result, final_result)
            rel_d = relchg(previous_source_result.JD, final_result.JD)
            rel_r = relchg(previous_source_result.JR, final_result.JR)
            rel_a = relchg(previous_source_result.JA, final_result.JA)
            if not all(source_monotone.values()):
                warnings.append("NON_MONOTONE_REFINEMENT")
            if rel_d <= 1.0e-3 and rel_r <= 1.0e-3 and all(source_monotone.values()):
                source_status = "PASS"
        source_history.append({
            "source_level_m": source_level,
            "source_count": final_result.source_count,
            "error_step_deg": final_error_step,
            "error_count": final_result.error_count,
            "JD": final_result.JD, "JR": final_result.JR, "JA": final_result.JA,
            "relchg_D": rel_d, "relchg_R": rel_r, "relchg_A": rel_a,
            "JD_monotone": source_monotone["JD"], "JR_monotone": source_monotone["JR"],
            "JA_monotone": source_monotone["JA"],
        })
        previous_source_result = final_result
        if source_status != "PASS":
            continue

        verify_sources = build_Gverify(P1_bound, s1, source_level, final_sources)
        # Gverify is independent and twice as dense in source space.  The
        # confirmed final error step is reused, as explicitly allowed by v2.1.
        verify_error_step = final_error_step
        verify_result = evaluate_candidate_resolution(
            s2, s1, P1_bound, verify_sources, verify_error_step, cfg, certificate=certificate
        )
        final_verify_result = verify_result
        previous_error_record = level_error_records[-2]
        error_est_d = max(cfg.tolerances.eps_cover, abs(final_result.JD - previous_error_record["JD"]))
        error_est_r = max(cfg.tolerances.eps_mec, abs(final_result.JR - previous_error_record["JR"]))
        source_est_d = max(cfg.tolerances.eps_cover, abs(final_result.JD - source_history[-2]["JD"]))
        source_est_r = max(cfg.tolerances.eps_mec, abs(final_result.JR - source_history[-2]["JR"]))
        estimated_d, estimated_r = error_est_d + source_est_d, error_est_r + source_est_r
        max_receive_violation = max((receive_violation(s2, item.G, s1) for item in verify_sources), default=-math.inf)
        verify_d_ok = verify_result.JD <= final_result.JD + estimated_d
        verify_r_ok = verify_result.JR <= final_result.JR + estimated_r
        receive_ok = certificate["status"] != "CERTIFIED_STRICT" or max_receive_violation <= certificate["eps_rec_m"]
        gverify_report = {
            "status": "PASS" if verify_d_ok and verify_r_ok and receive_ok else "GVERIFY_FAIL",
            "sample_set": "Gverify",
            "source_step_m": source_level / 2.0,
            "source_count": verify_result.source_count,
            "error_step_deg": verify_error_step,
            "error_count": verify_result.error_count,
            "JD_verify": verify_result.JD, "JR_verify": verify_result.JR, "JA_verify": verify_result.JA,
            "JD_final": final_result.JD, "JR_final": final_result.JR, "JA_final": final_result.JA,
            "estimated_error_D": estimated_d, "estimated_error_R": estimated_r,
            "JD_check": verify_d_ok, "JR_check": verify_r_ok,
            "max_receive_violation_m": max_receive_violation,
            "strict_receive_check": receive_ok,
            "independent_coordinate_overlap": len({_source_key(x.G) for x in verify_sources} & {_source_key(x.G) for x in final_sources}),
        }
        if gverify_report["status"] == "PASS":
            break
        warnings.append("GVERIFY_FAIL")
        source_status = "UNRESOLVED"

    assert final_result is not None
    overall_pass = (
        certificate["status"] != "UNRESOLVED"
        and source_status == "PASS"
        and error_status == "PASS"
        and gverify_report is not None
        and gverify_report["status"] == "PASS"
    )
    merge_report = None
    if final_verify_result is not None:
        merge_report = merge_verified_worst(
            final_result, final_verify_result, convergence_passed=overall_pass
        )
        if gverify_report is not None:
            gverify_report["validated_JD"] = final_result.JD
            gverify_report["validated_JR"] = final_result.JR
            gverify_report["validated_JA"] = final_result.JA
            gverify_report["verify_exceeded_optimizer"] = merge_report["verify_exceeded_optimizer"]
    if overall_pass:
        final_result.evaluation_status = "CONVERGED"
    else:
        final_result.evaluation_status = "UNRESOLVED"
    replay = {
        metric: replay_worst_scenario(worst, P1_bound, s2, cfg)
        for metric, worst in final_result.worst_scenarios.items()
    }
    if any(item["status"] != "PASS" for item in replay.values()):
        warnings.append("WORST_REPLAY_FAIL")
        overall_pass = False
    return {
        "status": "PASS" if overall_pass else "UNRESOLVED",
        "wording": "场景加密后的收敛数值最坏值",
        "candidate": final_result,
        "certificate": certificate,
        "eps_rec_m": certificate["eps_rec_m"],
        "eps_rec_source": certificate["eps_rec_source"],
        "strict_certificate_threshold_provisional": True,
        "source_convergence": source_status,
        "error_convergence": error_status,
        "source_history": source_history,
        "error_history": error_history,
        "gverify": gverify_report,
        "optimizer_worst": None if merge_report is None else merge_report["optimizer_worst"],
        "verify_worst": None if merge_report is None else merge_report["verify_worst"],
        "validated_worst": None if merge_report is None else merge_report["validated_worst"],
        "replay": replay,
        "warnings": sorted(set(warnings)),
    }


def _cell_class(cell: CandidateCell) -> str:
    if cell.status == "STRICT_INTERIOR":
        return "strict"
    if cell.status in {"CERTIFIED_VIOLATION_SAMPLE", "CERTIFIED_VIOLATION", "LMIN_EXCLUDED"}:
        return "violated"
    return "unresolved"


def _candidate_cells(
    bounds: Sequence[float],
    level_m: float,
    omega_move: Optional[Sequence[Point]],
    parents: Optional[Sequence[CandidateCell]],
    tolerances: NumericalTolerances,
) -> list[CandidateCell]:
    lo_x, lo_y, hi_x, hi_y = map(float, bounds)
    ix0, ix1 = math.floor(lo_x / level_m), math.ceil(hi_x / level_m) - 1
    iy0, iy1 = math.floor(lo_y / level_m), math.ceil(hi_y / level_m) - 1
    omega_kind = None
    if omega_move is not None:
        omega_kind = classify_region(omega_move, tolerances)[0]
    cells = []
    for ix in range(ix0, ix1 + 1):
        x = (ix + 0.5) * level_m
        if x < lo_x or x > hi_x:
            continue
        for iy in range(iy0, iy1 + 1):
            y = (iy + 0.5) * level_m
            if y < lo_y or y > hi_y:
                continue
            center = (x, y)
            if omega_move is not None and not point_in_convex_region(
                center, omega_move, omega_kind, tolerances
            ):
                continue
            containing = [] if parents is None else [
                parent.cell_id for parent in parents
                if parent.bbox[0] <= x <= parent.bbox[2] and parent.bbox[1] <= y <= parent.bbox[3]
            ]
            if parents is not None and not containing:
                continue
            cells.append(CandidateCell(
                cell_id=f"L{level_m:g}_X{ix}_Y{iy}",
                level_m=level_m,
                ix=ix,
                iy=iy,
                center=center,
                bbox=(ix * level_m, iy * level_m, (ix + 1) * level_m, (iy + 1) * level_m),
                parent_ids=tuple(sorted(containing)),
            ))
    return cells


def _mark_boundaries(cells: Sequence[CandidateCell]) -> None:
    by_index = {(cell.ix, cell.iy): cell for cell in cells}
    for cell in cells:
        own = _cell_class(cell)
        cell.boundary_flag = cell.boundary_flag or own == "unresolved"
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            neighbor = by_index.get((cell.ix + dx, cell.iy + dy))
            if neighbor is not None and _cell_class(neighbor) != own:
                cell.boundary_flag = True
                neighbor.boundary_flag = True


def _strict_components(cells: Sequence[CandidateCell]) -> list[list[CandidateCell]]:
    strict = {(cell.ix, cell.iy): cell for cell in cells if cell.status == "STRICT_INTERIOR"}
    components = []
    while strict:
        start_key = min(strict)
        stack = [strict.pop(start_key)]
        component = []
        while stack:
            cell = stack.pop()
            component.append(cell)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                neighbor = strict.pop((cell.ix + dx, cell.iy + dy), None)
                if neighbor is not None:
                    stack.append(neighbor)
        components.append(sorted(component, key=lambda item: item.cell_id))
    return components


def select_from_evaluated(
    candidates: Iterable[CandidateResult],
    *,
    eps_rec_provisional: bool = True,
) -> dict:
    """Apply the frozen Cstrict/C20/Pareto selection contract."""

    cstrict = [
        candidate for candidate in candidates
        if candidate.certificate.get("status") == "CERTIFIED_STRICT"
        and candidate.strict_receive is True
        and candidate.evaluation_status == "CONVERGED"
    ]
    c20 = [candidate for candidate in cstrict if candidate.official20 is True]
    if c20:
        pareto = pareto_front(cstrict)
        selected = min(c20, key=lambda c: (c.T2, c.JR, c.JD, c.S2[0], c.S2[1]))
        rule = "C20_LEXICOGRAPHIC_T2_JR_JD_X_Y"
    elif cstrict:
        pareto = pareto_front(cstrict)
        selected = min(pareto, key=lambda c: (c.JR, c.JD, c.T2, c.S2[0], c.S2[1]))
        rule = "STRICT_PARETO_LEXICOGRAPHIC_JR_JD_T2_X_Y"
    else:
        pareto, selected, rule = [], None, "NO_CSTRICT"
    return {
        "selection_status": "DEVELOPMENT_EPS_REC_PROVISIONAL" if eps_rec_provisional else "DEVELOPMENT",
        "rule": rule,
        "Cstrict": cstrict,
        "C20": c20,
        "pareto": pareto,
        "selected_strict": selected,
    }


def _jsonable(value):
    if isinstance(value, CandidateResult):
        return value.to_dict()
    if isinstance(value, WorstScenario):
        return asdict(value)
    if isinstance(value, CandidateCell):
        return value.to_record()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _write_m5a_outputs(output_dir: str | Path, result: dict) -> None:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    all_cells: list[CandidateCell] = result["cells"]
    # Resolution ordering is descending, so the numerically smallest level is final.
    final_level = min(cell.level_m for cell in all_cells)
    final_cells = [cell for cell in all_cells if cell.level_m == final_level]
    records = [cell.to_record() for cell in all_cells]
    strict_records = [cell.to_record() for cell in final_cells if cell.status == "STRICT_INTERIOR"]
    for filename, rows in (("candidate_status.csv", records), ("strict_candidates.csv", strict_records)):
        fieldnames = list(rows[0]) if rows else list(CandidateCell("", 0, 0, 0, (0, 0), (0, 0, 0, 0)).to_record())
        with (directory / filename).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    features = []
    for cell in final_cells:
        properties = cell.to_record()
        properties.update({"artifact_status": "DEVELOPMENT", "final_result": False})
        if cell.status == "STRICT_INTERIOR":
            geometry = {"type": "Point", "coordinates": list(cell.center)}
            properties["representation"] = "point_certified"
            features.append({"type": "Feature", "geometry": geometry, "properties": properties})
        elif cell.boundary_flag or _cell_class(cell) == "unresolved":
            x0, y0, x1, y1 = cell.bbox
            geometry = {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}
            properties["representation"] = "uncertainty_cell"
            features.append({"type": "Feature", "geometry": geometry, "properties": properties})
    geojson = {
        "type": "FeatureCollection",
        "name": "Fstrict DEVELOPMENT point-certified approximation",
        "artifact_status": "DEVELOPMENT / NOT_FINAL_Q2_RESULT",
        "features": features,
    }
    (directory / "Fstrict.geojson").write_text(json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8")

    selection = result["selection"]
    selection_payload = {
        "artifact_status": "DEVELOPMENT / NOT_FINAL_Q2_RESULT",
        "selection_status": selection["selection_status"],
        "rule": selection["rule"],
        "Cstrict_size": len(selection["Cstrict"]),
        "C20_size": len(selection["C20"]),
        "pareto_size": len(selection["pareto"]),
        "selected_strict": _jsonable(selection["selected_strict"]),
    }
    (directory / "selection_dev.json").write_text(json.dumps(selection_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    diagnostics_payload = _jsonable({key: value for key, value in result.items() if key not in {"cells", "selection"}})
    diagnostics_payload["artifact_status"] = "DEVELOPMENT / NOT_FINAL_Q2_RESULT"
    (directory / "candidate_search_diagnostics.json").write_text(
        json.dumps(diagnostics_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def search_strict_candidates(
    S1: Sequence[float],
    theta1_hat_deg: float,
    config: Optional[Q2Config] = None,
    *,
    P1_bound: Optional[Mapping[str, object]] = None,
    sample_scenarios: Optional[Iterable[SourceScenario]] = None,
    certificate_fn=certified_strict,
    m4_fn=evaluate_candidate_nested,
    output_dir: Optional[str | Path] = None,
) -> dict:
    """Run the M5A 50->20->5 m point-certified strict search."""

    cfg = config or Q2Config()
    s1 = _point(S1, "S1")
    p1 = dict(P1_bound) if P1_bound is not None else build_P1_bound(s1, theta1_hat_deg, cfg)
    bounds = list(p1["search_box"])
    omega = None if cfg.omega_move is None else [_point(point) for point in cfg.omega_move]
    if omega is not None:
        xs, ys = [p[0] for p in omega], [p[1] for p in omega]
        bounds = [max(bounds[0], min(xs)), max(bounds[1], min(ys)), min(bounds[2], max(xs)), min(bounds[3], max(ys))]
    if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
        raise ValueError("Omega_move does not intersect the Q2 search box")
    samples = list(sample_scenarios) if sample_scenarios is not None else build_Gext(
        p1, s1, cfg.source_step_m
    )
    eps_rec, eps_source = _certificate_epsilon(cfg)
    levels = tuple(float(level) for level in cfg.candidate_steps_m)
    if levels != (50.0, 20.0, 5.0):
        raise ValueError("M5A candidate_steps_m must be exactly (50,20,5)")
    all_cells: list[CandidateCell] = []
    level_diagnostics = []
    near_optimal_components = []
    parents: Optional[list[CandidateCell]] = None
    search_started = time.perf_counter()

    for level in levels:
        level_started = time.perf_counter()
        cells = _candidate_cells(bounds, level, omega, parents, cfg.tolerances)
        counters = {
            "candidate_total": len(cells), "sample_rejected": 0,
            "certificate_violation": 0, "certificate_strict": 0,
            "certificate_unresolved": 0, "M4_evaluated": 0,
            "M4_pass": 0, "M4_unresolved": 0, "lmin_excluded": 0,
            "cell_exclusion_certified": 0,
        }
        for cell in cells:
            cell_half_diagonal = math.sqrt(2.0) * level / 2.0
            if _distance(cell.center, s1) < cfg.lmin_m:
                counters["lmin_excluded"] += 1
                if _distance(cell.center, s1) + cell_half_diagonal < cfg.lmin_m:
                    cell.status = "LMIN_EXCLUDED"
                    cell.cell_exclusion_certified = True
                    counters["cell_exclusion_certified"] += 1
                else:
                    cell.status = "LMIN_BOUNDARY"
                    cell.boundary_flag = True
                continue
            counterexample = None
            counterexample_margin = -math.inf
            for scenario in samples:
                margin = receive_violation(cell.center, scenario.G, s1)
                if margin > eps_rec and margin > counterexample_margin:
                    counterexample, counterexample_margin = scenario.G, margin
            if counterexample is not None:
                cell.status = "CERTIFIED_VIOLATION_SAMPLE"
                cell.sample_counterexample = counterexample
                cell.certificate = {
                    "status": "CERTIFIED_VIOLATION_SAMPLE", "certified": True,
                    "strict_receive": False, "counterexample": counterexample,
                    "eps_rec_m": eps_rec, "eps_rec_source": eps_source,
                }
                counters["sample_rejected"] += 1
                if counterexample_margin - cell_half_diagonal > eps_rec:
                    cell.cell_exclusion_certified = True
                    counters["cell_exclusion_certified"] += 1
                else:
                    cell.boundary_flag = True
                continue
            certificate = certificate_fn(cell.center, p1, s1, cfg)
            cell.certificate = certificate
            if certificate["status"] == "CERTIFIED_VIOLATION":
                cell.status = "CERTIFIED_VIOLATION"
                counters["certificate_violation"] += 1
                counterexample = certificate.get("counterexample")
                if counterexample is not None and receive_violation(
                    cell.center, counterexample, s1
                ) - cell_half_diagonal > eps_rec:
                    cell.cell_exclusion_certified = True
                    counters["cell_exclusion_certified"] += 1
                else:
                    cell.boundary_flag = True
            elif certificate["status"] == "UNRESOLVED":
                cell.status = "BOUNDARY_OR_UNRESOLVED"
                counters["certificate_unresolved"] += 1
            elif certificate["status"] == "CERTIFIED_STRICT":
                counters["certificate_strict"] += 1
                counters["M4_evaluated"] += 1
                m4_result = m4_fn(cell.center, s1, p1, cfg)
                cell.m4_result = m4_result
                if m4_result["status"] == "PASS":
                    cell.status = "STRICT_INTERIOR"
                    counters["M4_pass"] += 1
                else:
                    cell.status = "EVALUATION_UNRESOLVED"
                    counters["M4_unresolved"] += 1
            else:
                raise ValueError(f"unknown certificate status {certificate['status']!r}")
        _mark_boundaries(cells)
        components = _strict_components(cells)
        c20_cells = [
            cell for cell in cells if cell.status == "STRICT_INTERIOR"
            and cell.m4_result["candidate"].official20 is True
        ]
        selected_component_indices: set[int] = set()
        if c20_cells:
            best_t2 = min(cell.m4_result["candidate"].T2 for cell in c20_cells)
            for index, component in enumerate(components):
                lower_t2 = min(max(0.0, _distance(cell.center, s1) - math.sqrt(2.0) * level / 2.0) / SPEED_MPS for cell in component)
                if lower_t2 <= best_t2 + 1.0e-3 * max(1.0, best_t2):
                    selected_component_indices.add(index)
        else:
            selected_component_indices.update(range(len(components)))
        for index, component in enumerate(components):
            near_optimal_components.append({
                "grid_level_m": level,
                "component_id": f"L{level:g}_C{index}",
                "cell_ids": [cell.cell_id for cell in component],
                "selected_for_refinement": index in selected_component_indices,
            })
        counters["runtime_s"] = time.perf_counter() - level_started
        level_diagnostics.append(counters)
        all_cells.extend(cells)
        if level != levels[-1]:
            selected_ids = {
                cell.cell_id for index in selected_component_indices for cell in components[index]
            }
            parents = [cell for cell in cells if cell.boundary_flag or cell.cell_id in selected_ids]
            if not parents:
                parents = [cell for cell in cells if _cell_class(cell) == "unresolved"]

    final_cells = [cell for cell in all_cells if cell.level_m == levels[-1]]
    evaluated = [
        cell.m4_result["candidate"] for cell in final_cells
        if cell.status == "STRICT_INTERIOR" and cell.m4_result is not None
    ]
    selection = select_from_evaluated(evaluated, eps_rec_provisional=cfg.eps_rec_m is None)
    result = {
        "artifact_status": "DEVELOPMENT / NOT_FINAL_Q2_RESULT",
        "selection_status": selection["selection_status"],
        "eps_rec_m": eps_rec,
        "eps_rec_source": eps_source,
        "strict_region_representation": "point-certified approximation plus uncertainty cells",
        "search_box": bounds,
        "candidate_levels_m": list(levels),
        "level_diagnostics": level_diagnostics,
        "near_optimal_components": near_optimal_components,
        "cells": all_cells,
        "selection": selection,
        "runtime_s": time.perf_counter() - search_started,
        "warnings": ["EPS_REC_PROVISIONAL"] if cfg.eps_rec_m is None else [],
    }
    if output_dir is not None:
        _write_m5a_outputs(output_dir, result)
    return result


def _dominates(a: CandidateResult, b: CandidateResult, epsD: float, epsR: float, epsT: float) -> bool:
    assert a.JD is not None and a.JR is not None and b.JD is not None and b.JR is not None
    tolD = max(epsD, 1.0e-3 * max(1.0, b.JD))
    tolR = max(epsR, 1.0e-3 * max(1.0, b.JR))
    tolT = max(epsT, 1.0e-3 * max(1.0, b.T2))
    no_worse = a.JR <= b.JR + tolR and a.JD <= b.JD + tolD and a.T2 <= b.T2 + tolT
    better = a.JR < b.JR - tolR or a.JD < b.JD - tolD or a.T2 < b.T2 - tolT
    return no_worse and better


def pareto_front(candidates: Iterable[CandidateResult], epsD: float = 0.0, epsR: float = 0.0, epsT: float = 0.0) -> list[CandidateResult]:
    valid = [c for c in candidates if c.strict_receive is True and c.JD is not None and c.JR is not None]
    return [c for c in valid if not any(_dominates(other, c, epsD, epsR, epsT) for other in valid if other is not c)]


def select_best(candidates: Iterable[CandidateResult], config: Optional[Q2Config] = None) -> Optional[CandidateResult]:
    cfg = config or Q2Config()
    strict = [c for c in candidates if c.certificate.get("status") == "CERTIFIED_STRICT" and c.strict_receive is True and _distance(c.S2, (0.0, 0.0)) < math.inf and c.T2 * SPEED_MPS + cfg.tolerances.eps_geo >= cfg.lmin_m]
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
    if data.get("official20") is not None and data.get("official20") != (radius is not None and radius + EPS_MEC <= 20.0):
        failures.append("official20_mismatch")
    if data.get("operational17") is not None and data.get("operational17") != (radius is not None and radius + EPS_MEC <= 17.0):
        failures.append("operational17_mismatch")
    if data.get("official20_provisional") is not None and data.get("official20_provisional") != (radius is not None and radius + EPS_MEC <= 20.0):
        failures.append("official20_provisional_mismatch")
    if data.get("operational17_provisional") is not None and data.get("operational17_provisional") != (radius is not None and radius + EPS_MEC <= 17.0):
        failures.append("operational17_provisional_mismatch")
    return {"valid": not failures, "failures": failures}


def solve_q2(S1: Sequence[float], theta1_hat_deg: float, config: Optional[Q2Config] = None) -> dict:
    """Build the formal Q2 domain; M5A search remains an explicit dev call."""

    cfg = config or Q2Config()
    p1 = build_P1_bound(S1, theta1_hat_deg, cfg)
    return Q2Result(
        status="M1_M5A_COMPONENTS_IMPLEMENTED",
        model_version="Q2-robust-selection-v2.1",
        P1=p1,
        selected_strict=None,
        diagnostics={
            "milestones_complete": ["M1", "M2", "M3", "M4", "M5A"],
            "pending": ["M5B", "M6"],
            "geometry_dependency": "Q1-localization-v1 VERIFIED",
            "continuous_strict_certificate": "triangle-cell 2-Lipschitz branch-and-bound",
            "eps_rec_m": _certificate_epsilon(cfg)[0],
            "eps_rec_source": _certificate_epsilon(cfg)[1],
            "worst_value_wording": "场景加密后的收敛数值最坏值",
        },
    ).to_dict()


__all__ = [
    "Q2Config", "SourceScenario", "CandidateResult", "WorstScenario", "Q2Result", "CandidateCell",
    "bearing", "wrap_pi", "build_P1_bound", "physical_filter", "receive_floor",
    "receive_violation", "certified_strict", "make_P2", "fim_order_score",
    "build_Gext", "build_Gverify", "build_error_grid", "relchg",
    "evaluate_candidate_resolution", "evaluate_candidate", "evaluate_candidate_nested",
    "merge_verified_worst", "replay_worst_scenario", "pareto_front", "select_best",
    "select_from_evaluated", "search_strict_candidates", "validate_solution", "solve_q2",
]
