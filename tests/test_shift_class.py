from pathlib import Path
import sys
import unittest

from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.generator.manual_constraint import add_manual_shift_constraints
from logic.schedule_controller import ScheduleController
from model.day_schedule import DaySchedule
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig


class DayScheduleShiftClassTests(unittest.TestCase):
    def test_set_shift_class_clears_other_fields(self):
        ds = DaySchedule()
        ds.set_hours("08:00", "16:00")

        ds.set_shift_class("1")

        self.assertEqual(ds.shift_class, "1")
        self.assertIsNone(ds.start)
        self.assertIsNone(ds.end)
        self.assertFalse(ds.is_leave)
        self.assertFalse(ds.is_sick)
        self.assertFalse(ds.is_day_off)

    def test_as_rows_shows_code_before_generation_and_normal_rows_after(self):
        ds = DaySchedule()
        ds.set_shift_class("2")
        self.assertEqual(ds.as_rows(), ("2", "", ""))

        ds.set_hours("14:00", "22:00")
        self.assertEqual(ds.shift_class, "2")
        self.assertEqual(ds.as_rows(), ("14:00", "22:00", "8:00"))

    def test_total_minutes_zero_before_generation(self):
        ds = DaySchedule()
        ds.set_shift_class("1")
        self.assertEqual(ds.total_minutes(), 0)


class ScheduleControllerShiftClassTests(unittest.TestCase):
    def _controller(self):
        shop = ShopConfig(2026, 8)
        schedule = MonthSchedule(2026, 8)
        emp = Employee("Kowalski", "Jan")
        schedule.add_employee(emp)
        return ScheduleController(schedule, shop), emp

    def test_set_shift_class_rejects_invalid_code(self):
        controller, emp = self._controller()
        controller.set_shift_class(emp, 1, "X")
        self.assertIsNone(controller.get_day(emp, 1).shift_class)
        self.assertEqual(controller.history, [])

    def test_set_shift_class_sets_code_and_supports_undo(self):
        controller, emp = self._controller()
        controller.set_shift_class(emp, 1, "1")

        self.assertEqual(controller.get_day(emp, 1).shift_class, "1")
        self.assertEqual(len(controller.history), 1)

        controller.undo()
        self.assertIsNone(controller.get_day(emp, 1).shift_class)

    def test_set_shift_class_accepts_can_work_code(self):
        """"W" (Może pracować, ui/main_window.py) - trzeci dozwolony kod
        obok "1"/"2"."""
        controller, emp = self._controller()
        controller.set_shift_class(emp, 1, "W")

        self.assertEqual(controller.get_day(emp, 1).shift_class, "W")
        self.assertEqual(len(controller.history), 1)

    def test_other_setters_clear_shift_class(self):
        controller, emp = self._controller()
        controller.set_shift_class(emp, 1, "1")

        controller.set_day_hours(emp, 1, "08:00", "16:00")
        self.assertIsNone(controller.get_day(emp, 1).shift_class)

        controller.set_shift_class(emp, 2, "2")
        controller.set_day_free(emp, 2)
        self.assertIsNone(controller.get_day(emp, 2).shift_class)

        controller.set_shift_class(emp, 3, "1")
        controller.set_day_leave(emp, 3)
        self.assertIsNone(controller.get_day(emp, 3).shift_class)


