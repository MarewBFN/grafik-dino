"""Ręczne wpisy pracowników rotacji służby liczone jako pokrycie doby
(logic/generator/duty_rotation_manual_coverage.py, decyzja użytkownika
2026-09-25): plan zmian resztkowych, generowanie end-to-end, ręczna edycja
przez dwuklik (ScheduleController, DayEditDialog)."""

import io
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from logic.auto_generator import AutoScheduleGenerator
from logic.duty_coverage_presenter import is_day_fully_covered
from logic.generator.custom_profile_wiring import default_policies
from logic.generator.duty_rotation_manual_coverage import (
    DAY_MINUTES,
    DutyShiftMap,
    build_duty_coverage_plan,
    manual_offsets,
    planned_minutes_expr,
)
from logic.schedule_controller import ScheduleController
from model.business_profile import register_custom_profile
from model.constraint_policy import ConstraintPolicy
from model.custom_profile import CustomBusinessProfile
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from ui.day_edit_dialog import DayEditDialog

YEAR, MONTH = 2026, 10
ROTATION = {
    "only_12_24h": True,
    "weekend_full": {"start": "08:00"},
    "weekend_half_a": {"start": "08:00", "end": "20:00"},
    "weekend_half_b": {"start": "20:00", "end": "08:00"},
}


def _project(n=5):
    profile = CustomBusinessProfile(key="test_manual_coverage", display_name="T", roles=[], rules=[])
    register_custom_profile(profile)
    shop = ShopConfig(YEAR, MONTH)
    shop.business_type = profile.key
    loc = LocationConfig(key="pge", name="PGE", closed_on_public_holidays=False)
    loc.set_24_7(True)
    loc.set_duty_rotation(ROTATION)
    shop.locations = {"pge": loc}
    shop.constraint_policies.update(default_policies(profile))
    shop.constraint_policies["balance"] = ConstraintPolicy.DISABLED
    shop.constraint_policies["monthly_hours"] = ConstraintPolicy.DISABLED
    employees = [Employee(last_name=f"G{i}", first_name="X", location_key="pge") for i in range(n)]
    return shop, MonthSchedule(YEAR, MONTH, employees=employees), employees


def _lock(schedule, emp, day, start, end):
    schedule.get_day(emp, day).set_hours(start, end)
    schedule.get_day(emp, day).is_locked = True


def _hm(minutes):
    return f"{(minutes % DAY_MINUTES) // 60:02d}:{minutes % 60:02d}"


def _pieces(plan, day):
    return [(_hm(s), _hm(e)) for s, e in plan.day_pieces("pge", day)]


class PlanTests(unittest.TestCase):
    def test_users_example_07_19_trims_and_merges(self):
        """Przykład z pytania do użytkownika: PGE 08-20 / 20-08, ręcznie
        10.10 07:00-19:00 -> noc 9.10 20:00-07:00, 10.10 19:00-08:00."""
        shop, schedule, employees = _project()
        _lock(schedule, employees[0], 10, "07:00", "19:00")

        plan = build_duty_coverage_plan(schedule, shop, employees)

        self.assertEqual(_pieces(plan, 9), [("08:00", "20:00"), ("20:00", "07:00")])
        self.assertEqual(_pieces(plan, 10), [("19:00", "08:00")])
        self.assertTrue(plan.is_planned("pge", 9) and plan.is_planned("pge", 10))
        self.assertFalse(plan.is_planned("pge", 11))
        self.assertTrue(plan.is_fixed(employees[0], 10))

    def test_short_piece_after_midnight_merges_with_next_day(self):
        """Ręcznie 7.10 22:00-06:00: zostaje 06:00-08:00 (2h) - scalone ze
        zmianą 8.10 08:00-20:00 w jedną 06:00-20:00, w komórce 8.10."""
        shop, schedule, employees = _project()
        _lock(schedule, employees[0], 7, "22:00", "06:00")

        plan = build_duty_coverage_plan(schedule, shop, employees)

        self.assertEqual(_pieces(plan, 7), [("08:00", "22:00")])
        self.assertEqual(_pieces(plan, 8), [("06:00", "20:00"), ("20:00", "08:00")])

    def test_manual_shift_matching_the_rotation_needs_no_plan(self):
        shop, schedule, employees = _project()
        _lock(schedule, employees[0], 10, "08:00", "20:00")

        self.assertIsNone(build_duty_coverage_plan(schedule, shop, employees))

    def test_fixed_manual_minutes_count_to_the_employees_hours(self):
        from collections import defaultdict

        from logic.generator.duty_rotation_manual_coverage import CUSTOM_KEYS

        shop, schedule, employees = _project()
        _lock(schedule, employees[0], 10, "07:00", "19:00")
        duty_shifts = DutyShiftMap({key: 100 + i for i, key in enumerate(CUSTOM_KEYS)})
        duty_shifts.plan = build_duty_coverage_plan(schedule, shop, employees)
        x = defaultdict(int)  # żadna zmiana resztkowa nie przydzielona
        days = list(range(1, 32))

        self.assertEqual(planned_minutes_expr(x, 0, employees[0], days, duty_shifts), 12 * 60)
        self.assertEqual(planned_minutes_expr(x, 1, employees[1], days, duty_shifts), 0)


