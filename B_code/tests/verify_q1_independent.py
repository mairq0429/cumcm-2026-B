"""Independent, standard-library-only verification for Q1 localization."""

from __future__ import annotations

import itertools
import json
import math
import os
import random
import sys


SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from q1_localization import (  # noqa: E402
    ANGLE_ERROR_DEG,
    EPS_MEC,
    TARGET_RADIUS_M,
    analyze_convex_region,
    q1_localize,
)


VERIFICATION_VERSION = "Q1-independent-v1"
SOURCE_CASES = 1000
RANDOM_MEC_CASES = 100
SOURCE_BASE_SEED = 2026091200
MEC_SEED = 2026091201
WEDGE_CHECK_TOL = 2.0e-6
POLYGON_CROSS_TOL = 1.0e-3
ORACLE_COVER_TOL = 1.0e-9


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def subtract(a, b):
    return a[0] - b[0], a[1] - b[1]


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def independent_wedge_contains(source, station, measured_theta_deg):
    vector = subtract(source, station)
    lower = math.radians(measured_theta_deg - ANGLE_ERROR_DEG)
    upper = math.radians(measured_theta_deg + ANGLE_ERROR_DEG)
    u_lower = math.cos(lower), math.sin(lower)
    u_upper = math.cos(upper), math.sin(upper)
    return (
        cross(u_lower, vector) >= -WEDGE_CHECK_TOL
        and cross(u_upper, vector) <= WEDGE_CHECK_TOL
    )


def independent_ccw_polygon_contains(point, polygon):
    if len(polygon) < 3:
        return False
    return all(
        cross(subtract(polygon[(index + 1) % len(polygon)], polygon[index]),
              subtract(point, polygon[index]))
        >= -POLYGON_CROSS_TOL
        for index in range(len(polygon))
    )


def verify_true_source_containment():
    failures = []
    for case_index in range(SOURCE_CASES):
        case_seed = SOURCE_BASE_SEED + case_index
        rng = random.Random(case_seed)
        source_angle = rng.uniform(-math.pi, math.pi)
        source_radius = TARGET_RADIUS_M * math.sqrt(rng.random())
        source = (
            source_radius * math.cos(source_angle),
            source_radius * math.sin(source_angle),
        )
        observations = []
        independent_constraints_ok = math.hypot(*source) <= TARGET_RADIUS_M + 1.0e-10
        for _ in range(rng.randint(2, 6)):
            while True:
                station = (
                    rng.uniform(-2600.0, 2600.0),
                    rng.uniform(-2600.0, 2600.0),
                )
                if distance(station, source) > 5.0:
                    break
            true_theta = math.degrees(
                math.atan2(source[1] - station[1], source[0] - station[0])
            )
            measured_theta = true_theta + rng.uniform(-1.0, 1.0)
            observations.append(
                {"x": station[0], "y": station[1], "theta_deg": measured_theta}
            )
            independent_constraints_ok &= independent_wedge_contains(
                source, station, measured_theta
            )

        result = q1_localize(observations)
        returned_polygon_ok = (
            result["status"] == "NORMAL"
            and result["region_type"] == "POLYGON"
            and independent_ccw_polygon_contains(source, result["polygon"])
        )
        if not independent_constraints_ok or not returned_polygon_ok:
            failures.append(
                {
                    "seed": case_seed,
                    "independent_constraints_ok": independent_constraints_ok,
                    "returned_polygon_ok": returned_polygon_ok,
                    "status": result["status"],
                    "region_type": result["region_type"],
                }
            )
            break
    return {
        "cases": SOURCE_CASES,
        "failures": len(failures),
        "first_failure_seed": failures[0]["seed"] if failures else None,
        "first_failure": failures[0] if failures else None,
    }


def circle_from_one(point):
    return point, 0.0


def circle_from_two(a, b):
    center = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    return center, distance(center, a)


def circle_from_three(a, b, c):
    determinant = 2.0 * cross(subtract(b, a), subtract(c, a))
    if abs(determinant) <= 1.0e-12:
        return None
    aa = a[0] * a[0] + a[1] * a[1]
    bb = b[0] * b[0] + b[1] * b[1]
    cc = c[0] * c[0] + c[1] * c[1]
    center = (
        (aa * (b[1] - c[1]) + bb * (c[1] - a[1]) + cc * (a[1] - b[1]))
        / determinant,
        (aa * (c[0] - b[0]) + bb * (a[0] - c[0]) + cc * (b[0] - a[0]))
        / determinant,
    )
    return center, distance(center, a)


