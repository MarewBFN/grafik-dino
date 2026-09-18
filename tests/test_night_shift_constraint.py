from pathlib import Path
import sys
import unittest

from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.generator.night_shift_constraint import (
    night_shift_duration_minutes,
    night_shift_minutes_for_employee,
    add_night_shift_gate_constraint,
    add_night_shift_adjacency_constraint,
)
from logic.generator.constraints_logic import add_work_dependency_constraint
from logic.generator.availability_constraint import add_availability_constraint
from logic.generator.hours_constraint import add_monthly_hours_constraint, add_balance_constraint
from logic.generator.solution_mapper import save_solution
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig

SHIFT_OPEN, SHIFT_CLOSE = 0, 1
START_SHIFT_MAP = {2: 15, 3: 30}
END_SHIFT_MAP = {8: 15, 9: 30}
SHIFT_NIGHT = 14
ALL_SHIFTS = (SHIFT_OPEN, SHIFT_CLOSE, *START_SHIFT_MAP, *END_SHIFT_MAP, SHIFT_NIGHT)


def _location_with_night(key="site1"):
    # Default open_hours already overlap 22:00-06:00, so this auto-detects
    # the standard night window - LocationConfig no longer has a way to
    # configure an arbitrary/custom night window (see model/location.py).
    return LocationConfig(key=key, name="Site 1")


def _employee_at(location_key="site1", **kwargs):
    return Employee(last_name="Kowalski", first_name="Jan", location_key=location_key, **kwargs)


def _one_day_model():
    model = cp_model.CpModel()
    x = {(0, 1, SHIFT_NIGHT): model.NewBoolVar("x_night")}
    return model, x


DAY_1, DAY_2 = 3, 4  # Mon/Tue in the 2026-08 fixture below - never a "non-trade Sunday"


def _two_day_full_model():
    model = cp_model.CpModel()
    x = {}
    for d in (DAY_1, DAY_2):
        for s in ALL_SHIFTS:
            x[0, d, s] = model.NewBoolVar(f"x_{d}_{s}")
        model.Add(sum(x[0, d, s] for s in ALL_SHIFTS) <= 1)
    return model, x


class NightShiftDurationTests(unittest.TestCase):
    def test_duration_crossing_midnight(self):
        self.assertEqual(night_shift_duration_minutes(("22:00", "06:00")), 8 * 60)

    def test_duration_within_same_clock_day(self):
        self.assertEqual(night_shift_duration_minutes(("20:00", "23:00")), 3 * 60)

    def test_minutes_for_employee_zero_without_configured_window(self):
        shop = ShopConfig(2026, 8)
        emp = Employee(last_name="Nowak", first_name="Anna")
        self.assertEqual(night_shift_minutes_for_employee(shop, emp), 0)

    def test_minutes_for_employee_matches_location_window(self):
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_night()
        emp = _employee_at()
        self.assertEqual(night_shift_minutes_for_employee(shop, emp), 8 * 60)


class NightShiftGateTests(unittest.TestCase):
    def test_gate_blocks_employee_without_night_window(self):
        shop = ShopConfig(2026, 8)
        emp = Employee(last_name="Nowak", first_name="Anna")  # no location, no night_shift

        model, x = _one_day_model()
        add_night_shift_gate_constraint(model, x, [emp], [1], shop, SHIFT_NIGHT)
        model.Add(x[0, 1, SHIFT_NIGHT] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertEqual(status, cp_model.INFEASIBLE)

    def test_gate_allows_employee_with_configured_night_window(self):
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_night()
        emp = _employee_at()

        model, x = _one_day_model()
        add_night_shift_gate_constraint(model, x, [emp], [1], shop, SHIFT_NIGHT)
        model.Add(x[0, 1, SHIFT_NIGHT] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))


