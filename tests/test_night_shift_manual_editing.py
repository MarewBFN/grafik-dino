import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

from ortools.sat.python import cp_model
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_app = QApplication.instance() or QApplication([])

from logic.generator.fix import setup_fix_hints_and_penalties
from logic.generator.manual_constraint import add_manual_shift_constraints
from logic.generator.night_constraint import add_no_night_constraint
from logic.schedule_controller import ScheduleController
from logic.schedule_presenter import SchedulePresenter
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from ui import theme
from ui.day_edit_dialog import DayEditDialog
from ui.main_window import MainWindow

SHIFT_OPEN, SHIFT_CLOSE = 0, 1
START_SHIFT_MAP = {2: 15}
END_SHIFT_MAP = {8: 15}
SHIFT_NIGHT = 14
ALL_SHIFTS = (SHIFT_OPEN, SHIFT_CLOSE, *START_SHIFT_MAP, *END_SHIFT_MAP, SHIFT_NIGHT)
NIGHT_HOURS = ("22:00", "06:00")


def _shop_with_night():
    shop = ShopConfig(2026, 8)
    # Default open_hours already overlap 22:00-06:00, so this auto-detects
    # the standard night window - LocationConfig no longer has a way to
    # configure an arbitrary/custom night window (see model/location.py).
    loc = LocationConfig(key="site1", name="Site 1")
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


class NoNightConstraintShiftNightTests(unittest.TestCase):
    """Codex review finding on PR #2: manual_constraint.py recognizes and
    hard-pins a manually-entered night shift purely by matching the
    location's configured window - it never checked no_night. Meanwhile
    add_no_night_constraint never touched SHIFT_NIGHT at all (it only knew
    about OPEN/CLOSE/START/END). Combined, a no_night=True employee could be
    manually locked into the night shift with the model still solving
    "successfully", silently violating their restriction instead of the
    generator reporting infeasible."""

    def test_no_night_employee_cannot_be_manually_locked_into_night_shift(self):
        shop = _shop_with_night()
        emp = Employee(last_name="Kowalski", first_name="Jan", location_key="site1", no_night=True)
        schedule = MonthSchedule(2026, 8)
        schedule.add_employee(emp)
        schedule.set_day_hours(emp, 3, *NIGHT_HOURS)
        schedule.get_day(emp, 3).is_locked = True

        model = cp_model.CpModel()
        x = {(0, 3, s): model.NewBoolVar(f"x_{s}") for s in ALL_SHIFTS}

        add_manual_shift_constraints(
            model, x, [emp], [3], schedule, shop, ALL_SHIFTS,
            SHIFT_OPEN, SHIFT_CLOSE, START_SHIFT_MAP, END_SHIFT_MAP,
            shift_night=SHIFT_NIGHT,
        )
        add_no_night_constraint(
            model, x, [emp], [3], shop, ALL_SHIFTS,
            SHIFT_OPEN, SHIFT_CLOSE, START_SHIFT_MAP, END_SHIFT_MAP,
            soft=False, shift_night=SHIFT_NIGHT,
        )

        status = cp_model.CpSolver().Solve(model)
        self.assertEqual(status, cp_model.INFEASIBLE)

    def test_no_night_employee_is_blocked_from_night_shift_even_without_manual_lock(self):
        shop = _shop_with_night()
        emp = Employee(last_name="Kowalski", first_name="Jan", location_key="site1", no_night=True)

        model = cp_model.CpModel()
        x = {(0, 3, s): model.NewBoolVar(f"x_{s}") for s in ALL_SHIFTS}

        add_no_night_constraint(
            model, x, [emp], [3], shop, ALL_SHIFTS,
            SHIFT_OPEN, SHIFT_CLOSE, START_SHIFT_MAP, END_SHIFT_MAP,
            soft=False, shift_night=SHIFT_NIGHT,
        )
        model.Add(x[0, 3, SHIFT_NIGHT] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertEqual(status, cp_model.INFEASIBLE)

    def test_employee_without_no_night_flag_can_still_be_locked_into_night_shift(self):
        """Regression: the fix must not block an ordinary (non no_night)
        employee's manual night lock - this worked before and must keep
        working."""
        shop = _shop_with_night()
        emp = _employee()  # no_night defaults to False
        schedule = MonthSchedule(2026, 8)
        schedule.add_employee(emp)
        schedule.set_day_hours(emp, 3, *NIGHT_HOURS)
        schedule.get_day(emp, 3).is_locked = True

        model = cp_model.CpModel()
        x = {(0, 3, s): model.NewBoolVar(f"x_{s}") for s in ALL_SHIFTS}

        add_manual_shift_constraints(
            model, x, [emp], [3], schedule, shop, ALL_SHIFTS,
            SHIFT_OPEN, SHIFT_CLOSE, START_SHIFT_MAP, END_SHIFT_MAP,
            shift_night=SHIFT_NIGHT,
        )
        add_no_night_constraint(
            model, x, [emp], [3], shop, ALL_SHIFTS,
            SHIFT_OPEN, SHIFT_CLOSE, START_SHIFT_MAP, END_SHIFT_MAP,
            soft=False, shift_night=SHIFT_NIGHT,
        )

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))
        self.assertEqual(solver.Value(x[0, 3, SHIFT_NIGHT]), 1)

    def test_no_night_soft_policy_adds_violation_instead_of_hard_block(self):
        shop = _shop_with_night()
        emp = Employee(last_name="Kowalski", first_name="Jan", location_key="site1", no_night=True)

        model = cp_model.CpModel()
        x = {(0, 3, s): model.NewBoolVar(f"x_{s}") for s in ALL_SHIFTS}
        model.Add(sum(x[0, 3, s] for s in ALL_SHIFTS) <= 1)

        violations = add_no_night_constraint(
            model, x, [emp], [3], shop, ALL_SHIFTS,
            SHIFT_OPEN, SHIFT_CLOSE, START_SHIFT_MAP, END_SHIFT_MAP,
            soft=True, shift_night=SHIFT_NIGHT,
        )
        night_violation = next(v for v in violations if v.Name() == f"night_violation_e0_d3_s{SHIFT_NIGHT}")
        model.Add(x[0, 3, SHIFT_NIGHT] == 1)

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))
        self.assertEqual(solver.Value(x[0, 3, SHIFT_NIGHT]), 1)
        self.assertEqual(solver.Value(night_violation), 1)

    # test_no_night_does_not_block_a_night_shift_window_that_is_not_actually_nocturnal
    # and test_no_night_blocks_a_fixed_window_that_partially_overlaps_night_hours
    # (Codex review regression coverage for a bug where normalize_night_shift
    # allowed an arbitrary non-nocturnal/partial-overlap window to be
    # misclassified) were removed: LocationConfig can no longer configure an
    # arbitrary "night_shift" window at all (see model/location.py) - a
    # location's night window is always exactly 22:00-06:00 or None, so
    # neither scenario can be constructed any more.

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


