import copy
from dataclasses import replace
import math
import os
import sys
import time
import unittest


SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from q1_localization import DEFAULT_TOLERANCES, EPS_MEC, point_in_convex_region, wedge_halfplanes  # noqa: E402
from q2_selection import (  # noqa: E402
    Q2Config,
    bearing,
    build_Gext,
    build_Gverify,
    build_error_grid,
    build_P1_bound,
    certified_strict,
    evaluate_candidate_nested,
    make_P2,
    merge_verified_worst,
    physical_filter,
    receive_floor,
    receive_violation,
    wrap_pi,
)


class TestQ2V21M1ToM3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S1 = (-1000.0, 0.0)
        cls.G = (0.0, 0.0)
        cls.config = Q2Config()
        cls.P1 = build_P1_bound(cls.S1, 0.0, cls.config)

    def test_T01_S1_is_strict_without_lmin(self):
        certificate = certified_strict(self.S1, self.P1, self.S1, self.config)
        self.assertEqual(certificate["status"], "CERTIFIED_STRICT")
        self.assertTrue(certificate["certified"])
        self.assertIs(certificate["strict_receive"], True)
        self.assertNotEqual(certificate["method"], "sample_all")
        shifted = certified_strict((-900.0, 0.0), self.P1, self.S1, self.config)
        self.assertTrue(shifted["certified"])
        self.assertEqual(shifted["status"], "CERTIFIED_STRICT")
        self.assertIs(shifted["strict_receive"], True)
        self.assertEqual(shifted["method"], "triangle_cell_2_lipschitz")
        self.assertLessEqual(shifted["upper_bound_m"], shifted["eps_rec_m"])

    def test_T02_true_source_is_in_P1_out(self):
        self.assertTrue(point_in_convex_region(
            self.G, self.P1["P1_out"], self.P1["P1_out_region_type"], DEFAULT_TOLERANCES
        ))
        self.assertTrue(physical_filter(self.G, self.S1))

    def test_T03_plus_minus_delta_wedge_contains_G(self):
        S2 = (0.0, -1000.0)
        true_bearing = bearing(S2, self.G)
        for error in (-1.0, 1.0):
            measured = true_bearing + error
            for a, b, c in wedge_halfplanes(S2[0], S2[1], measured, 1.0):
                self.assertLessEqual(a * self.G[0] + b * self.G[1], c + DEFAULT_TOLERANCES.eps_geo)
            result = make_P2(self.P1, S2, self.G, error, config=self.config)
            self.assertTrue(point_in_convex_region(
                self.G, result["polygon"], result["region_type"], DEFAULT_TOLERANCES
            ))

    def test_T04_receive_boundary(self):
        G = (500.0, 0.0)
        self.assertEqual(receive_floor(G, self.S1), 1500.0)
        self.assertAlmostEqual(receive_violation(self.S1, G, self.S1), 0.0)
        self.assertGreater(receive_violation((-1000.01, 0.0), G, self.S1), 0.0)

    def test_T05_no_signal_preserves_P1(self):
        result = make_P2(self.P1, (1200.0, 1200.0), self.G, rho=1000.0, config=self.config)
        self.assertEqual(result["status"], "NO_SIGNAL")
        self.assertIsNone(result["theta2_hat_deg"])
        self.assertEqual(result["polygon"], self.P1["P1_out"])
        self.assertGreater(result["diameter"], 0.0)

    def test_T06_P2_subset_P1(self):
        result = make_P2(self.P1, (0.0, -1000.0), self.G, 0.4, config=self.config)
        self.assertEqual(result["status"], "BEARING")
        self.assertTrue(all(point_in_convex_region(
            point, self.P1["P1_out"], self.P1["P1_out_region_type"], DEFAULT_TOLERANCES
        ) for point in result["polygon"]))

    def test_T07_diameter_mec_relation(self):
        result = make_P2(self.P1, (0.0, -1000.0), self.G, 0.0, config=self.config)
        D, R = result["diameter"], result["mec_radius"]
        self.assertGreaterEqual(R + DEFAULT_TOLERANCES.eps_mec, D / 2.0)
        self.assertLessEqual(R, D / math.sqrt(3.0) + DEFAULT_TOLERANCES.eps_mec)
        self.assertTrue(result["mec_lower_bound_ok"])
        self.assertTrue(result["mec_jung_upper_ok"])

    def test_T08_diameter_circle_decision_and_gap(self):
        result = make_P2(self.P1, self.G, self.G, config=self.config)
        expected = abs(2.0 * result["mec_radius"] - result["diameter"]) <= 2.0 * DEFAULT_TOLERANCES.eps_mec
        self.assertEqual(result["cover_by_diameter_circle"], expected)
        self.assertAlmostEqual(result["gap_m"], 2.0 * result["mec_radius"] - result["diameter"])

    def test_T09_near_computes_geometry(self):
        result = make_P2(self.P1, (2.0, 0.0), self.G, config=self.config)
        self.assertEqual(result["status"], "NEAR_TERMINAL")
        self.assertTrue(result["near_terminal"])
        self.assertGreater(result["diameter"], 0.0)
        self.assertGreater(result["mec_radius"], 0.0)
        self.assertGreater(result["area"], 0.0)
        self.assertLessEqual(result["diameter"], 10.0 + DEFAULT_TOLERANCES.eps_cover)
        self.assertLessEqual(result["mec_radius"], 5.0 + DEFAULT_TOLERANCES.eps_mec)

    def test_T10_repeated_point_is_near_not_zero_stub(self):
        result = make_P2(self.P1, self.G, self.G, config=self.config)
        self.assertEqual(result["status"], "NEAR_TERMINAL")
        self.assertIsNone(result["theta2_hat_deg"])
        self.assertGreater(result["diameter"], 0.0)

    def test_T11_wrap_zero(self):
        self.assertEqual(wrap_pi(0.0), 0.0)
        self.assertEqual(wrap_pi(2.0 * math.pi), 0.0)
        self.assertAlmostEqual(wrap_pi(math.pi), -math.pi)


