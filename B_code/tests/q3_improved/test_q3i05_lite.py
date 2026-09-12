import math
import tempfile
import unittest
from pathlib import Path

from q3_improved.conservative_geometry import Box
from q3_improved.fallback import GRID_H, build_fallback_candidates
from q3_improved.protocol import ActionKind, ClearResult, MeasureResult, normalize_response
from q3_improved.runner import P0Runner
from q3_improved.scheduler import CoverageScheduler
from q3_improved.state import ChannelStatus, Q3State


class FallbackTests(unittest.TestCase):
    def test_intersection_edge_and_corner_are_retained(self):
        b = Box(0.0, GRID_H, 0.0, GRID_H)
        # Closed-cell intersection retains all 3x3 cells touching the square.
        self.assertEqual(len(build_fallback_candidates([b])), 9)
        edge = Box(GRID_H, GRID_H * 2, 0.0, GRID_H)
        corner = Box(GRID_H * 2, GRID_H * 3, GRID_H, GRID_H * 2)
        ids = {c.cell_id for c in build_fallback_candidates([edge, corner])}
        self.assertIn((1, 0), ids)
        self.assertIn((2, 1), ids)

    def test_separated_box_dropped(self):
        candidates = build_fallback_candidates([Box(10 * GRID_H + 0.1, 10 * GRID_H + 0.2, 10 * GRID_H + 0.1, 10 * GRID_H + 0.2)])
        self.assertEqual(len(candidates), 1)
        self.assertNotIn((0, 0), {c.cell_id for c in candidates})

    def test_cell_center_bound(self):
        for candidate in build_fallback_candidates([Box(-GRID_H, GRID_H, -GRID_H, GRID_H)]):
            ix, iy = candidate.cell_id
            corner = (ix * GRID_H, iy * GRID_H)
            self.assertLessEqual(math.dist(corner, candidate.center), 17.0 + 1e-12)


class _SyntheticAdapter:
    def __init__(self):
        self.first = True
        self.clear_calls = 0

    def enter(self):
        return normalize_response(ActionKind.ENTER, {"accepted": True, "virtual_time_s": 0.0})

    def measure(self, x, y, channel):
        if self.first and channel == 1 and abs(x) < 1e-9 and abs(y) < 1e-9:
            self.first = False
            raw = {"accepted": True, "measure_result": "direction", "svd_deg": 0.0, "virtual_time_s": 1.0}
        else:
            raw = {"accepted": True, "measure_result": "no_signal", "virtual_time_s": 1.0}
        return normalize_response(ActionKind.MEASURE, raw, channel=channel, position=(x, y))

    def clear(self, x, y, channel):
        self.clear_calls += 1
        return normalize_response(ActionKind.CLEAR, {"accepted": True, "clear_result": "success", "virtual_time_s": 2.0}, channel=channel, position=(x, y))

    def exit(self):
        return normalize_response(ActionKind.EXIT, {"accepted": True, "virtual_time_s": 2.0})


class RunnerIntegrationTests(unittest.TestCase):
    def test_coverage_precedes_fallback_and_synthetic_terminal(self):
        adapter = _SyntheticAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            state = P0Runner(adapter, journal_path=Path(tmp) / "actions.jsonl", max_actions=500).run()
            self.assertEqual(state.channels[1].status, ChannelStatus.CLEARED)
            self.assertTrue(state.terminal())
            self.assertGreaterEqual(adapter.clear_calls, 1)
            self.assertTrue((Path(tmp) / "actions.jsonl").exists())

    def test_scheduler_does_not_fallback_before_coverage(self):
        state = Q3State()
        action = CoverageScheduler().next_action(state)
        self.assertEqual(action.action_type.value, "measure")
