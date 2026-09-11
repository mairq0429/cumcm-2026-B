"""Q1 bounded-bearing-error set-membership localization.

The implementation is intentionally self contained and uses only the Python
standard library.  It does not depend on, or integrate with, the frozen Q3
baseline.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Iterable, Mapping, Optional, Sequence, Tuple


Point = Tuple[float, float]
Circle = Tuple[Point, float]

ANGLE_ERROR_DEG = 1.0
TARGET_RADIUS_M = 1800.0
CIRCLE_POLYGON_SIDES = 720
OPTICAL_RADIUS_M = 20.0
SAFETY_MARGIN_M = 3.0
CLEAR_RADIUS_THRESHOLD_M = 17.0
MAX_HALF_WIDTH_DEG = 89.999999
MAX_RELAXATION_DEG = MAX_HALF_WIDTH_DEG - ANGLE_ERROR_DEG

# Formal implementation tolerances supplied by the modeling specification.
EPS_GEO = 1.8e-6
EPS_MERGE = 1.8e-5
EPS_COLLINEAR = 1.8e-5
EPS_PARALLEL = 1.8e-9
EPS_AREA = 3.24e-4
EPS_CONVEX = 3.24e-4
EPS_AREA2 = 3.24e-4
EPS_COVER = 1.8e-4
EPS_MEC = 1.8e-4
EPS_DIAMETER_REL = 1.0e-7
EPS_ANGLE_DEG = 1.0e-6


@dataclass(frozen=True)
class NumericalTolerances:
    """Centralized implementation tolerances, with units in field comments.

    The defaults are tiny relative to the 1800 m domain, but remain several
    orders above binary64 roundoff in products of domain-scale coordinates.
    They are numerical implementation parameters, not physical parameters.
    """

    eps_geo: float = EPS_GEO  # m: half-plane inside residual
    eps_merge: float = EPS_MERGE  # m: near-duplicate vertices
    eps_collinear: float = EPS_COLLINEAR  # m: point-to-line distance
    eps_parallel: float = EPS_PARALLEL  # m: clipping residual difference
    eps_area: float = EPS_AREA  # m^2: region-area degeneracy
    eps_convex: float = EPS_CONVEX  # m^2: convexity cross product
    eps_area2: float = EPS_AREA2  # m^2: calipers doubled-area comparison
    eps_cover: float = EPS_COVER  # m: specified diameter-circle coverage
    eps_mec: float = EPS_MEC  # m: MEC coverage, bounds, and decisions
    eps_diameter_rel: float = EPS_DIAMETER_REL  # dimensionless
    eps_angle_deg: float = EPS_ANGLE_DEG  # degree: relaxation bisection


DEFAULT_TOLERANCES = NumericalTolerances()


def _cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _sub(a: Point, b: Point) -> Point:
    return a[0] - b[0], a[1] - b[1]


def _distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _signed_area2(polygon: Sequence[Point]) -> float:
    return sum(_cross(polygon[i], polygon[(i + 1) % len(polygon)]) for i in range(len(polygon)))


def polygon_area(polygon: Sequence[Point]) -> float:
    """Return the unsigned polygon area in square metres."""

    return abs(_signed_area2(polygon)) * 0.5 if len(polygon) >= 3 else 0.0


def wedge_halfplanes(
    sx: float, sy: float, theta_deg: float, half_width_deg: float = ANGLE_ERROR_DEG
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Return the two ``a*x + b*y <= c`` half-planes of a bearing wedge."""

    if not (0.0 <= half_width_deg < 90.0):
        raise ValueError("half_width_deg must satisfy 0 <= value < 90")
    beta_minus = math.radians(theta_deg - half_width_deg)
    beta_plus = math.radians(theta_deg + half_width_deg)
    ux_minus, uy_minus = math.cos(beta_minus), math.sin(beta_minus)
    ux_plus, uy_plus = math.cos(beta_plus), math.sin(beta_plus)
    lower = (uy_minus, -ux_minus, uy_minus * sx - ux_minus * sy)
    upper = (-uy_plus, ux_plus, -uy_plus * sx + ux_plus * sy)
    return lower, upper