class TestStrictCertificateImplementationSemantics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S1 = (-1000.0, 0.0)
        cls.P1 = build_P1_bound(cls.S1, 0.0, Q2Config())

    def test_budget_exhaustion_is_unresolved(self):
        config = Q2Config(certificate_max_cells=0)
        certificate = certified_strict((-900.0, 0.0), self.P1, self.S1, config)
        self.assertEqual(certificate["status"], "UNRESOLVED")
        self.assertFalse(certificate["certified"])
        self.assertIsNone(certificate["strict_receive"])
        self.assertEqual(certificate["reason"], "certificate_cell_budget_exhausted")

    def test_physical_counterexample_is_certified_violation(self):
        certificate = certified_strict((-3000.0, 0.0), self.P1, self.S1, Q2Config())
        self.assertEqual(certificate["status"], "CERTIFIED_VIOLATION")
        self.assertTrue(certificate["certified"])
        self.assertIs(certificate["strict_receive"], False)
        self.assertIsNotNone(certificate["counterexample"])
        self.assertTrue(physical_filter(certificate["counterexample"], self.S1))


class TestQ2M4NestedWorstCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S1 = (1700.0, 0.0)
        cls.S2 = (1710.0, 0.0)
        cls.config = Q2Config(circle_sides=360, max_error_refine_rounds=3)
        cls.P1 = build_P1_bound(cls.S1, 0.0, cls.config)
        started = time.perf_counter()
        cls.result = evaluate_candidate_nested(cls.S2, cls.S1, cls.P1, cls.config)
        cls.elapsed_seconds = time.perf_counter() - started
        print(f"M4_SYNTHETIC_RUNTIME_SECONDS={cls.elapsed_seconds:.6f}")

    def test_M4_sampling_metadata_and_nested_grids(self):
        coarse = build_Gext(self.P1, self.S1, 20.0)
        fine = build_Gext(self.P1, self.S1, 10.0, coarse)
        coarse_points = {item.G for item in coarse}
        fine_points = {item.G for item in fine}
        self.assertTrue(coarse_points <= fine_points)
        self.assertTrue(all(item.sample_set == "Gext" for item in fine))
        gext_origins = {
            "vertex", "boundary", "interior", "physical_boundary_target1800",
            "physical_boundary_receive1500", "physical_boundary_near_limit",
        }
        self.assertTrue(all(item.origin in gext_origins for item in fine))
        self.assertTrue(all(physical_filter(item.G, self.S1) for item in fine))
        self.assertTrue(any(item.origin == "physical_boundary_target1800" for item in fine))
        boundary_samples = [item for item in fine if item.origin.startswith("physical_boundary_")]
        self.assertTrue(boundary_samples)
        self.assertTrue(all(physical_filter(item.G, self.S1) for item in boundary_samples))
        near_samples = [item for item in fine if item.origin == "physical_boundary_near_limit"]
        self.assertTrue(near_samples)
        self.assertTrue(all(math.dist(item.G, self.S1) > 5.0 for item in near_samples))
        finest = build_Gext(self.P1, self.S1, 5.0, fine)
        eta20 = {item.near_limit_eta_m for item in coarse if item.origin == "physical_boundary_near_limit"}
        eta10 = {item.near_limit_eta_m for item in fine if item.origin == "physical_boundary_near_limit" and item.source_level_m == 10.0}
        eta5 = {item.near_limit_eta_m for item in finest if item.origin == "physical_boundary_near_limit" and item.source_level_m == 5.0}
        self.assertEqual((eta20, eta10, eta5), ({2.0}, {1.0}, {0.5}))
        verify = build_Gverify(self.P1, self.S1, 10.0, fine)
        self.assertGreater(len(verify), len(fine))
        self.assertFalse({item.G for item in verify} & fine_points)
        self.assertTrue(all(item.sample_set == "Gverify" for item in verify))
        verify_origins = {
            "verify_boundary", "verify_interior", "verify_target1800",
            "verify_receive1500", "verify_near_limit",
        }
        self.assertTrue(all(item.origin in verify_origins for item in verify))
        self.assertTrue(any(item.origin == "verify_target1800" for item in verify))
        self.assertTrue(all(physical_filter(item.G, self.S1) for item in verify))
        coarse_errors, fine_errors = build_error_grid(0.1), build_error_grid(0.05)
        self.assertEqual((coarse_errors[0], coarse_errors[-1]), (-1.0, 1.0))
        self.assertIn(0.0, coarse_errors)
        self.assertTrue(set(coarse_errors) <= set(fine_errors))

    def test_T13_independent_Gverify(self):
        report = self.result["gverify"]
        self.assertEqual(self.result["status"], "PASS")
        self.assertEqual(self.result["certificate"]["status"], "CERTIFIED_STRICT")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["independent_coordinate_overlap"], 0)
        self.assertTrue(report["strict_receive_check"])
        self.assertTrue(report["JD_check"])
        self.assertTrue(report["JR_check"])
        self.assertLessEqual(
            report["max_receive_violation_m"], self.result["certificate"]["eps_rec_m"]
        )

    def test_T14_worst_scenario_replay(self):
        candidate = self.result["candidate"]
        self.assertEqual(set(candidate.worst_scenarios), {"JD", "JR", "JA"})
        self.assertEqual(set(self.result["replay"]), {"JD", "JR", "JA"})
        for metric in ("JD", "JR", "JA"):
            worst = candidate.worst_scenarios[metric]
            self.assertEqual(worst.metric, metric)
            self.assertIn(worst.sample_set, {"Gext", "Gverify"})
            self.assertTrue(physical_filter(worst.G, self.S1))
            self.assertEqual(self.result["replay"][metric]["status"], "PASS")

    def test_M4_verified_threshold_crossing_uses_validated_JR(self):
        optimizer = copy.deepcopy(self.result["candidate"])
        verify = copy.deepcopy(self.result["candidate"])
        optimizer.JR = 19.9998
        optimizer.worst_scenarios["JR"] = replace(
            optimizer.worst_scenarios["JR"], value=19.9998, mec_radius=19.9998,
            sample_set="Gext", sample_origin="interior",
        )
        verify.JR = 20.0001
        verify.worst_scenarios["JR"] = replace(
            verify.worst_scenarios["JR"], value=20.0001, mec_radius=20.0001,
            sample_set="Gverify", sample_origin="verify_interior",
        )
        self.assertLessEqual(verify.JR - optimizer.JR, 0.00036)
        self.assertTrue(optimizer.JR + EPS_MEC <= 20.0)
        report = merge_verified_worst(optimizer, verify, convergence_passed=True)
        self.assertTrue(report["verify_exceeded_optimizer"]["JR"])
        self.assertEqual(optimizer.JR, 20.0001)
        self.assertEqual(optimizer.worst_scenarios["JR"].sample_set, "Gverify")
        self.assertIs(optimizer.official20, False)

    def test_T17_source_error_convergence(self):
        self.assertEqual(self.result["source_convergence"], "PASS")
        self.assertEqual(self.result["error_convergence"], "PASS")
        self.assertEqual([item["source_level_m"] for item in self.result["source_history"]], [20.0, 10.0])
        for source_level in (20.0, 10.0):
            records = [item for item in self.result["error_history"] if item["source_level_m"] == source_level]
            self.assertEqual([item["error_step_deg"] for item in records], [0.1, 0.05])
            self.assertLessEqual(records[-1]["relchg_D"], 1.0e-3)
            self.assertLessEqual(records[-1]["relchg_R"], 1.0e-3)
            self.assertTrue(records[-1]["JD_monotone"])
            self.assertTrue(records[-1]["JR_monotone"])
            self.assertTrue(records[-1]["JA_monotone"])
        final_source = self.result["source_history"][-1]
        self.assertLessEqual(final_source["relchg_D"], 1.0e-3)
        self.assertLessEqual(final_source["relchg_R"], 1.0e-3)
        self.assertNotIn("NON_MONOTONE_REFINEMENT", self.result["warnings"])
        self.assertTrue(self.result["strict_certificate_threshold_provisional"])


