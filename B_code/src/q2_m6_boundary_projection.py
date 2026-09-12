"""M6A.7a radial Lmin-boundary revalidation for two representative candidates."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import math
from pathlib import Path
import time

import q2_selection as q2


LABEL = "VALIDATION / DIAGNOSTIC / NOT_FINAL_Q2_RESULT"
ORIGINAL_CANDIDATES = ((1710.0, -50.0), (1727.5, -42.5))


def radial_project_to_lmin(S2, S1=(1700.0, 0.0), lmin_m=50.0):
    dx, dy = float(S2[0]) - S1[0], float(S2[1]) - S1[1]
    radius = math.hypot(dx, dy)
    if radius == 0.0:
        raise ValueError("cannot radially project S1 itself")
    scale = float(lmin_m) / radius
    return (S1[0] + scale * dx, S1[1] + scale * dy)


def _jsonable(value):
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def revalidate_projected_candidate(original_S2, config=None, S1=(1700.0, 0.0), theta1_hat_deg=0.0):
    cfg = config or q2.Q2Config(circle_sides=1440, eps_rec_cert_m=1e-3, lmin_m=50.0)
    projected = radial_project_to_lmin(original_S2, S1, cfg.lmin_m)
    original_radius = math.dist(original_S2, S1)
    projected_radius = math.dist(projected, S1)
    fresh_p1 = q2.build_P1_bound(S1, theta1_hat_deg, cfg)
    certificate = q2.certified_strict(projected, fresh_p1, S1, cfg)
    evaluation = q2.evaluate_candidate_nested(projected, S1, fresh_p1, cfg)
    candidate = evaluation.get("candidate")
    gverify = evaluation.get("gverify", {})
    replay = evaluation.get("replay", {})
    replay_pass = all(replay.get(metric, {}).get("status") == "PASS" for metric in ("JD", "JR", "JA"))
    gates = {
        "strict": certificate.get("status") == "CERTIFIED_STRICT",
        "M4": evaluation.get("status") == "PASS",
        "source": evaluation.get("source_convergence") == "PASS",
        "error": evaluation.get("error_convergence") == "PASS",
        "Gverify": gverify.get("status") == "PASS",
        "replay": replay_pass,
        "official20": candidate is not None and candidate.official20 is True,
    }
    near_count = sum(
        item.get("status") == "NEAR_TERMINAL"
        for item in evaluation.get("scenario_records", [])
    )
    return {
        "original_S2": list(original_S2), "projected_S2": list(projected),
        "original_radius_from_S1_m": original_radius,
        "projected_radius_from_S1_m": projected_radius,
        "radial_projection_error_m": abs(projected_radius - cfg.lmin_m),
        "T2_numeric_s": projected_radius / q2.SPEED_MPS,
        "T2_exact_by_Lmin_s": cfg.lmin_m / q2.SPEED_MPS,
        "certificate": certificate, "M4": evaluation,
        "metrics": None if candidate is None else {
            "JD": candidate.JD, "JR": candidate.JR, "JA": candidate.JA,
            "official20": candidate.official20, "operational17": candidate.operational17,
        },
        "gates": gates, "boundary_C20": all(gates.values()),
        "near_terminal_scenario_count": near_count,
        "near_semantics": "NEAR_TERMINAL uses P2=P1_bound intersect B(S2,5); no bearing is fabricated",
    }


def run_boundary_projection_validation(output_path="03_results/q2/m6_validation/lmin_boundary_projection.json"):
    started = time.perf_counter()
    cfg = q2.Q2Config(circle_sides=1440, eps_rec_cert_m=1e-3, lmin_m=50.0)
    results = [revalidate_projected_candidate(point, cfg) for point in ORIGINAL_CANDIDATES]
    witnesses = [item for item in results if item["boundary_C20"]]
    unresolved = any(
        item["certificate"].get("status") in {"UNRESOLVED", "UNCERTAIN_BOUNDARY"}
        or item["M4"].get("status") != "PASS" for item in results
    )
    exists = True if witnesses else ("unresolved" if unresolved else False)
    payload = {
        "artifact_status": LABEL,
        "case": "REPRESENTATIVE_CASE / NOT_UNIQUE_PROBLEM_ANSWER",
        "boundary_witness_exists": exists,
        "T2_lower_bound_from_Lmin_s": 10.0,
        "T2_feasible_witness_s": 10.0 if witnesses else None,
        "T2_optimality_conclusion": "PROVED_T2_STAR_EQ_10" if witnesses else
            ("UNRESOLVED" if unresolved else "NO_BOUNDARY_C20_WITNESS_FOUND"),
        "candidates": results, "runtime_s": time.perf_counter() - started,
        "strict_physical_threshold_m": 0.0,
        "eps_rec_cert_m": cfg.eps_rec_cert_m,
        "warnings": [] if witnesses else ["NO_CERTIFIED_BOUNDARY_C20_WITNESS"],
    }
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


__all__ = ["ORIGINAL_CANDIDATES", "radial_project_to_lmin",
           "revalidate_projected_candidate", "run_boundary_projection_validation"]
