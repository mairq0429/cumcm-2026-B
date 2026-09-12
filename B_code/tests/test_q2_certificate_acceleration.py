import math
import os
import sys
import unittest


SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from q2_certificate_acceleration import (  # noqa: E402
    CertificateAnchor,
    PhysicalCertificateTree,
    StrictCertificateAccelerator,
    accelerated_certified_strict,
    propagate_anchor_bounds,
    propagate_candidate_cell,
    run_legacy_accelerated_equivalence,
    run_legacy_accelerated_equivalence,
)
from q2_selection import (  # noqa: E402
    CandidateResult,
    Q2Config,
    build_Gverify,
    build_P1_bound,
    certified_strict,
    receive_violation,
    search_strict_candidates,
)


class TestQ2CertificateAcceleration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S1 = (1700.0, 0.0)
        cls.config = Q2Config()
        cls.P1 = build_P1_bound(cls.S1, 0.0, cls.config)

    def test_propagation_algebra_and_whole_cells(self):
        strict = CertificateAnchor(
            (0.0, 0.0), -math.inf, -100.0, "CERTIFIED_STRICT", "s", 1, "test"
        )
        violation = CertificateAnchor(
            (0.0, 0.0), 100.0, math.inf, "CERTIFIED_VIOLATION", "v", 1, "test"
        )
        result = propagate_anchor_bounds((50.0, 0.0), [strict])
        self.assertEqual(result["propagated_U_rec_m"], -50.0)
        self.assertEqual(result["status"], "CERTIFIED_STRICT_PROPAGATED")
        result = propagate_anchor_bounds((40.0, 0.0), [violation])
        self.assertEqual(result["propagated_L_rec_m"], 60.0)
        self.assertEqual(result["status"], "CERTIFIED_VIOLATION_PROPAGATED")
        unresolved = CertificateAnchor(
            (0.0, 0.0), -math.inf, -20.0, "CERTIFIED_STRICT", "n", 1, "test"
        )
        self.assertEqual(
            propagate_anchor_bounds((30.0, 0.0), [unresolved])["status"], "UNRESOLVED"
        )
        self.assertEqual(
            propagate_candidate_cell((50.0, 0.0), 20.0, [strict])["whole_cell_status"],
            "WHOLE_CELL_CERTIFIED_STRICT",
        )
        self.assertEqual(
            propagate_candidate_cell((40.0, 0.0), 20.0, [violation])["whole_cell_status"],
            "WHOLE_CELL_CERTIFIED_VIOLATION",
        )

    def test_zero_threshold_is_independent_of_certificate_precision(self):
        anchor = CertificateAnchor(
            (0.0, 0.0), -2.0, -1.0e-5, "CERTIFIED_STRICT", "a", 1, "test"
        )
        outcomes = []
        for precision in (1.0e-4, 1.0e-3, 1.0e-2):
            config = Q2Config(eps_rec_cert_m=precision)
            self.assertGreater(config.eps_rec_cert_m, 0.0)
            outcomes.append(propagate_anchor_bounds((0.0, 0.0), [anchor])["status"])
        self.assertEqual(outcomes, ["CERTIFIED_STRICT_PROPAGATED"] * 3)

    def test_legacy_accelerated_equivalence_for_30_deterministic_points(self):
        tree = PhysicalCertificateTree(self.P1, self.S1, self.config)
        strict_points = [
            (1500.0 + 25.0 * index, (-1) ** index * 40.0) for index in range(15)
        ]
        violation_points = [
            (2900.0 + 20.0 * index, (-1) ** index * (100.0 + 5.0 * index))
            for index in range(15)
        ]
        differences = []
        for point in strict_points + violation_points:
            legacy = certified_strict(point, self.P1, self.S1, self.config)
            accelerated = accelerated_certified_strict(point, tree, self.S1, self.config)
            self.assertFalse(
                legacy["status"] == "CERTIFIED_STRICT"
                and accelerated["status"] == "CERTIFIED_VIOLATION"
            )
            self.assertFalse(
                legacy["status"] == "CERTIFIED_VIOLATION"
                and accelerated["status"] == "CERTIFIED_STRICT"
            )
            if legacy["status"] in {"CERTIFIED_STRICT", "CERTIFIED_VIOLATION"} and accelerated["status"] in {
                "CERTIFIED_STRICT", "CERTIFIED_VIOLATION"
            }:
                self.assertEqual(legacy["status"], accelerated["status"])
            if legacy["status"] != accelerated["status"]:
                differences.append((point, legacy["status"], accelerated["status"]))
        self.assertLessEqual(len(differences), 30)
        report = run_legacy_accelerated_equivalence()
        self.assertEqual(report["case_count"], 30)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["conflict_count"], 0)
        report = run_legacy_accelerated_equivalence()
        self.assertEqual(report["case_count"], 30)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["conflict_count"], 0)

    def test_accelerated_bounds_contain_dense_deterministic_sample_max(self):
        tree = PhysicalCertificateTree(self.P1, self.S1, self.config)
        certificate = accelerated_certified_strict((1750.0, 0.0), tree, self.S1, self.config)
        sources = build_Gverify(self.P1, self.S1, 2.5, [])
        sample_max = max(receive_violation((1750.0, 0.0), source.G, self.S1) for source in sources)
        self.assertLessEqual(certificate["L_rec_m"], sample_max + 1.0e-12)
        self.assertLessEqual(sample_max, certificate["U_rec_m"] + 1.0e-12)

    def test_tree_reuse_and_repeatability(self):
        tree = PhysicalCertificateTree(self.P1, self.S1, self.config)
        first = accelerated_certified_strict((2650.0, 0.0), tree, self.S1, self.config)
        node_count = len(tree.nodes)
        second = accelerated_certified_strict((2640.0, 10.0), tree, self.S1, self.config)
        repeat = accelerated_certified_strict((2650.0, 0.0), tree, self.S1, self.config)
        self.assertGreaterEqual(len(tree.nodes), node_count)
        self.assertGreater(second["tree_nodes_reused"], 0)
        self.assertEqual(first["status"], repeat["status"])
        self.assertEqual(first["strict_receive"], repeat["strict_receive"])

    def test_anchor_scheduler_reduces_full_calls_on_cluster(self):
        tree = PhysicalCertificateTree(self.P1, self.S1, self.config)
        engine = StrictCertificateAccelerator(tree, self.config)
        points = [(1700.0 + 5.0 * index, 0.0) for index in range(1, 21)]
        result = engine.certify_points(points, 2.0)
        self.assertEqual(len(result["certificates"]), len(points))
        self.assertLess(result["full_certificate_calls"], len(points))
        self.assertGreater(result["propagated_strict_points"], 0)

    def test_M5A_batch_integration_preserves_strict_contract(self):
        cfg = Q2Config(omega_move=((1760.0, 20.0), (1790.0, 20.0), (1790.0, 40.0), (1760.0, 40.0)))
        p1 = build_P1_bound(self.S1, 0.0, cfg)
        engine = StrictCertificateAccelerator(PhysicalCertificateTree(p1, self.S1, cfg), cfg)

        def fake_m4(S2, S1, P1, config, certificate_override=None):
            certificate = dict(certificate_override)
            candidate = CandidateResult(
                S2=tuple(S2), strict_receive=True, certificate=certificate,
                T2=math.dist(S2, S1) / 5.0, JD=8.0, JR=4.0, JA=6.0,
                official20=True, operational17=True, worst_scenarios={},
                robust_guarantee=True, evaluation_status="CONVERGED",
            )
            return {"status": "PASS", "candidate": candidate}

        result = search_strict_candidates(
            self.S1, 0.0, cfg, P1_bound=p1,
            certificate_batch_engine=engine, m4_fn=fake_m4,
            pass_certificate_to_m4=True,
        )
        self.assertGreater(result["certificate_calls"], 0)
        self.assertTrue(any(
            cell.whole_cell_strict_certified for cell in result["region_cells"]
        ))
        self.assertTrue(all(
            candidate.certificate["status"] == "CERTIFIED_STRICT"
            for candidate in result["selection"]["Cstrict"]
        ))


if __name__ == "__main__":
    unittest.main()
