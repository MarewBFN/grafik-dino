import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
import unittest

from ortools.sat.python import cp_model
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_app = QApplication.instance() or QApplication([])

from logic.generator.fix import setup_fix_hints_and_penalties
from logic.generator.manual_constraint import add_manual_shift_constraints
from logic.schedule_controller import ScheduleController
from logic.schedule_presenter import SchedulePresenter
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from ui import theme
from ui.day_edit_dialog import DayEditDialog

SHIFT_OPEN, SHIFT_CLOSE = 0, 1
START_SHIFT_MAP = {2: 15}
END_SHIFT_MAP = {8: 15}
SHIFT_NIGHT = 14
ALL_SHIFTS = (SHIFT_OPEN, SHIFT_CLOSE, *START_SHIFT_MAP, *END_SHIFT_MAP, SHIFT_NIGHT)
NIGHT_HOURS = ("22:00", "06:00")


def _shop_with_night():
    shop = ShopConfig(2026, 8)
    loc = LocationConfig(key="site1", name="Site 1")
    loc.set_night_shift(*NIGHT_HOURS)
    shop.locations["site1"] = loc
    return shop


def _employee():
    return Employee(last_name="Kowalski", first_name="Jan", location_key="site1")


class ScheduleControllerNightShiftTests(unittest.TestCase):
    def _controller(self):
        shop = _shop_with_night()
        schedule = MonthSchedule(2026, 8)
        emp = _employee()
        schedule.add_employee(emp)
        return ScheduleController(schedule, shop), emp

    def test_set_day_hours_accepts_exact_configured_night_window(self):
        controller, emp = self._controller()
        controller.set_day_hours(emp, 3, *NIGHT_HOURS)

        ds = controller.get_day(emp, 3)
        self.assertEqual((ds.start, ds.end), NIGHT_HOURS)
        self.assertTrue(ds.is_locked)

    def test_set_day_hours_rejects_arbitrary_overnight_range(self):
        controller, emp = self._controller()
        controller.set_day_hours(emp, 3, "23:00", "05:00")  # not the configured window

        ds = controller.get_day(emp, 3)
        self.assertIsNone(ds.start)
        self.assertIsNone(ds.end)

    def test_set_day_hours_rejects_night_window_without_location_configured(self):
        shop = ShopConfig(2026, 8)  # no locations at all
        schedule = MonthSchedule(2026, 8)
        emp = Employee(last_name="Nowak", first_name="Anna")
        schedule.add_employee(emp)
        controller = ScheduleController(schedule, shop)

        controller.set_day_hours(emp, 3, *NIGHT_HOURS)

        ds = controller.get_day(emp, 3)
        self.assertIsNone(ds.start)

    def test_set_shift_work_accepts_exact_configured_night_window(self):
        controller, emp = self._controller()
        controller.set_shift(emp, 3, "WORK", *NIGHT_HOURS)

        ds = controller.get_day(emp, 3)
        self.assertEqual((ds.start, ds.end), NIGHT_HOURS)

    def test_set_shift_work_rejects_arbitrary_overnight_range(self):
        controller, emp = self._controller()
        controller.set_shift(emp, 3, "WORK", "23:00", "05:00")

        ds = controller.get_day(emp, 3)
        self.assertIsNone(ds.start)


class ManualConstraintNightShiftTests(unittest.TestCase):
    def _model_for_day(self, shop, emp, day=3):
        schedule = MonthSchedule(2026, 8)
        schedule.add_employee(emp)
        model = cp_model.CpModel()
        x = {(0, day, s): model.NewBoolVar(f"x_{s}") for s in ALL_SHIFTS}
        return schedule, model, x

    def test_locked_night_shift_is_hard_pinned_on_regenerate(self):
        shop = _shop_with_night()
        emp = _employee()
        schedule, model, x = self._model_for_day(shop, emp)
        schedule.set_day_hours(emp, 3, *NIGHT_HOURS)
        schedule.get_day(emp, 3).is_locked = True

        add_manual_shift_constraints(
            model, x, [emp], [3], schedule, shop, ALL_SHIFTS,
            SHIFT_OPEN, SHIFT_CLOSE, START_SHIFT_MAP, END_SHIFT_MAP,
            shift_night=SHIFT_NIGHT,
        )

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))
        self.assertEqual(solver.Value(x[0, 3, SHIFT_NIGHT]), 1)
        for s in ALL_SHIFTS:
            if s != SHIFT_NIGHT:
                self.assertEqual(solver.Value(x[0, 3, s]), 0)

    def test_locked_night_shift_survives_missing_open_hours_that_day(self):
        """Before the fix, resolve_manual_shift needed get_open_hours_for_day
        to succeed just to look up OPEN/CLOSE - a day without normal hours
        would silently drop the night lock. Night is checked first now."""
        shop = _shop_with_night()
        shop.locations["site1"].day_overrides[3] = ("", "")  # no hours that day
        emp = _employee()
        schedule, model, x = self._model_for_day(shop, emp)
        schedule.set_day_hours(emp, 3, *NIGHT_HOURS)
        schedule.get_day(emp, 3).is_locked = True

        add_manual_shift_constraints(
            model, x, [emp], [3], schedule, shop, ALL_SHIFTS,
            SHIFT_OPEN, SHIFT_CLOSE, START_SHIFT_MAP, END_SHIFT_MAP,
            shift_night=SHIFT_NIGHT,
        )

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))
        self.assertEqual(solver.Value(x[0, 3, SHIFT_NIGHT]), 1)


