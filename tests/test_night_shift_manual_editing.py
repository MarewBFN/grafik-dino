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

from logic.generator.custom_profile_wiring import default_policies
from logic.generator.fix import setup_fix_hints_and_penalties
from logic.generator.manual_constraint import add_manual_shift_constraints
from logic.generator.night_constraint import add_no_night_constraint
from logic.schedule_controller import ScheduleController
from logic.schedule_presenter import SchedulePresenter
from model.business_profile import register_custom_profile
from model.custom_profile import (
    RULE_TYPE_MIN_STAFF_WITH_ROLE,
    CustomBusinessProfile,
    RoleDefinition,
    RuleInstance,
)
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from ui import theme
from ui.config_dialog import ConfigDialog
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

    def test_no_night_does_not_block_a_night_shift_window_that_is_not_actually_nocturnal(self):
        """Codex review finding on PR #3 (P2): normalize_night_shift only
        requires start != end - a location could configure "night_shift" as
        an arbitrary fixed midday block (e.g. a delivery-unloading window)
        that never touches 22:00-06:00. no_night describes "before 6:00 and
        after 22:00" (ui/employee_dialog.py); it must not block a
        configured window that doesn't actually overlap that range."""
        shop = ShopConfig(2026, 8)
        loc = LocationConfig(key="site1", name="Site 1")
        loc.set_night_shift("10:00", "14:00")  # a fixed midday block, not night
        shop.locations["site1"] = loc
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
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))

    def test_no_night_blocks_a_fixed_window_that_partially_overlaps_night_hours(self):
        """Regression companion to the test above: a fixed window that
        genuinely touches the night range (05:00-06:00 here) must still be
        blocked, even though it isn't the "canonical" 22:00-06:00 window."""
        shop = ShopConfig(2026, 8)
        loc = LocationConfig(key="site1", name="Site 1")
        loc.set_night_shift("05:00", "13:00")  # overlaps 22:00-06:00 by one hour
        shop.locations["site1"] = loc
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