class RestAroundPlannedDaysTests(unittest.TestCase):
    def _model(self, schedule, shop, employees):
        from ortools.sat.python import cp_model

        from logic.generator.duty_rotation_manual_coverage import CUSTOM_KEYS
        from logic.generator.duty_rotation_rest_constraint import add_duty_rotation_rest_constraint

        keys = ("weekday_long", "weekday_short", "weekend_full", "weekend_half_a", "weekend_half_b", *CUSTOM_KEYS)
        duty_shifts = DutyShiftMap({key: 100 + i for i, key in enumerate(keys)})
        duty_shifts.plan = build_duty_coverage_plan(schedule, shop, employees)
        days = list(range(1, schedule.days_in_month + 1))
        model = cp_model.CpModel()
        x = {
            (e, d, s): model.NewBoolVar(f"x_{e}_{d}_{s}")
            for e in range(len(employees)) for d in days for s in duty_shifts.values()
        }
        add_duty_rotation_rest_constraint(model, x, employees, days, shop, duty_shifts, schedule=schedule)
        return model, x, duty_shifts

    def test_day_fully_covered_by_manual_entries_does_not_end_the_rest_lookahead(self):
        """12.10 w całości ręcznie (08:00-19:00 + 19:00-08:00,
        oba niepasujące do rotacji) - doba 12 zaplanowana bez żadnej zmiany
        resztkowej. Po 24h 11.10 przy N=4 wymagane 72h odpoczynku, więc
        13.10 08:00 (24h później) musi być zabronione - wcześniej pusty
        dzień 12 kończył sprawdzanie kolejnych dni."""
        from ortools.sat.python import cp_model

        shop, schedule, employees = _project(n=4)
        _lock(schedule, employees[0], 12, "08:00", "19:00")
        _lock(schedule, employees[1], 12, "19:00", "08:00")
        model, x, duty_shifts = self._model(schedule, shop, employees)
        self.assertTrue(duty_shifts.plan.is_planned("pge", 12))
        self.assertEqual(duty_shifts.plan.day_pieces("pge", 12), [])

        model.Add(x[2, 11, duty_shifts["weekend_full"]] == 1)
        model.Add(x[2, 13, duty_shifts["weekend_half_a"]] == 1)

        self.assertEqual(cp_model.CpSolver().Solve(model), cp_model.INFEASIBLE)


class MaxConsecutiveAroundPlannedDaysTests(unittest.TestCase):
    def test_fixed_manual_entry_counts_as_a_work_day(self):
        """Ręczny wpis 08:00-20:00 pasujący do rotacji (9.10) w dobie
        zaplanowanej wokół cudzego wpisu 07:00-19:00 (10.10) jest stałym
        przedziałem planu (x == 0) - wcześniej przez to znikał z "Dni pod
        rząd" (przed planem liczył się jako x == 1)."""
        from types import SimpleNamespace

        from ortools.sat.python import cp_model

        from logic.generator.base_specs import _build_max_consecutive
        from logic.generator.duty_rotation_manual_coverage import CUSTOM_KEYS

        shop, schedule, employees = _project()
        shop.locations["pge"].constraints["max_consecutive_days"] = 4
        _lock(schedule, employees[0], 9, "08:00", "20:00")
        _lock(schedule, employees[1], 10, "07:00", "19:00")
        keys = ("weekday_long", "weekday_short", "weekend_full", "weekend_half_a", "weekend_half_b", *CUSTOM_KEYS)
        duty_shifts = DutyShiftMap({key: 100 + i for i, key in enumerate(keys)})
        duty_shifts.plan = build_duty_coverage_plan(schedule, shop, employees)
        self.assertTrue(duty_shifts.plan.is_fixed(employees[0], 9))

        days = list(range(1, schedule.days_in_month + 1))
        model = cp_model.CpModel()
        all_shifts = list(duty_shifts.values())
        x = {(e, d, s): model.NewBoolVar(f"x{e}_{d}_{s}") for e in range(len(employees)) for d in days for s in all_shifts}
        ctx = SimpleNamespace(
            model=model, x=x, employees=employees, days=days, shop=shop, all_shifts=all_shifts,
            trace=None, duty_shifts=duty_shifts,
        )
        _build_max_consecutive(ctx, soft=False)
        for d in (5, 6, 7, 8):
            model.Add(x[0, d, duty_shifts["weekend_half_a"]] == 1)

        self.assertEqual(cp_model.CpSolver().Solve(model), cp_model.INFEASIBLE)


