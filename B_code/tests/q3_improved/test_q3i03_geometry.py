import math
import os
import random
import sys
import unittest


SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from q3_improved.conservative_geometry import (  # noqa: E402
    Box,
    BoxStatus,
    ExclusionReason,
    classify_box,
    dist_hi,
    dist_lo,
    fixed_radius_interval_at_point,
    rebuild_outer_from_observations,
)
from q3_improved.observations import (  # noqa: E402
    ClearNoTargetObservation,
    DirectionObservation,
    NearObservation,
    NoSignalObservation,
    ObservationHistory,
)
from q3_improved.protocol import ActionKind, normalize_response  # noqa: E402
from q3_improved.state import Q3State  # noqa: E402


def history(*records):
    return ObservationHistory(tuple(records))


def point_box(x, y):
    return Box(x, x, y, y)


class TestBoxPrimitives(unittest.TestCase):
    def test_box_value_operations_and_distances(self):
        box = Box(-1.0, 3.0, 2.0, 6.0)
        self.assertEqual(box.width, 4.0)
        self.assertEqual(box.height, 4.0)
        self.assertEqual(box.center, (1.0, 4.0))
        self.assertEqual(len(box.corners), 4)
        self.assertEqual(len(box.split4()), 4)
        self.assertEqual(dist_lo(box, (0.0, 0.0)), 2.0)
        self.assertAlmostEqual(dist_hi(box, (0.0, 0.0)), math.hypot(3.0, 6.0))

    def test_arena_boundary_kept_and_outside_excluded(self):
        self.assertEqual(classify_box(point_box(1800.0, 0.0), history()).status, BoxStatus.RETAINED_UNCERTAIN)
        result = classify_box(point_box(1800.01, 0.0), history())
        self.assertEqual(result.reason, ExclusionReason.OUTSIDE_ARENA)


class TestFixedRadiusPointFeasibility(unittest.TestCase):
    def test_c04_positive_distance_exactly_1500_is_feasible(self):
        observations = history(DirectionObservation((1500.0, 0.0), 180.0))
        interval = fixed_radius_interval_at_point((0.0, 0.0), observations)
        self.assertEqual(interval.lower, 1500.0)
        self.assertTrue(interval.feasible)

    def test_positive_distance_over_1500_is_infeasible(self):
        observations = history(DirectionObservation((1500.01, 0.0), 180.0))
        self.assertFalse(fixed_radius_interval_at_point((0.0, 0.0), observations).feasible)

    def test_c05_shared_fixed_radius_conflict(self):
        observations = history(
            DirectionObservation((1400.0, 0.0), 180.0),
            NoSignalObservation((0.0, 1200.0)),
        )
        interval = fixed_radius_interval_at_point((0.0, 0.0), observations)
        self.assertEqual(interval.lower, 1400.0)
        self.assertEqual(interval.negative_distance_limit, 1200.0)
        self.assertFalse(interval.feasible)

    def test_l_equal_d_is_infeasible(self):
        observations = history(
            DirectionObservation((1400.0, 0.0), 180.0),
            NoSignalObservation((0.0, 1400.0)),
        )
        self.assertFalse(fixed_radius_interval_at_point((0.0, 0.0), observations).feasible)

    def test_near_does_not_raise_radius_floor(self):
        interval = fixed_radius_interval_at_point(
            (0.0, 0.0), history(NearObservation((3.0, 4.0))),
        )
        self.assertEqual(interval.lower, 1000.0)
        self.assertTrue(interval.feasible)

    def test_random_point_interval_oracle_1000_cases(self):
        rng = random.Random(2026091203)
        for case in range(1000):
            point = (rng.uniform(-1800, 1800), rng.uniform(-1800, 1800))
            positives = [
                (rng.uniform(-2200, 2200), rng.uniform(-2200, 2200))
                for _ in range(rng.randrange(4))
            ]
            negatives = [
                (rng.uniform(-2200, 2200), rng.uniform(-2200, 2200))
                for _ in range(rng.randrange(4))
            ]
            observations = history(
                *(DirectionObservation(position, 0.0) for position in positives),
                *(NoSignalObservation(position) for position in negatives),
            )
            actual = fixed_radius_interval_at_point(point, observations)
            lower = max([1000.0, *(math.dist(point, item) for item in positives)])
            negative_limit = min((math.dist(point, item) for item in negatives), default=math.inf)
            independent = lower <= 1500.0 and lower < negative_limit
            self.assertEqual(actual.feasible, independent, msg=f"case={case}")


