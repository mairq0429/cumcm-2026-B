import math
import os
import random
import sys
import unittest
from dataclasses import replace


SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from q1_localization import (  # noqa: E402
    ANGLE_ERROR_DEG,
    CIRCLE_POLYGON_SIDES,
    CLEAR_RADIUS_THRESHOLD_M,
    OPTICAL_RADIUS_M,
    SAFETY_MARGIN_M,
    TARGET_RADIUS_M,
    DEFAULT_TOLERANCES,
    EPS_ANGLE_DEG,
    EPS_AREA,
    EPS_AREA2,
    EPS_COLLINEAR,
    EPS_CONVEX,
    EPS_COVER,
    EPS_DIAMETER_REL,
    EPS_GEO,
    EPS_MEC,
    EPS_MERGE,
    EPS_PARALLEL,
    analyze_convex_region,
    brute_force_diameter,
    circumscribed_circle_polygon,
    classify_region,
    half_plane_clip,
    minimum_enclosing_circle,
    point_in_convex_region,
    polygon_area,
    q1_localize,
    rotating_calipers_diameter,
    wedge_halfplanes,
)


def bearing_degrees(station, target):
    return math.degrees(math.atan2(target[1] - station[1], target[0] - station[0]))


def inside_halfplanes(point, halfplanes, tolerance=1.0e-10):
    return all(a * point[0] + b * point[1] <= c + tolerance for a, b, c in halfplanes)


def convex_hull(points):
    points = sorted(set(points))
    if len(points) <= 1:
        return points

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


class TestWedges(unittest.TestCase):
    def assert_direction_membership(self, theta_deg):
        halfplanes = wedge_halfplanes(13.0, -7.0, theta_deg)
        radians = math.radians(theta_deg)
        point = (13.0 + 100.0 * math.cos(radians), -7.0 + 100.0 * math.sin(radians))
        self.assertTrue(inside_halfplanes(point, halfplanes))
        outside_angle = math.radians(theta_deg + 1.1)
        outside = (13.0 + 100.0 * math.cos(outside_angle), -7.0 + 100.0 * math.sin(outside_angle))
        self.assertFalse(inside_halfplanes(outside, halfplanes))

    def test_theta_zero(self):
        self.assert_direction_membership(0.0)

    def test_theta_ninety(self):
        self.assert_direction_membership(90.0)

    def test_theta_one_eighty(self):
        self.assert_direction_membership(180.0)

    def test_theta_359_5_and_wraparound(self):
        self.assert_direction_membership(359.5)
        halfplanes = wedge_halfplanes(0.0, 0.0, 359.5)
        self.assertTrue(inside_halfplanes((100.0, 0.0), halfplanes))
        angle = math.radians(358.0)
        self.assertFalse(inside_halfplanes((100.0 * math.cos(angle), 100.0 * math.sin(angle)), halfplanes))


