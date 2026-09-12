import os
import sys
import unittest


SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from q2_m6_validation import (  # noqa: E402
    aggregate_t12,
    assess_candidate_convergence,
    assess_circle_sensitivity,
    assess_eps_cert_sensitivity,
    assess_lmin_sensitivity,
    preserve_risk_threshold_status,
)


def selected(x=10.0, jd=8.0, jr=4.0, t2=2.0, official=True):
    return {
        "S2": [x, 0.0], "JD": jd, "JR": jr, "JA": 3.0, "T2": t2,
        "official20": official, "operational17": official,
    }


class TestQ2M6AValidationLogic(unittest.TestCase):
    def test_T12_aggregation_requires_every_gate(self):
        gates = {key: "PASS" for key in (
            "circle", "source_error", "candidate", "gverify", "replay", "monotone"
        )}
        self.assertEqual(aggregate_t12(gates)["T12_status"], "PASS")
        gates["gverify"] = "UNRESOLVED"
        self.assertEqual(aggregate_t12(gates)["T12_status"], "UNRESOLVED")
        gates["gverify"] = "PASS"
        gates["circle"] = "CIRCLE_DISCRETIZATION_SENSITIVE"
        self.assertEqual(aggregate_t12(gates)["T12_status"], "FAIL")

    def test_circle_sensitivity_status_logic(self):
        base = {"selected": selected(), "C20_count": 2, "P1_area_bracket_m2": 0.01,
                "main_component_id": "A"}
        fine = {"selected": selected(jd=8.0004, jr=4.0002), "C20_count": 3,
                "P1_area_bracket_m2": 0.004, "main_component_id": "A"}
        self.assertEqual(assess_circle_sensitivity(base, fine)["status"], "PASS")
        fine["selected"] = selected(official=False)
        self.assertEqual(
            assess_circle_sensitivity(base, fine)["status"],
            "CIRCLE_DISCRETIZATION_SENSITIVE",
        )

    def test_eps_cert_sensitivity_status_logic(self):
        records = [
            {"selected": selected(), "main_component_id": "A",
             "certificate_status_counts": {"CERTIFIED_STRICT": 3, "UNCERTAIN_BOUNDARY": n}}
            for n in (0, 1, 2)
        ]
        self.assertEqual(
            assess_eps_cert_sensitivity(records)["status"],
            "STABLE_WITH_BOUNDARY_VARIATION",
        )
        records[-1]["selected"] = selected(x=30.0)
        self.assertEqual(
            assess_eps_cert_sensitivity(records)["status"], "EPS_REC_CERT_SENSITIVE"
        )

    def test_lmin_sensitivity_warning_logic(self):
        stable = [
            {"selected": selected(t2=value), "C20_count": 2}
            for value in (4.0, 10.0, 20.0, 30.0)
        ]
        self.assertEqual(assess_lmin_sensitivity(stable)["status"], "PASS")
        stable[-1]["selected"] = selected(jr=8.0)
        self.assertEqual(assess_lmin_sensitivity(stable)["status"], "LMIN_SENSITIVE")

    def test_candidate_convergence_logic(self):
        records = [
            {"grid_level_m": 20.0, "selected": selected(), "Fstrict_components": [{}]},
            {"grid_level_m": 5.0, "selected": selected(jd=8.0004, jr=4.0002, t2=2.0001),
             "Fstrict_components": [{}]},
        ]
        self.assertEqual(assess_candidate_convergence(records)["status"], "PASS")
        records[-1]["selected"] = selected(jd=10.0)
        self.assertEqual(
            assess_candidate_convergence(records)["status"], "CANDIDATE_GRID_SENSITIVE"
        )

    def test_final_risk_threshold_unresolved_remains_unresolved(self):
        coverage = {
            "alpha_099_status": "THRESHOLD_UNRESOLVED",
            "alpha_095_status": "CERTIFIED_ABOVE_ALPHA",
        }
        result = preserve_risk_threshold_status(coverage)
        self.assertEqual(result["alpha_099_status"], "THRESHOLD_UNRESOLVED")
        self.assertEqual(result["unresolved_count"], 1)


if __name__ == "__main__":
    unittest.main()
