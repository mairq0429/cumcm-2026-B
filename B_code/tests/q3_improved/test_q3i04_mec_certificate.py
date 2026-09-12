import itertools
import math
import os
import random
import sys
import time
import unittest


SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from q3_improved.clear_certificate import (  # noqa: E402
    CertificateStatus,
    bind_clear_certificate,
    certificate_from_outer,
    certificate_is_current,
)
from q3_improved.conservative_geometry import (  # noqa: E402
    Box, OuterDiagnostics, OuterResult, rebuild_outer_from_observations,
)
from q3_improved.mec import EPS_MEC, minimum_enclosing_circle  # noqa: E402
from q3_improved.observations import (  # noqa: E402
    DirectionObservation, NearObservation, NoSignalObservation,
    ObservationHistory,
)
from q3_improved.protocol import ActionKind, normalize_response  # noqa: E402
from q3_improved.scheduler import ActionType, CoverageScheduler  # noqa: E402
from q3_improved.state import ChannelStatus, Q3State  # noqa: E402


ORACLE_TOL = 1.0e-9


def circle_one(point):
    return point, 0.0


def circle_two(a, b):
    center = ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)
    return center, math.dist(center, a)


def circle_three(a, b, c):
    determinant = 2.0 * ((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
    if abs(determinant) <= 1.0e-14:
        return None
    aa = a[0] * a[0] + a[1] * a[1]
    bb = b[0] * b[0] + b[1] * b[1]
    cc = c[0] * c[0] + c[1] * c[1]
    center = (
        (aa * (b[1] - c[1]) + bb * (c[1] - a[1]) + cc * (a[1] - b[1])) / determinant,
        (aa * (c[0] - b[0]) + bb * (a[0] - c[0]) + cc * (b[0] - a[0])) / determinant,
    )
    return center, math.dist(center, a)


def brute_force_mec(points):
    """Independent test oracle; does not call any production MEC helper."""

    points = tuple(set(points))
    if not points:
        return None
    candidates = [circle_one(point) for point in points]
    candidates.extend(circle_two(a, b) for a, b in itertools.combinations(points, 2))
    candidates.extend(
        circle for circle in (
            circle_three(a, b, c) for a, b, c in itertools.combinations(points, 3)
        ) if circle is not None
    )
    covering = [
        circle for circle in candidates
        if all(math.dist(point, circle[0]) <= circle[1] + ORACLE_TOL for point in points)
    ]
    return min(covering, key=lambda item: item[1])


def outer_from_boxes(boxes, observation_revision="obs", geometry_revision="geo", budget=False):
    boxes = tuple(boxes)
    diagnostics = OuterDiagnostics(
        retained_box_count=len(boxes), excluded_box_count=0, split_count=0,
        max_depth_reached=0, budget_exhausted=budget,
        exclusion_reason_counts={},
    )
    return OuterResult(boxes, diagnostics, observation_revision, geometry_revision)


def point_outer(points, revision="obs"):
    return outer_from_boxes(
        [Box(x, x, y, y) for x, y in points], revision, "geo-" + revision,
    )


def detected_state(channel=1):
    state = Q3State()
    response = normalize_response(
        ActionKind.MEASURE,
        {"accepted": True, "virtual_time_s": 1.0, "measure_result": "direction", "svd_deg": 0.0},
        channel=channel, position=(0.0, 0.0), request_id="detected",
    )
    state.apply_measure(response)
    return state


class TestMECClassics(unittest.TestCase):
    def test_m01_empty_and_single_point(self):
        self.assertIsNone(minimum_enclosing_circle([]))
        circle = minimum_enclosing_circle([(3.0, -4.0)])
        self.assertEqual(circle.center, (3.0, -4.0))
        self.assertEqual(circle.radius, 0.0)

    def test_m02_two_points(self):
        circle = minimum_enclosing_circle([(0.0, 0.0), (6.0, 8.0)])
        self.assertEqual(circle.center, (3.0, 4.0))
        self.assertEqual(circle.radius, 5.0)

    def test_m03_three_collinear_points(self):
        circle = minimum_enclosing_circle([(-5.0, 0.0), (1.0, 0.0), (7.0, 0.0)])
        self.assertAlmostEqual(circle.center[0], 1.0)
        self.assertAlmostEqual(circle.radius, 6.0)

    def test_m04_right_triangle(self):
        circle = minimum_enclosing_circle([(0.0, 0.0), (6.0, 0.0), (0.0, 8.0)])
        self.assertAlmostEqual(circle.center[0], 3.0)
        self.assertAlmostEqual(circle.center[1], 4.0)
        self.assertAlmostEqual(circle.radius, 5.0)

    def test_m05_equilateral_triangle(self):
        points = [(0.0, 0.0), (40.0, 0.0), (20.0, 20.0 * math.sqrt(3.0))]
        circle = minimum_enclosing_circle(points)
        self.assertAlmostEqual(circle.radius, 40.0 / math.sqrt(3.0), places=10)

    def test_m06_duplicates_do_not_change_result(self):
        base = minimum_enclosing_circle([(0.0, 0.0), (10.0, 0.0)])
        duplicate = minimum_enclosing_circle([(0.0, 0.0), (10.0, 0.0), (0.0, 0.0), (10.0, 0.0)])
        self.assertEqual(base, duplicate)

    def test_m07_nearly_collinear_is_finite_and_containing(self):
        points = [(-10.0, 0.0), (0.0, 1.0e-12), (10.0, 0.0), (3.0, -1.0e-12)]
        circle = minimum_enclosing_circle(points)
        self.assertTrue(all(math.isfinite(value) for value in (*circle.center, circle.radius)))
        self.assertTrue(all(math.dist(point, circle.center) <= circle.radius + EPS_MEC for point in points))

    def test_independent_oracle_500_random_small_sets(self):
        rng = random.Random(2026091205)
        max_radius_error = 0.0
        max_containment_excess = 0.0
        for case in range(500):
            points = [
                (rng.uniform(-1800.0, 1800.0), rng.uniform(-1800.0, 1800.0))
                for _ in range(rng.randint(1, 8))
            ]
            production = minimum_enclosing_circle(points)
            oracle_center, oracle_radius = brute_force_mec(points)
            radius_error = abs(production.radius - oracle_radius)
            containment_excess = max(math.dist(point, production.center) - production.radius for point in points)
            max_radius_error = max(max_radius_error, radius_error)
            max_containment_excess = max(max_containment_excess, containment_excess)
            self.assertLessEqual(radius_error, EPS_MEC, msg=f"case={case}")
            self.assertLessEqual(containment_excess, EPS_MEC, msg=f"case={case}")
        self.assertLessEqual(max_radius_error, EPS_MEC)
        self.assertLessEqual(max_containment_excess, EPS_MEC)


class TestClearCertificate(unittest.TestCase):
    @staticmethod
    def certificate_with_upper(target):
        radius = target - EPS_MEC
        return certificate_from_outer(point_outer([(-radius, 0.0), (radius, 0.0)], revision=f"r{target}"))

    def test_c07_operational_boundaries(self):
        below = self.certificate_with_upper(16.99)
        boundary = self.certificate_with_upper(17.0)
        above = self.certificate_with_upper(17.01)
        self.assertAlmostEqual(below.r_upper, 16.99, places=12)
        self.assertTrue(below.operational_clearable)
        self.assertAlmostEqual(boundary.r_upper, 17.0, places=12)
        self.assertTrue(boundary.operational_clearable)
        self.assertFalse(above.operational_clearable)

    def test_raw_mec_below_17_but_upper_above_is_not_clearable(self):
        radius = 16.9999
        certificate = certificate_from_outer(point_outer([(-radius, 0.0), (radius, 0.0)]))
        self.assertLess(certificate.r_mec, 17.0)
        self.assertGreater(certificate.r_upper, 17.0)
        self.assertFalse(certificate.operational_clearable)

    def test_physical_only_certificate_does_not_authorize_scheduler(self):
        radius = 18.0
        state = detected_state()
        outer = point_outer(
            [(-radius, 0.0), (radius, 0.0)],
            revision=state.channels[1].geometry_history.revision,
        )
        certificate = certificate_from_outer(outer)
        self.assertTrue(certificate.physical_clearable)
        self.assertFalse(certificate.operational_clearable)
        self.assertFalse(bind_clear_certificate(state, 1, outer, certificate))
        action = CoverageScheduler().next_action(state)
        self.assertEqual(action.action_type, ActionType.MEASURE)

    def test_c08_equilateral_diameter_40_not_clear_ready(self):
        points = [(0.0, 0.0), (40.0, 0.0), (20.0, 20.0 * math.sqrt(3.0))]
        certificate = certificate_from_outer(point_outer(points))
        diameter = max(math.dist(a, b) for a, b in itertools.combinations(points, 2))
        self.assertAlmostEqual(diameter, 40.0)
        self.assertAlmostEqual(certificate.r_mec, 40.0 / math.sqrt(3.0), places=10)
        self.assertFalse(certificate.operational_clearable)
        self.assertFalse(certificate.physical_clearable)

    def test_empty_outer_is_invalid_not_zero_radius(self):
        certificate = certificate_from_outer(outer_from_boxes([]))
        self.assertEqual(certificate.status, CertificateStatus.OUTER_EMPTY_INVALID)
        self.assertIsNone(certificate.r_mec)
        self.assertIsNone(certificate.r_upper)
        self.assertFalse(certificate.operational_clearable)

    def test_all_box_corners_are_used_and_interior_is_covered(self):
        rng = random.Random(2026091206)
        for case in range(100):
            boxes = []
            for _ in range(rng.randint(1, 12)):
                xmin = rng.uniform(-100.0, 80.0)
                ymin = rng.uniform(-100.0, 80.0)
                boxes.append(Box(xmin, xmin + rng.uniform(0.0, 20.0), ymin, ymin + rng.uniform(0.0, 20.0)))
            certificate = certificate_from_outer(outer_from_boxes(boxes))
            self.assertEqual(certificate.corner_count, 4 * len(boxes))
            self.assertEqual(certificate.diagnostics["corner_source"], "all retained box corners")
            for box in boxes:
                for _ in range(20):
                    point = (rng.uniform(box.xmin, box.xmax), rng.uniform(box.ymin, box.ymax))
                    self.assertLessEqual(math.dist(point, certificate.center), certificate.r_upper)

    def test_budget_exhausted_coarse_outer_still_has_safe_certificate(self):
        outer = rebuild_outer_from_observations(
            ObservationHistory(), max_depth=8, max_boxes=100,
            split_budget=0,
        )
        self.assertTrue(outer.diagnostics.budget_exhausted)
        certificate = certificate_from_outer(outer)
        self.assertEqual(certificate.status, CertificateStatus.CERTIFIED)
        self.assertTrue(certificate.diagnostics["outer_budget_exhausted"])
        self.assertFalse(certificate.operational_clearable)
        self.assertTrue(all(math.dist(corner, certificate.center) <= certificate.r_upper for corner in outer.boxes[0].corners))

    def test_stale_certificate_rejected_then_recomputed(self):
        state = detected_state()
        channel_state = state.channels[1]
        old_outer = point_outer(
            [(-1.0, 0.0), (1.0, 0.0)],
            revision=channel_state.geometry_history.revision,
        )
        old_certificate = certificate_from_outer(old_outer)
        self.assertTrue(bind_clear_certificate(state, 1, old_outer, old_certificate))
        self.assertTrue(certificate_is_current(state, 1))

        new_observation = normalize_response(
            ActionKind.MEASURE,
            {"accepted": True, "virtual_time_s": 2.0, "measure_result": "direction", "svd_deg": 1.0},
            channel=1, position=(10.0, 0.0), request_id="new-observation",
        )
        state.apply_measure(new_observation)
        self.assertFalse(certificate_is_current(state, 1))
        self.assertNotEqual(state.channels[1].status, ChannelStatus.CLEAR_READY)

        new_outer = point_outer(
            [(0.0, 0.0), (2.0, 0.0)],
            revision=state.channels[1].geometry_history.revision,
        )
        new_certificate = certificate_from_outer(new_outer)
        self.assertTrue(bind_clear_certificate(state, 1, new_outer, new_certificate))
        self.assertTrue(certificate_is_current(state, 1))

    def test_unknown_execution_invalidates_certificate(self):
        state = detected_state()
        channel_state = state.channels[1]
        outer = point_outer([(0.0, 0.0)], revision=channel_state.geometry_history.revision)
        certificate = certificate_from_outer(outer)
        self.assertTrue(bind_clear_certificate(state, 1, outer, certificate))
        from q3_improved.protocol import unknown_response
        unknown = unknown_response(
            ActionKind.MEASURE, channel=1, position=(1.0, 1.0),
            request_id="unknown",
        )
        state.apply_measure(unknown)
        self.assertEqual(state.channels[1].status, ChannelStatus.RECOVERY)
        self.assertFalse(certificate_is_current(state, 1))

    def test_near_current_position_has_priority_over_mec(self):
        state = detected_state(channel=1)
        channel_state = state.channels[1]
        outer = point_outer([(100.0, 0.0)], revision=channel_state.geometry_history.revision)
        certificate = certificate_from_outer(outer)
        self.assertTrue(bind_clear_certificate(state, 1, outer, certificate))
        near = normalize_response(
            ActionKind.MEASURE,
            {"accepted": True, "virtual_time_s": 2.0, "measure_result": "near"},
            channel=2, position=(7.0, 8.0), request_id="near",
        )
        state.apply_measure(near)
        action = CoverageScheduler().next_action(state)
        self.assertEqual(action.channel, 2)
        self.assertEqual(action.position, (7.0, 8.0))

    def test_certified_clear_failure_records_contradiction(self):
        state = detected_state()
        channel_state = state.channels[1]
        outer = point_outer([(0.0, 0.0)], revision=channel_state.geometry_history.revision)
        certificate = certificate_from_outer(outer)
        self.assertTrue(bind_clear_certificate(state, 1, outer, certificate))
        failure = normalize_response(
            ActionKind.CLEAR,
            {"accepted": True, "virtual_time_s": 2.0, "clear_result": "no_target_in_range"},
            channel=1, position=certificate.center, request_id="failed-certified-clear",
        )
        state.apply_clear(failure)
        self.assertEqual(state.channels[1].status, ChannelStatus.RECOVERY)
        self.assertEqual(state.channels[1].recovery_history[-1]["status"], "CERTIFIED_CLEAR_CONTRADICTION")
        self.assertIs(state.channels[1].recovery_history[-1]["certificate"], certificate)
        self.assertIs(state.channels[1].recovery_history[-1]["outer"], outer)


class TestOuterCertificateMonteCarlo(unittest.TestCase):
    def test_1000_true_sources_covered_and_operational_claims_safe(self):
        rng = random.Random(2026091207)
        operational_count = 0
        for case in range(1000):
            source_radius = 1800.0 * math.sqrt(rng.random())
            source_angle = rng.uniform(-math.pi, math.pi)
            source = (source_radius * math.cos(source_angle), source_radius * math.sin(source_angle))
            fixed_radius = rng.choice([1000.0, rng.uniform(1000.0, 1500.0), 1500.0])
            direction_distance = rng.uniform(5.01, fixed_radius)
            direction_angle = rng.uniform(-math.pi, math.pi)
            direction_station = (
                source[0] + direction_distance * math.cos(direction_angle),
                source[1] + direction_distance * math.sin(direction_angle),
            )
            true_bearing = math.degrees(math.atan2(
                source[1] - direction_station[1],
                source[0] - direction_station[0],
            )) % 360.0
            measured_bearing = (true_bearing + rng.uniform(-0.95, 0.95)) % 360.0
            negative_distance = fixed_radius + rng.uniform(0.01, 500.0)
            negative_angle = rng.uniform(-math.pi, math.pi)
            negative_station = (
                source[0] + negative_distance * math.cos(negative_angle),
                source[1] + negative_distance * math.sin(negative_angle),
            )
            near_distance = rng.uniform(0.0, 4.99)
            near_angle = rng.uniform(-math.pi, math.pi)
            near_station = (
                source[0] + near_distance * math.cos(near_angle),
                source[1] + near_distance * math.sin(near_angle),
            )
            observations = ObservationHistory((
                DirectionObservation(direction_station, measured_bearing),
                NoSignalObservation(negative_station),
                NearObservation(near_station),
            ))
            outer = rebuild_outer_from_observations(
                observations, max_depth=9, max_boxes=5000,
                split_budget=5000,
            )
            certificate = certificate_from_outer(outer)
            self.assertEqual(certificate.status, CertificateStatus.CERTIFIED, msg=f"case={case}")
            self.assertLessEqual(math.dist(source, certificate.center), certificate.r_upper, msg=f"case={case}")
            if certificate.operational_clearable:
                operational_count += 1
                self.assertLessEqual(math.dist(source, certificate.center), 17.0, msg=f"case={case}")
        self.assertGreater(operational_count, 0)


if __name__ == "__main__":
    unittest.main()
