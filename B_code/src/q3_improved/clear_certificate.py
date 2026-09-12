"""Safe clear certificates built from every retained OUTER-box corner."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING

from .config import CLEAR_R, OPER_CLEAR_R
from .conservative_geometry import OuterResult
from .mec import EPS_MEC, minimum_enclosing_circle

if TYPE_CHECKING:
    from .state import Q3State


class CertificateStatus(str, Enum):
    CERTIFIED = "CERTIFIED"
    OUTER_EMPTY_INVALID = "OUTER_EMPTY_INVALID"
    NUMERICAL_CERTIFICATE_INVALID = "NUMERICAL_CERTIFICATE_INVALID"


@dataclass(frozen=True)
class ClearCertificate:
    status: CertificateStatus
    center: Optional[tuple[float, float]]
    r_mec: Optional[float]
    eps_mec: float
    r_upper: Optional[float]
    corner_count: int
    unique_corner_count: int
    max_corner_distance: Optional[float]
    raw_radius_gap: Optional[float]
    operational_clearable: bool
    physical_clearable: bool
    observation_revision: str
    geometry_revision: str
    mec_runtime_s: float
    certificate_runtime_s: float
    diagnostics: dict[str, Any]


def certificate_from_outer(outer: OuterResult) -> ClearCertificate:
    """Cover the OUTER using all box corners, never box centres or samples.

    A disk is convex. If all four corners of an axis-aligned box are in a
    disk, the entire box is in that disk. Therefore a circle containing every
    retained-box corner contains the complete union of retained boxes.
    """

    started = time.perf_counter()
    all_corners = tuple(corner for box in outer.boxes for corner in box.corners)
    unique_corners = tuple(sorted(set(all_corners)))
    if not unique_corners:
        elapsed = time.perf_counter() - started
        return ClearCertificate(
            CertificateStatus.OUTER_EMPTY_INVALID, None, None, EPS_MEC, None,
            len(all_corners), 0, None, None, False, False,
            outer.observation_revision, outer.geometry_revision, 0.0, elapsed,
            {"corner_source": "all retained box corners", "outer_budget_exhausted": outer.diagnostics.budget_exhausted},
        )

    mec_started = time.perf_counter()
    circle = minimum_enclosing_circle(unique_corners)
    mec_runtime = time.perf_counter() - mec_started
    if circle is None:
        elapsed = time.perf_counter() - started
        return ClearCertificate(
            CertificateStatus.NUMERICAL_CERTIFICATE_INVALID, None, None,
            EPS_MEC, None, len(all_corners), len(unique_corners), None, None,
            False, False, outer.observation_revision, outer.geometry_revision,
            mec_runtime, elapsed,
            {"reason": "MEC unavailable", "corner_source": "all retained box corners"},
        )

    distances = tuple(math.dist(point, circle.center) for point in unique_corners)
    max_distance = max(distances)
    gap = max_distance - circle.radius
    r_upper = circle.radius + EPS_MEC
    valid = all(math.isfinite(value) for value in (*circle.center, circle.radius, r_upper, max_distance)) and max_distance <= r_upper
    status = CertificateStatus.CERTIFIED if valid else CertificateStatus.NUMERICAL_CERTIFICATE_INVALID
    elapsed = time.perf_counter() - started
    return ClearCertificate(
        status=status,
        center=circle.center,
        r_mec=circle.radius,
        eps_mec=EPS_MEC,
        r_upper=r_upper,
        corner_count=len(all_corners),
        unique_corner_count=len(unique_corners),
        max_corner_distance=max_distance,
        raw_radius_gap=gap,
        operational_clearable=valid and r_upper <= OPER_CLEAR_R,
        physical_clearable=valid and r_upper <= CLEAR_R,
        observation_revision=outer.observation_revision,
        geometry_revision=outer.geometry_revision,
        mec_runtime_s=mec_runtime,
        certificate_runtime_s=elapsed,
        diagnostics={
            "corner_source": "all retained box corners",
            "convex_disk_box_coverage": True,
            "outer_budget_exhausted": outer.diagnostics.budget_exhausted,
            "containment_replay_passed": valid,
        },
    )


def certificate_is_current(state: "Q3State", channel: int) -> bool:
    channel_state = state.channels[channel]
    certificate = channel_state.clear_certificate
    return bool(
        isinstance(certificate, ClearCertificate)
        and channel_state.status.value == "clear_ready"
        and certificate.status == CertificateStatus.CERTIFIED
        and certificate.operational_clearable
        and certificate.observation_revision == channel_state.geometry_history.revision
        and certificate.geometry_revision == channel_state.geometry_revision
        and certificate.geometry_revision == channel_state.certificate_revision
        and channel_state.clear_target == certificate.center
    )


def bind_clear_certificate(
    state: "Q3State", channel: int, outer: OuterResult,
    certificate: ClearCertificate,
) -> bool:
    channel_state = state.channels[channel]
    channel_state.geometry_revision = outer.geometry_revision
    channel_state.clear_certificate = certificate
    channel_state.certificate_outer_snapshot = outer
    if (
        channel_state.status.value == "detected"
        and certificate.status == CertificateStatus.CERTIFIED
        and certificate.operational_clearable
        and outer.observation_revision == channel_state.geometry_history.revision
        and certificate.observation_revision == outer.observation_revision
        and certificate.geometry_revision == outer.geometry_revision
    ):
        channel_state.certificate_revision = certificate.geometry_revision
        channel_state.clear_target = certificate.center
        channel_state.status = type(channel_state.status).CLEAR_READY
        return True
    channel_state.certificate_revision = None
    channel_state.clear_target = None
    return False


__all__ = [
    "CertificateStatus", "ClearCertificate", "bind_clear_certificate",
    "certificate_from_outer", "certificate_is_current",
]
