import math
import os
import sys
import unittest

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path: sys.path.insert(0, SRC_DIR)
import q2_m6_boundary_scan as scan  # noqa: E402


class TestBoundaryScan(unittest.TestCase):
    def test_boundary_points_have_exact_radius_numerically(self):
        for angle in (0, 1, 90, 179, 270, 359):
            self.assertLess(abs(math.dist(scan.boundary_point(angle), (1700.0, 0.0)) - 50.0), 1e-12)

    def test_linear_arcs(self):
        self.assertEqual(scan.sampled_circular_arcs([10, 12, 14, 30], 2), [[10.0,12.0,14.0],[30.0]])

    def test_wraparound_arc(self):
        arcs = scan.sampled_circular_arcs([356, 358, 0, 2, 20], 2)
        self.assertEqual(len(arcs), 2)
        self.assertEqual(arcs[0], [356.0, 358.0, 0.0, 2.0])

    def test_empty_and_full_circle(self):
        self.assertEqual(scan.sampled_circular_arcs([], 2), [])
        self.assertEqual(len(scan.sampled_circular_arcs(range(0,360,2), 2)), 1)


if __name__ == "__main__": unittest.main()