def circumscribed_circle_polygon(
    radius_m: float = TARGET_RADIUS_M, sides: int = CIRCLE_POLYGON_SIDES
) -> list[Point]:
    """Construct the CCW polygon formed by intersections of circle tangents."""

    if radius_m <= 0.0:
        raise ValueError("radius_m must be positive")
    if sides < 3:
        raise ValueError("sides must be at least 3")
    vertex_radius = radius_m / math.cos(math.pi / sides)
    step = 2.0 * math.pi / sides
    return [
        (
            vertex_radius * math.cos((k + 0.5) * step),
            vertex_radius * math.sin((k + 0.5) * step),
        )
        for k in range(sides)
    ]


def _cleanup_polygon(polygon: Sequence[Point], tolerances: NumericalTolerances) -> list[Point]:
    if not polygon:
        return []
    cleaned: list[Point] = []
    for point in polygon:
        if not cleaned or _distance(point, cleaned[-1]) > tolerances.eps_merge:
            cleaned.append(point)
    if len(cleaned) > 1 and _distance(cleaned[0], cleaned[-1]) <= tolerances.eps_merge:
        cleaned.pop()

    changed = True
    while changed and len(cleaned) >= 3:
        changed = False
        result: list[Point] = []
        n = len(cleaned)
        for i, point in enumerate(cleaned):
            prev_point = cleaned[(i - 1) % n]
            next_point = cleaned[(i + 1) % n]
            ac = _sub(next_point, prev_point)
            ab = _sub(point, prev_point)
            bc = _sub(point, next_point)
            ac_length = math.hypot(ac[0], ac[1])
            point_line_distance = (
                abs(_cross(ac, ab)) / ac_length if ac_length > tolerances.eps_merge else math.inf
            )
            between = ab[0] * bc[0] + ab[1] * bc[1] <= tolerances.eps_merge ** 2
            if (
                point_line_distance <= tolerances.eps_collinear
                and between
            ):
                changed = True
            else:
                result.append(point)
        if not result:
            break
        cleaned = result
    return cleaned


def half_plane_clip(
    polygon: Sequence[Point],
    a: float,
    b: float,
    c: float,
    tolerances: NumericalTolerances = DEFAULT_TOLERANCES,
) -> list[Point]:
    """Sutherland-Hodgman clip against ``a*x + b*y <= c``."""

    if not polygon:
        return []

    def residual(point: Point) -> float:
        return a * point[0] + b * point[1] - c

    output: list[Point] = []
    start = polygon[-1]
    f_start = residual(start)
    start_inside = f_start <= tolerances.eps_geo
    for end in polygon:
        f_end = residual(end)
        end_inside = f_end <= tolerances.eps_geo
        if start_inside != end_inside:
            denominator = f_start - f_end
            if abs(denominator) > tolerances.eps_parallel:
                t = min(1.0, max(0.0, f_start / denominator))
                output.append(
                    (start[0] + t * (end[0] - start[0]), start[1] + t * (end[1] - start[1]))
                )
            elif end_inside:
                output.append(end)
        if end_inside:
            output.append(end)
        start, f_start, start_inside = end, f_end, end_inside
    return _cleanup_polygon(output, tolerances)


def _farthest_pair(points: Sequence[Point]) -> Tuple[float, Optional[Point], Optional[Point]]:
    if not points:
        return 0.0, None, None
    if len(points) == 1:
        return 0.0, points[0], points[0]
    best_sq = -1.0
    best = (points[0], points[1])
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            dx = points[i][0] - points[j][0]
            dy = points[i][1] - points[j][1]
            distance_sq = dx * dx + dy * dy
            if distance_sq > best_sq:
                best_sq = distance_sq
                best = points[i], points[j]
    return math.sqrt(max(0.0, best_sq)), best[0], best[1]


