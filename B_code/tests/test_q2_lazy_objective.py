import os
import sys
import unittest


SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from q2_selection import (  # noqa: E402
    CandidateResult, Q2Config, build_Gext, build_P1_bound,
    evaluate_candidate_nested, screen_candidate_c20, search_strict_candidates,
)


def strict_certificate(S2, P1, S1, config):
    return {
        "status": "CERTIFIED_STRICT", "strict_receive": True, "certified": True,
        "L_rec_m": -1.0, "U_rec_m": -0.5, "interval_width_m": 0.5,
        "eps_rec_cert_m": config.eps_rec_cert_m,
        "eps_rec_cert_source": "MODEL_FROZEN_CERTIFICATION_PRECISION",
        "cells_examined": 1, "counterexample": None, "reason": "synthetic",
    }


class FakeM4:
    def __init__(self, c20=True):
        self.calls = []
        self.c20 = c20

    def __call__(self, S2, S1, P1, config, certificate_override=None):
        point = tuple(S2)
        self.calls.append(point)
        jr = 4.0 + (0.001 if point[0] < 0 else 0.0)
        candidate = CandidateResult(
            S2=point, strict_receive=True, certificate=certificate_override or strict_certificate(point, P1, S1, config),
            T2=((point[0] ** 2 + point[1] ** 2) ** 0.5) / 5.0,
            JD=2.0 * jr, JR=jr, JA=1.0,
            official20=self.c20, operational17=self.c20,
            worst_scenarios={}, robust_guarantee=True, evaluation_status="CONVERGED",
        )
        return {"status": "PASS", "candidate": candidate}


class TestQ2LazyObjective(unittest.TestCase):
    def setUp(self):
        self.cfg = Q2Config(
            circle_sides=72, lmin_m=0.0,
            omega_move=((-100.0, -100.0), (100.0, -100.0), (100.0, 100.0), (-100.0, 100.0)),
        )

    def test_lazy_and_exhaustive_select_same_c20_and_preserve_region(self):
        lazy_m4, full_m4 = FakeM4(True), FakeM4(True)
        common = dict(config=self.cfg, sample_scenarios=[], certificate_fn=strict_certificate)
        lazy = search_strict_candidates((0.0, 0.0), 0.0, m4_fn=lazy_m4, lazy_objective=True, **common)
        full = search_strict_candidates((0.0, 0.0), 0.0, m4_fn=full_m4, lazy_objective=False, **common)
        a, b = lazy["selection"]["selected_strict"], full["selection"]["selected_strict"]
        self.assertEqual(a.S2, b.S2)
        self.assertEqual((a.T2, a.JR, a.JD), (b.T2, b.JR, b.JD))
        self.assertLess(len(lazy_m4.calls), len(full_m4.calls))
        lazy_region = {(c.level_m, c.ix, c.iy) for c in lazy["region_cells"] if c.certificate}
        full_region = {(c.level_m, c.ix, c.iy) for c in full["region_cells"] if c.certificate}
        self.assertEqual(lazy_region, full_region)
        best_50 = min(
            c.m4_result["candidate"].T2 for c in lazy["objective_cells"]
            if c.level_m == 50.0 and c.m4_result is not None
            and c.m4_result["candidate"].official20
        )
        retained_by_lower_bound = [
            c for c in lazy["objective_cells"] if c.level_m == 20.0
            and ((c.center[0] ** 2 + c.center[1] ** 2) ** 0.5) / 5.0 > best_50
            and max(0.0, (c.center[0] ** 2 + c.center[1] ** 2) ** 0.5 - (2.0 ** 0.5) * 10.0) / 5.0
            <= best_50 + 1.0e-3 * max(1.0, best_50)
        ]
        self.assertTrue(retained_by_lower_bound)

    def test_equal_T2_candidates_are_all_evaluated_for_tie_break(self):
        m4 = FakeM4(True)
        result = search_strict_candidates(
            (0.0, 0.0), 0.0, self.cfg, sample_scenarios=[],
            certificate_fn=strict_certificate, m4_fn=m4, stop_after_level_m=50.0,
        )
        closest = min((x * x + y * y) ** 0.5 for x, y in m4.calls)
        tied = [(x, y) for x, y in m4.calls if abs((x * x + y * y) ** 0.5 - closest) <= 1e-9]
        self.assertEqual(len(tied), 4)
        self.assertEqual(result["selection"]["selected_strict"].S2, (25.0, -25.0))

    def test_no_C20_fallback_matches_exhaustive(self):
        lazy_m4, full_m4 = FakeM4(False), FakeM4(False)
        common = dict(config=self.cfg, sample_scenarios=[], certificate_fn=strict_certificate)
        lazy = search_strict_candidates((0.0, 0.0), 0.0, m4_fn=lazy_m4, lazy_objective=True, **common)
        full = search_strict_candidates((0.0, 0.0), 0.0, m4_fn=full_m4, lazy_objective=False, **common)
        self.assertFalse(lazy["selection"]["C20"])
        self.assertEqual(lazy["selection"]["selected_strict"].S2, full["selection"]["selected_strict"].S2)

    def test_cheap_rejection_is_one_sided_safe(self):
        cfg = Q2Config(circle_sides=1440)
        p1 = build_P1_bound((1700.0, 0.0), 0.0, cfg)
        sources = build_Gext(p1, (1700.0, 0.0), 20.0)
        point = (825.0, -175.0)
        screen = screen_candidate_c20(point, (1700.0, 0.0), p1, sources, cfg)
        full = evaluate_candidate_nested(point, (1700.0, 0.0), p1, cfg)
        self.assertEqual(screen["screen_status"], "PROVEN_NOT_C20")
        self.assertFalse(full["candidate"].official20)


if __name__ == "__main__":
    unittest.main()