class NoNightConstraintCloseShiftBugTests(unittest.TestCase):
    """Refactoring finding (constraint plan, priority 1): add_no_night_constraint
    computed the CLOSE shift's forbidden-window check against a stale `start`
    variable left over from the OPEN check above it, instead of the CLOSE
    shift's own start time. For any shop opening at/before 6:00, that stale
    `start.hour <= 6` was always true, so the CLOSE shift was forbidden for
    every no_night employee regardless of when it actually ended - even on a
    shop that closes well before 22:00. Fixed by sharing the (now also
    corrected) window computation with
    generic_rules.py::build_role_time_restriction instead of a second,
    independently-maintained copy."""

    def _early_opening_shop(self):
        shop = ShopConfig(2026, 8)
        for wd in range(7):
            shop.open_hours[wd] = ("05:00", "20:00")  # opens early, closes well before 22:00
        return shop

    def test_no_night_does_not_forbid_a_close_shift_that_never_touches_night_hours(self):
        shop = self._early_opening_shop()
        emp = Employee(last_name="Kowalski", first_name="Jan", no_night=True)

        model = cp_model.CpModel()
        x = {(0, 3, s): model.NewBoolVar(f"x_{s}") for s in ALL_SHIFTS}

        add_no_night_constraint(
            model, x, [emp], [3], shop, ALL_SHIFTS,
            SHIFT_OPEN, SHIFT_CLOSE, START_SHIFT_MAP, END_SHIFT_MAP,
            soft=False, shift_night=SHIFT_NIGHT,
        )
        model.Add(x[0, 3, SHIFT_CLOSE] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))

    def test_no_night_still_forbids_a_close_shift_that_genuinely_ends_at_night(self):
        """Regression companion: a shop that actually closes late (touching
        22:00-06:00) must still block the CLOSE shift for no_night employees."""
        shop = ShopConfig(2026, 8)  # default open hours close at 22:45/23:00

        emp = Employee(last_name="Kowalski", first_name="Jan", no_night=True)

        model = cp_model.CpModel()
        x = {(0, 3, s): model.NewBoolVar(f"x_{s}") for s in ALL_SHIFTS}

        add_no_night_constraint(
            model, x, [emp], [3], shop, ALL_SHIFTS,
            SHIFT_OPEN, SHIFT_CLOSE, START_SHIFT_MAP, END_SHIFT_MAP,
            soft=False, shift_night=SHIFT_NIGHT,
        )
        model.Add(x[0, 3, SHIFT_CLOSE] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertEqual(status, cp_model.INFEASIBLE)


class NoNightConstraintLocationHoursBugTests(unittest.TestCase):
    """Codex review finding on this PR: add_no_night_constraint evaluated
    the OPEN/CLOSE/START/END forbidding against project-wide shop hours even
    for an employee assigned to a location with its own, different hours -
    unlike the SHIFT_NIGHT check just above it, which was already
    location-aware. A location open well outside the project's default
    hours (or vice versa) got no_night evaluated against the wrong hours."""

    def _shop_with_daytime_only_location(self):
        shop = ShopConfig(2026, 8)  # default hours touch night at both ends (05:30/22:45)
        loc = LocationConfig(key="site1", name="Site 1")
        for wd in range(7):
            loc.open_hours[wd] = ("08:00", "20:00")  # this location never touches night
        shop.locations["site1"] = loc
        return shop

    def test_no_night_does_not_forbid_open_shift_using_the_employees_own_location_hours(self):
        shop = self._shop_with_daytime_only_location()
        emp = Employee(last_name="Kowalski", first_name="Jan", location_key="site1", no_night=True)

        model = cp_model.CpModel()
        x = {(0, 3, s): model.NewBoolVar(f"x_{s}") for s in ALL_SHIFTS}

        add_no_night_constraint(
            model, x, [emp], [3], shop, ALL_SHIFTS,
            SHIFT_OPEN, SHIFT_CLOSE, START_SHIFT_MAP, END_SHIFT_MAP,
            soft=False, shift_night=SHIFT_NIGHT,
        )
        model.Add(x[0, 3, SHIFT_OPEN] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))

    def test_no_night_does_not_forbid_close_shift_using_the_employees_own_location_hours(self):
        shop = self._shop_with_daytime_only_location()
        emp = Employee(last_name="Kowalski", first_name="Jan", location_key="site1", no_night=True)

        model = cp_model.CpModel()
        x = {(0, 3, s): model.NewBoolVar(f"x_{s}") for s in ALL_SHIFTS}

        add_no_night_constraint(
            model, x, [emp], [3], shop, ALL_SHIFTS,
            SHIFT_OPEN, SHIFT_CLOSE, START_SHIFT_MAP, END_SHIFT_MAP,
            soft=False, shift_night=SHIFT_NIGHT,
        )
        model.Add(x[0, 3, SHIFT_CLOSE] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))

    def test_no_night_still_forbids_open_shift_for_a_location_that_genuinely_opens_early(self):
        """Regression companion: the fix must stay location-aware in the
        other direction too - a location that itself opens before 6:00 must
        still block that employee's OPEN shift, even under a project default
        that doesn't touch night."""
        shop = ShopConfig(2026, 8)
        for wd in range(7):
            shop.open_hours[wd] = ("08:00", "20:00")  # project default never touches night
        loc = LocationConfig(key="site1", name="Site 1")
        for wd in range(7):
            loc.open_hours[wd] = ("05:00", "20:00")  # this location opens early
        shop.locations["site1"] = loc
        emp = Employee(last_name="Kowalski", first_name="Jan", location_key="site1", no_night=True)

        model = cp_model.CpModel()
        x = {(0, 3, s): model.NewBoolVar(f"x_{s}") for s in ALL_SHIFTS}

        add_no_night_constraint(
            model, x, [emp], [3], shop, ALL_SHIFTS,
            SHIFT_OPEN, SHIFT_CLOSE, START_SHIFT_MAP, END_SHIFT_MAP,
            soft=False, shift_night=SHIFT_NIGHT,
        )
        model.Add(x[0, 3, SHIFT_OPEN] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertEqual(status, cp_model.INFEASIBLE)


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


class EditDayLocationHoursBugTests(unittest.TestCase):
    """Codex review finding on this PR: _edit_day() bounded/validated a
    manual entry against project-wide open hours even for an employee
    assigned to a location with its own, different hours - night_hours was
    already resolved per location, open_start/open_end were not, so the
    dialog could reject a legal local shift or accept a locally-invalid one."""

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

    def test_day_editor_uses_the_employees_own_location_hours(self):
        shop = ShopConfig(2026, 8)  # project default hours: 05:30/22:45-23:00
        loc = LocationConfig(key="site1", name="Site 1")
        for wd in range(7):
            loc.open_hours[wd] = ("08:00", "20:00")
        shop.locations["site1"] = loc
        emp = Employee(last_name="Kowalski", first_name="Jan", location_key="site1")
        schedule = MonthSchedule(2026, 8)
        schedule.add_employee(emp)
        window = self._make_window(shop, schedule)

        fake_dialog = MagicMock()
        fake_dialog.exec.return_value = QDialog.Rejected  # only need the call args below

        with patch("ui.main_window.DayEditDialog", return_value=fake_dialog) as mock_dialog:
            window._edit_day(emp, 3)

        mock_dialog.assert_called_once()
        self.assertEqual(mock_dialog.call_args.kwargs["open_start"], "08:00")
        self.assertEqual(mock_dialog.call_args.kwargs["open_end"], "20:00")


class OpenNewProjectCustomProfilePolicyBugTests(unittest.TestCase):
    """Codex review finding on this PR: _open_new_project() never applied a
    freshly-selected custom profile's default_policies, unlike
    _apply_first_run_wizard_result - apply_registry skips a spec whose
    policy key is absent from shop.constraint_policies, so every rule of the
    profile (including one configured as MANDATORY in the wizard) stayed
    silently DISABLED until Config was opened and saved."""

    def test_new_project_applies_the_selected_custom_profiles_default_policies(self):
        profile = CustomBusinessProfile(
            key="custom_test_new_project_policy",
            display_name="Test Policy",
            roles=[RoleDefinition(key="guard", label="Ochroniarz")],
            rules=[RuleInstance(
                type=RULE_TYPE_MIN_STAFF_WITH_ROLE, role_key="guard",
                policy="MANDATORY", params={"min_count": 1, "scope": "open"},
            )],
        )
        register_custom_profile(profile)

        window = MainWindow.__new__(MainWindow)
        window.schedule = None
        window.year, window.month = 2026, 8
        window._set_date_controls = MagicMock()
        window._update_nominal_hours_label = MagicMock()
        window._sync_everything = MagicMock()
        window.statusBar = MagicMock(return_value=MagicMock())

        fake_dialog = MagicMock()
        fake_dialog.exec.return_value = QDialog.Accepted
        fake_dialog.result_year, fake_dialog.result_month = 2026, 8
        fake_dialog.result_business_type = profile.key

        with patch("ui.main_window.NewProjectDialog", return_value=fake_dialog):
            window._open_new_project()

        expected = default_policies(profile)
        for key, policy in expected.items():
            self.assertEqual(
                window.shop_config.constraint_policies.get(key), policy,
                f"policy {key!r} not initialized",
            )


class ConfigDialogLocationRenameBugTests(unittest.TestCase):
    """Codex review finding on this PR: ConfigDialog._save() regenerated
    every location's key from its current name via slugify() on every save,
    while Employee.location_key is a stable reference recorded once - so
    renaming a location with assigned employees replaced the whole
    shop_config.locations mapping under a new key, and ShopConfig.get_location
    silently fell back to the project-wide configuration for those
    employees."""

    def test_renaming_a_location_preserves_its_key(self):
        from ui.config_dialog import _LocationRow

        shop = ShopConfig(2026, 8)  # project default hours: 05:30-22:45/23:00
        shop.locations["site1"] = LocationConfig(
            key="site1", name="Site 1", open_hours={wd: ("08:00", "20:00") for wd in range(7)},
        )
        emp = Employee(last_name="Kowalski", first_name="Jan", location_key="site1")

        dialog = ConfigDialog.__new__(ConfigDialog)
        dialog.shop_config = shop
        dialog.name_edit = MagicMock(text=MagicMock(return_value=""))
        dialog.business_type_selector = MagicMock(currentData=MagicMock(return_value=shop.business_type))
        dialog.open_edits = {}
        dialog.sunday_checks = {}
        dialog.max_consecutive = MagicMock(value=MagicMock(return_value=4))
        dialog.standard_daily_hours = MagicMock(value=MagicMock(return_value=8.0))
        dialog.min_open = MagicMock(value=MagicMock(return_value=3))
        dialog.min_close = MagicMock(value=MagicMock(return_value=3))
        dialog.force_fulltime_845 = MagicMock(isChecked=MagicMock(return_value=True))
        dialog.hl_consecutive = MagicMock(isChecked=MagicMock(return_value=False))
        dialog.rest_11h_mode_selector = MagicMock(currentData=MagicMock(return_value="standard"))
        dialog.solver_time_limit = MagicMock(value=MagicMock(return_value=60))
        dialog.policy_selectors = {}
        dialog.accept = MagicMock()  # ConfigDialog.__new__ skips QDialog.__init__

        # Same row, but renamed - open/close hours (08:00-20:00) and
        # original_key ("site1", set by _build_locations_tab when this row
        # was populated) unchanged, only the display name differs.
        renamed_row = _LocationRow(
            lambda r: None, name="Nowa Nazwa",
            open_time="08:00", close_time="20:00", original_key="site1",
        )
        dialog._location_rows = [renamed_row]

        dialog._save()

        self.assertIn("site1", shop.locations, "renamed location lost its original, stable key")
        self.assertEqual(shop.locations["site1"].name, "Nowa Nazwa")
        # 3 (Aug 2026) is a Monday - if the rename had dropped the "site1"
        # key, get_location would silently fall back to the project-wide
        # default hours (05:30/22:45) instead of the location's own.
        self.assertEqual(shop.get_location(emp).get_open_hours_for_day(3), ("08:00", "20:00"))


if __name__ == "__main__":
    unittest.main()
