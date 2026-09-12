"""Complete 1440-only representative baseline validation for Q2 M6A.3."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import math
from pathlib import Path
import time

import q2_selection as q2
from q2_certificate_acceleration import PhysicalCertificateTree, StrictCertificateAccelerator


LABEL = "VALIDATION / NOT_FINAL_Q2_RESULT"


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


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dict(payload)
    data["artifact_status"] = LABEL
    path.write_text(json.dumps(_jsonable(data), ensure_ascii=False, indent=2), encoding="utf-8")


def _selected(candidate):
    if candidate is None:
        return None
    return {key: getattr(candidate, key) for key in ("S2", "T2", "JD", "JR", "JA", "official20", "operational17")}


def assess_20_to_5(level20: dict, level5: dict) -> dict:
    a, b = level20.get("best_C20"), level5.get("best_C20")
    if a is None or b is None:
        return {"status": "UNRESOLVED", "relchg": None}
    changes = {name: q2.relchg(a[name], b[name]) for name in ("T2", "JD", "JR")}
    return {"status": "PASS" if all(v <= 1e-3 for v in changes.values()) else "CANDIDATE_GRID_SENSITIVE", "relchg": changes}


def selected_verification_pass(result: dict) -> bool:
    return (
        result.get("status") == "PASS"
        and result.get("source_convergence") == "PASS"
        and result.get("error_convergence") == "PASS"
        and result.get("gverify", {}).get("status") == "PASS"
        and all(item.get("status") == "PASS" for item in result.get("replay", {}).values())
        and "NON_MONOTONE_REFINEMENT" not in result.get("warnings", [])
    )


def assess_unresolved_competition(final_cells, selected, S1) -> dict:
    """Hard gate: unresolved receive cells must not be able to beat the selected C20 point.

    For a cell with center c and half-diagonal r, every point in the cell obeys
    T2 >= max(0, ||c-S1||-r)/5.  The comparison tolerance intentionally matches
    the existing objective-refinement tolerance in q2_selection.
    """

    uncertain = []
    for cell in final_cells:
        status = None if cell.certificate is None else cell.certificate.get("status")
        if status not in {"UNRESOLVED", "UNCERTAIN_BOUNDARY"}:
            continue
        x0, y0, x1, y1 = cell.bbox
        half_diagonal = 0.5 * math.hypot(x1 - x0, y1 - y0)
        lower_t2 = max(0.0, math.hypot(cell.center[0] - S1[0], cell.center[1] - S1[1]) - half_diagonal) / q2.SPEED_MPS
        uncertain.append({
            "cell_id": cell.cell_id,
            "certificate_status": status,
            "center": list(cell.center),
            "bbox": list(cell.bbox),
            "half_diagonal_m": half_diagonal,
            "T2_lower_s": lower_t2,
        })

    if not uncertain:
        return {
            "status": "PASS",
            "uncertain_count": 0,
            "competitive_count": 0,
            "selected_T2_s": None if selected is None else selected.T2,
            "T2_tolerance_s": None,
            "cells": [],
        }

    if selected is None or selected.official20 is not True:
        competitive = uncertain
        tolerance = None
        mode = "NO_FINAL_C20_ALL_UNCERTAIN_COMPETITIVE"
    else:
        tolerance = 1.0e-3 * max(1.0, selected.T2)
        competitive = [item for item in uncertain if item["T2_lower_s"] <= selected.T2 + tolerance]
        mode = "C20_T2_LOWER_BOUND"

    return {
        "status": "PASS" if not competitive else "UNRESOLVED_COMPETITIVE",
        "mode": mode,
        "uncertain_count": len(uncertain),
        "competitive_count": len(competitive),
        "selected_T2_s": None if selected is None else selected.T2,
        "T2_tolerance_s": tolerance,
        "cells": uncertain,
        "competitive_cell_ids": [item["cell_id"] for item in competitive],
    }


def run_1440_baseline(output_dir="03_results/q2/m6_validation/1440_baseline") -> dict:
    directory = Path(output_dir)
    started = time.perf_counter()
    S1 = (1700.0, 0.0)
    config = q2.Q2Config(circle_sides=1440, eps_rec_cert_m=1e-3, lmin_m=50.0)
    p1 = q2.build_P1_bound(S1, 0.0, config)
    engine = StrictCertificateAccelerator(PhysicalCertificateTree(p1, S1, config), config)
    levels = {}

    def checkpoint(level, cells, diagnostics, c20_cells):
        evaluated = [
            cell.m4_result["candidate"] for cell in cells
            if cell.m4_result is not None and cell.m4_result.get("status") == "PASS"
        ]
        selection = q2.select_from_evaluated(evaluated)
        payload = {
            "case": "REPRESENTATIVE_CASE / NOT_UNIQUE_PROBLEM_ANSWER",
            "grid_level_m": level,
            "region_candidate_count": len(cells),
            "objective_candidate_count": sum(cell.objective_refinement for cell in cells),
            "diagnostics": diagnostics,
            "Cstrict_evaluated_count": len(selection["Cstrict"]),
            "C20_evaluated_count": len(selection["C20"]),
            "best_C20": _selected(selection["selected_strict"] if selection["C20"] else None),
            "Fstrict_component_count": len(q2._strict_components(cells)),
        }
        levels[float(level)] = payload
        _write(directory / f"level_{int(level)}.json", payload)

    search = q2.search_strict_candidates(
        S1, 0.0, config, P1_bound=p1,
        certificate_batch_engine=engine, pass_certificate_to_m4=True,
        lazy_objective=True, level_checkpoint_fn=checkpoint,
    )
    selected = search["selection"]["selected_strict"]
    convergence = assess_20_to_5(levels[20.0], levels[5.0])
    _write(directory / "candidate_convergence.json", convergence)

    verification = None
    if selected is not None:
        fresh_p1 = q2.build_P1_bound(S1, 0.0, config)
        verification = q2.evaluate_candidate_nested(selected.S2, S1, fresh_p1, config)
    verification_payload = {
        "selected": _selected(selected),
        "independent_full_M4": verification,
        "gate": "PASS" if verification is not None and selected_verification_pass(verification) else "FAIL",
    }
    _write(directory / "selected_verification.json", verification_payload)

    final_cells = [cell for cell in search["region_cells"] if cell.level_m == 5.0]
    unresolved_gate = assess_unresolved_competition(final_cells, selected, S1)
    _write(directory / "unresolved_competitive_gate.json", unresolved_gate)

    features = []
    for cell in final_cells:
        status = None if cell.certificate is None else cell.certificate.get("status")
        if status == "CERTIFIED_STRICT":
            geometry = {"type": "Point", "coordinates": list(cell.center)}
            representation = "point_certified"
        elif cell.boundary_flag or status in {"UNCERTAIN_BOUNDARY", "UNRESOLVED"}:
            x0, y0, x1, y1 = cell.bbox
            geometry = {"type": "Polygon", "coordinates": [[[x0,y0],[x1,y0],[x1,y1],[x0,y1],[x0,y0]]]}
            representation = "uncertainty_cell"
        else:
            continue
        features.append({"type": "Feature", "geometry": geometry, "properties": {
            "cell_id": cell.cell_id, "grid_level_m": 5.0,
            "certificate_status": status, "representation": representation,
        }})
    geo = {"type": "FeatureCollection", "artifact_status": LABEL, "features": features}
    _write(directory / "Fstrict_1440_validation.geojson", geo)

    warnings = []
    if convergence["status"] != "PASS":
        warnings.append(convergence["status"])
    if verification_payload["gate"] != "PASS":
        warnings.append("SELECTED_REVALIDATION_FAIL")
    if unresolved_gate["status"] != "PASS":
        warnings.append("UNRESOLVED_COMPETITIVE")
    runtime = time.perf_counter() - started
    status = "PASS" if selected is not None and not warnings and all(level in levels for level in (50.0,20.0,5.0)) else "FAIL"
    summary = {
        "case": "REPRESENTATIVE_CASE / NOT_UNIQUE_PROBLEM_ANSWER",
        "status": status, "selected": _selected(selected),
        "Cstrict_final_evaluated": len(search["selection"]["Cstrict"]),
        "C20_final_evaluated": len(search["selection"]["C20"]),
        "pareto_size": len(search["selection"]["pareto"]),
        "candidate_convergence": convergence["status"],
        "source_convergence": None if verification is None else verification["source_convergence"],
        "error_convergence": None if verification is None else verification["error_convergence"],
        "Gverify": None if verification is None else verification["gverify"]["status"],
        "replay": None if verification is None else {k:v["status"] for k,v in verification["replay"].items()},
        "monotone": verification is not None and "NON_MONOTONE_REFINEMENT" not in verification["warnings"],
        "unresolved_competitive_gate": unresolved_gate["status"],
        "unresolved_count": unresolved_gate["uncertain_count"],
        "competitive_unresolved_count": unresolved_gate["competitive_count"],
        "Fstrict_component_count": levels.get(5.0, {}).get("Fstrict_component_count"),
        "runtime_s": runtime, "warnings": warnings,
        "T12_status": "UNRESOLVED_PENDING_2880" if status == "PASS" else "UNRESOLVED",
        "entry_to_2880_comparison": status == "PASS",
    }
    _write(directory / "runtime_breakdown.json", {"levels": levels, "total_runtime_s": runtime})
    _write(directory / "summary.json", summary)
    return summary


__all__ = [
    "assess_20_to_5", "assess_unresolved_competition",
    "run_1440_baseline", "selected_verification_pass",
]
