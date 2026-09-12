"""Q3-improved-v1 protocol, state, and deterministic coverage layer."""

from .config import COVERAGE_RING_R
from .conservative_geometry import Box, OuterResult, rebuild_outer_from_observations
from .clear_certificate import ClearCertificate, certificate_from_outer
from .mec import MECCircle, minimum_enclosing_circle
from .coverage import CoverageMatrix, CoverageRecord, coverage_nodes
from .protocol import (
    ActionKind,
    ClearResult,
    ExecutionStatus,
    MeasureResult,
    NormalizedResponse,
    normalize_response,
)
from .scheduler import Action, ActionType, CoverageScheduler
from .observations import ObservationHistory
from .state import ChannelStatus, Q3State
from .fallback import FallbackCandidate, GRID_H, build_fallback_candidates
from .runner import P0Runner

__all__ = [
    "Action", "ActionKind", "ActionType", "ChannelStatus", "ClearResult",
    "Box", "COVERAGE_RING_R", "ClearCertificate", "CoverageMatrix", "CoverageRecord",
    "CoverageScheduler", "ExecutionStatus", "MeasureResult",
    "MECCircle", "NormalizedResponse", "ObservationHistory", "OuterResult", "Q3State",
    "certificate_from_outer", "coverage_nodes", "minimum_enclosing_circle",
    "normalize_response", "rebuild_outer_from_observations",
    "FallbackCandidate", "GRID_H", "build_fallback_candidates", "P0Runner",
]