class NightShiftAdjacencyTests(unittest.TestCase):
    def test_night_shift_forbids_default_open_hours_next_day(self):
        """An 8h night shift ending at 06:00 leaves at most ~8h15 of real
        rest before the latest a normal shift can start under the default
        05:30-22:45 window (SHIFT_CLOSE start ~14:15) - every normal shift
        on day 2 should be forbidden, matching real Kodeks pracy 11h rest."""
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_night()
        emp = _employee_at()

        model, x = _two_day_full_model()
        add_night_shift_adjacency_constraint(
            model, x, [emp], [DAY_1, DAY_2], shop, SHIFT_NIGHT, SHIFT_OPEN, SHIFT_CLOSE,
            START_SHIFT_MAP, END_SHIFT_MAP,
        )

        model.Add(x[0, DAY_1, SHIFT_NIGHT] == 1)
        for s in ALL_SHIFTS:
            if s == SHIFT_NIGHT:
                continue
            model.Add(x[0, DAY_2, s] == 0)

        status = cp_model.CpSolver().Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))

    def test_night_shift_and_open_next_day_is_infeasible(self):
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_night()
        emp = _employee_at()

        model, x = _two_day_full_model()
        add_night_shift_adjacency_constraint(
            model, x, [emp], [DAY_1, DAY_2], shop, SHIFT_NIGHT, SHIFT_OPEN, SHIFT_CLOSE,
            START_SHIFT_MAP, END_SHIFT_MAP,
        )

        model.Add(x[0, DAY_1, SHIFT_NIGHT] == 1)
        model.Add(x[0, DAY_2, SHIFT_OPEN] == 1)  # opens 05:30, before night even ends at 06:00

        status = cp_model.CpSolver().Solve(model)
        self.assertEqual(status, cp_model.INFEASIBLE)

    def test_back_to_back_night_shifts_with_enough_rest_is_feasible(self):
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_night()
        emp = _employee_at()

        model, x = _two_day_full_model()
        add_night_shift_adjacency_constraint(
            model, x, [emp], [DAY_1, DAY_2], shop, SHIFT_NIGHT, SHIFT_OPEN, SHIFT_CLOSE,
            START_SHIFT_MAP, END_SHIFT_MAP,
        )

        model.Add(x[0, DAY_1, SHIFT_NIGHT] == 1)
        model.Add(x[0, DAY_2, SHIFT_NIGHT] == 1)  # ends day1 06:00, starts day2 22:00 -> 16h rest

        status = cp_model.CpSolver().Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))

    # test_back_to_back_night_shifts_without_enough_rest_is_infeasible and
    # test_late_shift_today_forbids_early_night_shift_tomorrow were removed:
    # both relied on constructing a location with a non-standard night
    # window (14h "18:00-08:00" / "00:30-08:30") via set_night_shift(), which
    # no longer exists - a location's night window is always exactly
    # 22:00-06:00 or None now (see model/location.py). Duration-math
    # coverage for arbitrary windows still exists directly against
    # night_shift_duration_minutes() in NightShiftDurationTests above.

    def test_employee_without_night_window_is_left_unconstrained(self):
        shop = ShopConfig(2026, 8)
        emp = Employee(last_name="Nowak", first_name="Anna")  # no night window at all

        model, x = _two_day_full_model()
        violations = add_night_shift_adjacency_constraint(
            model, x, [emp], [DAY_1, DAY_2], shop, SHIFT_NIGHT, SHIFT_OPEN, SHIFT_CLOSE,
            START_SHIFT_MAP, END_SHIFT_MAP,
        )
        self.assertEqual(violations, [])


class WorkDependencyNightExemptionTests(unittest.TestCase):
    def test_night_shift_does_not_require_open_close_coverage(self):
        """Etap C fix: without this exemption, a 24/7 profile with no
        OPEN/CLOSE constraint registered at all could never use SHIFT_NIGHT,
        since total_open_close would always be 0."""
        model = cp_model.CpModel()
        x = {(0, 1, s): model.NewBoolVar(f"x_{s}") for s in ALL_SHIFTS}
        model.Add(sum(x[0, 1, s] for s in ALL_SHIFTS) <= 1)

        add_work_dependency_constraint(
            model, x, [object()], [1], SHIFT_OPEN, SHIFT_CLOSE, ALL_SHIFTS,
            shift_night=SHIFT_NIGHT,
        )
        model.Add(x[0, 1, SHIFT_NIGHT] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))

    def test_other_work_shifts_still_require_open_close_coverage(self):
        """Regression: the exemption must be night-only - WORK_START/END
        still depend on someone covering OPEN/CLOSE that day, same as before."""
        model = cp_model.CpModel()
        x = {(0, 1, s): model.NewBoolVar(f"x_{s}") for s in ALL_SHIFTS}
        model.Add(sum(x[0, 1, s] for s in ALL_SHIFTS) <= 1)

        add_work_dependency_constraint(
            model, x, [object()], [1], SHIFT_OPEN, SHIFT_CLOSE, ALL_SHIFTS,
            shift_night=SHIFT_NIGHT,
        )
        model.Add(x[0, 1, 2] == 1)  # a START_SHIFT_MAP shift, no OPEN/CLOSE anywhere

        status = cp_model.CpSolver().Solve(model)
        self.assertEqual(status, cp_model.INFEASIBLE)