class GenerationTests(unittest.TestCase):
    def _generate(self, schedule, shop):
        with redirect_stdout(io.StringIO()):
            return AutoScheduleGenerator(schedule, shop).generate(solver_time_limit_seconds=30, solver_workers=2)

    def _intervals(self, schedule, emp):
        out = []
        for d in range(1, schedule.days_in_month + 1):
            offsets = manual_offsets(schedule.get_day(emp, d))
            if offsets is not None:
                out.append((d * DAY_MINUTES + offsets[0], d * DAY_MINUTES + offsets[1]))
        return sorted(out)

    def _assert_month_consistent(self, schedule, shop, employees):
        for day in range(1, schedule.days_in_month + 1):
            self.assertTrue(is_day_fully_covered(schedule, shop, employees, day), f"dzień {day}")
        for emp in employees:
            ivs = self._intervals(schedule, emp)
            for (s1, e1), (s2, e2) in zip(ivs, ivs[1:]):
                self.assertGreaterEqual(s2 - e1, 11 * 60, f"{emp.last_name}: odpoczynek {_hm(e1)} -> {_hm(s2)}")

    def test_manual_07_19_counts_as_coverage(self):
        shop, schedule, employees = _project()
        _lock(schedule, employees[0], 10, "07:00", "19:00")

        result = self._generate(schedule, shop)

        self.assertTrue(result["success"], result)
        day10 = sorted((schedule.get_day(e, 10).start, schedule.get_day(e, 10).end) for e in employees
                       if not schedule.get_day(e, 10).is_empty())
        self.assertEqual(day10, [("07:00", "19:00"), ("19:00", "08:00")])
        self._assert_month_consistent(schedule, shop, employees)

    def test_manual_night_22_06_and_24h_shift(self):
        shop, schedule, employees = _project()
        _lock(schedule, employees[0], 7, "22:00", "06:00")
        schedule.get_day(employees[1], 15).set_full_day_shift("10:00")
        schedule.get_day(employees[1], 15).is_locked = True

        result = self._generate(schedule, shop)

        self.assertTrue(result["success"], result)
        self._assert_month_consistent(schedule, shop, employees)


class ClosedDayCellTests(unittest.TestCase):
    def test_grid_shows_a_piece_of_the_previous_doba_in_a_closed_days_cell(self):
        """17.10 ręcznie 15:30-01:30, 18.10 "Nieczynne" - reszta doby 17
        (01:30-08:00) to zmiana w komórce 18.10. Siatka maskowała komórki
        dnia zamkniętego (szare, puste), więc zmiana liczona do godzin i
        eksportu była niewidoczna."""
        from ui.grid_view import ScheduleGrid

        shop, schedule, employees = _project()
        shop.locations["pge"].day_overrides[18] = (None, None)
        schedule.get_day(employees[1], 18).set_hours("01:30", "08:00")

        grid = ScheduleGrid()
        grid.set_data(schedule, shop, ScheduleController(schedule, shop), location_filter="pge")
        grid.refresh()

        item = grid.item(1, 18 + grid._prev_col_offset)
        self.assertIn("01:30", item.text())
        empty_closed = grid.item(0, 18 + grid._prev_col_offset)
        self.assertEqual(empty_closed.text(), "")


class ManualEditingTests(unittest.TestCase):
    def test_controller_accepts_overnight_hours_for_duty_employee(self):
        shop, schedule, employees = _project()
        controller = ScheduleController(schedule, shop)

        controller.set_day_hours(employees[0], 5, "20:00", "08:00")

        ds = schedule.get_day(employees[0], 5)
        self.assertEqual((ds.start, ds.end, ds.is_locked), ("20:00", "08:00", True))

    def test_controller_still_rejects_overnight_hours_without_rotation(self):
        shop = ShopConfig(YEAR, MONTH)
        emp = Employee(last_name="Zwykly", first_name="X")
        schedule = MonthSchedule(YEAR, MONTH, employees=[emp])
        controller = ScheduleController(schedule, shop)

        controller.set_day_hours(emp, 5, "20:00", "08:00")

        self.assertTrue(schedule.get_day(emp, 5).is_empty())

    def test_day_edit_dialog_quick_24h_and_overnight(self):
        dialog = DayEditDialog(duty_rotation=ROTATION, open_start="00:00", open_end="23:45")
        dialog._apply_quick_shift("08:00", None)
        dialog._save()
        self.assertEqual((dialog.result_mode, dialog.result_start), ("full_day", "08:00"))

        dialog = DayEditDialog(duty_rotation=ROTATION, open_start="00:00", open_end="23:45")
        dialog.start_edit.set_time_str("20:00")
        dialog.end_edit.set_time_str("08:00")
        dialog._save()
        self.assertEqual((dialog.result_mode, dialog.result_start, dialog.result_end), ("hours", "20:00", "08:00"))


if __name__ == "__main__":
    unittest.main()