class FixModeNightShiftTests(unittest.TestCase):
    def test_nominal_hours_count_night_duration_not_standard_shift(self):
        shop = _shop_with_night()  # 8h window
        emp = _employee()
        schedule = MonthSchedule(2026, 8)
        schedule.add_employee(emp)
        schedule.set_day_hours(emp, 3, *NIGHT_HOURS)
        schedule.get_day(emp, 3).is_locked = True

        model = cp_model.CpModel()
        x = {(0, 3, s): model.NewBoolVar(f"x_{s}") for s in ALL_SHIFTS}

        setup_fix_hints_and_penalties(
            model, x, [emp], [3], schedule, shop, ALL_SHIFTS,
            SHIFT_OPEN, SHIFT_CLOSE, START_SHIFT_MAP, END_SHIFT_MAP,
            shift_night=SHIFT_NIGHT,
        )
        model.Add(x[0, 3, SHIFT_NIGHT] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))


class SchedulePresenterNightShiftTests(unittest.TestCase):
    def test_night_shift_cell_shows_plus_one_and_night_background(self):
        shop = _shop_with_night()
        schedule = MonthSchedule(2026, 8)
        emp = _employee()
        schedule.add_employee(emp)
        schedule.set_day_hours(emp, 3, *NIGHT_HOURS)

        presenter = SchedulePresenter(schedule, shop)
        cell = presenter.get_cell_view(emp, 3)

        self.assertEqual(cell.text_start, "22:00")
        self.assertIn("06:00", cell.text_end)
        self.assertIn("+1", cell.text_end)
        self.assertEqual(cell.bg, theme.SHIFT_NIGHT)

    def test_normal_shift_cell_is_unaffected(self):
        shop = _shop_with_night()
        schedule = MonthSchedule(2026, 8)
        emp = _employee()
        schedule.add_employee(emp)
        schedule.set_day_hours(emp, 3, "08:00", "16:00")

        presenter = SchedulePresenter(schedule, shop)
        cell = presenter.get_cell_view(emp, 3)

        self.assertNotEqual(cell.bg, theme.SHIFT_NIGHT)
        self.assertNotIn("+1", cell.text_end)


class DayEditDialogNightShiftTests(unittest.TestCase):
    def test_toggling_night_checkbox_fills_and_locks_fields(self):
        dialog = DayEditDialog(night_hours=NIGHT_HOURS)
        dialog.night_check.setChecked(True)

        self.assertEqual(dialog.start_edit.get_time_str(), "22:00")
        self.assertEqual(dialog.end_edit.get_time_str(), "06:00")
        self.assertFalse(dialog.start_edit.isEnabled())
        self.assertFalse(dialog.end_edit.isEnabled())
        self.assertEqual(dialog.duration_label.text(), "Czas pracy: 8:00")

    def test_save_with_night_checkbox_returns_configured_window(self):
        dialog = DayEditDialog(night_hours=NIGHT_HOURS)
        dialog.night_check.setChecked(True)
        dialog.accept = lambda: None  # avoid closing a real (nonexistent) event loop
        dialog._save()

        self.assertEqual(dialog.result_mode, "hours")
        self.assertEqual((dialog.result_start, dialog.result_end), NIGHT_HOURS)

    def test_existing_night_shift_day_preselects_checkbox(self):
        dialog = DayEditDialog(start="22:00", end="06:00", night_hours=NIGHT_HOURS)
        self.assertTrue(dialog.night_check.isChecked())

    def test_no_night_hours_means_no_checkbox(self):
        dialog = DayEditDialog(night_hours=None)
        self.assertIsNone(dialog.night_check)

    def test_unchecking_night_reenables_fields_within_open_hours(self):
        dialog = DayEditDialog(open_start="05:30", open_end="22:45", night_hours=NIGHT_HOURS)
        dialog.night_check.setChecked(True)
        dialog.night_check.setChecked(False)

        self.assertTrue(dialog.start_edit.isEnabled())
        self.assertTrue(dialog.end_edit.isEnabled())


if __name__ == "__main__":
    unittest.main()