def classify_region(
    polygon: Sequence[Point], tolerances: NumericalTolerances = DEFAULT_TOLERANCES
) -> Tuple[str, list[Point], float]:
    """Classify and canonicalize a clipped convex region."""

    points = _cleanup_polygon(polygon, tolerances)
    if not points:
        return "EMPTY", [], 0.0
    if len(points) == 1:
        return "POINT", [points[0]], 0.0
    if len(points) == 2:
        if _distance(points[0], points[1]) <= tolerances.eps_merge:
            return "POINT", [points[0]], 0.0
        return "SEGMENT", points, 0.0
    signed_area2 = _signed_area2(points)
    area = abs(signed_area2) * 0.5
    if area <= tolerances.eps_area:
        _, endpoint_a, endpoint_b = _farthest_pair(points)
        assert endpoint_a is not None and endpoint_b is not None
        if _distance(endpoint_a, endpoint_b) <= tolerances.eps_merge:
            return "POINT", [endpoint_a], 0.0
        return "SEGMENT", [endpoint_a, endpoint_b], 0.0
    if signed_area2 < 0.0:
        points.reverse()
    return "POLYGON", points, area


def is_convex_ccw(
    polygon: Sequence[Point], tolerances: NumericalTolerances = DEFAULT_TOLERANCES
) -> bool:
    if len(polygon) < 3:
        return True
    return all(
        _cross(_sub(polygon[(i + 1) % len(polygon)], polygon[i]),
               _sub(polygon[(i + 2) % len(polygon)], polygon[(i + 1) % len(polygon)]))
        >= -tolerances.eps_convex
        for i in range(len(polygon))
    )


def brute_force_diameter(points: Sequence[Point]) -> Tuple[float, Optional[Point], Optional[Point]]:
    """Reference O(n^2) diameter implementation."""

    return _farthest_pair(points)


def rotating_calipers_diameter(
    polygon: Sequence[Point], tolerances: NumericalTolerances = DEFAULT_TOLERANCES
) -> Tuple[float, Optional[Point], Optional[Point]]:
    """Return a diameter and endpoints for a CCW convex polygon in O(n)."""

    n = len(polygon)
    if n <= 2:
        return _farthest_pair(polygon)
    j = 1
    best_sq = -1.0
    best = (polygon[0], polygon[1])

    def consider(p: Point, q: Point) -> None:
        nonlocal best_sq, best
        dx, dy = p[0] - q[0], p[1] - q[1]
        distance_sq = dx * dx + dy * dy
        if distance_sq > best_sq:
            best_sq, best = distance_sq, (p, q)

    for i in range(n):
        next_i = (i + 1) % n
        edge = _sub(polygon[next_i], polygon[i])
        while True:
            next_j = (j + 1) % n
            current_area = abs(_cross(edge, _sub(polygon[j], polygon[i])))
            next_area = abs(_cross(edge, _sub(polygon[next_j], polygon[i])))
            if next_area > current_area + tolerances.eps_area2:
                j = next_j
            else:
                break
        consider(polygon[i], polygon[j])
        consider(polygon[next_i], polygon[j])
        next_j = (j + 1) % n
        current_area = abs(_cross(edge, _sub(polygon[j], polygon[i])))
        next_area = abs(_cross(edge, _sub(polygon[next_j], polygon[i])))
        if abs(next_area - current_area) <= tolerances.eps_area2:
            consider(polygon[i], polygon[next_j])
            consider(polygon[next_i], polygon[next_j])
    return math.sqrt(max(0.0, best_sq)), best[0], best[1]


def _circle_from_two(a: Point, b: Point) -> Circle:
    center = ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)
    return center, _distance(a, b) * 0.5


def _circle_from_three(
    a: Point, b: Point, c: Point, tolerances: NumericalTolerances
) -> Optional[Circle]:
    ab = _sub(b, a)
    ab_length = math.hypot(ab[0], ab[1])
    if ab_length <= tolerances.eps_merge:
        return None
    determinant = 2.0 * _cross(_sub(b, a), _sub(c, a))
    if abs(determinant) / (2.0 * ab_length) <= tolerances.eps_collinear:
        return None
    aa, bb, cc = a[0] * a[0] + a[1] * a[1], b[0] * b[0] + b[1] * b[1], c[0] * c[0] + c[1] * c[1]
    ux = (aa * (b[1] - c[1]) + bb * (c[1] - a[1]) + cc * (a[1] - b[1])) / determinant
    uy = (aa * (c[0] - b[0]) + bb * (a[0] - c[0]) + cc * (b[0] - a[0])) / determinant
    center = (ux, uy)
    return center, _distance(center, a)


def _inside_circle(point: Point, circle: Circle, eps_cover: float) -> bool:
    return _distance(point, circle[0]) <= circle[1] + eps_cover