class MainWindowNoNightWarningTests(unittest.TestCase):
    """Codex review finding on PR #2: ui/day_edit_dialog.py showed the
    "Zmiana nocna" checkbox to a no_night=True employee with no warning at
    all - the conflict only ever surfaced later as a generic, hard-to-trace
    "infeasible" from the generator. _edit_day() now asks for confirmation
    before saving. Constructs MainWindow via __new__ to skip its heavy
    __init__ (menus/toolbars/last-project loading) - only the attributes
    _edit_day actually touches are set by hand."""

    def _make_window(self, shop, schedule):
        window = MainWindow.__new__(MainWindow)
        window.shop_config = shop
        window.schedule = schedule
        window.controller = MagicMock()
        window.controller.get_day = schedule.get_day
        window.controller.schedule = schedule
        window._sync_everything = MagicMock()
        window.statusBar = MagicMock(return_value=MagicMock())
        return window

    def _fake_dialog(self):
        dialog = MagicMock()
        dialog.exec.return_value = QDialog.Accepted
        dialog.result_mode = "hours"
        dialog.result_start, dialog.result_end = NIGHT_HOURS
        return dialog

    def test_warns_before_saving_night_shift_for_no_night_employee(self):
        shop = _shop_with_night()
        emp = Employee(last_name="Kowalski", first_name="Jan", location_key="site1", no_night=True)
        schedule = MonthSchedule(2026, 8)
        schedule.add_employee(emp)
        window = self._make_window(shop, schedule)

        with patch("ui.main_window.DayEditDialog", return_value=self._fake_dialog()), \
             patch("ui.main_window.QMessageBox.question", return_value=QMessageBox.No) as mock_question:
            window._edit_day(emp, 3)

        mock_question.assert_called_once()
        window.controller.set_day_hours.assert_not_called()

    def test_proceeds_to_save_when_user_confirms_the_warning(self):
        shop = _shop_with_night()
        emp = Employee(last_name="Kowalski", first_name="Jan", location_key="site1", no_night=True)
        schedule = MonthSchedule(2026, 8)
        schedule.add_employee(emp)
        window = self._make_window(shop, schedule)

        with patch("ui.main_window.DayEditDialog", return_value=self._fake_dialog()), \
             patch("ui.main_window.QMessageBox.question", return_value=QMessageBox.Yes) as mock_question:
            window._edit_day(emp, 3)

        mock_question.assert_called_once()
        window.controller.set_day_hours.assert_called_once_with(emp, 3, *NIGHT_HOURS)

    def test_no_warning_for_employee_without_no_night_flag(self):
        shop = _shop_with_night()
        emp = _employee()  # no_night defaults to False
        schedule = MonthSchedule(2026, 8)
        schedule.add_employee(emp)
        window = self._make_window(shop, schedule)

        with patch("ui.main_window.DayEditDialog", return_value=self._fake_dialog()), \
             patch("ui.main_window.QMessageBox.question") as mock_question:
            window._edit_day(emp, 3)

        mock_question.assert_not_called()
        window.controller.set_day_hours.assert_called_once_with(emp, 3, *NIGHT_HOURS)


if __name__ == "__main__":
    unittest.main()
