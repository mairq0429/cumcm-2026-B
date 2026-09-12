import copy
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest


SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from q1_localization import DEFAULT_TOLERANCES, EPS_MEC, point_in_convex_region, wedge_halfplanes  # noqa: E402
from q2_selection import (  # noqa: E402
    AreaCoverageResult,
    AreaIntegrationCell,
    Q2Config,
    CandidateResult,
    SourceScenario,
    bearing,
    build_Gext,
    build_Gverify,
    build_error_grid,
    build_Garea,
    build_P1_bound,
    certified_strict,
    evaluate_candidate_nested,
    evaluate_candidate_resolution,
    evaluate_risk_received_subset,
    evaluate_risk_candidate,
    integrate_qarea,
    classify_risk_threshold,
    classify_receive_certificate_bounds,
    make_P2,
    merge_verified_worst,
    physical_filter,
    receive_floor,
    receive_violation,
    run_eps_rec_cert_sensitivity,
    sample_receive_screen,
    search_strict_candidates,
    select_from_evaluated,
    write_m5b_outputs,
    strict_gverify_receive_status,
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
        self.assertLessEqual(shifted["U_rec_m"], 0.0)

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

    def test_zero_threshold_four_state_bounds(self):
        self.assertEqual(
            classify_receive_certificate_bounds(5e-4, 8e-4, 1e-3),
            "CERTIFIED_VIOLATION",
        )
        self.assertEqual(
            classify_receive_certificate_bounds(-2e-4, -1e-5, 1e-3),
            "CERTIFIED_STRICT",
        )
        self.assertEqual(
            classify_receive_certificate_bounds(-4e-4, 4e-4, 1e-3),
            "UNCERTAIN_BOUNDARY",
        )
        self.assertEqual(
            classify_receive_certificate_bounds(-1.0, 1.0, 1e-3),
            "CONTINUE",
        )

    def test_certificate_contract_and_analytic_zero_upper(self):
        certificate = certified_strict(self.S1, self.P1, self.S1, Q2Config())
        required = {
            "status", "strict_receive", "certified", "L_rec_m", "U_rec_m",
            "interval_width_m", "eps_rec_cert_m", "eps_rec_cert_source",
            "cells_examined", "counterexample", "reason",
        }
        self.assertTrue(required <= set(certificate))
        self.assertEqual(certificate["U_rec_m"], 0.0)
        self.assertEqual(certificate["eps_rec_cert_m"], 1e-3)
        self.assertEqual(
            certificate["eps_rec_cert_source"],
            "MODEL_FROZEN_CERTIFICATION_PRECISION",
        )

    def test_M5A_submillimetre_sample_screen_and_whole_cell(self):
        point = sample_receive_screen((-1000.0005, 0.0), (500.0, 0.0), self.S1)
        self.assertGreater(point["margin_m"], 0.0)
        self.assertLess(point["margin_m"], 1e-3)
        self.assertTrue(point["point_violation"])
        self.assertTrue(sample_receive_screen(
            (-1000.4, 0.0), (500.0, 0.0), self.S1, 0.3
        )["whole_cell_violation"])
        self.assertFalse(sample_receive_screen(
            (-1000.2, 0.0), (500.0, 0.0), self.S1, 0.3
        )["whole_cell_violation"])

    def test_Gverify_positive_micrometre_fails_strict(self):
        self.assertEqual(
            strict_gverify_receive_status("CERTIFIED_STRICT", 1e-6),
            "GVERIFY_FAIL_RECEIVE",
        )
        self.assertEqual(
            strict_gverify_receive_status("CERTIFIED_STRICT", 0.0), "PASS"
        )


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
            report["max_receive_violation_m"], 0.0
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
        self.assertEqual(self.result["strict_physical_threshold_m"], 0.0)
        self.assertEqual(self.result["eps_rec_cert_m"], 1e-3)
        self.assertEqual(
            self.result["eps_rec_cert_source"],
            "MODEL_FROZEN_CERTIFICATION_PRECISION",
        )


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


class TestQ2M5AStrictCandidateSearch(unittest.TestCase):
    @staticmethod
    def _certificate(point, _p1, _s1, config):
        x = point[0]
        eps = config.eps_rec_cert_m
        common = {
            "eps_rec_cert_m": eps,
            "eps_rec_cert_source": "MODEL_FROZEN_CERTIFICATION_PRECISION",
            "counterexample": None,
        }
        if -50.0 <= x <= 50.0:
            return dict(common, status="UNRESOLVED", certified=False, strict_receive=None)
        if x <= -100.0 or x >= 100.0:
            return dict(common, status="CERTIFIED_STRICT", certified=True, strict_receive=True)
        return dict(common, status="CERTIFIED_VIOLATION", certified=True, strict_receive=False)

    @classmethod
    def _m4(cls, point, _s1, _p1, config):
        certificate = cls._certificate(point, _p1, _s1, config)
        candidate = CandidateResult(
            S2=point,
            strict_receive=True,
            certificate=certificate,
            T2=math.dist(point, _s1) / 5.0,
            JD=12.0 + abs(point[1]) / 1000.0,
            JR=6.0 + abs(point[1]) / 2000.0,
            JA=20.0,
            official20=True,
            operational17=True,
            worst_scenarios={},
            robust_guarantee=True,
            official20_provisional=True,
            operational17_provisional=True,
            evaluation_status="CONVERGED",
        )
        return {"status": "PASS", "candidate": candidate}

    @classmethod
    def setUpClass(cls):
        cls.S1 = (0.0, 0.0)
        cls.omega = ((-250.0, -100.0), (250.0, -100.0), (250.0, 100.0), (-250.0, 100.0))
        cls.config = Q2Config(circle_sides=90, omega_move=cls.omega, lmin_m=0.0)
        cls.P1 = build_P1_bound(cls.S1, 0.0, cls.config)
        cls.result = search_strict_candidates(
            cls.S1, 0.0, cls.config, P1_bound=cls.P1, sample_scenarios=[],
            certificate_fn=cls._certificate, m4_fn=cls._m4,
        )

    def test_candidate_grid_50_20_5_boundary_unresolved_and_components(self):
        diagnostics = self.result["level_diagnostics"]
        self.assertEqual(self.result["candidate_levels_m"], [50.0, 20.0, 5.0])
        self.assertTrue(all(item["candidate_total"] > 0 for item in diagnostics))
        self.assertTrue(any(item["certificate_unresolved"] > 0 for item in diagnostics))
        fine = [cell for cell in self.result["cells"] if cell.level_m == 5.0]
        self.assertTrue(fine)
        self.assertTrue(any(cell.parent_ids for cell in fine))
        self.assertTrue(any(cell.status == "BOUNDARY_OR_UNRESOLVED" for cell in fine))
        coarse_components = [
            item for item in self.result["near_optimal_components"]
            if item["grid_level_m"] == 50.0 and item["selected_for_refinement"]
        ]
        self.assertGreaterEqual(len(coarse_components), 2)

    def test_sample_counterexample_rejects_point_but_only_safe_cells_stop(self):
        omega = ((1100.0, -25.0), (1150.0, -25.0), (1150.0, 25.0), (1100.0, 25.0))
        config = Q2Config(circle_sides=90, omega_move=omega, lmin_m=0.0)
        p1 = build_P1_bound(self.S1, 0.0, config)
        physical_sample = SourceScenario(
            G=(100.0, 0.0), sample_set="Gext", source_level_m=20.0, origin="interior"
        )
        result = search_strict_candidates(
            self.S1, 0.0, config, P1_bound=p1, sample_scenarios=[physical_sample],
            certificate_fn=lambda p, p1, s1, c: dict(
                self._certificate((150.0, p[1]), p1, s1, c), status="CERTIFIED_STRICT",
                certified=True, strict_receive=True,
            ),
            m4_fn=self._m4,
        )
        self.assertGreater(sum(item["sample_rejected"] for item in result["level_diagnostics"]), 0)
        rejected = [cell for cell in result["cells"] if cell.status == "CERTIFIED_VIOLATION_SAMPLE"]
        self.assertTrue(rejected)
        self.assertTrue(any(cell.boundary_flag and not cell.cell_exclusion_certified for cell in rejected))
        self.assertTrue(any(cell.level_m == 5.0 for cell in result["cells"]))

        safe_config = Q2Config(
            circle_sides=90,
            omega_move=((1500.0, -25.0), (1550.0, -25.0), (1550.0, 25.0), (1500.0, 25.0)),
            lmin_m=0.0,
        )
        safe_p1 = build_P1_bound(self.S1, 0.0, safe_config)
        safely_excluded = search_strict_candidates(
            self.S1, 0.0, safe_config, P1_bound=safe_p1,
            sample_scenarios=[physical_sample], certificate_fn=self._certificate,
            m4_fn=self._m4,
        )
        coarse = [cell for cell in safely_excluded["region_cells"] if cell.level_m == 50.0]
        self.assertTrue(coarse)
        self.assertTrue(all(cell.cell_exclusion_certified for cell in coarse))
        self.assertEqual(safely_excluded["region_candidate_count_by_level"]["20"], 0)
        self.assertEqual(safely_excluded["region_candidate_count_by_level"]["5"], 0)

    def test_nonoptimal_strict_component_remains_in_region_not_objective(self):
        omega = ((50.0, -25.0), (550.0, -25.0), (550.0, 25.0), (50.0, 25.0))
        config = Q2Config(circle_sides=90, omega_move=omega, lmin_m=0.0)
        p1 = build_P1_bound(self.S1, 0.0, config)

        def separated_certificate(point, _p1, _s1, cfg):
            eps = cfg.eps_rec_cert_m
            strict = point[0] < 200.0 or point[0] >= 400.0
            return {
                "status": "CERTIFIED_STRICT" if strict else "CERTIFIED_VIOLATION",
                "certified": True,
                "strict_receive": strict,
                "counterexample": None,
                "eps_rec_cert_m": eps,
                "eps_rec_cert_source": "MODEL_FROZEN_CERTIFICATION_PRECISION",
            }

        def separated_m4(point, s1, p1_arg, cfg):
            certificate = separated_certificate(point, p1_arg, s1, cfg)
            candidate = CandidateResult(
                S2=point, strict_receive=True, certificate=certificate,
                T2=math.dist(point, s1) / 5.0, JD=10.0, JR=5.0, JA=1.0,
                official20=True, operational17=True, worst_scenarios={},
                robust_guarantee=True, evaluation_status="CONVERGED",
            )
            return {"status": "PASS", "candidate": candidate}

        with tempfile.TemporaryDirectory() as temporary:
            result = search_strict_candidates(
                self.S1, 0.0, config, P1_bound=p1, sample_scenarios=[],
                certificate_fn=separated_certificate, m4_fn=separated_m4,
                output_dir=temporary,
            )
            selected = result["selection"]["selected_strict"]
            self.assertLess(selected.S2[0], 200.0)
            fine_a = [
                cell for cell in result["region_cells"]
                if cell.level_m == 5.0 and cell.center[0] < 200.0
                and cell.certificate is not None
                and cell.certificate["status"] == "CERTIFIED_STRICT"
            ]
            fine_b = [
                cell for cell in result["region_cells"]
                if cell.level_m == 5.0 and cell.center[0] >= 400.0
                and cell.certificate is not None
                and cell.certificate["status"] == "CERTIFIED_STRICT"
            ]
            self.assertTrue(fine_a)
            self.assertTrue(fine_b)
            self.assertTrue(any(cell.objective_refinement and cell.m4_result for cell in fine_a))
            self.assertTrue(all(not cell.objective_refinement and cell.m4_result is None for cell in fine_b))
            geojson = json.loads((Path(temporary) / "Fstrict.geojson").read_text(encoding="utf-8"))
            strict_x = [
                feature["geometry"]["coordinates"][0]
                for feature in geojson["features"]
                if feature["properties"]["representation"] == "point_certified"
            ]
            self.assertTrue(any(x < 200.0 for x in strict_x))
            self.assertTrue(any(x >= 400.0 for x in strict_x))
            self.assertGreater(
                result["region_candidate_count_by_level"]["5"],
                result["objective_candidate_count_by_level"]["5"],
            )
            self.assertLess(result["M4_calls"], result["certificate_calls"])

    def test_omega_boundary_intersection_is_retained_as_uncertainty(self):
        omega = ((1.0, 1.0), (2.0, 1.0), (2.0, 2.0), (1.0, 2.0))
        config = Q2Config(circle_sides=90, omega_move=omega, lmin_m=0.0)
        p1 = build_P1_bound(self.S1, 0.0, config)
        result = search_strict_candidates(
            self.S1, 0.0, config, P1_bound=p1, sample_scenarios=[],
            certificate_fn=self._certificate, m4_fn=self._m4,
        )
        self.assertTrue(all(result["region_candidate_count_by_level"][str(int(level))] > 0 for level in (50, 20, 5)))
        fine = [cell for cell in result["region_cells"] if cell.level_m == 5.0]
        self.assertTrue(any(cell.omega_boundary_flag for cell in fine))
        self.assertIn("conservative", result["omega_boundary_method"])

    def test_same_input_is_deterministic_and_outputs_point_certificates(self):
        with tempfile.TemporaryDirectory() as temporary:
            second = search_strict_candidates(
                self.S1, 0.0, self.config, P1_bound=self.P1, sample_scenarios=[],
                certificate_fn=self._certificate, m4_fn=self._m4, output_dir=temporary,
            )
            first_selected = self.result["selection"]["selected_strict"]
            second_selected = second["selection"]["selected_strict"]
            self.assertEqual(first_selected.to_dict(), second_selected.to_dict())
            expected = {
                "strict_candidates.csv", "candidate_status.csv", "Fstrict.geojson",
                "selection_dev.json", "candidate_search_diagnostics.json",
            }
            self.assertEqual({path.name for path in Path(temporary).iterdir()}, expected)
            geojson = json.loads((Path(temporary) / "Fstrict.geojson").read_text(encoding="utf-8"))
            representations = {feature["properties"]["representation"] for feature in geojson["features"]}
            self.assertIn("point_certified", representations)
            self.assertIn("uncertainty_cell", representations)
            self.assertTrue(all(
                feature["geometry"]["type"] == "Point"
                for feature in geojson["features"]
                if feature["properties"]["representation"] == "point_certified"
            ))

    def test_candidates_may_be_outside_target_circle_and_lmin_excludes(self):
        outside_omega = ((1850.0, -50.0), (2050.0, -50.0), (2050.0, 50.0), (1850.0, 50.0))
        outside_config = Q2Config(circle_sides=90, omega_move=outside_omega, lmin_m=0.0)
        outside_p1 = build_P1_bound(self.S1, 0.0, outside_config)
        outside = search_strict_candidates(
            self.S1, 0.0, outside_config, P1_bound=outside_p1, sample_scenarios=[],
            certificate_fn=lambda p, p1, s1, c: dict(
                self._certificate((150.0, p[1]), p1, s1, c), status="CERTIFIED_STRICT",
                certified=True, strict_receive=True,
            ),
            m4_fn=self._m4,
        )
        self.assertGreater(math.dist(outside["selection"]["selected_strict"].S2, (0.0, 0.0)), 1800.0)
        near_omega = ((-40.0, -40.0), (40.0, -40.0), (40.0, 40.0), (-40.0, 40.0))
        near_config = Q2Config(circle_sides=90, omega_move=near_omega, lmin_m=50.0)
        near_p1 = build_P1_bound(self.S1, 0.0, near_config)
        excluded = search_strict_candidates(
            self.S1, 0.0, near_config, P1_bound=near_p1, sample_scenarios=[],
            certificate_fn=self._certificate, m4_fn=self._m4,
        )
        self.assertGreater(excluded["level_diagnostics"][0]["lmin_excluded"], 0)
        final_strict = [
            cell for cell in excluded["cells"]
            if cell.level_m == 5.0 and cell.status == "STRICT_INTERIOR"
        ]
        self.assertTrue(all(math.dist(cell.center, self.S1) >= 50.0 for cell in final_strict))

    def test_T15_selection_rule(self):
        def candidate(x, t2, jr, jd, official, status="CERTIFIED_STRICT", evaluation="CONVERGED"):
            return CandidateResult(
                S2=(x, 0.0), strict_receive=True if status == "CERTIFIED_STRICT" else None,
                certificate={"status": status}, T2=t2, JD=jd, JR=jr, JA=1.0,
                official20=official, operational17=False, worst_scenarios={},
                evaluation_status=evaluation,
            )
        a = candidate(2.0, 5.0, 10.0, 15.0, True)
        b = candidate(1.0, 4.0, 12.0, 14.0, True)
        unresolved = candidate(0.0, 1.0, 1.0, 1.0, True, status="UNRESOLVED", evaluation="UNRESOLVED")
        selected_a = select_from_evaluated([a, b, unresolved])
        self.assertIs(selected_a["selected_strict"], b)
        self.assertNotIn(unresolved, selected_a["Cstrict"])
        p = candidate(3.0, 5.0, 4.0, 10.0, False)
        q = candidate(4.0, 4.0, 5.0, 9.0, False)
        selected_b = select_from_evaluated([p, q])
        self.assertIs(selected_b["selected_strict"], p)
        selected_c = select_from_evaluated([unresolved])
        self.assertIsNone(selected_c["selected_strict"])

    def test_T16_all_sources_and_worst_scenarios_are_physical(self):
        gext = build_Gext(self.P1, self.S1, 20.0)
        fine = build_Gext(self.P1, self.S1, 10.0, gext)
        verify = build_Gverify(self.P1, self.S1, 10.0, fine)
        self.assertTrue(all(physical_filter(item.G, self.S1) for item in fine + verify))
        evaluated = evaluate_candidate_resolution(
            (100.0, 0.0), self.S1, self.P1, fine[:12], 0.1, self.config,
        )
        self.assertEqual(set(evaluated.worst_scenarios), {"JD", "JR", "JA"})
        for worst in evaluated.worst_scenarios.values():
            self.assertTrue(physical_filter(worst.G, self.S1))

    def test_eps_rec_cert_sensitivity_keeps_zero_physical_threshold(self):
        report = run_eps_rec_cert_sensitivity(
            self.S1, 0.0, config=self.config, P1_bound=self.P1,
            sample_scenarios=[], certificate_fn=self._certificate, m4_fn=self._m4,
        )
        self.assertEqual(report["strict_physical_threshold_m"], 0.0)
        self.assertEqual(
            [item["eps_rec_cert_m"] for item in report["records"]],
            [1e-4, 1e-3, 1e-2],
        )
        self.assertTrue(all(
            item["strict_physical_threshold_m"] == 0.0 for item in report["records"]
        ))
        self.assertEqual(report["status"], "PASS")


class TestQ2M5BGeometricRiskArea(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S1 = (0.0, 0.0)
        cls.P1 = [(100.0, -50.0), (200.0, -50.0), (200.0, 50.0), (100.0, 50.0)]
        cls.config = Q2Config(
            circle_sides=90, area_step_m=40.0, area_q_tol=0.02,
            max_area_refine_rounds=4,
        )

    @staticmethod
    def _coverage(lower, upper):
        return AreaCoverageResult(
            S2=(0.0, 0.0), Aphys_low=100.0, Aphys_high=100.0,
            Aphys_est=100.0, Arecv_low=100.0 * lower,
            Arecv_high=100.0 * upper, Arecv_est=50.0 * (lower + upper),
            Q_lower=lower, Q_upper=upper, Qarea_est=(lower + upper) / 2.0,
            Earea_phys=0.0, Earea_recv=100.0 * (upper - lower),
            Earea=100.0 * (upper - lower), EPS_Q=max(1e-6, upper - lower),
            integration_status="PASS", alpha_099_status="", alpha_095_status="",
            cell_count=1, refinement_history=[], cells=[],
        )

    def test_qarea_strict_far_refinement_and_real_Earea(self):
        strict = integrate_qarea(self.S1, self.S1, self.P1, self.config)
        self.assertEqual((strict.Q_lower, strict.Q_upper, strict.Qarea_est), (1.0, 1.0, 1.0))
        self.assertEqual(strict.alpha_099_status, "CERTIFIED_ABOVE_ALPHA")
        far = integrate_qarea((1200.0, 0.0), self.S1, self.P1, self.config)
        self.assertLess(far.Qarea_est, 0.1)
        eareas = [item["Earea"] for item in far.refinement_history]
        self.assertTrue(all(after <= before + 1e-12 for before, after in zip(eareas, eareas[1:])))
        self.assertGreater(far.Earea, 0.0)
        self.assertAlmostEqual(far.EPS_Q, far.Earea / far.Aphys_est)

    def test_dense_deterministic_oracle_is_inside_certified_interval(self):
        s2 = (1150.0, 0.0)
        result = integrate_qarea(s2, self.S1, self.P1, self.config)
        count = received = 0
        n = 300
        for ix in range(n):
            x = 100.0 + (ix + 0.5) * 100.0 / n
            for iy in range(n):
                y = -50.0 + (iy + 0.5) * 100.0 / n
                count += 1
                received += receive_violation(s2, (x, y), self.S1) <= 0.0
        oracle = received / count
        self.assertLessEqual(result.Q_lower, oracle)
        self.assertLessEqual(oracle, result.Q_upper)

    def test_threshold_three_state_never_uses_estimate_to_upgrade(self):
        unresolved = self._coverage(0.985, 0.995)
        unresolved.Qarea_est = 0.991
        self.assertEqual(classify_risk_threshold(unresolved, 0.99), "THRESHOLD_UNRESOLVED")
        self.assertEqual(classify_risk_threshold(self._coverage(0.995, 1.0), 0.99), "CERTIFIED_ABOVE_ALPHA")
        self.assertEqual(classify_risk_threshold(self._coverage(0.90, 0.98), 0.99), "CERTIFIED_BELOW_ALPHA")

    def test_received_subset_excludes_no_signal_and_merges_Gverify(self):
        s2 = (1150.0, 0.0)
        gext = [
            SourceScenario((110.0, 0.0), sample_set="Gext", origin="interior"),
            SourceScenario((190.0, 0.0), sample_set="Gext", origin="interior"),
        ]
        gverify = [
            SourceScenario((120.0, 10.0), sample_set="Gverify", origin="verify_interior"),
            SourceScenario((180.0, 10.0), sample_set="Gverify", origin="verify_interior"),
        ]
        coverage = integrate_qarea(s2, self.S1, self.P1, self.config)
        result = evaluate_risk_received_subset(
            s2, self.S1, self.P1, gext, gverify, 0.1, self.config,
            coverage=coverage,
        )
        self.assertFalse(result.robust_guarantee)
        self.assertEqual(result.gverify["optimizer_received_count"], 1)
        self.assertEqual(result.gverify["verify_received_count"], 1)
        self.assertTrue(any(result.gverify["verify_exceeded_optimizer"].values()))
        for worst in result.worst_received_scenarios.values():
            self.assertLessEqual(receive_violation(s2, worst.G, self.S1), 0.0)
            self.assertNotEqual(worst.status, "NO_SIGNAL")

    def test_received_subset_nested_convergence_and_independent_verify(self):
        result = evaluate_risk_candidate(
            (1150.0, 0.0), self.S1, self.P1, self.config
        )
        self.assertEqual(result.evaluation_status, "PASS")
        self.assertGreaterEqual(len(result.source_history), 2)
        self.assertGreaterEqual(len(result.error_history), 4)
        self.assertLessEqual(result.source_history[-1]["relchg_D"], 1e-3)
        self.assertLessEqual(result.source_history[-1]["relchg_R"], 1e-3)
        self.assertEqual(result.gverify["status"], "PASS")
        self.assertTrue(all(
            item["status"] == "PASS" for item in result.gverify["replay"].values()
        ))

    def test_Garea_is_area_weighted_independent_and_outputs_are_separate(self):
        cells = build_Garea(self.P1, self.S1, self.S1, self.config)
        self.assertTrue(all(isinstance(cell, AreaIntegrationCell) for cell in cells))
        self.assertAlmostEqual(sum(cell.area for cell in cells), 10000.0)
        baseline = integrate_qarea(self.S1, self.S1, self.P1, self.config)
        artificial_boundary_points = [
            SourceScenario((100.0, -50.0 + index / 10.0), origin="boundary")
            for index in range(1001)
        ]
        self.assertGreater(len(artificial_boundary_points), len(cells))
        repeated = integrate_qarea(self.S1, self.S1, self.P1, self.config)
        self.assertEqual(baseline.to_dict(), repeated.to_dict())
        risk = evaluate_risk_received_subset(
            self.S1, self.S1, self.P1,
            [SourceScenario((150.0, 0.0), sample_set="Gext")],
            [SourceScenario((175.0, 0.0), sample_set="Gverify")],
            0.1, self.config, coverage=baseline,
        )
        with tempfile.TemporaryDirectory() as temporary:
            write_m5b_outputs([risk], temporary)
            expected = {
                "area_coverage_candidates.csv", "risk099_candidates.csv",
                "risk095_candidates.csv", "Frisk099.geojson", "Frisk095.geojson",
                "area_integration_diagnostics.json", "risk_worst_diagnostics.json",
            }
            self.assertEqual({path.name for path in Path(temporary).iterdir()}, expected)
            geojson = json.loads((Path(temporary) / "Frisk099.geojson").read_text(encoding="utf-8"))
            self.assertTrue(geojson["features"])
            self.assertTrue(all(not feature["properties"]["robust_guarantee"] for feature in geojson["features"]))
            self.assertEqual(geojson["coverage_type"], "GEOMETRIC_AREA_NOT_PROBABILITY")


if __name__ == "__main__":
    unittest.main(verbosity=2)
