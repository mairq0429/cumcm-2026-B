import copy
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError


SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from q1_localization import wedge_halfplanes  # noqa: E402
from q3_improved.adapter import SimulatorAdapter  # noqa: E402
from q3_improved.config import ARENA_R, COVERAGE_RING_R, N_CHANNELS  # noqa: E402
from q3_improved.coverage import coverage_nodes  # noqa: E402
from q3_improved.protocol import (  # noqa: E402
    ActionKind,
    ClearResult,
    ExecutionStatus,
    MeasureResult,
    normalize_response,
    unknown_response,
)
from q3_improved.replay import replay_console_files  # noqa: E402
from q3_improved.scheduler import ActionType, CoverageScheduler  # noqa: E402
from q3_improved.state import ChannelStatus, Q3State  # noqa: E402


def measure_response(channel, result, node, virtual_time=10.0, direction=None, accepted=True):
    raw = {"accepted": accepted, "virtual_time_s": virtual_time}
    if accepted:
        raw["measure_result"] = result
        if direction is not None:
            raw["svd_deg"] = direction
    return normalize_response(
        ActionKind.MEASURE,
        raw,
        channel=channel,
        position=coverage_nodes()[node],
        request_id=f"m-{channel}-{node}-{result}",
    )


def clear_response(channel, result, virtual_time=20.0, position=(1.0, 2.0), accepted=True):
    raw = {"accepted": accepted, "virtual_time_s": virtual_time}
    if accepted:
        raw["clear_result"] = result
    return normalize_response(
        ActionKind.CLEAR, raw, channel=channel, position=position,
        request_id=f"c-{channel}-{result}",
    )


class TestCoverageGeometry(unittest.TestCase):
    def test_new_seven_node_coordinates(self):
        nodes = coverage_nodes()
        self.assertEqual(len(nodes), 7)
        self.assertEqual(nodes[0], (0.0, 0.0))
        for point in nodes[1:]:
            self.assertAlmostEqual(math.hypot(*point), COVERAGE_RING_R, places=9)
            self.assertLess(math.hypot(*point), ARENA_R)
        for index in range(6):
            self.assertAlmostEqual(
                math.dist(nodes[1 + index], nodes[1 + (index + 1) % 6]),
                COVERAGE_RING_R,
                places=9,
            )

    def test_dense_grid_sampled_cover_radius(self):
        nodes = coverage_nodes()
        sampled_max = 0.0
        step = 10.0
        limit = int(ARENA_R / step)
        for ix in range(-limit, limit + 1):
            x = ix * step
            ymax = math.sqrt(max(0.0, ARENA_R * ARENA_R - x * x))
            iymax = int(ymax / step)
            for iy in range(-iymax, iymax + 1):
                point = (x, iy * step)
                sampled_max = max(sampled_max, min(math.dist(point, node) for node in nodes))
        self.assertLessEqual(sampled_max, 900.0 + 1.0e-9)

    def test_c01_improved_direction_uses_verified_wraparound_wedge(self):
        response = measure_response(1, "direction", 0, direction=359.5)
        self.assertEqual(response.measure_result, MeasureResult.DIRECTION)
        halfplanes = wedge_halfplanes(0.0, 0.0, response.direction_deg)
        true_point = (100.0, 0.0)
        opposite = (-100.0, 0.0)
        inside = lambda point: all(a * point[0] + b * point[1] <= c + 1e-10 for a, b, c in halfplanes)
        self.assertTrue(inside(true_point))
        self.assertFalse(inside(opposite))