def minimum_enclosing_circle(
    points: Sequence[Point], tolerances: NumericalTolerances = DEFAULT_TOLERANCES
) -> Tuple[Optional[Point], Optional[float]]:
    """Deterministic-seed incremental minimum enclosing circle."""

    if not points:
        return None, None
    shuffled = list(points)
    random.Random(0).shuffle(shuffled)
    circle: Optional[Circle] = None
    for i, p in enumerate(shuffled):
        if circle is not None and _inside_circle(p, circle, tolerances.eps_mec):
            continue
        circle = (p, 0.0)
        for j in range(i):
            q = shuffled[j]
            if _inside_circle(q, circle, tolerances.eps_mec):
                continue
            circle = _circle_from_two(p, q)
            for k in range(j):
                r = shuffled[k]
                if _inside_circle(r, circle, tolerances.eps_mec):
                    continue
                candidate = _circle_from_three(p, q, r, tolerances)
                if candidate is None:
                    candidates = [_circle_from_two(p, q), _circle_from_two(p, r), _circle_from_two(q, r)]
                    enclosing = [candidate_circle for candidate_circle in candidates if all(
                        _inside_circle(point, candidate_circle, tolerances.eps_mec) for point in (p, q, r)
                    )]
                    circle = min(enclosing, key=lambda item: item[1])
                else:
                    circle = candidate
    assert circle is not None
    # Recompute the radius from the returned centre so coverage cannot be lost
    # to a final rounding error.
    radius = max(_distance(point, circle[0]) for point in points)
    return circle[0], radius


def point_in_convex_region(
    point: Point,
    polygon: Sequence[Point],
    region_type: str,
    tolerances: NumericalTolerances = DEFAULT_TOLERANCES,
) -> bool:
    """Numerically test membership in a canonical region."""

    if region_type == "EMPTY":
        return False
    if region_type == "POINT":
        return _distance(point, polygon[0]) <= tolerances.eps_merge
    if region_type == "SEGMENT":
        a, b = polygon
        ab, ap = _sub(b, a), _sub(point, a)
        ab_length = math.hypot(ab[0], ab[1])
        line_distance = abs(_cross(ab, ap)) / ab_length if ab_length > tolerances.eps_merge else math.inf
        return line_distance <= tolerances.eps_collinear and (
            min(a[0], b[0]) - tolerances.eps_merge <= point[0] <= max(a[0], b[0]) + tolerances.eps_merge
            and min(a[1], b[1]) - tolerances.eps_merge <= point[1] <= max(a[1], b[1]) + tolerances.eps_merge
        )
    return all(
        _cross(_sub(polygon[(i + 1) % len(polygon)], polygon[i]), _sub(point, polygon[i]))
        >= -tolerances.eps_convex
        for i in range(len(polygon))
    )


def _validated_observations(observations: Iterable[Mapping[str, float]]) -> list[Tuple[float, float, float]]:
    result = []
    for index, observation in enumerate(observations):
        try:
            values = tuple(float(observation[key]) for key in ("x", "y", "theta_deg"))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"observation {index} must contain finite x, y, theta_deg") from exc
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"observation {index} must contain finite x, y, theta_deg")
        result.append(values)
    return result


def _localization_polygon(
    observations: Sequence[Tuple[float, float, float]],
    half_width_deg: float,
    circle_polygon_sides: int,
    tolerances: NumericalTolerances,
) -> list[Point]:
    polygon = circumscribed_circle_polygon(TARGET_RADIUS_M, circle_polygon_sides)
    for sx, sy, theta_deg in observations:
        for a, b, c in wedge_halfplanes(sx, sy, theta_deg, half_width_deg):
            polygon = half_plane_clip(polygon, a, b, c, tolerances)
            if not polygon:
                return []
    return polygon


