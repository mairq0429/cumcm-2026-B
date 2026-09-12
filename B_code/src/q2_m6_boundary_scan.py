"""M6A.7b full-angle Lmin-circle branch discovery (not final selection)."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import math
from pathlib import Path
import time

import q2_selection as q2
from q2_certificate_acceleration import PhysicalCertificateTree, StrictCertificateAccelerator

LABEL = "VALIDATION / DIAGNOSTIC / NOT_FINAL_Q2_RESULT"


def boundary_point(phi_deg, S1=(1700.0, 0.0), radius_m=50.0):
    angle = math.radians(phi_deg)
    return (S1[0] + radius_m * math.cos(angle), S1[1] + radius_m * math.sin(angle))


def sampled_circular_arcs(angles, step_deg):
    ordered = sorted({float(a) % 360.0 for a in angles})
    if not ordered:
        return []
    arcs, current = [], [ordered[0]]
    for angle in ordered[1:]:
        if math.isclose(angle - current[-1], step_deg, abs_tol=1e-9):
            current.append(angle)
        else:
            arcs.append(current); current = [angle]
    arcs.append(current)
    if len(arcs) > 1 and math.isclose((arcs[0][0] + 360.0) - arcs[-1][-1], step_deg, abs_tol=1e-9):
        arcs[0] = arcs[-1] + arcs[0]
        arcs.pop()
    return arcs


def _jsonable(value):
    if is_dataclass(value): return _jsonable(asdict(value))
    if isinstance(value, dict): return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_jsonable(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value): return None
    return value


def _m4_pass(evaluation):
    return (evaluation.get("status") == "PASS"
            and evaluation.get("source_convergence") == "PASS"
            and evaluation.get("error_convergence") == "PASS"
            and evaluation.get("gverify", {}).get("status") == "PASS"
            and all(evaluation.get("replay", {}).get(k, {}).get("status") == "PASS" for k in ("JD", "JR", "JA")))


def run_boundary_scan(step_deg=2.0, output_path="03_results/q2/m6_validation/lmin_circle_branch_scan.json"):
    if step_deg <= 0 or not math.isclose(360.0 / step_deg, round(360.0 / step_deg), abs_tol=1e-12):
        raise ValueError("step_deg must partition 360 degrees")
    started = time.perf_counter()
    S1 = (1700.0, 0.0)
    cfg = q2.Q2Config(circle_sides=1440, eps_rec_cert_m=1e-3, lmin_m=50.0)
    p1 = q2.build_P1_bound(S1, 0.0, cfg)
    angles = [index * step_deg for index in range(round(360.0 / step_deg))]
    points = [boundary_point(angle, S1, cfg.lmin_m) for angle in angles]
    accelerator = StrictCertificateAccelerator(PhysicalCertificateTree(p1, S1, cfg), cfg)
    certificate_started = time.perf_counter()
    certificate_batch = accelerator.certify_points(points, 0.0)
    certificate_runtime = time.perf_counter() - certificate_started
    certificates = certificate_batch["certificates"]
    sources = q2.build_Gext(p1, S1, 20.0)
    records = []
    screen_runtime = m4_runtime = 0.0
    for angle, point in zip(angles, points):
        certificate = certificates[point]
        record = {
            "phi_deg": angle, "S2": list(point),
            "radius_error_m": abs(math.dist(point, S1) - cfg.lmin_m),
            "T2_exact_by_Lmin_s": 10.0,
            "certificate": {k: certificate.get(k) for k in
                            ("status", "strict_receive", "L_rec_m", "U_rec_m", "eps_rec_cert_m", "reason")},
            "cheap_screen": None, "M4": None, "boundary_C20": False,
        }
        status = certificate["status"]
        if status != "CERTIFIED_STRICT":
            record["angle_status"] = ("CERTIFIED_VIOLATION" if status == "CERTIFIED_VIOLATION"
                                      else "CERTIFICATE_" + status)
            records.append(record); continue
        screen_started = time.perf_counter()
        screen = q2.screen_candidate_c20(point, S1, p1, sources, cfg)
        screen_runtime += time.perf_counter() - screen_started
        record["cheap_screen"] = screen
        if screen["screen_status"] == "PROVEN_NOT_C20":
            record["angle_status"] = "STRICT_NOT_C20"
            records.append(record); continue
        m4_started = time.perf_counter()
        evaluation = q2.evaluate_candidate_nested(point, S1, p1, cfg, certificate_override=certificate)
        m4_runtime += time.perf_counter() - m4_started
        candidate = evaluation.get("candidate")
        valid = _m4_pass(evaluation)
        record["M4"] = {
            "status": evaluation.get("status"), "source_convergence": evaluation.get("source_convergence"),
            "error_convergence": evaluation.get("error_convergence"),
            "JD": None if candidate is None else candidate.JD,
            "JR": None if candidate is None else candidate.JR,
            "JA": None if candidate is None else candidate.JA,
            "official20": None if candidate is None else candidate.official20,
            "operational17": None if candidate is None else candidate.operational17,
            "source_history": evaluation.get("source_history"), "error_history": evaluation.get("error_history"),
            "gverify": evaluation.get("gverify"),
            "replay": {k: v.get("status") for k, v in evaluation.get("replay", {}).items()},
            "warnings": evaluation.get("warnings", []),
        }
        record["boundary_C20"] = bool(valid and candidate is not None and candidate.official20 is True)
        record["angle_status"] = "STRICT_C20" if record["boundary_C20"] else (
            "STRICT_NOT_C20" if valid else "STRICT_M4_UNRESOLVED")
        records.append(record)

    # Fixed deterministic legacy checks, including both half-planes and wrap adjacency.
    check_angles = (0.0, 46.0, 90.0, 180.0, 270.0, 358.0)
    equivalence = []
    for angle in check_angles:
        point = boundary_point(angle, S1, cfg.lmin_m)
        legacy = q2.certified_strict(point, p1, S1, cfg)
        accelerated = certificates[point]
        equivalence.append({"phi_deg": angle, "legacy": legacy["status"],
                            "accelerated": accelerated["status"],
                            "consistent": legacy["status"] == accelerated["status"]})
    c20_angles = [r["phi_deg"] for r in records if r["boundary_C20"]]
    arcs = sampled_circular_arcs(c20_angles, step_deg)
    evaluated = [r for r in records if r["M4"] is not None and r["M4"]["status"] == "PASS"]
    secondary = None if not c20_angles else min(
        (r for r in evaluated if r["boundary_C20"]),
        key=lambda r: (r["M4"]["JR"], r["M4"]["JD"], r["S2"][0], r["S2"][1]),
    )
    payload = {
        "artifact_status": LABEL, "phase": "Q2_M6A.7b_BRANCH_DISCOVERY",
        "case": "REPRESENTATIVE_CASE / NOT_UNIQUE_PROBLEM_ANSWER",
        "step_deg": step_deg, "angle_count": len(angles), "full_circle_covered": True,
        "T2_exact_by_Lmin_s": 10.0, "records": records,
        "C20_boundary_sample_angles": c20_angles,
        "sampled_connected_arcs": arcs, "arc_count": len(arcs),
        "secondary_diagnostic_best": secondary,
        "next_refinement_arcs": arcs,
        "certificate_counts": {status: sum(r["certificate"]["status"] == status for r in records)
                               for status in ("CERTIFIED_STRICT", "CERTIFIED_VIOLATION", "UNCERTAIN_BOUNDARY", "UNRESOLVED")},
        "angle_status_counts": {status: sum(r["angle_status"] == status for r in records)
                                for status in sorted({r["angle_status"] for r in records})},
        "certificate_acceleration": {k: certificate_batch.get(k) for k in
                                     ("full_certificate_calls_this_batch", "propagated_strict_points",
                                      "propagated_violation_points", "shared_tree_nodes")},
        "legacy_accelerated_checks": equivalence,
        "legacy_accelerated_conflicts": sum(not x["consistent"] for x in equivalence),
        "runtime": {"certificate_s": certificate_runtime, "cheap_screen_s": screen_runtime,
                    "full_M4_s": m4_runtime, "total_s": time.perf_counter() - started},
        "standards_reduced": False, "final_secondary_optimum_signed_off": False,
        "warnings": [],
    }
    path = Path(output_path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


__all__ = ["boundary_point", "sampled_circular_arcs", "run_boundary_scan"]
