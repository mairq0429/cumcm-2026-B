"""Strict-certificate acceleration with exact zero-threshold semantics.

All propagated bounds follow from the 1-Lipschitz property of ``V_rec`` in
candidate-position space.  The reusable tree caches geometry only; every
source-dependent ``f(G; S2)`` value is recomputed for each candidate.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import time
from typing import Iterable, Mapping, Optional, Sequence

import q2_selection as q2


Point = tuple[float, float]


def _distance(a: Sequence[float], b: Sequence[float]) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


@dataclass(frozen=True)
class CertificateAnchor:
    S2: Point
    L_rec_m: float
    U_rec_m: float
    status: str
    certificate_id: str
    cells_examined: int
    source: str


@dataclass
class PhysicalCertificateNode:
    node_id: str
    triangle: tuple[Point, Point, Point]
    clipped_polygon: tuple[Point, ...]
    center: Optional[Point]
    h: float
    depth: int
    physical_intersection_possible: bool
    physical_sample_points: tuple[Point, ...]
    children: Optional[tuple[str, str]] = None


@dataclass
class PendingState:
    point: Point
    nearest_anchor_distance: float = math.inf
    nearest_anchor_id: Optional[str] = None
    best_L_rec_m: float = -math.inf
    best_U_rec_m: float = math.inf
    lower_anchor_id: Optional[str] = None
    upper_anchor_id: Optional[str] = None


class PhysicalCertificateTree:
    """Lazy geometry tree shared by all S2 candidates for one P1/S1."""

    def __init__(
        self,
        P1_bound: Sequence[Point] | Mapping[str, object],
        S1: Sequence[float],
        config: Optional[q2.Q2Config] = None,
    ) -> None:
        self.config = config or q2.Q2Config()
        self.S1 = q2._point(S1, "S1")
        self.polygon = tuple(
            P1_bound["P1_out"] if isinstance(P1_bound, Mapping) else P1_bound
        )
        xs, ys = [point[0] for point in self.polygon], [point[1] for point in self.polygon]
        lo_x, hi_x, lo_y, hi_y = min(xs), max(xs), min(ys), max(ys)
        roots = (
            ((lo_x, lo_y), (hi_x, lo_y), (hi_x, hi_y)),
            ((lo_x, lo_y), (hi_x, hi_y), (lo_x, hi_y)),
        )
        self.nodes: dict[str, PhysicalCertificateNode] = {}
        self.root_ids = tuple(self._create_node(f"R{index}", triangle, 0) for index, triangle in enumerate(roots))
        self.total_nodes_created = len(self.nodes)

    def _create_node(self, node_id: str, triangle: Sequence[Point], depth: int) -> str:
        clipped = q2._clip_by_convex(triangle, self.polygon, self.config.tolerances)
        possible = q2._physical_intersection_possible(clipped, self.S1)
        if clipped:
            center = (
                sum(point[0] for point in clipped) / len(clipped),
                sum(point[1] for point in clipped) / len(clipped),
            )
            h = max(_distance(center, point) for point in clipped)
            samples = tuple(
                point for point in [*clipped, center]
                if q2.physical_filter(point, self.S1)
            )
        else:
            center, h, samples = None, 0.0, ()
        self.nodes[node_id] = PhysicalCertificateNode(
            node_id=node_id,
            triangle=tuple(q2._point(point) for point in triangle),
            clipped_polygon=tuple(clipped),
            center=center,
            h=h,
            depth=depth,
            physical_intersection_possible=possible,
            physical_sample_points=samples,
        )
        return node_id

    def refine(self, node_id: str) -> tuple[str, str]:
        node = self.nodes[node_id]
        if node.children is not None:
            return node.children
        first, second = q2._triangle_children(node.triangle)
        children = (
            self._create_node(f"{node_id}0", first, node.depth + 1),
            self._create_node(f"{node_id}1", second, node.depth + 1),
        )
        node.children = children
        self.total_nodes_created = len(self.nodes)
        return children

    def leaf_ids(self) -> list[str]:
        leaves = []
        stack = list(reversed(self.root_ids))
        while stack:
            node_id = stack.pop()
            node = self.nodes[node_id]
            if node.children is None:
                if node.physical_intersection_possible:
                    leaves.append(node_id)
            else:
                stack.extend(reversed(node.children))
        return leaves


def propagate_anchor_bounds(S2: Sequence[float], anchors: Iterable[CertificateAnchor]) -> dict:
    """Safely propagate finite anchor bounds to a new candidate point."""

    point = q2._point(S2, "S2")
    lower, upper = -math.inf, math.inf
    lower_anchor = upper_anchor = None
    for anchor in anchors:
        distance = _distance(point, anchor.S2)
        if math.isfinite(anchor.L_rec_m):
            value = anchor.L_rec_m - distance
            if value > lower:
                lower, lower_anchor = value, anchor.certificate_id
        if math.isfinite(anchor.U_rec_m):
            value = anchor.U_rec_m + distance
            if value < upper:
                upper, upper_anchor = value, anchor.certificate_id
    status = "CERTIFIED_STRICT_PROPAGATED" if upper <= 0.0 else (
        "CERTIFIED_VIOLATION_PROPAGATED" if lower > 0.0 else "UNRESOLVED"
    )
    return {
        "status": status,
        "propagated_L_rec_m": lower,
        "propagated_U_rec_m": upper,
        "lower_anchor_id": lower_anchor,
        "upper_anchor_id": upper_anchor,
        "strict_physical_threshold_m": 0.0,
    }


def propagate_candidate_cell(
    S2_center: Sequence[float], cell_radius_m: float,
    anchors: Iterable[CertificateAnchor],
) -> dict:
    bounds = propagate_anchor_bounds(S2_center, anchors)
    lower, upper, radius = (
        bounds["propagated_L_rec_m"], bounds["propagated_U_rec_m"], float(cell_radius_m)
    )
    bounds.update({
        "whole_cell_status": (
            "WHOLE_CELL_CERTIFIED_STRICT" if upper + radius <= 0.0 else (
                "WHOLE_CELL_CERTIFIED_VIOLATION" if lower - radius > 0.0 else "UNRESOLVED"
            )
        ),
        "cell_radius_m": radius,
    })
    return bounds


def _certificate_result(
    status: str, lower: float, upper: float, precision: float, examined: int,
    *, counterexample: Optional[Point], reason: str, reused: int, created: int,
) -> dict:
    width = upper - lower if math.isfinite(lower) and math.isfinite(upper) else math.inf
    return {
        "status": status,
        "strict_receive": True if status == "CERTIFIED_STRICT" else (
            False if status == "CERTIFIED_VIOLATION" else None
        ),
        "certified": status in {"CERTIFIED_STRICT", "CERTIFIED_VIOLATION"},
        "method": "shared_physical_tree_2_lipschitz",
        "L_rec_m": lower,
        "U_rec_m": upper,
        "interval_width_m": width,
        "eps_rec_cert_m": precision,
        "eps_rec_cert_source": "MODEL_FROZEN_CERTIFICATION_PRECISION",
        "cells_examined": examined,
        "counterexample": counterexample,
        "reason": reason,
        "accelerated": True,
        "tree_nodes_reused": reused,
        "tree_nodes_created": created,
        "anchor_used": None,
    }


def accelerated_certified_strict(
    S2: Sequence[float],
    tree: PhysicalCertificateTree,
    S1: Sequence[float],
    config: Optional[q2.Q2Config] = None,
) -> dict:
    """Run the four-state certificate over a reusable lazy geometry tree."""

    cfg = config or tree.config
    s1, s2 = q2._point(S1, "S1"), q2._point(S2, "S2")
    if s1 != tree.S1:
        raise ValueError("tree S1 does not match certificate S1")
    precision = cfg.eps_rec_cert_m
    if s1 == s2:
        return _certificate_result(
            "CERTIFIED_STRICT", -math.inf, 0.0, precision, 0,
            counterexample=None, reason="analytic_S2_equals_S1", reused=0, created=0,
        )
    before_ids = set(tree.nodes)
    lower, lower_point = -math.inf, None
    leaves = tree.leaf_ids()
    examined_ids: set[str] = set()

    def evaluate_node(node_id: str) -> float:
        nonlocal lower, lower_point
        node = tree.nodes[node_id]
        examined_ids.add(node_id)
        for point in node.physical_sample_points:
            value = q2.receive_violation(s2, point, s1)
            if value > lower:
                lower, lower_point = value, point
        assert node.center is not None
        return q2.receive_violation(s2, node.center, s1) + 2.0 * node.h

    uppers = {node_id: evaluate_node(node_id) for node_id in leaves}
    while True:
        upper = max(uppers.values(), default=-math.inf)
        decision = q2.classify_receive_certificate_bounds(lower, upper, precision)
        created = len(set(tree.nodes) - before_ids)
        reused = len(examined_ids & before_ids)
        if decision == "CERTIFIED_STRICT":
            return _certificate_result(
                decision, lower, upper, precision, len(examined_ids), counterexample=None,
                reason="global_upper_bound_nonpositive", reused=reused, created=created,
            )
        if decision == "CERTIFIED_VIOLATION":
            return _certificate_result(
                decision, lower, upper, precision, len(examined_ids), counterexample=lower_point,
                reason="physical_counterexample", reused=reused, created=created,
            )
        if decision == "UNCERTAIN_BOUNDARY":
            return _certificate_result(
                decision, lower, upper, precision, len(examined_ids), counterexample=None,
                reason="certificate_interval_straddles_zero", reused=reused, created=created,
            )
        if len(examined_ids) >= cfg.certificate_max_cells:
            return _certificate_result(
                "UNRESOLVED", lower, upper, precision, len(examined_ids), counterexample=None,
                reason="certificate_cell_budget_exhausted", reused=reused, created=created,
            )
        target_id = min(uppers, key=lambda node_id: (-uppers[node_id], node_id))
        target = tree.nodes[target_id]
        if target.depth >= cfg.certificate_max_depth:
            return _certificate_result(
                "UNRESOLVED", lower, upper, precision, len(examined_ids), counterexample=None,
                reason="max_depth_with_active_physical_cell", reused=reused, created=created,
            )
        del uppers[target_id]
        for child_id in tree.refine(target_id):
            child = tree.nodes[child_id]
            if child.physical_intersection_possible:
                uppers[child_id] = evaluate_node(child_id)


class StrictCertificateAccelerator:
    """Deterministic anchor scheduler backed by one shared physical tree."""

    def __init__(self, tree: PhysicalCertificateTree, config: Optional[q2.Q2Config] = None):
        self.tree = tree
        self.config = config or tree.config
        self.anchors: list[CertificateAnchor] = [
            CertificateAnchor(tree.S1, -math.inf, 0.0, "CERTIFIED_STRICT", "analytic-S1", 0, "analytic")
        ]
        self.full_certificate_calls = 0
        self.tree_nodes_created = 0
        self.tree_nodes_reused = 0
        self.anchor_sequence: list[Point] = []

    def _add_anchor(self, S2: Point, certificate: Mapping[str, object]) -> None:
        self.full_certificate_calls += 1
        self.tree_nodes_created += int(certificate.get("tree_nodes_created", 0))
        self.tree_nodes_reused += int(certificate.get("tree_nodes_reused", 0))
        self.anchors.append(CertificateAnchor(
            S2=S2,
            L_rec_m=float(certificate["L_rec_m"]),
            U_rec_m=float(certificate["U_rec_m"]),
            status=str(certificate["status"]),
            certificate_id=f"full-{self.full_certificate_calls:05d}",
            cells_examined=int(certificate["cells_examined"]),
            source="accelerated_full_certificate",
        ))
        self.anchor_sequence.append(S2)

    def certify_points_legacy(self, points: Iterable[Sequence[float]], cell_radius_m: float = 0.0) -> dict:
        """Pre-M6A.5 all-anchor rescanning implementation retained as oracle."""
        pending = {q2._point(point, "S2") for point in points}
        results: dict[Point, dict] = {}
        counts = {
            "propagated_strict_points": 0, "propagated_violation_points": 0,
            "whole_cell_strict_by_anchor": 0, "whole_cell_violation_by_anchor": 0,
        }
        while pending:
            # Anchors do not change while propagated points are removed, so one
            # deterministic pass is mathematically identical to rescanning after
            # every removal and avoids quadratic pending-set traversal.
            resolved = []
            for point in sorted(pending):
                propagated = propagate_candidate_cell(point, cell_radius_m, self.anchors)
                if propagated["status"] == "UNRESOLVED":
                    continue
                resolved.append((point, propagated))
            for point, propagated in resolved:
                    physical_status = (
                        "CERTIFIED_STRICT" if propagated["status"] == "CERTIFIED_STRICT_PROPAGATED"
                        else "CERTIFIED_VIOLATION"
                    )
                    results[point] = {
                        "status": physical_status,
                        "strict_receive": physical_status == "CERTIFIED_STRICT",
                        "certified": True,
                        "L_rec_m": propagated["propagated_L_rec_m"],
                        "U_rec_m": propagated["propagated_U_rec_m"],
                        "interval_width_m": math.inf,
                        "eps_rec_cert_m": self.config.eps_rec_cert_m,
                        "eps_rec_cert_source": "MODEL_FROZEN_CERTIFICATION_PRECISION",
                        "cells_examined": 0,
                        "counterexample": None,
                        "reason": propagated["status"],
                        "accelerated": True,
                        "tree_nodes_reused": 0,
                        "tree_nodes_created": 0,
                        "anchor_used": propagated[
                            "upper_anchor_id" if physical_status == "CERTIFIED_STRICT" else "lower_anchor_id"
                        ],
                        "whole_cell_status": propagated["whole_cell_status"],
                    }
                    counts[
                        "propagated_strict_points" if physical_status == "CERTIFIED_STRICT"
                        else "propagated_violation_points"
                    ] += 1
                    if propagated["whole_cell_status"] == "WHOLE_CELL_CERTIFIED_STRICT":
                        counts["whole_cell_strict_by_anchor"] += 1
                    elif propagated["whole_cell_status"] == "WHOLE_CELL_CERTIFIED_VIOLATION":
                        counts["whole_cell_violation_by_anchor"] += 1
                    pending.remove(point)
            if not pending:
                break
            # Farthest-from-anchor scheduling; ties are deterministic by x/y.
            point = max(
                pending,
                key=lambda candidate: (
                    min(_distance(candidate, anchor.S2) for anchor in self.anchors),
                    -candidate[0], -candidate[1],
                ),
            )
            certificate = accelerated_certified_strict(point, self.tree, self.tree.S1, self.config)
            if certificate["U_rec_m"] + cell_radius_m <= 0.0:
                certificate["whole_cell_status"] = "WHOLE_CELL_CERTIFIED_STRICT"
                counts["whole_cell_strict_by_anchor"] += 1
            elif certificate["L_rec_m"] - cell_radius_m > 0.0:
                certificate["whole_cell_status"] = "WHOLE_CELL_CERTIFIED_VIOLATION"
                counts["whole_cell_violation_by_anchor"] += 1
            else:
                certificate["whole_cell_status"] = "UNRESOLVED"
            results[point] = certificate
            self._add_anchor(point, certificate)
            pending.remove(point)
        return {
            "certificates": results,
            "anchor_count": len(self.anchors),
            "full_certificate_calls": self.full_certificate_calls,
            "shared_tree_nodes": len(self.tree.nodes),
            "tree_nodes_created": self.tree_nodes_created,
            "tree_nodes_reused": self.tree_nodes_reused,
            **counts,
            "still_unresolved": sum(
                value["status"] in {"UNCERTAIN_BOUNDARY", "UNRESOLVED"}
                for value in results.values()
            ),
        }

    def _incremental_result(self, state: PendingState, cell_radius_m: float) -> Optional[dict]:
        if state.best_U_rec_m <= 0.0 and state.best_L_rec_m > 0.0:
            raise RuntimeError("CERTIFICATE_PROPAGATION_CONFLICT")
        status = "CERTIFIED_STRICT" if state.best_U_rec_m <= 0.0 else (
            "CERTIFIED_VIOLATION" if state.best_L_rec_m > 0.0 else None
        )
        if status is None:
            return None
        whole = (
            "WHOLE_CELL_CERTIFIED_STRICT"
            if state.best_U_rec_m + cell_radius_m <= 0.0 else (
                "WHOLE_CELL_CERTIFIED_VIOLATION"
                if state.best_L_rec_m - cell_radius_m > 0.0 else "UNRESOLVED"
            )
        )
        return {
            "status": status,
            "strict_receive": status == "CERTIFIED_STRICT",
            "certified": True,
            "L_rec_m": state.best_L_rec_m,
            "U_rec_m": state.best_U_rec_m,
            "interval_width_m": (
                state.best_U_rec_m - state.best_L_rec_m
                if math.isfinite(state.best_L_rec_m) and math.isfinite(state.best_U_rec_m)
                else math.inf
            ),
            "eps_rec_cert_m": self.config.eps_rec_cert_m,
            "eps_rec_cert_source": "MODEL_FROZEN_CERTIFICATION_PRECISION",
            "cells_examined": 0,
            "counterexample": None,
            "reason": (
                "CERTIFIED_STRICT_PROPAGATED" if status == "CERTIFIED_STRICT"
                else "CERTIFIED_VIOLATION_PROPAGATED"
            ),
            "accelerated": True,
            "tree_nodes_reused": 0,
            "tree_nodes_created": 0,
            "anchor_used": state.upper_anchor_id if status == "CERTIFIED_STRICT" else state.lower_anchor_id,
            "whole_cell_status": whole,
        }

    def certify_points_incremental(
        self, points: Iterable[Sequence[float]], cell_radius_m: float = 0.0
    ) -> dict:
        """Event-driven exact anchor propagation; each anchor-point pair is evaluated once."""

        total_started = time.perf_counter()
        states = {point: PendingState(point) for point in {q2._point(p, "S2") for p in points}}
        results: dict[Point, dict] = {}
        initial_anchor_count = len(self.anchors)
        full_before = self.full_certificate_calls
        distance_evaluations = scheduler_scans = 0
        initial_runtime = incremental_runtime = full_runtime = 0.0
        propagated_existing = propagated_new = 0

        def resolve_pending() -> int:
            resolved = []
            for point, state in states.items():
                result = self._incremental_result(state, cell_radius_m)
                if result is not None:
                    resolved.append((point, result))
            for point, result in resolved:
                results[point] = result
                del states[point]
            return len(resolved)

        def apply(anchor: CertificateAnchor, phase: str, *, resolve: bool = True) -> int:
            nonlocal distance_evaluations, initial_runtime, incremental_runtime
            started = time.perf_counter()
            for point, state in states.items():
                distance = _distance(point, anchor.S2)
                distance_evaluations += 1
                if distance < state.nearest_anchor_distance:
                    state.nearest_anchor_distance = distance
                    state.nearest_anchor_id = anchor.certificate_id
                if math.isfinite(anchor.L_rec_m):
                    value = anchor.L_rec_m - distance
                    if value > state.best_L_rec_m:
                        state.best_L_rec_m, state.lower_anchor_id = value, anchor.certificate_id
                if math.isfinite(anchor.U_rec_m):
                    value = anchor.U_rec_m + distance
                    if value < state.best_U_rec_m:
                        state.best_U_rec_m, state.upper_anchor_id = value, anchor.certificate_id
            resolved_count = resolve_pending() if resolve else 0
            elapsed = time.perf_counter() - started
            if phase == "initial":
                initial_runtime += elapsed
            else:
                incremental_runtime += elapsed
            return resolved_count

        for anchor in tuple(self.anchors):
            apply(anchor, "initial", resolve=False)
        initial_resolution_started = time.perf_counter()
        propagated_existing = resolve_pending()
        initial_runtime += time.perf_counter() - initial_resolution_started
        while states:
            scheduler_scans += len(states)
            point = max(
                states,
                key=lambda candidate: (
                    states[candidate].nearest_anchor_distance,
                    -candidate[0], -candidate[1],
                ),
            )
            cert_started = time.perf_counter()
            certificate = accelerated_certified_strict(point, self.tree, self.tree.S1, self.config)
            full_runtime += time.perf_counter() - cert_started
            if certificate["U_rec_m"] + cell_radius_m <= 0.0:
                certificate["whole_cell_status"] = "WHOLE_CELL_CERTIFIED_STRICT"
            elif certificate["L_rec_m"] - cell_radius_m > 0.0:
                certificate["whole_cell_status"] = "WHOLE_CELL_CERTIFIED_VIOLATION"
            else:
                certificate["whole_cell_status"] = "UNRESOLVED"
            results[point] = certificate
            del states[point]
            self._add_anchor(point, certificate)
            propagated_new += apply(self.anchors[-1], "incremental")

        values = list(results.values())
        full_this_batch = self.full_certificate_calls - full_before
        return {
            "certificates": results,
            "anchor_count": len(self.anchors),
            "full_certificate_calls": self.full_certificate_calls,
            "full_certificate_calls_this_batch": full_this_batch,
            "shared_tree_nodes": len(self.tree.nodes),
            "tree_nodes_created": self.tree_nodes_created,
            "tree_nodes_reused": self.tree_nodes_reused,
            "propagated_strict_points": sum(v.get("reason") == "CERTIFIED_STRICT_PROPAGATED" for v in values),
            "propagated_violation_points": sum(v.get("reason") == "CERTIFIED_VIOLATION_PROPAGATED" for v in values),
            "whole_cell_strict_by_anchor": sum(v.get("whole_cell_status") == "WHOLE_CELL_CERTIFIED_STRICT" for v in values),
            "whole_cell_violation_by_anchor": sum(v.get("whole_cell_status") == "WHOLE_CELL_CERTIFIED_VIOLATION" for v in values),
            "still_unresolved": sum(v["status"] in {"UNCERTAIN_BOUNDARY", "UNRESOLVED"} for v in values),
            "incremental_distance_evaluations": distance_evaluations,
            "legacy_estimated_anchor_distance_evaluations": scheduler_scans * max(1, len(self.anchors)),
            "initial_anchor_count": initial_anchor_count,
            "new_anchor_count": full_this_batch,
            "pending_initial": len(results),
            "pending_after_initial_anchor_propagation": len(results) - propagated_existing,
            "propagated_by_existing_anchors": propagated_existing,
            "propagated_by_new_anchors": propagated_new,
            "scheduler_scan_count": scheduler_scans,
            "runtime_initial_propagation_s": initial_runtime,
            "runtime_incremental_propagation_s": incremental_runtime,
            "runtime_full_certificate_s": full_runtime,
            "runtime_total_s": time.perf_counter() - total_started,
            "anchor_sequence": list(self.anchor_sequence[full_before:]),
        }

    def certify_points(self, points: Iterable[Sequence[float]], cell_radius_m: float = 0.0) -> dict:
        return self.certify_points_incremental(points, cell_radius_m)


def benchmark_coarse_50m(
    S1: Sequence[float] = (1700.0, 0.0), theta1_hat_deg: float = 0.0,
    config: Optional[q2.Q2Config] = None,
) -> dict:
    """Run only the prescribed 50 m strict-certificate performance benchmark."""

    cfg = config or q2.Q2Config()
    if cfg.circle_sides != 1440 or cfg.omega_move is not None:
        raise ValueError("benchmark requires circle_sides=1440 and Omega_move=None")
    total_started = time.perf_counter()
    p1 = q2.build_P1_bound(S1, theta1_hat_deg, cfg)
    cells = q2._candidate_cells(p1["search_box"], 50.0, None, None, None, cfg.tolerances)
    sources = q2.build_Gext(p1, S1, 20.0)
    radius = math.sqrt(2.0) * 25.0
    sample_started = time.perf_counter()
    candidates = []
    sample_point_violations = whole_exclusions = 0
    for cell in cells:
        margins = [q2.sample_receive_screen(cell.center, source.G, S1, radius) for source in sources]
        violations = [item for item in margins if item["point_violation"]]
        if violations:
            sample_point_violations += 1
            if any(item["whole_cell_violation"] for item in violations):
                whole_exclusions += 1
        else:
            candidates.append(cell.center)
    sample_runtime = time.perf_counter() - sample_started
    tree = PhysicalCertificateTree(p1, S1, cfg)
    accelerator = StrictCertificateAccelerator(tree, cfg)
    certificate_started = time.perf_counter()
    batch = accelerator.certify_points(candidates, radius)
    certificate_runtime = time.perf_counter() - certificate_started
    certificates = list(batch.pop("certificates").values())
    profile = {
        "artifact_status": "VALIDATION / NOT_FINAL_Q2_RESULT",
        "benchmark": "Q2_M6A1_50M_COARSE_ONLY",
        "strict_physical_threshold_m": 0.0,
        "eps_rec_cert_m": cfg.eps_rec_cert_m,
        "search_box": p1["search_box"],
        "coarse_cells": len(cells),
        "Gext_count": len(sources),
        "sample_point_violations": sample_point_violations,
        "whole_cell_exclusions": whole_exclusions,
        "remaining_after_sample": len(candidates),
        **batch,
        "uncertain_boundary": sum(item["status"] == "UNCERTAIN_BOUNDARY" for item in certificates),
        "unresolved": sum(item["status"] == "UNRESOLVED" for item in certificates),
        "sample_screen_runtime_s": sample_runtime,
        "certificate_runtime_s": certificate_runtime,
        "total_runtime_s": time.perf_counter() - total_started,
        "legacy_full_certificate_estimate": 1190,
        "full_certificate_call_reduction": 1190 - batch["full_certificate_calls"],
        "prior_runtime_lower_bound_s": 300.0,
        "standards_reduced": False,
    }
    profile["speedup_lower_bound"] = 300.0 / profile["total_runtime_s"]
    conflict = sample_point_violations != 2654 or whole_exclusions != 2572 or len(candidates) != 1190
    profile["status"] = "CERTIFICATE_ACCEL_CONFLICT" if conflict else (
        "PASS" if batch["full_certificate_calls"] < 1190 and profile["total_runtime_s"] < 300.0
        else "ACCELERATION_INSUFFICIENT"
    )
    profile["warnings"] = [] if profile["status"] == "PASS" else [profile["status"]]
    return profile


def benchmark_lazy_objective_50m(
    S1: Sequence[float] = (1700.0, 0.0), theta1_hat_deg: float = 0.0,
    config: Optional[q2.Q2Config] = None,
) -> dict:
    """Run the formal 1440/50 m certificate plus lazy-objective benchmark only."""

    cfg = config or q2.Q2Config()
    if cfg.circle_sides != 1440 or cfg.omega_move is not None:
        raise ValueError("benchmark requires circle_sides=1440 and Omega_move=None")
    p1 = q2.build_P1_bound(S1, theta1_hat_deg, cfg)
    engine = StrictCertificateAccelerator(PhysicalCertificateTree(p1, S1, cfg), cfg)
    started = time.perf_counter()
    result = q2.search_strict_candidates(
        S1, theta1_hat_deg, cfg, P1_bound=p1,
        certificate_batch_engine=engine, pass_certificate_to_m4=True,
        stop_after_level_m=50.0, lazy_objective=True,
    )
    diagnostics = result["level_diagnostics"][0]
    selected = result["selection"]["selected_strict"]
    return {
        "artifact_status": "VALIDATION / NOT_FINAL_Q2_RESULT",
        "benchmark": "M6A.2_LAZY_OBJECTIVE_50M_ONLY",
        "strict_objective_candidates": diagnostics["strict_objective_candidates"],
        "cheap_screen_calls": diagnostics["cheap_screen_calls"],
        "cheap_screen_rejected": diagnostics["cheap_screen_rejected"],
        "cheap_screen_inconclusive": diagnostics["cheap_screen_inconclusive"],
        "full_M4_calls": diagnostics["M4_evaluated"],
        "C20_found": bool(result["selection"]["C20"]),
        "best_T2": None if selected is None else selected.T2,
        "pruned_after_C20": diagnostics["pruned_after_C20"],
        "runtime_certificate_s": diagnostics["runtime_certificate_s"],
        "runtime_cheap_screen_s": diagnostics["runtime_cheap_screen_s"],
        "runtime_full_M4_s": diagnostics["runtime_full_M4_s"],
        "runtime_total_s": time.perf_counter() - started,
        "legacy_full_M4_estimate": diagnostics["strict_objective_candidates"],
        "warnings": [],
    }


def run_coarse_benchmark_to_file(output_path: str | Path) -> dict:
    """Explicit non-unittest entry point for the prescribed 50 m benchmark."""

    result = benchmark_coarse_50m()
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def run_legacy_accelerated_equivalence(
    output_path: Optional[str | Path] = None,
    S1: Sequence[float] = (1700.0, 0.0),
    theta1_hat_deg: float = 0.0,
) -> dict:
    """Record the prescribed deterministic 30-point oracle comparison."""

    started = time.perf_counter()
    cfg = q2.Q2Config()
    p1 = q2.build_P1_bound(S1, theta1_hat_deg, cfg)
    tree = PhysicalCertificateTree(p1, S1, cfg)
    points = (
        [(1500.0 + 50.0 * index, (-1) ** index * 100.0) for index in range(8)]
        + [(3000.0 + 30.0 * index, (-1) ** index * 200.0) for index in range(8)]
        + [(2700.0 + delta, (-1) ** index * 25.0) for index, delta in enumerate(
            (-20.0, -10.0, -1.0, 0.0, 1.0, 10.0, 20.0, 30.0)
        )]
        + [(700.0, 600.0), (700.0, -600.0), (1000.0, 900.0),
           (1000.0, -900.0), (2300.0, 900.0), (2300.0, -900.0)]
    )
    cases, differences, conflicts = [], [], []
    determined = {"CERTIFIED_STRICT", "CERTIFIED_VIOLATION"}
    for point in points:
        legacy = q2.certified_strict(point, p1, S1, cfg)
        accelerated = accelerated_certified_strict(point, tree, S1, cfg)
        record = {
            "S2": list(point),
            "legacy_status": legacy["status"],
            "accelerated_status": accelerated["status"],
            "legacy_L_rec_m": legacy["L_rec_m"],
            "legacy_U_rec_m": legacy["U_rec_m"],
            "accelerated_L_rec_m": accelerated["L_rec_m"],
            "accelerated_U_rec_m": accelerated["U_rec_m"],
        }
        cases.append(record)
        if legacy["status"] != accelerated["status"]:
            differences.append(record)
        opposite = (
            {legacy["status"], accelerated["status"]}
            == {"CERTIFIED_STRICT", "CERTIFIED_VIOLATION"}
        )
        inconsistent_determined = (
            legacy["status"] in determined and accelerated["status"] in determined
            and legacy["status"] != accelerated["status"]
        )
        if opposite or inconsistent_determined:
            conflicts.append(record)
    result = {
        "artifact_status": "VALIDATION / NOT_FINAL_Q2_RESULT",
        "status": "PASS" if not conflicts else "CERTIFICATE_ACCEL_CONFLICT",
        "case_count": len(cases),
        "difference_count": len(differences),
        "conflict_count": len(conflicts),
        "cases": cases,
        "differences": differences,
        "conflicts": conflicts,
        "runtime_s": time.perf_counter() - started,
        "strict_physical_threshold_m": 0.0,
        "eps_rec_cert_m": cfg.eps_rec_cert_m,
    }
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


__all__ = [
    "CertificateAnchor", "PendingState", "PhysicalCertificateNode", "PhysicalCertificateTree",
    "StrictCertificateAccelerator", "accelerated_certified_strict",
    "benchmark_coarse_50m", "propagate_anchor_bounds", "propagate_candidate_cell",
    "run_coarse_benchmark_to_file", "run_legacy_accelerated_equivalence",
]