class TestStateAndCoverage(unittest.TestCase):
    def setUp(self):
        self.state = Q3State()

    def _commit_negative(self, channel, node):
        self.assertTrue(self.state.apply_measure(measure_response(channel, "no_signal", node), node))

    def test_s01_accepted_false_commits_nothing(self):
        before_position = self.state.position
        before_receiver = self.state.receiver_channel
        before_time = self.state.virtual_time
        before_channels = copy.deepcopy(self.state.channels)
        before_coverage = self.state.coverage.records_for(1)
        response = measure_response(1, "no_signal", 0, virtual_time=0.0, accepted=False)
        self.assertFalse(self.state.apply_measure(response, 0))
        self.assertEqual(self.state.position, before_position)
        self.assertEqual(self.state.receiver_channel, before_receiver)
        self.assertEqual(self.state.virtual_time, before_time)
        self.assertEqual(self.state.channels, before_channels)
        self.assertEqual(self.state.coverage.records_for(1), before_coverage)

    def test_s02_one_negative_is_unknown_c02(self):
        self._commit_negative(1, 0)
        self.assertEqual(self.state.channels[1].status, ChannelStatus.UNKNOWN)

    def test_s03_six_negatives_are_unknown(self):
        for node in range(6):
            self._commit_negative(1, node)
        self.assertEqual(self.state.channels[1].status, ChannelStatus.UNKNOWN)

    def test_s04_seven_negatives_certify_absence_c03(self):
        for node in range(7):
            self._commit_negative(1, node)
        self.assertEqual(self.state.channels[1].status, ChannelStatus.ABSENT_CERTIFIED)
        self.assertTrue(self.state.absent_certified(1))

    def test_s05_six_negative_and_one_direction_is_detected(self):
        for node in range(6):
            self._commit_negative(1, node)
        self.state.apply_measure(measure_response(1, "direction", 6, direction=20.0), 6)
        self.assertEqual(self.state.channels[1].status, ChannelStatus.DETECTED)
        self.assertFalse(self.state.absent_certified(1))

    def test_s06_positive_evidence_permanently_forbids_absence(self):
        self.state.apply_measure(measure_response(1, "direction", 0, direction=20.0), 0)
        for node in range(7):
            self._commit_negative(1, node)
        self.assertTrue(self.state.channels[1].positive_evidence)
        self.assertEqual(self.state.channels[1].status, ChannelStatus.DETECTED)
        self.assertFalse(self.state.absent_certified(1))

    def test_s07_near_is_clear_ready_and_same_point_next_c06(self):
        response = measure_response(2, "near", 3, virtual_time=12.0)
        self.state.apply_measure(response, 3)
        self.assertEqual(self.state.channels[2].status, ChannelStatus.CLEAR_READY)
        action = CoverageScheduler().next_action(self.state)
        self.assertEqual(action.action_type, ActionType.CLEAR)
        self.assertEqual(action.position, response.position)
        self.assertEqual(action.channel, 2)

    def test_s08_clear_success_is_cleared(self):
        self.state.apply_measure(measure_response(2, "direction", 0, direction=5.0), 0)
        self.state.apply_clear(clear_response(2, "success"))
        self.assertEqual(self.state.channels[2].status, ChannelStatus.CLEARED)

    def test_s09_detected_no_target_guard_allowed(self):
        self.state.apply_measure(measure_response(2, "direction", 0, direction=5.0), 0)
        response = clear_response(2, "no_target_in_range")
        self.state.apply_clear(response)
        self.assertNotEqual(self.state.channels[2].status, ChannelStatus.CLEARED)
        self.assertEqual(self.state.channels[2].status, ChannelStatus.RECOVERY)
        self.assertTrue(self.state.may_add_clear_distance_exclusion(response))

    def test_s10_unknown_no_target_guard_forbidden(self):
        response = clear_response(2, "no_target_in_range")
        self.state.apply_clear(response)
        self.assertFalse(self.state.may_add_clear_distance_exclusion(response))

    def test_s11_unknown_execution_enters_recovery_without_speculative_commit(self):
        before_position = self.state.position
        before_receiver = self.state.receiver_channel
        before_time = self.state.virtual_time
        before_observations = list(self.state.channels[3].observations)
        before_coverage = self.state.coverage.records_for(3)
        response = unknown_response(
            ActionKind.MEASURE, channel=3, position=coverage_nodes()[2],
            request_id="measure-unknown", error="timeout",
        )
        self.assertFalse(self.state.apply_measure(response, 2))
        self.assertEqual(self.state.channels[3].status, ChannelStatus.RECOVERY)
        self.assertEqual(self.state.position, before_position)
        self.assertEqual(self.state.receiver_channel, before_receiver)
        self.assertEqual(self.state.virtual_time, before_time)
        self.assertEqual(self.state.channels[3].observations, before_observations)
        self.assertEqual(self.state.coverage.records_for(3), before_coverage)

    def test_s12_terminal_at_exactly_sixteen_cleared(self):
        for channel in range(1, 17):
            self.state.channels[channel].status = ChannelStatus.CLEARED
        self.assertTrue(self.state.terminal())

    def test_s13_ten_cleared_not_terminal(self):
        for channel in range(1, 11):
            self.state.channels[channel].status = ChannelStatus.CLEARED
        self.assertFalse(self.state.terminal())

    def test_s14_all_channels_terminal(self):
        for channel in range(1, N_CHANNELS + 1):
            self.state.channels[channel].status = (
                ChannelStatus.CLEARED if channel % 2 else ChannelStatus.ABSENT_CERTIFIED
            )
        self.assertTrue(self.state.terminal())

    def test_s15_one_unknown_prevents_all_terminal(self):
        for channel in range(1, N_CHANNELS):
            self.state.channels[channel].status = ChannelStatus.ABSENT_CERTIFIED
        self.assertFalse(self.state.terminal())

    def test_s16_direction_completes_fixed_node(self):
        self.state.apply_measure(measure_response(1, "direction", 2, direction=1.0), 2)
        self.assertTrue(self.state.coverage.get(1, 2).completed)

    def test_s17_near_completes_fixed_node(self):
        self.state.apply_measure(measure_response(1, "near", 2), 2)
        self.assertTrue(self.state.coverage.get(1, 2).completed)

    def test_s18_rejected_fixed_node_does_not_complete(self):
        self.state.apply_measure(measure_response(1, "no_signal", 2, accepted=False), 2)
        self.assertFalse(self.state.coverage.get(1, 2).completed)

    def test_scheduler_starts_at_center_and_skips_terminal_channels(self):
        self.state.channels[1].status = ChannelStatus.CLEARED
        action = CoverageScheduler().next_action(self.state)
        self.assertEqual(action.position, (0.0, 0.0))
        self.assertEqual(action.coverage_node, 0)
        self.assertEqual(action.channel, 2)

    def test_scheduler_completes_nodes_in_c_v0_through_v5_order(self):
        scheduler = CoverageScheduler()
        actions = []
        while True:
            action = scheduler.next_action(self.state)
            if action is None:
                break
            self.assertEqual(action.action_type, ActionType.MEASURE)
            actions.append(action)
            response = normalize_response(
                ActionKind.MEASURE,
                {"accepted": True, "virtual_time_s": float(len(actions)), "measure_result": "no_signal"},
                channel=action.channel,
                position=action.position,
                request_id=f"route-{len(actions)}",
            )
            self.state.apply_measure(response, action.coverage_node)
        self.assertEqual(len(actions), 140)
        for node, point in enumerate(coverage_nodes()):
            block = actions[node * 20:(node + 1) * 20]
            self.assertTrue(all(action.coverage_node == node and action.position == point for action in block))
        self.assertEqual([action.channel for action in actions[:20]], list(range(1, 21)))
        self.assertEqual([action.channel for action in actions[20:40]], list(range(20, 0, -1)))


