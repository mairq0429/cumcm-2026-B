"""Local numerical refinement of the secondary boundary optimum (M6A.7c).

This module deliberately consumes the cached 2-degree scan.  It does not run a
new full-circle scan and does not alter the frozen selection rule.
"""
from __future__ import annotations

import csv, json, math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from q2_selection import (Q2Config, build_P1_bound, build_Gext,
                          certified_strict, screen_candidate_c20,
                          evaluate_candidate_nested)
from q2_m6_boundary_scan import boundary_point


def _angle(a: float) -> float:
    x = float(a) % 360.0
    return 0.0 if abs(x - 360.0) < 1e-10 else x


def _key(a: float) -> float:
    return round(_angle(a), 8)


def detect_local_minima(records: Sequence[Mapping[str, Any]], arcs=None):
    """Detect circular local JR minima among cached C20 records."""
    good = [r for r in records if r.get("boundary_C20") and isinstance((r.get("M4") or {}).get("JR"), (int, float))]
    if not good:
        return []
    ordered = sorted(good, key=lambda r: _angle(r["phi_deg"]))
    vals = [float(r["M4"]["JR"]) for r in ordered]
    out = []
    for i, r in enumerate(ordered):
        if vals[i] <= vals[(i - 1) % len(vals)] and vals[i] <= vals[(i + 1) % len(vals)]:
            branch = None
            if arcs:
                for j, arc in enumerate(arcs):
                    if _key(r["phi_deg"]) in {_key(x) for x in arc}:
                        branch = j; break
            out.append({"phi_deg": _angle(r["phi_deg"]), "JR": vals[i], "branch": branch})
    return out


def window_angles(phi0: float, half_width: float, step_deg: float):
    n = int(round((2 * half_width) / step_deg))
    vals = [_key(phi0 - half_width + i * step_deg) for i in range(n + 1)]
    return sorted(set(vals))


def _candidate_record(phi, point, cert, screen, ev, source):
    m4 = None
    if ev:
        c = ev.get("candidate") if isinstance(ev, Mapping) else None
        if c is not None:
            m4 = {k: getattr(c, k) for k in ("JD", "JR", "JA", "official20", "operational17")}
        elif isinstance(ev, Mapping):
            m4 = ev
    return {"phi_deg": _angle(phi), "S2": [float(point[0]), float(point[1])],
            "T2_exact_by_Lmin_s": 10.0, "certificate": cert,
            "cheap_screen": screen, "M4": m4,
            "boundary_C20": bool(m4 and m4.get("official20") is True),
            "angle_status": "STRICT_C20" if m4 and m4.get("official20") else
                            ("STRICT_NOT_C20" if cert.get("status") == "CERTIFIED_STRICT" else cert.get("status")),
            "source": source}


def _sort_key(r):
    m = r.get("M4") or {}
    return (float(m.get("JR", math.inf)), float(m.get("JD", math.inf)),
            float(r["S2"][0]), float(r["S2"][1]))


