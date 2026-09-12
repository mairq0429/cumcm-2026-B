import json
import os
import sys
import tempfile
import unittest


SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import q2_m6_1440_validation as validation  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
