from pathlib import Path
import sys
import unittest

from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.generator.rest_constraint import add_rest_11h_constraint_simplified

SHIFT_OPEN, SHIFT_CLOSE = 0, 1
START_SHIFT_MAP = {2: 15}
END_SHIFT_MAP = {3: 15}
ALL_SHIFTS = (SHIFT_OPEN, SHIFT_CLOSE, 2, 3)


def _build_model():
    model = cp_model.CpModel()
    x = {}
    for d in (1, 2):
        for s in ALL_SHIFTS:
            x[0, d, s] = model.NewBoolVar(f"x_{d}_{s}")
        # co najwyżej jedna zmiana na dzień, jak w prawdziwym modelu
        model.Add(sum(x[0, d, s] for s in ALL_SHIFTS) <= 1)

    add_rest_11h_constraint_simplified(
        model, x, [object()], [1, 2], [1, 2],
        SHIFT_OPEN, SHIFT_CLOSE, START_SHIFT_MAP, END_SHIFT_MAP,
    )
    return model, x


class Rest11hSimplifiedTests(unittest.TestCase):
    def test_afternoon_today_forbids_morning_tomorrow(self):
        model, x = _build_model()
        model.Add(x[0, 1, SHIFT_CLOSE] == 1)
        model.Add(x[0, 2, SHIFT_OPEN] == 1)

        solver = cp_model.CpSolver()
        status = solver.Solve(model)

        self.assertEqual(status, cp_model.INFEASIBLE)

    def test_afternoon_today_allows_afternoon_tomorrow(self):
        model, x = _build_model()
        model.Add(x[0, 1, SHIFT_CLOSE] == 1)
        model.Add(x[0, 2, 3] == 1)  # END_SHIFT_MAP shift id — nadal klasa "popołudnie"

        solver = cp_model.CpSolver()
        status = solver.Solve(model)

        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))

    def test_afternoon_today_allows_day_off_tomorrow(self):
        model, x = _build_model()
        model.Add(x[0, 1, SHIFT_CLOSE] == 1)
        for s in ALL_SHIFTS:
            model.Add(x[0, 2, s] == 0)

        solver = cp_model.CpSolver()
        status = solver.Solve(model)

        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))

    def test_morning_today_leaves_tomorrow_unrestricted(self):
        model, x = _build_model()
        model.Add(x[0, 1, SHIFT_OPEN] == 1)
        model.Add(x[0, 2, SHIFT_OPEN] == 1)

        solver = cp_model.CpSolver()
        status = solver.Solve(model)

        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))


if __name__ == "__main__":
    unittest.main()
