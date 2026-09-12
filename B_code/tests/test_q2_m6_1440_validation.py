import json
import math
import os
import sys
import tempfile
import unittest


SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import q2_m6_1440_validation as validation  # noqa: E402


class DummyCell:
    def __init__(self, cell_id, center, bbox, status):
        self.cell_id = cell_id
        self.center = center
        self.bbox = bbox
        self.certificate = {"status": status}


class DummySelected:
    def __init__(self, T2, official20=True):
        self.T2 = T2
        self.official20 = official20


class TestQ2M61440Validation(unittest.TestCase):
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

    def test_unresolved_noncompetitive_passes(self):
        selected = DummySelected(T2=10.0)
        # Lower bound = (100 - sqrt(2)*2.5) / 5 > 10.01
        far = DummyCell("far", (100.0, 0.0), (97.5, -2.5, 102.5, 2.5), "UNRESOLVED")
        result = validation.assess_unresolved_competition([far], selected, (0.0, 0.0))
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["competitive_count"], 0)

    def test_unresolved_competitive_blocks(self):
        selected = DummySelected(T2=10.0)
        near = DummyCell("near", (50.0, 0.0), (47.5, -2.5, 52.5, 2.5), "UNRESOLVED")
        result = validation.assess_unresolved_competition([near], selected, (0.0, 0.0))
        self.assertEqual(result["status"], "UNRESOLVED_COMPETITIVE")
        self.assertEqual(result["competitive_cell_ids"], ["near"])

    def test_uncertain_boundary_is_also_gated(self):
        selected = DummySelected(T2=20.0)
        cell = DummyCell("u", (10.0, 0.0), (7.5, -2.5, 12.5, 2.5), "UNCERTAIN_BOUNDARY")
        result = validation.assess_unresolved_competition([cell], selected, (0.0, 0.0))
        self.assertEqual(result["status"], "UNRESOLVED_COMPETITIVE")

    def test_no_c20_makes_all_uncertain_competitive(self):
        cell = DummyCell("u", (1000.0, 0.0), (997.5, -2.5, 1002.5, 2.5), "UNRESOLVED")
        result = validation.assess_unresolved_competition([cell], None, (0.0, 0.0))
        self.assertEqual(result["status"], "UNRESOLVED_COMPETITIVE")
        self.assertEqual(result["competitive_count"], 1)


if __name__ == "__main__":
    unittest.main()
