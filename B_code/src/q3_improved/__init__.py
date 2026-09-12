"""Q3-improved-v1 protocol, state, and deterministic coverage layer."""

from .config import COVERAGE_RING_R
from .conservative_geometry import Box, OuterResult, rebuild_outer_from_observations
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

__all__ = [
    "Action", "ActionKind", "ActionType", "ChannelStatus", "ClearResult",
    "Box", "COVERAGE_RING_R", "CoverageMatrix", "CoverageRecord",
    "CoverageScheduler", "ExecutionStatus", "MeasureResult",
    "NormalizedResponse", "ObservationHistory", "OuterResult", "Q3State",
    "coverage_nodes", "normalize_response", "rebuild_outer_from_observations",
]