def run_secondary_refinement(scan_path: str | Path, out_dir: str | Path,
                            config: Q2Config | None = None,
                            medium_step: float = 0.5, fine_step: float = 0.1):
    config = config or Q2Config(circle_sides=1440, lmin_m=50.0)
    data = json.loads(Path(scan_path).read_text(encoding="utf-8"))
    records = data["records"]
    S1 = (1700.0, 0.0)
    p1 = build_P1_bound(S1, 0.0, config)
    sources = build_Gext(p1, S1, 20.0)
    arcs = data.get("sampled_connected_arcs", [])
    minima = detect_local_minima(records, arcs)
    # At least the two best minima per connected branch, capped at six seeds.
    seeds = []
    for b in sorted({m.get("branch") for m in minima}):
        seeds.extend(sorted([m for m in minima if m.get("branch") == b], key=lambda x: x["JR"])[:2])
    if not seeds: seeds = sorted(minima, key=lambda x: x["JR"])[:4]
    seeds = sorted(seeds, key=lambda x: x["JR"])[:6]
    cache = {_key(r["phi_deg"]): r for r in records}
    def evaluate(phi, phase):
        k = _key(phi)
        if k in cache:
            return cache[k]
        point = boundary_point(k, S1)
        cert = certified_strict(point, p1, S1, config)
        screen = None
        ev = None
        if cert.get("status") == "CERTIFIED_STRICT":
            screen = screen_candidate_c20(point, S1, p1, sources, config)
            if screen.get("screen_status") != "PROVEN_NOT_C20":
                ev = evaluate_candidate_nested(point, S1, p1, config, certificate_override=cert)
        r = _candidate_record(k, point, cert, screen, ev, phase)
        cache[k] = r
        return r
    medium = []
    for s in seeds:
        medium.extend(evaluate(a, "medium") for a in window_angles(s["phi_deg"], 2.0, medium_step))
    c20 = [r for r in cache.values() if r.get("boundary_C20") and r.get("M4")]
    top2 = sorted(c20, key=_sort_key)[:2]
    fine = []
    for r in top2:
        phi = r["phi_deg"]
        fine.extend(evaluate(a, "fine") for a in window_angles(phi, 0.5, fine_step))
    c20 = [r for r in cache.values() if r.get("boundary_C20") and r.get("M4")]
    top3 = sorted(c20, key=_sort_key)[:3]
    best = top3[0] if top3 else None
    # Independent final replay using a fresh P1 and certificate.
    final = None
    if best:
        fp1 = build_P1_bound(S1, 0.0, config)
        cert = certified_strict(best["S2"], fp1, S1, config)
        ev = evaluate_candidate_nested(best["S2"], S1, fp1, config, certificate_override=cert)
        ev_json = dict(ev)
        if hasattr(ev_json.get("candidate"), "__dict__"):
            ev_json["candidate"] = dict(ev_json["candidate"].__dict__)
        final = {"S2": best["S2"], "phi_deg": best["phi_deg"], "T2": 10.0,
                 "certificate": cert, "evaluation": ev_json,
                 "validation": {"source_convergence": ev.get("source_convergence"),
                                "error_convergence": ev.get("error_convergence"),
                                "gverify": ev.get("gverify"), "replay": ev.get("replay")}}
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    def write_csv(name, rows):
        fields = ["phi_deg","source","boundary_C20","angle_status","JR","JD","JA","certificate_status","cheap_screen_status"]
        with (out/name).open("w", newline="", encoding="utf-8") as f:
            w=csv.DictWriter(f, fieldnames=fields); w.writeheader()
            for r in rows:
                m=r.get("M4") or {}; c=r.get("certificate") or {}; q=r.get("cheap_screen") or {}
                w.writerow({"phi_deg":r["phi_deg"],"source":r.get("source"),"boundary_C20":r.get("boundary_C20"),"angle_status":r.get("angle_status"),"JR":m.get("JR"),"JD":m.get("JD"),"JA":m.get("JA"),"certificate_status":c.get("status"),"cheap_screen_status":q.get("screen_status")})
    write_csv("refinement_0p5deg.csv", [r for r in cache.values() if r.get("source") == "medium"])
    write_csv("refinement_fine.csv", [r for r in cache.values() if r.get("source") == "fine"])
    (out/"seeds.json").write_text(json.dumps({"seeds":seeds,"arcs":arcs}, indent=2), encoding="utf-8")
    (out/"final_candidate.json").write_text(json.dumps(final, indent=2, default=lambda o: o.__dict__ if hasattr(o, "__dict__") else str(o)), encoding="utf-8")
    coarse = next((r for r in c20 if r.get("source") is None), None)
    summary = {"artifact_status":"NUMERICAL_FINAL_CANDIDATE / COMPETITION_DELIVERABLE",
      "case":"REPRESENTATIVE_CASE / NOT_UNIQUE_PROBLEM_ANSWER",
      "primary_optimum":{"T2_s":10.0,"status":"PROVED"},
      "secondary_method":"2deg full-circle + local 0.5 + local 0.1/0.125",
      "secondary_status":"NUMERICALLY_REFINED, NOT_INTERVAL_CERTIFIED_CONTINUOUS_GLOBAL_OPTIMUM",
      "seed_count":len(seeds),"medium_new_count":sum(r.get("source")=="medium" for r in cache.values()),
      "fine_new_count":sum(r.get("source")=="fine" for r in cache.values()),"final":final,
      "top3":[{"phi_deg":r["phi_deg"],"S2":r["S2"],"JR":r["M4"]["JR"],"JD":r["M4"]["JD"],"JA":r["M4"]["JA"]} for r in top3],
      "near_tie": bool(len(top3)>1 and abs(top3[1]["M4"]["JR"]-top3[0]["M4"]["JR"]) <= 1e-3)}
    (out/"summary.json").write_text(json.dumps(summary, indent=2, default=lambda o: o.__dict__ if hasattr(o, "__dict__") else str(o)), encoding="utf-8")
    return summary
