"""Q2 M6A convergence/sensitivity validation (not final Q2 results).

The helpers in this module aggregate already model-aligned M1--M5B engines.
They do not alter the zero receive threshold, selection rule, or risk semantics.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass, replace
import json
import math
from pathlib import Path
import time
from typing import Callable, Mapping, Optional, Sequence

from q2_selection import (
    CandidateCell,
    CandidateResult,
    Q2Config,
    build_P1_bound,
    classify_receive_certificate_bounds,
    evaluate_candidate_nested,
    integrate_qarea,
    relchg,
    search_strict_candidates,
    select_from_evaluated,
)


Point = tuple[float, float]
VALIDATION_LABEL = "VALIDATION / NOT_FINAL_Q2_RESULT"


def _jsonable(value):
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _selected_record(candidate: Optional[CandidateResult]) -> Optional[dict]:
    if candidate is None:
        return None
    return {
        "S2": list(candidate.S2),
        "JD": candidate.JD,
        "JR": candidate.JR,
        "JA": candidate.JA,
        "T2": candidate.T2,
        "official20": candidate.official20,
        "operational17": candidate.operational17,
    }


def _status_counts(cells: Sequence[CandidateCell]) -> dict:
    names = ("CERTIFIED_STRICT", "CERTIFIED_VIOLATION", "UNCERTAIN_BOUNDARY", "UNRESOLVED")
    counts = {name: 0 for name in names}
    for cell in cells:
        status = None if cell.certificate is None else cell.certificate.get("status")
        if status == "CERTIFIED_VIOLATION_SAMPLE":
            status = "CERTIFIED_VIOLATION"
        if status in counts:
            counts[status] += 1
        elif "UNRESOLVED" in cell.status:
            counts["UNRESOLVED"] += 1
    return counts


def _component_signature(cells: Sequence[CandidateCell]) -> list[dict]:
    strict = {
        (cell.ix, cell.iy): cell
        for cell in cells
        if cell.certificate is not None
        and cell.certificate.get("status") == "CERTIFIED_STRICT"
        and cell.center_in_move_domain
    }
    components = []
    while strict:
        seed = min(strict)
        stack = [seed]
        points = []
        while stack:
            key = stack.pop()
            cell = strict.pop(key, None)
            if cell is None:
                continue
            points.append(cell.center)
            ix, iy = key
            stack.extend(((ix - 1, iy), (ix + 1, iy), (ix, iy - 1), (ix, iy + 1)))
        xs, ys = [point[0] for point in points], [point[1] for point in points]
        components.append({
            "point_count": len(points),
            "bbox": [min(xs), min(ys), max(xs), max(ys)],
            "centroid": [sum(xs) / len(xs), sum(ys) / len(ys)],
        })
    return sorted(components, key=lambda item: (-item["point_count"], item["centroid"]))


def summarize_search(search: Mapping[str, object]) -> dict:
    """Produce per-level convergence records from one 50/20/5 search."""

    records = []
    region_cells = list(search["region_cells"])
    objective_cells = list(search["objective_cells"])
    diagnostics = {
        float(level): item
        for level, item in zip(search["candidate_levels_m"], search["level_diagnostics"])
    }
    for level in (50.0, 20.0, 5.0):
        region = [cell for cell in region_cells if cell.level_m == level]
        objective = [cell for cell in objective_cells if cell.level_m == level]
        evaluated = [
            cell.m4_result["candidate"] for cell in objective
            if cell.m4_result is not None and cell.m4_result.get("status") == "PASS"
        ]
        selection = select_from_evaluated(evaluated)
        selected = selection["selected_strict"]
        records.append({
            "grid_level_m": level,
            "selected": _selected_record(selected),
            "Cstrict_count": len(selection["Cstrict"]),
            "C20_count": len(selection["C20"]),
            "uncertain_count": sum(
                cell.status in {
                    "BOUNDARY_OR_UNRESOLVED", "OMEGA_BOUNDARY_UNRESOLVED",
                    "LMIN_BOUNDARY", "EVALUATION_UNRESOLVED",
                }
                for cell in region
            ),
            "certificate_status_counts": _status_counts(region),
            "Fstrict_components": _component_signature(region),
            "region_candidate_count": len(region),
            "objective_candidate_count": len(objective),
            "runtime_s": diagnostics.get(level, {}).get("runtime_s"),
        })
    return {
        "levels": records,
        "selected": _selected_record(search["selection"]["selected_strict"]),
        "Cstrict_count": len(search["selection"]["Cstrict"]),
        "C20_count": len(search["selection"]["C20"]),
        "runtime_s": search["runtime_s"],
        "near_optimal_components": _jsonable(search["near_optimal_components"]),
    }


def assess_circle_sensitivity(coarse: Mapping[str, object], fine: Mapping[str, object]) -> dict:
    selected_a, selected_b = coarse.get("selected"), fine.get("selected")
    warnings = []
    if bool(coarse.get("C20_count")) != bool(fine.get("C20_count")):
        warnings.append("CIRCLE_DISCRETIZATION_SENSITIVE")
    for field in ("official20", "operational17"):
        if selected_a is not None and selected_b is not None and selected_a.get(field) != selected_b.get(field):
            warnings.append("CIRCLE_DISCRETIZATION_SENSITIVE")
    rel_d = None if selected_a is None or selected_b is None else relchg(selected_a["JD"], selected_b["JD"])
    rel_r = None if selected_a is None or selected_b is None else relchg(selected_a["JR"], selected_b["JR"])
    bracket_ok = fine["P1_area_bracket_m2"] <= coarse["P1_area_bracket_m2"] + 1.0e-12
    metrics_ok = rel_d is not None and rel_r is not None and rel_d <= 1.0e-3 and rel_r <= 1.0e-3
    same_main_component = coarse.get("main_component_id") == fine.get("main_component_id")
    if not metrics_ok or not bracket_ok or not same_main_component:
        warnings.append("CIRCLE_DISCRETIZATION_SENSITIVE")
    warnings = sorted(set(warnings))
    return {
        "status": "PASS" if not warnings else "CIRCLE_DISCRETIZATION_SENSITIVE",
        "relchg_JD": rel_d,
        "relchg_JR": rel_r,
        "P1_bracket_nonincreasing": bracket_ok,
        "same_main_component": same_main_component,
        "warnings": warnings,
    }


def assess_candidate_convergence(records: Sequence[Mapping[str, object]]) -> dict:
    by_level = {float(item["grid_level_m"]): item for item in records}
    a, b = by_level.get(20.0), by_level.get(5.0)
    warnings = []
    if a is None or b is None or a.get("selected") is None or b.get("selected") is None:
        return {"status": "UNRESOLVED", "warnings": ["CANDIDATE_CONVERGENCE_UNRESOLVED"]}
    rels = {field: relchg(a["selected"][field], b["selected"][field]) for field in ("T2", "JD", "JR")}
    if any(value > 1.0e-3 for value in rels.values()):
        warnings.append("CANDIDATE_GRID_SENSITIVE")
    if not b.get("Fstrict_components"):
        warnings.append("CANDIDATE_CONVERGENCE_UNRESOLVED")
    return {
        "status": "PASS" if not warnings else (
            "CANDIDATE_GRID_SENSITIVE" if "CANDIDATE_GRID_SENSITIVE" in warnings else "UNRESOLVED"
        ),
        "relchg_20_to_5": rels,
        "final_competitive_branch_fully_refined": b.get("selected") is not None,
        "Fstrict_components_at_5m": len(b.get("Fstrict_components", [])),
        "warnings": warnings,
    }


def assess_eps_cert_sensitivity(records: Sequence[Mapping[str, object]]) -> dict:
    if not records:
        return {"status": "UNRESOLVED", "warnings": ["EPS_REC_CERT_SENSITIVITY_UNRESOLVED"]}
    selected = [None if item.get("selected") is None else tuple(item["selected"]["S2"]) for item in records]
    main_regions = [repr(item.get("main_component_id")) for item in records]
    stable_metrics = True
    base = records[0].get("selected")
    for item in records[1:]:
        current = item.get("selected")
        if base is None or current is None:
            stable_metrics = base is current
        else:
            stable_metrics = stable_metrics and relchg(base["JD"], current["JD"]) <= 1.0e-3
            stable_metrics = stable_metrics and relchg(base["JR"], current["JR"]) <= 1.0e-3
            stable_metrics = stable_metrics and relchg(base["T2"], current["T2"]) <= 1.0e-3
    same_selection = len(set(selected)) == 1
    same_region = len(set(main_regions)) == 1
    if same_selection and same_region and stable_metrics:
        count_signatures = [item.get("certificate_status_counts") for item in records]
        status = "PASS" if all(value == count_signatures[0] for value in count_signatures) else "STABLE_WITH_BOUNDARY_VARIATION"
        return {"status": status, "warnings": []}
    return {"status": "EPS_REC_CERT_SENSITIVE", "warnings": ["EPS_REC_CERT_SENSITIVE"]}


def assess_lmin_sensitivity(records: Sequence[Mapping[str, object]]) -> dict:
    warnings = []
    c20_exists = [bool(item.get("C20_count")) for item in records]
    if len(set(c20_exists)) > 1:
        warnings.append("LMIN_SENSITIVE")
    metrics = [item.get("selected") for item in records if item.get("selected") is not None]
    for first, second in zip(metrics, metrics[1:]):
        if relchg(first["JD"], second["JD"]) > 1.0e-3 or relchg(first["JR"], second["JR"]) > 1.0e-3:
            warnings.append("LMIN_SENSITIVE")
    warnings = sorted(set(warnings))
    return {"status": "PASS" if not warnings else "LMIN_SENSITIVE", "warnings": warnings}


def preserve_risk_threshold_status(coverage: Mapping[str, object]) -> dict:
    """Keep threshold-straddling M5B results unresolved during M6A."""

    return {
        "alpha_099_status": coverage["alpha_099_status"],
        "alpha_095_status": coverage["alpha_095_status"],
        "unresolved_count": sum(
            coverage[key] == "THRESHOLD_UNRESOLVED"
            for key in ("alpha_099_status", "alpha_095_status")
        ),
    }


def aggregate_t12(parts: Mapping[str, object]) -> dict:
    required = ("circle", "source_error", "candidate", "gverify", "replay", "monotone")
    states = {key: parts.get(key) for key in required}
    if any(value in {"FAIL", "SENSITIVE"} or (isinstance(value, str) and value.endswith("_SENSITIVE")) for value in states.values()):
        status = "FAIL"
    elif all(value == "PASS" for value in states.values()):
        status = "PASS"
    else:
        status = "UNRESOLVED"
    return {"T12_status": status, "requirements": states}


class _ValidationCache:
    def __init__(self):
        self.certificates = {}
        self.m4 = {}

    def certificate(self, S2, P1, S1, config):
        from q2_selection import certified_strict
        geometry_key = (tuple(S2), tuple(S1), config.circle_sides)
        if geometry_key not in self.certificates:
            fine = replace(config, eps_rec_cert_m=1.0e-4, eps_rec_m=None)
            self.certificates[geometry_key] = certified_strict(S2, P1, S1, fine)
        answer = dict(self.certificates[geometry_key])
        decision = classify_receive_certificate_bounds(
            answer["L_rec_m"], answer["U_rec_m"], config.eps_rec_cert_m
        )
        if decision != "CONTINUE":
            answer["status"] = decision
            answer["strict_receive"] = True if decision == "CERTIFIED_STRICT" else (
                False if decision == "CERTIFIED_VIOLATION" else None
            )
            answer["certified"] = decision in {"CERTIFIED_STRICT", "CERTIFIED_VIOLATION"}
        answer["eps_rec_cert_m"] = config.eps_rec_cert_m
        return answer

    def evaluate(self, S2, S1, P1, config):
        key = (tuple(S2), tuple(S1), config.circle_sides)
        if key not in self.m4:
            self.m4[key] = evaluate_candidate_nested(S2, S1, P1, config)
        return self.m4[key]


def _write(directory: Path, name: str, payload: Mapping[str, object]) -> None:
    value = dict(payload)
    value["artifact_status"] = VALIDATION_LABEL
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(_jsonable(value), ensure_ascii=False, indent=2), encoding="utf-8")


def write_m6a_runtime_blocked_reports(
    output_dir: str | Path,
    *,
    representative_case: Mapping[str, object],
    runtime_profile: Mapping[str, object],
) -> dict:
    """Write an honest M6A UNRESOLVED bundle after a bounded runtime stop."""

    directory = Path(output_dir)
    warning = "FULL_DOMAIN_RUNTIME_LIMIT_EXCEEDED"
    common = {
        "validation_status": "UNRESOLVED",
        "representative_case": dict(representative_case),
        "runtime_profile": dict(runtime_profile),
        "warnings": [warning],
    }
    payloads = {
        "convergence_circle.json": {**common, "runs": [], "assessment": {"status": "UNRESOLVED"}},
        "convergence_source_error.json": {**common, "selected": None, "all_final_competitors": []},
        "convergence_candidate.json": {**common, "levels": [], "assessment": {"status": "UNRESOLVED"}},
        "eps_rec_cert_sensitivity.json": {
            **common, "physical_threshold_m": 0.0, "eps_rec_cert_values_m": [1e-4, 1e-3, 1e-2],
            "runs": [], "assessment": {"status": "UNRESOLVED"},
        },
        "lmin_sensitivity.json": {
            **common, "design_parameter_not_official": True, "lmin_values_m": [20, 50, 100, 150],
            "runs": [], "assessment": {"status": "UNRESOLVED"},
        },
        "area_risk_refinement.json": {
            **common, "refined_candidates": [], "threshold_unresolved_count": None,
            "reason": "not_started_after_full_domain_runtime_stop",
        },
        "T12_report.json": {
            **common, "T12_status": "UNRESOLVED",
            "requirements": {key: "NOT_RUN" for key in (
                "circle", "source_error", "candidate", "gverify", "replay", "monotone"
            )},
        },
        "M6A_summary.json": {
            **common,
            "scope": "representative case; method validation, not a unique problem answer",
            "M6A_status": "UNRESOLVED",
            "T12_status": "UNRESOLVED",
            "M6B_status": "BLOCKED_PENDING_M6A",
            "entry_to_M6B": False,
        },
    }
    for name, payload in payloads.items():
        _write(directory, name, payload)
    return payloads["M6A_summary.json"]


def run_m6a_validation(
    S1: Sequence[float] = (1700.0, 0.0),
    theta1_hat_deg: float = 0.0,
    *,
    output_dir: str | Path = "03_results/q2/m6_validation",
    omega_move: Optional[Sequence[Point]] = None,
    search_fn: Callable = search_strict_candidates,
    progress_fn: Optional[Callable[[str], None]] = None,
) -> dict:
    """Run M6A on a clearly labelled representative case."""

    started = time.perf_counter()
    directory = Path(output_dir)
    cache = _ValidationCache()
    search_cache = {}
    base = Q2Config(omega_move=omega_move)

    def run(config: Q2Config, label: str) -> tuple[dict, dict]:
        key = (config.circle_sides, config.eps_rec_cert_m, config.lmin_m)
        if key in search_cache:
            if progress_fn is not None:
                progress_fn(f"REUSE {label}")
            return search_cache[key]
        if progress_fn is not None:
            progress_fn(f"START {label}")
        run_started = time.perf_counter()
        p1 = build_P1_bound(S1, theta1_hat_deg, config)
        search = search_fn(
            S1, theta1_hat_deg, config, P1_bound=p1,
            certificate_fn=cache.certificate, m4_fn=cache.evaluate,
        )
        snapshot = summarize_search(search)
        snapshot.update({
            "circle_sides": config.circle_sides,
            "eps_rec_cert_m": config.eps_rec_cert_m,
            "lmin_m": config.lmin_m,
            "P1_out_area_m2": p1["P1_out_area_m2"],
            "P1_in_area_m2": p1["P1_in_area_m2"],
            "P1_area_bracket_m2": p1["area_discretization_gap_m2"],
            "main_component_id": (
                None if not snapshot["levels"][-1]["Fstrict_components"]
                else snapshot["levels"][-1]["Fstrict_components"][0]["bbox"]
            ),
        })
        if progress_fn is not None:
            progress_fn(f"DONE {label} runtime_s={time.perf_counter() - run_started:.3f}")
        search_cache[key] = (search, snapshot)
        return search, snapshot

    baseline_search, baseline = run(base, "circle1440_baseline")
    fine_search, fine_circle = run(replace(base, circle_sides=2880), "circle2880")
    circle_assessment = assess_circle_sensitivity(baseline, fine_circle)
    circle_report = {"representative_case": {"S1": list(S1), "theta1_hat_deg": theta1_hat_deg},
                     "runs": [baseline, fine_circle], "assessment": circle_assessment}

    candidate_assessment = assess_candidate_convergence(baseline["levels"])
    candidate_report = {"levels": baseline["levels"], "assessment": candidate_assessment,
                        "near_optimal_components": baseline["near_optimal_components"]}

    selected = baseline_search["selection"]["selected_strict"]
    evaluated_m4 = [
        cell.m4_result for cell in baseline_search["objective_cells"]
        if cell.level_m == 5.0 and cell.m4_result is not None
    ]
    selected_m4 = None
    if selected is not None:
        selected_m4 = next((item for item in evaluated_m4 if item["candidate"].S2 == selected.S2), None)
    source_error_report = {
        "selected": _selected_record(selected),
        "selected_source_history": None if selected_m4 is None else selected_m4["source_history"],
        "selected_error_history": None if selected_m4 is None else selected_m4["error_history"],
        "all_final_competitors": [
            {"S2": list(item["candidate"].S2), "status": item["status"],
             "source_convergence": item["source_convergence"], "error_convergence": item["error_convergence"],
             "gverify": item["gverify"], "replay": item["replay"], "warnings": item["warnings"]}
            for item in evaluated_m4
        ],
    }

    eps_records = []
    for value in (1.0e-4, 1.0e-3, 1.0e-2):
        _, snapshot = run(replace(base, eps_rec_cert_m=value), f"eps_rec_cert_{value:g}")
        eps_records.append(snapshot)
    eps_report = {"physical_threshold_m": 0.0, "runs": eps_records,
                  "assessment": assess_eps_cert_sensitivity(eps_records)}

    lmin_records = []
    for value in (20.0, 50.0, 100.0, 150.0):
        _, snapshot = run(replace(base, lmin_m=value), f"lmin_{value:g}")
        lmin_records.append(snapshot)
    lmin_report = {"design_parameter_not_official": True, "runs": lmin_records,
                   "assessment": assess_lmin_sensitivity(lmin_records)}

    risk_candidates = []
    if selected is not None:
        risk_cfg = replace(base, max_area_refine_rounds=7, area_cell_budget=1_000_000)
        risk_started = time.perf_counter()
        coverage = integrate_qarea(
            selected.S2, S1, build_P1_bound(S1, theta1_hat_deg, risk_cfg), risk_cfg
        )
        risk_candidates.append({**coverage.to_dict(), "runtime_s": time.perf_counter() - risk_started})
    risk_report = {
        "refined_candidates": risk_candidates,
        "threshold_unresolved_count": sum(
            preserve_risk_threshold_status(item)["unresolved_count"] for item in risk_candidates
        ),
    }

    gverify_status = "PASS" if selected_m4 is not None and selected_m4["gverify"]["status"] == "PASS" else "UNRESOLVED"
    replay_status = "PASS" if selected_m4 is not None and all(
        item["status"] == "PASS" for item in selected_m4["replay"].values()
    ) else "UNRESOLVED"
    source_error_status = "PASS" if selected_m4 is not None and (
        selected_m4["source_convergence"] == "PASS" and selected_m4["error_convergence"] == "PASS"
    ) else "UNRESOLVED"
    monotone_status = "PASS" if selected_m4 is not None and "NON_MONOTONE_REFINEMENT" not in selected_m4["warnings"] else "UNRESOLVED"
    t12 = aggregate_t12({
        "circle": circle_assessment["status"],
        "source_error": source_error_status,
        "candidate": candidate_assessment["status"],
        "gverify": gverify_status,
        "replay": replay_status,
        "monotone": monotone_status,
    })
    warnings = sorted(set(
        circle_assessment["warnings"] + candidate_assessment["warnings"]
        + eps_report["assessment"]["warnings"] + lmin_report["assessment"]["warnings"]
    ))
    runtime = time.perf_counter() - started
    summary = {
        "scope": "representative case; method validation, not a unique problem answer",
        "representative_case": {"S1": list(S1), "theta1_hat_deg": theta1_hat_deg,
                                "omega_move": _jsonable(omega_move)},
        "T12_status": t12["T12_status"],
        "circle_status": circle_assessment["status"],
        "candidate_status": candidate_assessment["status"],
        "eps_rec_cert_sensitivity": eps_report["assessment"]["status"],
        "lmin_sensitivity": lmin_report["assessment"]["status"],
        "risk_threshold_unresolved_count": risk_report["threshold_unresolved_count"],
        "gverify": gverify_status,
        "replay": replay_status,
        "runtime_s": runtime,
        "warnings": warnings,
        "M6B_status": "PENDING",
    }
    for name, payload in (
        ("convergence_circle.json", circle_report),
        ("convergence_source_error.json", source_error_report),
        ("convergence_candidate.json", candidate_report),
        ("eps_rec_cert_sensitivity.json", eps_report),
        ("lmin_sensitivity.json", lmin_report),
        ("area_risk_refinement.json", risk_report),
        ("T12_report.json", t12),
        ("M6A_summary.json", summary),
    ):
        _write(directory, name, payload)
    return summary


__all__ = [
    "VALIDATION_LABEL", "aggregate_t12", "assess_candidate_convergence",
    "assess_circle_sensitivity", "assess_eps_cert_sensitivity",
    "assess_lmin_sensitivity", "preserve_risk_threshold_status",
    "run_m6a_validation", "summarize_search", "write_m6a_runtime_blocked_reports",
]