class TestDomainAndClipping(unittest.TestCase):
    def test_circle_is_inside_circumscribed_polygon(self):
        polygon = circumscribed_circle_polygon()
        rng = random.Random(20260911)
        for _ in range(5000):
            angle = rng.uniform(-math.pi, math.pi)
            radius = TARGET_RADIUS_M * math.sqrt(rng.random())
            point = (radius * math.cos(angle), radius * math.sin(angle))
            self.assertTrue(point_in_convex_region(point, polygon, "POLYGON"))
        for k in range(1440):
            angle = 2.0 * math.pi * k / 1440
            point = (TARGET_RADIUS_M * math.cos(angle), TARGET_RADIUS_M * math.sin(angle))
            self.assertTrue(point_in_convex_region(point, polygon, "POLYGON"))

    def test_half_plane_clip_and_degenerate_classification(self):
        square = [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
        clipped = half_plane_clip(square, 1.0, 0.0, 0.0)
        self.assertAlmostEqual(polygon_area(clipped), 2.0)
        self.assertEqual(classify_region([])[0], "EMPTY")
        self.assertEqual(classify_region([(1.0, 2.0)])[0], "POINT")
        self.assertEqual(classify_region([(0.0, 0.0), (2.0, 0.0)])[0], "SEGMENT")
        collinear = [(0.0, 0.0), (1.0, 0.0), (3.0, 0.0), (2.0, 0.0)]
        kind, endpoints, _ = classify_region(collinear)
        self.assertEqual(kind, "SEGMENT")
        self.assertAlmostEqual(brute_force_diameter(endpoints)[0], 3.0)


class TestLocalization(unittest.TestCase):
    def test_fixed_constants(self):
        self.assertEqual(ANGLE_ERROR_DEG, 1.0)
        self.assertEqual(TARGET_RADIUS_M, 1800.0)
        self.assertEqual(CIRCLE_POLYGON_SIDES, 720)
        self.assertEqual(OPTICAL_RADIUS_M, 20.0)
        self.assertEqual(SAFETY_MARGIN_M, 3.0)
        self.assertEqual(CLEAR_RADIUS_THRESHOLD_M, 17.0)
        self.assertEqual(
            (
                EPS_GEO, EPS_MERGE, EPS_COLLINEAR, EPS_PARALLEL, EPS_AREA,
                EPS_CONVEX, EPS_AREA2, EPS_COVER, EPS_MEC,
                EPS_DIAMETER_REL, EPS_ANGLE_DEG,
            ),
            (
                1.8e-6, 1.8e-5, 1.8e-5, 1.8e-9, 3.24e-4,
                3.24e-4, 3.24e-4, 1.8e-4, 1.8e-4, 1.0e-7, 1.0e-6,
            ),
        )

    def test_two_near_orthogonal_observations(self):
        observations = [
            {"x": -1000.0, "y": 0.0, "theta_deg": 0.0},
            {"x": 0.0, "y": -1000.0, "theta_deg": 90.0},
        ]
        result = q1_localize(observations)
        self.assertEqual(result["status"], "NORMAL")
        self.assertEqual(result["region_type"], "POLYGON")
        self.assertTrue(point_in_convex_region((0.0, 0.0), result["polygon"], result["region_type"]))
        self.assertTrue(result["certificate_under_original_bound"])

    def test_near_parallel_is_long_thin_and_legal(self):
        target = (0.0, 0.0)
        stations = [(-1000.0, -10.0), (-1000.0, 10.0)]
        observations = [
            {"x": x, "y": y, "theta_deg": bearing_degrees((x, y), target)} for x, y in stations
        ]
        result = q1_localize(observations)
        self.assertEqual(result["status"], "NORMAL")
        self.assertEqual(result["region_type"], "POLYGON")
        # A dimensionless area/diameter^2 ratio distinguishes this long, thin
        # region without contradicting the universal MEC >= diameter/2 bound.
        self.assertLess(result["area"] / result["diameter"] ** 2, 0.02)
        self.assertTrue(point_in_convex_region(target, result["polygon"], result["region_type"]))

    def test_empty_original_is_repaired_without_original_certificate(self):
        observations = [
            {"x": -1000.0, "y": 0.0, "theta_deg": 0.0},
            {"x": 1000.0, "y": 100.0, "theta_deg": 0.0},
        ]
        result = q1_localize(observations)
        self.assertEqual(result["status"], "REPAIRED")
        self.assertGreater(result["relaxation_deg"], 0.0)
        self.assertFalse(result["certificate_under_original_bound"])
        self.assertTrue(result["diagnostics"]["original_region_empty"])

    def test_inconsistent_even_at_maximum_half_width(self):
        result = q1_localize([{"x": -2000.0, "y": 0.0, "theta_deg": 180.0}])
        self.assertEqual(result["status"], "INCONSISTENT")
        self.assertEqual(result["region_type"], "EMPTY")
        self.assertIsNone(result["relaxation_deg"])
        self.assertFalse(result["certificate_under_original_bound"])

    def test_repeatability(self):
        observations = [
            {"x": -900.0, "y": -300.0, "theta_deg": 18.43494882292201},
            {"x": 400.0, "y": -1100.0, "theta_deg": 109.9831065219},
            {"x": 1000.0, "y": 500.0, "theta_deg": -153.4349488229},
        ]
        first = q1_localize(observations)
        second = q1_localize(observations)
        self.assertEqual(first, second)


class TestDiameterAndMEC(unittest.TestCase):
    max_relative_error = 0.0

    def test_random_convex_polygons_calipers_matches_bruteforce(self):
        rng = random.Random(8675309)
        maximum = 0.0
        for _ in range(300):
            cloud = [(rng.uniform(-100.0, 100.0), rng.uniform(-100.0, 100.0)) for _ in range(50)]
            polygon = convex_hull(cloud)
            calipers = rotating_calipers_diameter(polygon)[0]
            brute = brute_force_diameter(polygon)[0]
            relative = abs(calipers - brute) / max(1.0, brute)
            maximum = max(maximum, relative)
            self.assertLessEqual(relative, 1.0e-7)
        type(self).max_relative_error = maximum
        print(f"CALIPERS_MAX_RELATIVE_ERROR={maximum:.17g}")

    def test_equilateral_triangle_diameter_circle_counterexample_and_mec(self):
        side = 30.0
        triangle = [(0.0, 0.0), (side, 0.0), (side / 2.0, side * math.sqrt(3.0) / 2.0)]
        analysis = analyze_convex_region(triangle)
        diameter = analysis["diameter"]
        self.assertFalse(analysis["diameter_circle_covers"])
        self.assertFalse(analysis["exists_diameter_cover_circle"])
        self.assertFalse(analysis["diameter_length_cover_exists"])
        mec_center, mec_radius = minimum_enclosing_circle(triangle)
        self.assertTrue(all(math.dist(point, mec_center) <= mec_radius + 1.0e-6 for point in triangle))
        self.assertGreaterEqual(mec_radius + 1.0e-6, diameter / 2.0)
        self.assertLessEqual(mec_radius, diameter / math.sqrt(3.0) + 1.0e-6)
        self.assertAlmostEqual(mec_radius, diameter / math.sqrt(3.0), places=7)
        segment = analyze_convex_region([(-17.0, 0.0), (17.0, 0.0)])
        self.assertFalse(segment["clearable"])
        self.assertTrue(segment["within_optical_guarantee"])
        self.assertTrue(segment["exists_diameter_cover_circle"])
        self.assertEqual(
            segment["exists_diameter_cover_circle"],
            segment["diameter_length_cover_exists"],
        )


class TestMonteCarloAndConvergence(unittest.TestCase):
    def test_tolerance_sensitivity(self):
        target = (1300.0, -700.0)
        stations = [(-1600.0, -900.0), (200.0, -1900.0), (1900.0, 800.0)]
        observations = [
            {"x": station[0], "y": station[1], "theta_deg": bearing_degrees(station, target)}
            for station in stations
        ]

        def scaled(factor):
            return replace(
                DEFAULT_TOLERANCES,
                eps_geo=DEFAULT_TOLERANCES.eps_geo * factor,
                eps_merge=DEFAULT_TOLERANCES.eps_merge * factor,
                eps_collinear=DEFAULT_TOLERANCES.eps_collinear * factor,
                eps_parallel=DEFAULT_TOLERANCES.eps_parallel * factor,
                eps_area=DEFAULT_TOLERANCES.eps_area * factor,
                eps_convex=DEFAULT_TOLERANCES.eps_convex * factor,
                eps_area2=DEFAULT_TOLERANCES.eps_area2 * factor,
                eps_cover=DEFAULT_TOLERANCES.eps_cover * factor,
                eps_mec=DEFAULT_TOLERANCES.eps_mec * factor,
                eps_diameter_rel=DEFAULT_TOLERANCES.eps_diameter_rel * factor,
                eps_angle_deg=DEFAULT_TOLERANCES.eps_angle_deg * factor,
            )

        results = [q1_localize(observations, tolerances=scaled(factor)) for factor in (0.1, 1.0, 10.0)]
        self.assertTrue(all(result["status"] == "NORMAL" for result in results))
        for field, absolute_limit in (("area", 0.01), ("diameter", 1.0e-4), ("mec_radius", 1.0e-4)):
            spread = max(result[field] for result in results) - min(result[field] for result in results)
            print(f"TOLERANCE_SENSITIVITY field={field} spread={spread:.12g}")
            self.assertLessEqual(spread, absolute_limit)
        for field in (
            "clearable", "diameter_circle_covers", "exists_diameter_cover_circle"
        ):
            values = [result[field] for result in results]
            print(f"TOLERANCE_SENSITIVITY field={field} values={values}")
            self.assertEqual(len(set(values)), 1, (field, values))

    def test_monte_carlo_true_source_containment_1000(self):
        seed = 2026091101
        rng = random.Random(seed)
        failures = []
        cases = 1000
        for case_index in range(cases):
            angle = rng.uniform(-math.pi, math.pi)
            radius = TARGET_RADIUS_M * math.sqrt(rng.random())
            target = (radius * math.cos(angle), radius * math.sin(angle))
            observations = []
            for _ in range(rng.randint(2, 6)):
                while True:
                    station = (rng.uniform(-2600.0, 2600.0), rng.uniform(-2600.0, 2600.0))
                    if math.dist(station, target) > 5.0:
                        break
                theta_true = bearing_degrees(station, target)
                theta_measured = theta_true + rng.uniform(-1.0, 1.0)
                observations.append({"x": station[0], "y": station[1], "theta_deg": theta_measured})
            result = q1_localize(observations)
            contained = result["status"] == "NORMAL" and point_in_convex_region(
                target, result["polygon"], result["region_type"]
            )
            if not contained:
                failures.append((seed, case_index, target, observations, result))
                break
        print(f"MONTE_CARLO_CASES={cases} FAILURES={len(failures)} SEED={seed}")
        self.assertFalse(failures, failures[0] if failures else None)

    def test_monotonic_shrinkage(self):
        target = (120.0, -80.0)
        stations = [(-1500.0, -800.0), (-1200.0, 900.0), (300.0, -1700.0),
                    (1600.0, 500.0), (800.0, 1500.0), (-1700.0, 200.0)]
        observations = [
            {"x": station[0], "y": station[1], "theta_deg": bearing_degrees(station, target)}
            for station in stations
        ]
        previous = None
        for count in range(1, len(observations) + 1):
            current = q1_localize(observations[:count])
            self.assertEqual(current["status"], "NORMAL")
            self.assertTrue(point_in_convex_region(target, current["polygon"], current["region_type"]))
            if previous is not None:
                self.assertTrue(all(point_in_convex_region(
                    point, previous["polygon"], previous["region_type"]
                ) for point in current["polygon"]))
                self.assertLessEqual(current["area"], previous["area"] + 1.0e-4)
                self.assertLessEqual(current["diameter"], previous["diameter"] + 1.0e-6)
                self.assertLessEqual(current["mec_radius"], previous["mec_radius"] + 1.0e-6)
            previous = current

    def test_polygon_side_convergence(self):
        target = (1750.0, 0.0)
        stations = [(-1000.0, -800.0), (-900.0, 1000.0)]
        observations = [
            {"x": station[0], "y": station[1], "theta_deg": bearing_degrees(station, target)}
            for station in stations
        ]
        results = {sides: q1_localize(observations, circle_polygon_sides=sides) for sides in (360, 720, 1440)}
        for sides, result in results.items():
            self.assertEqual(result["status"], "NORMAL")
            print(
                f"N_CONVERGENCE sides={sides} area={result['area']:.12g} "
                f"diameter={result['diameter']:.12g} mec_radius={result['mec_radius']:.12g}"
            )
        # The remaining 720 -> 1440 discretization effect is small at the
        # problem scale. Exact stepwise monotonicity is not expected because
        # N=360 and N=720 may share the active extremal vertices.
        self.assertLess(
            abs(results[1440]["area"] - results[720]["area"]) / results[1440]["area"],
            3.0e-5,
        )
        self.assertLess(abs(results[1440]["diameter"] - results[720]["diameter"]), 0.05)
        self.assertLess(abs(results[1440]["mec_radius"] - results[720]["mec_radius"]), 0.05)


if __name__ == "__main__":
    unittest.main(verbosity=2)