class TestWholeBoxExclusions(unittest.TestCase):
    def assertReason(self, box, observations, reason):
        result = classify_box(box, observations)
        self.assertEqual(result.status, BoxStatus.EXCLUDED)
        self.assertEqual(result.reason, reason)

    def test_direction_distance_boundaries(self):
        obs = history(DirectionObservation((0.0, 0.0), 0.0))
        self.assertEqual(classify_box(point_box(1500.0, 0.0), obs).status, BoxStatus.RETAINED_UNCERTAIN)
        self.assertReason(point_box(1500.01, 0.0), obs, ExclusionReason.DIRECTION_TOO_FAR)
        self.assertReason(point_box(5.0, 0.0), obs, ExclusionReason.DIRECTION_TOO_NEAR)
        self.assertEqual(classify_box(Box(4.9, 5.1, 0.0, 0.0), obs).status, BoxStatus.RETAINED_UNCERTAIN)

    def test_no_signal_minimum_radius_boundaries(self):
        obs = history(NoSignalObservation((0.0, 0.0)))
        self.assertReason(point_box(1000.0, 0.0), obs, ExclusionReason.NO_SIGNAL_MIN_RX)
        self.assertEqual(classify_box(Box(999.0, 1001.0, 0.0, 0.0), obs).status, BoxStatus.RETAINED_UNCERTAIN)

    def test_near_boundaries(self):
        obs = history(NearObservation((0.0, 0.0)))
        self.assertEqual(classify_box(point_box(5.0, 0.0), obs).status, BoxStatus.RETAINED_UNCERTAIN)
        self.assertReason(point_box(5.01, 0.0), obs, ExclusionReason.NEAR_MISS)

    def _guarded_clear_history(self):
        state = Q3State()
        detected = normalize_response(
            ActionKind.MEASURE,
            {"accepted": True, "virtual_time_s": 1.0, "measure_result": "direction", "svd_deg": 0.0},
            channel=1, position=(0.0, 0.0), request_id="m1",
        )
        state.apply_measure(detected)
        clear = normalize_response(
            ActionKind.CLEAR,
            {"accepted": True, "virtual_time_s": 2.0, "clear_result": "no_target_in_range"},
            channel=1, position=(0.0, 0.0), request_id="c1",
        )
        return ObservationHistory().commit_clear_no_target(state, clear)

    def test_clear_distance_boundaries_and_guard(self):
        with self.assertRaises(ValueError):
            ClearNoTargetObservation((0.0, 0.0))
        obs = self._guarded_clear_history()
        self.assertEqual(len(obs.clear_no_targets), 1)
        self.assertReason(point_box(20.0, 0.0), obs, ExclusionReason.CLEAR_DISTANCE)
        self.assertEqual(classify_box(Box(19.9, 20.1, 0.0, 0.0), obs).status, BoxStatus.RETAINED_UNCERTAIN)

    def test_channel_state_commits_immutable_geometry_history(self):
        state = Q3State()
        detected = normalize_response(
            ActionKind.MEASURE,
            {"accepted": True, "virtual_time_s": 1.0, "measure_result": "direction", "svd_deg": 0.0},
            channel=1, position=(0.0, 0.0), request_id="m1",
        )
        state.apply_measure(detected)
        first_history = state.channels[1].geometry_history
        clear = normalize_response(
            ActionKind.CLEAR,
            {"accepted": True, "virtual_time_s": 2.0, "clear_result": "no_target_in_range"},
            channel=1, position=(100.0, 0.0), request_id="c1",
        )
        state.apply_clear(clear)
        self.assertEqual(len(first_history.records), 1)
        self.assertEqual(len(state.channels[1].geometry_history.records), 2)
        self.assertIsInstance(state.channels[1].geometry_history.records[-1], ClearNoTargetObservation)

    def test_unknown_channel_clear_cannot_enter_history(self):
        state = Q3State()
        clear = normalize_response(
            ActionKind.CLEAR,
            {"accepted": True, "virtual_time_s": 2.0, "clear_result": "no_target_in_range"},
            channel=1, position=(0.0, 0.0), request_id="c1",
        )
        obs = ObservationHistory().commit_clear_no_target(state, clear)
        self.assertEqual(obs.records, ())

    def test_fixed_radius_whole_box_equality_and_ulp_ambiguity(self):
        exact = history(
            DirectionObservation((1400.0, 0.0), 180.0),
            NoSignalObservation((0.0, 1400.0)),
        )
        self.assertReason(point_box(0.0, 0.0), exact, ExclusionReason.FIXED_R_INCONSISTENT)
        just_above = math.nextafter(1400.0, math.inf)
        ambiguous = history(
            DirectionObservation((1400.0, 0.0), 180.0),
            NoSignalObservation((0.0, just_above)),
        )
        self.assertEqual(classify_box(point_box(0.0, 0.0), ambiguous).status, BoxStatus.RETAINED_UNCERTAIN)

    def test_c01_wraparound_box_classification(self):
        obs = history(DirectionObservation((0.0, 0.0), 359.5))
        angle = math.radians(359.5)
        true = (100.0 * math.cos(angle), 100.0 * math.sin(angle))
        retained = Box(true[0] - 0.01, true[0] + 0.01, true[1] - 0.01, true[1] + 0.01)
        self.assertEqual(classify_box(retained, obs).status, BoxStatus.RETAINED_UNCERTAIN)
        self.assertReason(Box(-110.0, -100.0, -1.0, 1.0), obs, ExclusionReason.DIRECTION_WEDGE)
        crossing = Box(100.0, 110.0, -3.0, 3.0)
        self.assertEqual(classify_box(crossing, obs).status, BoxStatus.RETAINED_UNCERTAIN)