class TestQ2M41StressCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        angle_b = math.degrees(math.atan2(500.0, 1600.0))
        rad_b = math.radians(angle_b)
        rad_c = math.radians(-0.5)
        definitions = {
            "B": ((1600.0, 500.0), angle_b, (1600.0 + 10.0 * math.cos(rad_b), 500.0 + 10.0 * math.sin(rad_b))),
            "C": ((1700.0, 20.0), 359.5, (1700.0 + 10.0 * math.cos(rad_c), 20.0 + 10.0 * math.sin(rad_c))),
            "D": ((-1000.0, 0.0), 0.0, (-900.0, 0.0)),
        }
        cls.cases = {}
        for name, (s1, theta, s2) in definitions.items():
            config = Q2Config(circle_sides=180, max_error_refine_rounds=3)
            p1 = build_P1_bound(s1, theta, config)
            started = time.perf_counter()
            result = evaluate_candidate_nested(s2, s1, p1, config)
            elapsed = time.perf_counter() - started
            cls.cases[name] = (s1, p1, result, elapsed)
            print(
                f"M41_STRESS_{name} runtime={elapsed:.6f}s "
                f"source={result['source_history']} error={result['error_history']} "
                f"metrics={(result['candidate'].JD, result['candidate'].JR, result['candidate'].JA)} "
                f"gverify={result['gverify']} replay={result['replay']} warnings={result['warnings']}"
            )

    def test_stress_B_C_D_complete(self):
        for name, (_, _, result, _) in self.cases.items():
            with self.subTest(case=name):
                self.assertEqual(result["status"], "PASS")
                self.assertEqual(result["source_convergence"], "PASS")
                self.assertEqual(result["error_convergence"], "PASS")
                self.assertEqual(result["gverify"]["status"], "PASS")
                self.assertTrue(all(item["status"] == "PASS" for item in result["replay"].values()))
                self.assertNotIn("NON_MONOTONE_REFINEMENT", result["warnings"])

    def test_stress_D_receive_boundary_is_sampled(self):
        s1, p1, result, _ = self.cases["D"]
        gext = build_Gext(p1, s1, 20.0)
        verify = build_Gverify(p1, s1, 20.0, gext)
        receive_gext = [item for item in gext if item.origin == "physical_boundary_receive1500"]
        receive_verify = [item for item in verify if item.origin == "verify_receive1500"]
        self.assertTrue(receive_gext)
        self.assertTrue(receive_verify)
        self.assertTrue(all(physical_filter(item.G, s1) for item in receive_gext + receive_verify))
        exceeded = result["gverify"]["verify_exceeded_optimizer"]
        self.assertTrue(exceeded["JR"])
        self.assertTrue(exceeded["JA"])
        self.assertEqual(result["candidate"].worst_scenarios["JR"].sample_set, "Gverify")
        self.assertEqual(result["candidate"].worst_scenarios["JA"].sample_set, "Gverify")
        self.assertEqual(result["replay"]["JR"]["status"], "PASS")
        self.assertEqual(result["replay"]["JA"]["status"], "PASS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
