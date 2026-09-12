import math
import os
import sys
import tempfile
import unittest

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import q2_m6_boundary_projection as bp  # noqa: E402


class TestQ2M6BoundaryProjection(unittest.TestCase):
    def test_formula_hits_lmin_circle(self):
        for point in bp.ORIGINAL_CANDIDATES:
            projected = bp.radial_project_to_lmin(point)
            self.assertLess(abs(math.dist(projected, (1700.0, 0.0)) - 50.0), 1e-12)
            self.assertAlmostEqual(math.dist(projected, (1700.0, 0.0)) / 5.0, 10.0)

    def test_projection_cross_checks(self):
        a = bp.radial_project_to_lmin((1710.0, -50.0))
        b = bp.radial_project_to_lmin((1727.5, -42.5))
        self.assertAlmostEqual(a[0], 1709.8058067569, places=9)
        self.assertAlmostEqual(a[1], -49.0290337845, places=9)
        # The prompt values are rounded cross-checks, not the computational truth.
        self.assertAlmostEqual(b[0], 1727.162563973, places=6)
        self.assertAlmostEqual(b[1], -41.978507958, places=6)

    def test_s1_projection_is_undefined(self):
        with self.assertRaises(ValueError):
            bp.radial_project_to_lmin((1700.0, 0.0))


if __name__ == "__main__":
    unittest.main()