def brute_force_mec(points):
    candidates = [circle_from_one(point) for point in points]
    candidates.extend(circle_from_two(a, b) for a, b in itertools.combinations(points, 2))
    candidates.extend(
        circle
        for circle in (
            circle_from_three(a, b, c)
            for a, b, c in itertools.combinations(points, 3)
        )
        if circle is not None
    )
    covering = [
        circle
        for circle in candidates
        if all(distance(point, circle[0]) <= circle[1] + ORACLE_COVER_TOL for point in points)
    ]
    if not covering:
        raise AssertionError("independent MEC oracle found no covering candidate")
    return min(covering, key=lambda circle: circle[1])


def convex_hull(points):
    unique = sorted(set(points))
    if len(unique) <= 1:
        return unique

    def turn(o, a, b):
        return cross(subtract(a, o), subtract(b, o))

    lower = []
    for point in unique:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(unique):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def verify_mec_oracle():
    sqrt3 = math.sqrt(3.0)
    named = {
        "triangle": [(0.0, 0.0), (6.0, 0.0), (1.0, 4.0)],
        "rectangle": [(-4.0, -2.0), (4.0, -2.0), (4.0, 2.0), (-4.0, 2.0)],
        "obtuse_triangle": [(0.0, 0.0), (10.0, 0.0), (2.0, 1.0)],
        "acute_triangle": [(0.0, 0.0), (7.0, 0.0), (3.0, 5.0)],
        "equilateral_triangle": [(0.0, 0.0), (6.0, 0.0), (3.0, 3.0 * sqrt3)],
    }
    cases = list(named.items())
    rng = random.Random(MEC_SEED)
    while len(cases) < len(named) + RANDOM_MEC_CASES:
        cloud = [
            (rng.uniform(-50.0, 50.0), rng.uniform(-50.0, 50.0))
            for _ in range(rng.randint(5, 18))
        ]
        hull = convex_hull(cloud)
        if 3 <= len(hull) <= 10:
            cases.append((f"random_{len(cases) - len(named)}", hull))

    failures = []
    max_radius_error = 0.0
    max_center_error = 0.0
    for name, polygon in cases:
        oracle_center, oracle_radius = brute_force_mec(polygon)
        result = analyze_convex_region(polygon)
        radius_error = abs(result["mec_radius"] - oracle_radius)
        center_error = distance(result["mec_center"], oracle_center)
        max_radius_error = max(max_radius_error, radius_error)
        max_center_error = max(max_center_error, center_error)
        if radius_error > EPS_MEC or center_error > EPS_MEC:
            failures.append(
                {
                    "case": name,
                    "radius_error": radius_error,
                    "center_error": center_error,
                }
            )
            break
    return {
        "cases": len(cases),
        "random_cases": RANDOM_MEC_CASES,
        "failures": len(failures),
        "max_radius_error_m": max_radius_error,
        "max_center_error_m": max_center_error,
        "first_failure": failures[0] if failures else None,
    }


def segment_analysis(radius):
    return analyze_convex_region([(-radius, 0.0), (radius, 0.0)])


def verify_threshold_boundaries():
    clear_radii = [
        16.9990, 16.9997, 16.99981, 16.99982,
        16.99983, 16.9999, 17.0000, 17.001,
    ]
    optical_radii = [
        19.9990, 19.9997, 19.99981, 19.99982,
        19.99983, 19.9999, 20.0000, 20.001,
    ]
    clear_results = []
    optical_results = []
    failures = []
    for radius in clear_radii:
        actual = segment_analysis(radius)["clearable"]
        expected = radius + EPS_MEC <= 17.0
        clear_results.append({"radius": radius, "expected": expected, "actual": actual})
        if actual != expected:
            failures.append({"field": "clearable", "radius": radius})
    for radius in optical_radii:
        actual = segment_analysis(radius)["within_optical_guarantee"]
        expected = radius + EPS_MEC <= 20.0
        optical_results.append({"radius": radius, "expected": expected, "actual": actual})
        if actual != expected:
            failures.append({"field": "within_optical_guarantee", "radius": radius})
    return {
        "clearable": clear_results,
        "within_optical_guarantee": optical_results,
        "failures": len(failures),
        "first_failure": failures[0] if failures else None,
    }


