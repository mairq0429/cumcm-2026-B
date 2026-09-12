import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace


SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import q2_m6_1440_validation as validation  # noqa: E402


class TestQ2M61440Validation(unittest.TestCase):
    def cell(self, name, center, bbox, status="UNRESOLVED"):
        return SimpleNamespace(cell_id=name, center=center, bbox=bbox,
                               certificate={"status": status}, boundary_flag=True)

    def test_level_checkpoint_writer_marks_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = validation.Path(directory) / "level_50.json"
            validation._write(path, {"grid_level_m": 50.0})
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["artifact_status"], validation.LABEL)

    def test_candidate_20_to_5_gate(self):
        a = {"best_C20": {"T2": 10.0, "JD": 8.0, "JR": 4.0}}
        b = {"best_C20": {"T2": 10.005, "JD": 8.004, "JR": 4.002}}
        self.assertEqual(validation.assess_20_to_5(a, b)["status"], "PASS")
        b["best_C20"]["JR"] = 5.0
        self.assertEqual(validation.assess_20_to_5(a, b)["status"], "CANDIDATE_GRID_SENSITIVE")

    def test_selected_independent_revalidation_gate(self):
        good = {
            "status": "PASS", "source_convergence": "PASS", "error_convergence": "PASS",
            "gverify": {"status": "PASS"},
            "replay": {name: {"status": "PASS"} for name in ("JD", "JR", "JA")},
            "warnings": [],
        }
        self.assertTrue(validation.selected_verification_pass(good))
        good["gverify"]["status"] = "FAIL"
        self.assertFalse(validation.selected_verification_pass(good))

    def test_final_result_cannot_use_missing_5m_level(self):
        result = validation.assess_20_to_5({"best_C20": {"T2": 1, "JD": 1, "JR": 1}}, {})
        self.assertEqual(result["status"], "UNRESOLVED")

    def test_unresolved_gate_empty_and_noncompetitive(self):
        selected = SimpleNamespace(T2=10.0)
        empty = validation.assess_unresolved_competitiveness([], selected, (0.0, 0.0))
        self.assertEqual(empty["status"], "PASS_NO_UNRESOLVED")
        far = self.cell("far", (100.0, 0.0), (99.0, -1.0, 101.0, 1.0))
        result = validation.assess_unresolved_competitiveness([far], selected, (0.0, 0.0))
        self.assertEqual(result["status"], "PASS_NONCOMPETITIVE_UNRESOLVED")
        self.assertFalse(result["cells"][0]["competitive"])

    def test_competitive_and_no_c20_unresolved_block(self):
        cell = self.cell("near", (50.0, 0.0), (47.0, -4.0, 53.0, 4.0))
        selected = SimpleNamespace(T2=10.0)
        result = validation.assess_unresolved_competitiveness([cell], selected, (0.0, 0.0))
        self.assertEqual(result["status"], "FAIL_UNRESOLVED_COMPETITIVE")
        self.assertTrue(result["cells"][0]["competitive"])
        no_c20 = validation.assess_unresolved_competitiveness([cell], None, (0.0, 0.0))
        self.assertEqual(no_c20["status"], "UNRESOLVED_NO_C20")

    def test_bbox_half_diagonal_and_t2_lower(self):
        cell = self.cell("geometry", (13.0, 0.0), (10.0, -4.0, 16.0, 4.0))
        record = validation.assess_unresolved_competitiveness(
            [cell], SimpleNamespace(T2=0.0), (0.0, 0.0)
        )["cells"][0]
        self.assertEqual(record["half_diagonal_m"], 5.0)
        self.assertEqual(record["T2_lower_s"], 1.6)

    def test_noncompetitive_unresolved_remains_uncertainty_geometry(self):
        cell = self.cell("far", (100.0, 0.0), (99.0, -1.0, 101.0, 1.0))
        validation.assess_unresolved_competitiveness([cell], SimpleNamespace(T2=1.0), (0.0, 0.0))
        features = validation._fstrict_features([cell])
        self.assertEqual(len(features), 1)
        self.assertEqual(features[0]["properties"]["representation"], "uncertainty_cell")

    def test_competitive_gate_blocks_otherwise_good_summary(self):
        gate = {"status": "FAIL_UNRESOLVED_COMPETITIVE"}
        self.assertFalse(validation.baseline_pass_gate(
            True, SimpleNamespace(T2=10.0), {"status": "PASS"}, True, gate
        ))


if __name__ == "__main__":
    unittest.main()
