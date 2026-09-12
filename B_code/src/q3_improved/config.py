"""Central constants for the Problem 3 omnidirectional-source scope."""

import math


# PHYSICAL: official problem/simulator parameters.
ARENA_R = 1800.0
RX_MIN = 1000.0
RX_MAX = 1500.0
BEARING_ALPHA_DEG = 1.0
NEAR_R = 5.0
CLEAR_R = 20.0
ROBOT_SPEED = 5.0
N_CHANNELS = 20

# OPERATIONAL: team safety threshold, not an official physical parameter.
OPER_CLEAR_R = 17.0

# HEURISTIC/DESIGN: deterministic Q3 coverage construction.
COVERAGE_RING_R = 900.0 * math.sqrt(3.0)
N_COVERAGE_NODES = 7