class AvailabilityNightExemptionTests(unittest.TestCase):
    def test_availability_restriction_does_not_block_night_shift(self):
        """An employee with an unrelated availability restriction must not
        have SHIFT_NIGHT silently forced to 0 - availability_mapper doesn't
        model night hours yet, so treating "not in the allowed set" as
        "forbidden" would wrongly block it for every restricted employee."""
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_night()
        emp = _employee_at(availability={0: [{"start": "08:00", "end": "16:00", "mode": "hard"}]})

        model, x = _two_day_full_model()
        add_availability_constraint(
            model, x, [emp], [DAY_1, DAY_2], shop, ALL_SHIFTS, SHIFT_OPEN, SHIFT_CLOSE,
            START_SHIFT_MAP, END_SHIFT_MAP, soft=False, shift_night=SHIFT_NIGHT,
        )
        model.Add(x[0, DAY_1, SHIFT_NIGHT] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))


class ShiftMinutesByTypeTests(unittest.TestCase):
    """White-box coverage of hours_constraint._shift_minutes_by_type - the
    piece that lets monthly_hours/balance count SHIFT_NIGHT's own duration
    instead of the employee's standard shift length (Etap C)."""

    def test_night_shift_gets_its_own_duration(self):
        from logic.generator.hours_constraint import _shift_minutes_by_type

        mapping = _shift_minutes_by_type(
            (SHIFT_OPEN, SHIFT_CLOSE, SHIFT_NIGHT),
            standard_minutes=510, overrides={SHIFT_NIGHT: 480},
        )
        self.assertEqual(mapping[SHIFT_OPEN], 510)
        self.assertEqual(mapping[SHIFT_CLOSE], 510)
        self.assertEqual(mapping[SHIFT_NIGHT], 480)

    def test_uniform_minutes_when_no_overrides_given(self):
        from logic.generator.hours_constraint import _shift_minutes_by_type

        mapping = _shift_minutes_by_type((SHIFT_OPEN, SHIFT_CLOSE), 510, {})
        self.assertTrue(all(v == 510 for v in mapping.values()))


class HoursAccountingTests(unittest.TestCase):
    def test_monthly_hours_constraint_accepts_night_shift_without_crashing(self):
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_night()  # 8h window
        emp = _employee_at(employment_fraction=1.0)
        schedule = MonthSchedule(2026, 8)
        schedule.add_employee(emp)

        model = cp_model.CpModel()
        x = {(0, 1, s): model.NewBoolVar(f"x_{s}") for s in ALL_SHIFTS}

        add_monthly_hours_constraint(
            model, x, [emp], [1], schedule, shop, ALL_SHIFTS,
            soft=True, shift_night=SHIFT_NIGHT,
        )
        model.Add(x[0, 1, SHIFT_NIGHT] == 1)
        for s in ALL_SHIFTS:
            if s != SHIFT_NIGHT:
                model.Add(x[0, 1, s] == 0)

        status = cp_model.CpSolver().Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))

    def test_balance_constraint_accepts_night_shift_without_crashing(self):
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_night()  # 8h window
        emp = _employee_at(employment_fraction=1.0)

        model = cp_model.CpModel()
        x = {(0, 1, s): model.NewBoolVar(f"x_{s}") for s in ALL_SHIFTS}

        add_balance_constraint(
            model, x, [emp], [1], shop, ALL_SHIFTS, soft=True, shift_night=SHIFT_NIGHT,
        )
        model.Add(x[0, 1, SHIFT_NIGHT] == 1)
        for s in ALL_SHIFTS:
            if s != SHIFT_NIGHT:
                model.Add(x[0, 1, s] == 0)

        status = cp_model.CpSolver().Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))


class SolutionMapperNightShiftTests(unittest.TestCase):
    def test_night_shift_assignment_is_written_to_schedule(self):
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_night()
        emp = _employee_at()
        schedule = MonthSchedule(2026, 8)
        schedule.add_employee(emp)

        model = cp_model.CpModel()
        x = {(0, 1, s): model.NewBoolVar(f"x_{s}") for s in ALL_SHIFTS}
        model.Add(x[0, 1, SHIFT_NIGHT] == 1)
        for s in ALL_SHIFTS:
            if s != SHIFT_NIGHT:
                model.Add(x[0, 1, s] == 0)

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))

        success = save_solution(
            schedule, shop, solver, status, x, [emp], [1],
            SHIFT_OPEN, SHIFT_CLOSE, START_SHIFT_MAP, END_SHIFT_MAP,
            shift_night=SHIFT_NIGHT,
        )
        self.assertTrue(success)

        day = schedule.get_day(emp, 1)
        self.assertEqual(day.start, "22:00")
        self.assertEqual(day.end, "06:00")
        self.assertTrue(day.crosses_midnight())


if __name__ == "__main__":
    unittest.main()