def _analyze_region(
    raw_polygon: Sequence[Point], tolerances: NumericalTolerances, diagnostics: dict
) -> dict:
    region_type, polygon, area = classify_region(raw_polygon, tolerances)
    result = {"polygon": polygon, "region_type": region_type, "area": area}
    if region_type == "EMPTY":
        result.update({
            "diameter": None, "diameter_endpoint_A": None, "diameter_endpoint_B": None,
            "diameter_circle_center": None, "diameter_circle_covers": False,
            "exists_diameter_cover_circle": False,
            "diameter_length_cover_exists": False, "mec_center": None, "mec_radius": None,
            "within_optical_guarantee": False, "clearable": False,
        })
        return result

    convex = is_convex_ccw(polygon, tolerances)
    diagnostics["convexity_check_passed"] = convex
    if not convex:
        diagnostics.setdefault("validation_failures", []).append("non_convex_region")

    diameter, endpoint_a, endpoint_b = rotating_calipers_diameter(polygon, tolerances)
    brute_diameter, _, _ = brute_force_diameter(polygon)
    relative_error = abs(diameter - brute_diameter) / max(1.0, brute_diameter)
    diagnostics["diameter_calipers_m"] = diameter
    diagnostics["diameter_bruteforce_m"] = brute_diameter
    diagnostics["diameter_relative_error"] = relative_error
    diagnostics["diameter_crosscheck_passed"] = relative_error <= tolerances.eps_diameter_rel
    if relative_error > tolerances.eps_diameter_rel:
        diagnostics.setdefault("validation_failures", []).append("diameter_crosscheck_failed")

    assert endpoint_a is not None and endpoint_b is not None
    diameter_center = ((endpoint_a[0] + endpoint_b[0]) * 0.5, (endpoint_a[1] + endpoint_b[1]) * 0.5)
    diameter_radius = diameter * 0.5
    diameter_circle_covers = all(
        _distance(point, diameter_center) <= diameter_radius + tolerances.eps_cover for point in polygon
    )

    mec_center, mec_radius = minimum_enclosing_circle(polygon, tolerances)
    assert mec_center is not None and mec_radius is not None
    mec_covers = all(_distance(point, mec_center) <= mec_radius + tolerances.eps_mec for point in polygon)
    diagnostics["mec_covers_vertices"] = mec_covers
    if not mec_covers:
        diagnostics.setdefault("validation_failures", []).append("mec_coverage_failed")
    lower = diameter * 0.5
    upper = diameter / math.sqrt(3.0) if diameter else 0.0
    bound_ok = lower - tolerances.eps_mec <= mec_radius <= upper + tolerances.eps_mec
    diagnostics["mec_jung_bounds_passed"] = bound_ok
    if not bound_ok:
        diagnostics.setdefault("validation_failures", []).append("mec_jung_bounds_failed")

    exists_diameter_cover_circle = abs(mec_radius - lower) <= tolerances.eps_mec
    result.update({
        "diameter": diameter,
        "diameter_endpoint_A": endpoint_a,
        "diameter_endpoint_B": endpoint_b,
        "diameter_circle_center": diameter_center,
        "diameter_circle_covers": diameter_circle_covers,
        "exists_diameter_cover_circle": exists_diameter_cover_circle,
        "diameter_length_cover_exists": exists_diameter_cover_circle,
        "mec_center": mec_center,
        "mec_radius": mec_radius,
        "within_optical_guarantee": mec_radius + tolerances.eps_mec <= OPTICAL_RADIUS_M,
        "clearable": mec_radius + tolerances.eps_mec <= CLEAR_RADIUS_THRESHOLD_M,
    })
    return result


def analyze_convex_region(
    polygon: Sequence[Point],
    tolerances: NumericalTolerances = DEFAULT_TOLERANCES,
) -> dict:
    """Analyze a directly supplied convex region, primarily for validation.

    This helper applies the same classification, diameter, specified-diameter
    circle, MEC, and numerical certificate checks used by q1_localize.
    """

    diagnostics = {"validation_failures": []}
    result = _analyze_region(polygon, tolerances, diagnostics)
    result["diagnostics"] = diagnostics
    return result