class TestOuterRebuildSafety(unittest.TestCase):
    @staticmethod
    def random_source(rng):
        radius = 1800.0 * math.sqrt(rng.random())
        angle = rng.uniform(-math.pi, math.pi)
        return radius * math.cos(angle), radius * math.sin(angle)

    @staticmethod
    def offset(source, distance, angle):
        return source[0] + distance * math.cos(angle), source[1] + distance * math.sin(angle)

    def test_true_source_containment_1000_random_cases(self):
        rng = random.Random(2026091204)
        for case in range(1000):
            source = self.random_source(rng)
            radius = rng.choice([
                1000.0, math.nextafter(1000.0, math.inf),
                rng.uniform(1000.0, 1500.0),
                math.nextafter(1500.0, -math.inf), 1500.0,
            ])
            direction_distance = rng.uniform(5.01, radius)
            station_angle = rng.uniform(-math.pi, math.pi)
            station = self.offset(source, direction_distance, station_angle)
            true_bearing = math.degrees(math.atan2(source[1] - station[1], source[0] - station[0])) % 360.0
            measured = (true_bearing + rng.uniform(-0.95, 0.95)) % 360.0
            negative_station = self.offset(source, radius + rng.uniform(0.01, 500.0), rng.uniform(-math.pi, math.pi))
            near_station = self.offset(source, rng.uniform(0.0, 4.99), rng.uniform(-math.pi, math.pi))
            sequence = (
                DirectionObservation(station, measured),
                NoSignalObservation(negative_station),
                NearObservation(near_station),
            )
            observations = ObservationHistory()
            for step, record in enumerate(sequence):
                observations = ObservationHistory(observations.records + (record,))
                outer = rebuild_outer_from_observations(
                    observations, max_depth=4, max_boxes=2000,
                    split_budget=1000,
                )
                self.assertTrue(outer.contains(source), msg=f"case={case} step={step} source={source}")

    def test_rebuild_is_deterministic_and_budget_never_deletes(self):
        observations = history(DirectionObservation((0.0, 0.0), 0.0))
        first = rebuild_outer_from_observations(observations, max_depth=4, max_boxes=500, split_budget=100)
        second = rebuild_outer_from_observations(observations, max_depth=4, max_boxes=500, split_budget=100)
        self.assertEqual(first, second)
        exhausted = rebuild_outer_from_observations(ObservationHistory(), max_depth=8, max_boxes=100, split_budget=0)
        self.assertTrue(exhausted.diagnostics.budget_exhausted)
        self.assertEqual(exhausted.diagnostics.excluded_box_count, 0)
        self.assertEqual(exhausted.boxes, (Box(-1800.0, 1800.0, -1800.0, 1800.0),))

    def test_unconstrained_refinement_does_not_resurrect_excluded_points(self):
        base = rebuild_outer_from_observations(ObservationHistory(), max_depth=3, max_boxes=1000, split_budget=1000)
        constrained = rebuild_outer_from_observations(
            history(NearObservation((0.0, 0.0))),
            max_depth=3, max_boxes=1000, split_budget=1000,
        )
        samples = [(x, y) for x in range(-1800, 1801, 300) for y in range(-1800, 1801, 300)]
        for point in samples:
            if not base.contains(point):
                self.assertFalse(constrained.contains(point))


if __name__ == "__main__":
    unittest.main()