class TestProtocolAndReplay(unittest.TestCase):
    class _Response:
        status = 200

        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return self.body

    def test_adapter_preserves_confirmed_rejection(self):
        body = b'{"accepted":false,"real_timestamp_ms":1,"virtual_time_s":0}'
        with patch("q3_improved.adapter.urlopen", return_value=self._Response(body)):
            response = SimulatorAdapter("team").measure(1.0, 2.0, 3)
        self.assertEqual(response.execution, ExecutionStatus.REJECTED)
        self.assertFalse(response.accepted)
        self.assertEqual(response.raw_response["virtual_time_s"], 0)
        self.assertIsNone(response.virtual_time)

    def test_adapter_transport_failure_is_unknown_and_keeps_request_id(self):
        with patch("q3_improved.adapter.urlopen", side_effect=URLError("lost")):
            response = SimulatorAdapter("team").measure(1.0, 2.0, 3)
        self.assertEqual(response.execution, ExecutionStatus.UNKNOWN_EXECUTION_STATE)
        self.assertEqual(response.request_id, "measure-0001")
        self.assertIsNone(response.accepted)

    def test_normalization_preserves_raw_fields(self):
        raw = {"accepted": True, "virtual_time_s": 12.5, "measure_result": "direction", "svd_deg": 33.2}
        response = normalize_response(ActionKind.MEASURE, raw, channel=4, position=(1.0, 2.0), request_id="m-1")
        self.assertEqual(response.raw_response, raw)
        self.assertEqual(response.raw_result, "direction")
        self.assertEqual(response.direction_deg, 33.2)
        self.assertEqual(response.virtual_time, 12.5)

    def test_unknown_wire_clear_value_is_other_failure(self):
        response = clear_response(1, "future_known_failure")
        self.assertEqual(response.raw_result, "future_known_failure")
        self.assertEqual(response.clear_result, ClearResult.OTHER_FAILURE)

    def test_console_replay_normalizes_selective_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "a.txt"
            second = Path(directory) / "b.txt"
            first.write_text("result=success\nresult=no_target_in_range\n", encoding="utf-8")
            second.write_text("result=success\n", encoding="utf-8")
            summary = replay_console_files([first, second])
        self.assertEqual(summary.success_count, 2)
        self.assertEqual(summary.no_target_in_range_count, 1)
        self.assertIn("not raw wire", summary.evidence_source)
        self.assertEqual(summary.request_ids, "NOT_CHECKABLE")

    def test_historical_console_replay_counts(self):
        project_root = Path(__file__).resolve().parents[3]
        paths = [
            project_root / "03_results" / "stress_test" / "q3" / f"Q3-S-{index:03d}" / "console_output.txt"
            for index in range(1, 6)
        ]
        if not all(path.is_file() for path in paths):
            self.skipTest("historical console artifacts are not present")
        summary = replay_console_files(paths)
        self.assertEqual(summary.success_count, 65)
        self.assertEqual(summary.no_target_in_range_count, 3)
        self.assertEqual(summary.raw_response_completeness, "NOT_CHECKABLE")
        self.assertEqual(summary.duplicate_commit_semantics, "NOT_CHECKABLE")


if __name__ == "__main__":
    unittest.main()
