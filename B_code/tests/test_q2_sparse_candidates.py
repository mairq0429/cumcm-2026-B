import os
import sys
import unittest


SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import q2_selection as q2  # noqa: E402


FIELDS = (
    "cell_id", "level_m", "ix", "iy", "center", "bbox", "parent_ids",
    "objective_parent_ids", "objective_refinement", "center_in_move_domain",
    "omega_boundary_flag",
)


def signature(cells):
    return [tuple(getattr(cell, field) for field in FIELDS) for cell in cells]


def parent(name, bbox, objective=True):
    x0, y0, x1, y1 = bbox
    return q2.CandidateCell(
        name, x1 - x0, 0, 0, ((x0 + x1) / 2, (y0 + y1) / 2), bbox,
        objective_refinement=objective,
    )


class TestQ2SparseCandidateGeneration(unittest.TestCase):
    def compare(self, bounds, level, region, objective, omega=None):
        tol = q2.Q2Config().tolerances
        legacy = q2._candidate_cells_legacy(bounds, level, omega, region, objective, tol)
        diagnostics = {}
        sparse = q2._candidate_cells_sparse(bounds, level, omega, region, objective, tol, diagnostics)
        self.assertEqual(signature(legacy), signature(sparse))
        self.assertEqual({cell.cell_id for cell in legacy}, {cell.cell_id for cell in sparse})
        return sparse, diagnostics

    def test_noninteger_50_to_20_and_multi_parent_ids(self):
        region = [parent("A", (0, 0, 50, 50)), parent("B", (50, 0, 100, 50))]
        objective = [region[0], region[1]]
        cells, diagnostics = self.compare((-20, -20, 120, 80), 20.0, region, objective)
        shared = [cell for cell in cells if set(cell.parent_ids) == {"A", "B"}]
        self.assertTrue(shared)
        self.assertEqual(diagnostics["generation_method"], "sparse_parent_driven")

    def test_20_to_5_no_missing_or_extra_cells(self):
        region = [parent(f"R{i}", (i * 20, -20, (i + 1) * 20, 20)) for i in range(6)]
        sparse, diagnostics = self.compare((-10, -30, 140, 30), 5.0, region, region[1:5])
        self.assertEqual(len(sparse), diagnostics["unique_region_indices"])
        self.assertTrue(all(cell.parent_ids for cell in sparse))
        self.assertTrue(all(-2 <= cell.ix <= 27 for cell in sparse))

    def test_objective_parent_membership_is_independent(self):
        region = [parent("R0", (0, 0, 50, 50)), parent("R1", (50, 0, 100, 50))]
        objective = [region[1]]
        cells, _ = self.compare((0, 0, 100, 60), 20.0, region, objective)
        self.assertTrue(any(not cell.objective_parent_ids for cell in cells))
        self.assertTrue(any(cell.objective_parent_ids == ("R1",) for cell in cells))

    def test_omega_boundary_cells_are_identical(self):
        region = [parent("R", (-50, -50, 50, 50))]
        omega = ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))
        cells, _ = self.compare((-60, -60, 60, 60), 20.0, region, region, omega)
        self.assertTrue(any(cell.omega_boundary_flag for cell in cells))


if __name__ == "__main__":
    unittest.main()