def verify_diameter_cover_concepts():
    sqrt3 = math.sqrt(3.0)
    cases = {
        "line_segment": [(-5.0, 0.0), (5.0, 0.0)],
        "rectangle": [(-4.0, -2.0), (4.0, -2.0), (4.0, 2.0), (-4.0, 2.0)],
        "equilateral_triangle": [(0.0, 0.0), (6.0, 0.0), (3.0, 3.0 * sqrt3)],
        "obtuse_triangle": [(0.0, 0.0), (10.0, 0.0), (2.0, 1.0)],
    }
    expected = {
        "line_segment": (True, True),
        "rectangle": (True, True),
        "equilateral_triangle": (False, False),
        "obtuse_triangle": (True, True),
    }
    results = {}
    failures = []
    for name, polygon in cases.items():
        result = analyze_convex_region(polygon)
        actual = (
            result["diameter_circle_covers"],
            result["exists_diameter_cover_circle"],
        )
        alias_ok = (
            result["diameter_length_cover_exists"]
            == result["exists_diameter_cover_circle"]
        )
        results[name] = {
            "diameter_circle_covers": actual[0],
            "exists_diameter_cover_circle": actual[1],
            "legacy_alias_matches": alias_ok,
        }
        if actual != expected[name] or not alias_ok:
            failures.append({"case": name, "expected": expected[name], "actual": actual})
    return {
        "cases": results,
        "failures": len(failures),
        "first_failure": failures[0] if failures else None,
    }


def verify_outer_circle():
    result = q1_localize([])
    polygon = result["polygon"]
    failures = 0
    boundary_samples = 20000
    interior_samples = 10000
    rng = random.Random(2026091202)
    for index in range(boundary_samples):
        angle = 2.0 * math.pi * index / boundary_samples
        point = (
            TARGET_RADIUS_M * math.cos(angle),
            TARGET_RADIUS_M * math.sin(angle),
        )
        if not independent_ccw_polygon_contains(point, polygon):
            failures += 1
            break
    if failures == 0:
        for _ in range(interior_samples):
            angle = rng.uniform(-math.pi, math.pi)
            radius = TARGET_RADIUS_M * math.sqrt(rng.random())
            point = radius * math.cos(angle), radius * math.sin(angle)
            if not independent_ccw_polygon_contains(point, polygon):
                failures += 1
                break
    theoretical = TARGET_RADIUS_M * (1.0 / math.cos(math.pi / 720.0) - 1.0)
    recorded = result["diagnostics"]["circle_radial_excess_m"]
    radial_error = abs(recorded - theoretical)
    if radial_error > 1.0e-12:
        failures += 1
    return {
        "boundary_samples": boundary_samples,
        "interior_samples": interior_samples,
        "failures": failures,
        "theoretical_radial_excess_m": theoretical,
        "recorded_radial_excess_m": recorded,
        "radial_excess_error_m": radial_error,
    }


def verify_repaired_semantics():
    observations = [
        {"x": -1000.0, "y": 0.0, "theta_deg": 0.0},
        {"x": 1000.0, "y": 100.0, "theta_deg": 0.0},
    ]
    # Independently, overlap of the two east-facing +/-1 degree wedges inside
    # x <= 1800 would require x >= 50/tan(1 degree), which is outside the disk.
    required_x = 50.0 / math.tan(math.radians(1.0))
    independently_original_empty = required_x > TARGET_RADIUS_M
    result = q1_localize(observations)
    passed = (
        independently_original_empty
        and result["status"] == "REPAIRED"
        and result["relaxation_deg"] > 0.0
        and result["certificate_under_original_bound"] is False
        and result["diagnostics"]["original_region_empty"] is True
    )
    return {
        "independently_original_empty": independently_original_empty,
        "required_overlap_x_m": required_x,
        "status": result["status"],
        "relaxation_deg": result["relaxation_deg"],
        "certificate_under_original_bound": result["certificate_under_original_bound"],
        "passed": passed,
    }


def main():
    report = {
        "verification_version": VERIFICATION_VERSION,
        "true_source": verify_true_source_containment(),
        "mec_oracle": verify_mec_oracle(),
        "threshold_boundaries": verify_threshold_boundaries(),
        "diameter_cover": verify_diameter_cover_concepts(),
        "outer_circle": verify_outer_circle(),
        "repaired": verify_repaired_semantics(),
    }
    report["passed"] = (
        report["true_source"]["failures"] == 0
        and report["mec_oracle"]["failures"] == 0
        and report["threshold_boundaries"]["failures"] == 0
        and report["diameter_cover"]["failures"] == 0
        and report["outer_circle"]["failures"] == 0
        and report["repaired"]["passed"]
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