class ManualConstraintShiftClassTests(unittest.TestCase):
    def test_locked_morning_class_restricts_solver_to_morning_slots(self):
        SHIFT_OPEN, SHIFT_CLOSE = 0, 1
        START_SHIFT_MAP = {2: 15, 3: 30}
        END_SHIFT_MAP = {8: 15, 9: 30}
        all_shifts = (SHIFT_OPEN, SHIFT_CLOSE, *START_SHIFT_MAP, *END_SHIFT_MAP)

        shop = ShopConfig(2026, 8)
        schedule = MonthSchedule(2026, 8)
        emp = Employee("Nowak", "Anna")
        schedule.add_employee(emp)
        schedule.get_day(emp, 1).set_shift_class("1")

        model = cp_model.CpModel()
        x = {}
        for s in all_shifts:
            x[0, 1, s] = model.NewBoolVar(f"x_{s}")

        add_manual_shift_constraints(
            model, x, [emp], [1], schedule, shop, all_shifts,
            SHIFT_OPEN, SHIFT_CLOSE, START_SHIFT_MAP, END_SHIFT_MAP,
        )

        # Force one afternoon slot to 1 to prove the model is infeasible for it.
        model.Add(x[0, 1, SHIFT_CLOSE] == 1)
        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        self.assertEqual(status, cp_model.INFEASIBLE)

        model2 = cp_model.CpModel()
        x2 = {}
        for s in all_shifts:
            x2[0, 1, s] = model2.NewBoolVar(f"x_{s}")
        add_manual_shift_constraints(
            model2, x2, [emp], [1], schedule, shop, all_shifts,
            SHIFT_OPEN, SHIFT_CLOSE, START_SHIFT_MAP, END_SHIFT_MAP,
        )
        solver2 = cp_model.CpSolver()
        status2 = solver2.Solve(model2)
        self.assertIn(status2, (cp_model.OPTIMAL, cp_model.FEASIBLE))

        morning_slots = {SHIFT_OPEN, *START_SHIFT_MAP}
        chosen = [s for s in all_shifts if solver2.Value(x2[0, 1, s]) == 1]
        self.assertEqual(len(chosen), 1)
        self.assertIn(chosen[0], morning_slots)

    def test_can_work_forces_exactly_one_shift_of_any_type(self):
        """"W" (Może pracować) - w odróżnieniu od "1"/"2" nie zawęża do
        rano/popołudnie, tylko wymusza, że dzień NIE jest wolny (dokładnie
        jedna zmiana z całego zbioru), typ dobiera solver."""
        SHIFT_OPEN, SHIFT_CLOSE = 0, 1
        START_SHIFT_MAP = {2: 15}
        END_SHIFT_MAP = {8: 15}
        all_shifts = (SHIFT_OPEN, SHIFT_CLOSE, *START_SHIFT_MAP, *END_SHIFT_MAP)

        shop = ShopConfig(2026, 8)
        schedule = MonthSchedule(2026, 8)
        emp = Employee("Nowak", "Anna")
        schedule.add_employee(emp)
        schedule.get_day(emp, 1).set_shift_class("W")

        model = cp_model.CpModel()
        x = {(0, 1, s): model.NewBoolVar(f"x_{s}") for s in all_shifts}
        add_manual_shift_constraints(
            model, x, [emp], [1], schedule, shop, all_shifts,
            SHIFT_OPEN, SHIFT_CLOSE, START_SHIFT_MAP, END_SHIFT_MAP,
        )

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))
        chosen = [s for s in all_shifts if solver.Value(x[0, 1, s]) == 1]
        self.assertEqual(len(chosen), 1)

        # And it must actually be forced (not just allowed) - the "day off"
        # solution (all shifts 0) has to be infeasible.
        model2 = cp_model.CpModel()
        x2 = {(0, 1, s): model2.NewBoolVar(f"x_{s}") for s in all_shifts}
        add_manual_shift_constraints(
            model2, x2, [emp], [1], schedule, shop, all_shifts,
            SHIFT_OPEN, SHIFT_CLOSE, START_SHIFT_MAP, END_SHIFT_MAP,
        )
        for s in all_shifts:
            model2.Add(x2[0, 1, s] == 0)
        status2 = cp_model.CpSolver().Solve(model2)
        self.assertEqual(status2, cp_model.INFEASIBLE)

    def test_can_work_is_a_noop_on_a_closed_day(self):
        SHIFT_OPEN, SHIFT_CLOSE = 0, 1
        all_shifts = (SHIFT_OPEN, SHIFT_CLOSE)

        shop = ShopConfig(2026, 8)
        shop.locations = {}  # forces get_open_hours_for_day empty via shop-level fallback
        schedule = MonthSchedule(2026, 8)
        emp = Employee("Nowak", "Anna")
        schedule.add_employee(emp)
        schedule.get_day(emp, 1).set_shift_class("W")
        # Explicit "Nieczynne" override at the shop level.
        shop.day_overrides[1] = ("", "")

        model = cp_model.CpModel()
        x = {(0, 1, s): model.NewBoolVar(f"x_{s}") for s in all_shifts}
        add_manual_shift_constraints(
            model, x, [emp], [1], schedule, shop, all_shifts,
            SHIFT_OPEN, SHIFT_CLOSE, {}, {},
        )
        for s in all_shifts:
            model.Add(x[0, 1, s] == 0)

        status = cp_model.CpSolver().Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))


if __name__ == "__main__":
    unittest.main()