def q1_localize(
    observations: Iterable[Mapping[str, float]],
    *,
    tolerances: NumericalTolerances = DEFAULT_TOLERANCES,
    circle_polygon_sides: int = CIRCLE_POLYGON_SIDES,
) -> dict:
    """Localize a source using bounded bearing observations.

    ``circle_polygon_sides`` exists for convergence testing; production callers
    should retain the fixed default of 720.  Returned geometry is computed under
    the original +/-1 degree bound unless ``status == 'REPAIRED'``.
    """

    validated = _validated_observations(observations)
    if circle_polygon_sides < 3:
        raise ValueError("circle_polygon_sides must be at least 3")
    radial_excess = TARGET_RADIUS_M * (1.0 / math.cos(math.pi / circle_polygon_sides) - 1.0)
    diagnostics = {
        "circle_domain_representation": "circumscribed_polygon",
        "circle_polygon_sides": circle_polygon_sides,
        "circle_radial_excess_m": radial_excess,
        "angle_error_deg": ANGLE_ERROR_DEG,
        "optical_radius_m": OPTICAL_RADIUS_M,
        "safety_margin_m": SAFETY_MARGIN_M,
        "clear_radius_threshold_m": CLEAR_RADIUS_THRESHOLD_M,
        "clear_threshold_explanation": "17 m = 20 m optical radius - 3 m team safety margin",
        "tolerances": vars(tolerances),
        "validation_failures": [],
        "original_region_empty": False,
        "geometry_is_under_original_bound": True,
    }

    raw_polygon = _localization_polygon(
        validated, ANGLE_ERROR_DEG, circle_polygon_sides, tolerances
    )
    region_type, _, _ = classify_region(raw_polygon, tolerances)
    status = "NORMAL"
    relaxation_deg = 0.0

    if region_type == "EMPTY":
        diagnostics["original_region_empty"] = True
        diagnostics["geometry_is_under_original_bound"] = False
        upper_polygon = _localization_polygon(
            validated, MAX_HALF_WIDTH_DEG, circle_polygon_sides, tolerances
        )
        if classify_region(upper_polygon, tolerances)[0] == "EMPTY":
            status = "INCONSISTENT"
            relaxation_deg = None
            raw_polygon = []
        else:
            low, high = 0.0, MAX_RELAXATION_DEG
            while high - low > tolerances.eps_angle_deg:
                middle = (low + high) * 0.5
                candidate = _localization_polygon(
                    validated, ANGLE_ERROR_DEG + middle, circle_polygon_sides, tolerances
                )
                if classify_region(candidate, tolerances)[0] == "EMPTY":
                    low = middle
                else:
                    high = middle
                    upper_polygon = candidate
            relaxation_deg = high
            raw_polygon = _localization_polygon(
                validated, ANGLE_ERROR_DEG + relaxation_deg, circle_polygon_sides, tolerances
            )
            # At a tangency the bisection endpoint can be numerically empty;
            # use the latest known nonempty bracket endpoint in that case.
            if classify_region(raw_polygon, tolerances)[0] == "EMPTY":
                raw_polygon = upper_polygon
            status = "REPAIRED"
            diagnostics["repair_note"] = (
                "Geometry and clearable are diagnostic results under the relaxed bound; "
                "they are not a NORMAL certificate under the original +/-1 degree bound."
            )

    result = _analyze_region(raw_polygon, tolerances, diagnostics)
    if diagnostics["validation_failures"]:
        status = "INCONSISTENT"
        diagnostics["certificate_suppressed_due_to_validation_failure"] = True
    result.update({
        "status": status,
        "relaxation_deg": relaxation_deg,
        "certificate_under_original_bound": status == "NORMAL",
        "diagnostics": diagnostics,
    })
    return result


__all__ = [
    "ANGLE_ERROR_DEG", "TARGET_RADIUS_M", "CIRCLE_POLYGON_SIDES",
    "OPTICAL_RADIUS_M", "SAFETY_MARGIN_M", "CLEAR_RADIUS_THRESHOLD_M",
    "MAX_HALF_WIDTH_DEG", "MAX_RELAXATION_DEG",
    "EPS_GEO", "EPS_MERGE", "EPS_COLLINEAR", "EPS_PARALLEL",
    "EPS_AREA", "EPS_CONVEX", "EPS_AREA2", "EPS_COVER", "EPS_MEC",
    "EPS_DIAMETER_REL", "EPS_ANGLE_DEG", "NumericalTolerances",
    "DEFAULT_TOLERANCES", "wedge_halfplanes", "circumscribed_circle_polygon",
    "half_plane_clip", "classify_region", "polygon_area", "is_convex_ccw",
    "brute_force_diameter", "rotating_calipers_diameter",
    "minimum_enclosing_circle", "analyze_convex_region",
    "point_in_convex_region", "q1_localize",
]
