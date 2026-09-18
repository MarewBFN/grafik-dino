"""logic/generator/duty_rotation_manual_constraint.py - ręczna blokada dnia
dla pracowników rotacji 24/7. Przed tym plikiem zablokowanie takiego dnia
(dwuklik na komórce albo "Cała doba (24h)" w Ustawieniach trybu szybkiego)
robiło model sprzeczny z add_duty_rotation_gate_constraint - patrz
ENYO_ONLY_CHANGES.md dla pełnego opisu i reprodukcji na żywym generatorze."""

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.auto_generator import AutoScheduleGenerator
from logic.generator.custom_profile_wiring import default_policies
from logic.generator.duty_rotation_constraint import add_duty_rotation_gate_constraint
from logic.generator.duty_rotation_manual_constraint import add_duty_rotation_manual_shift_constraint
from model.business_profile import register_custom_profile
from model.custom_profile import CustomBusinessProfile
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig

SHIFT_OPEN, SHIFT_CLOSE = 0, 1
WEEKDAY_LONG, WEEKDAY_SHORT, WEEKEND_FULL, WEEKEND_HALF_A, WEEKEND_HALF_B = 15, 16, 17, 18, 19
ALL_SHIFTS = (SHIFT_OPEN, SHIFT_CLOSE, WEEKDAY_LONG, WEEKDAY_SHORT, WEEKEND_FULL, WEEKEND_HALF_A, WEEKEND_HALF_B)
DUTY_SHIFTS = {
    "weekday_long": WEEKDAY_LONG,
    "weekday_short": WEEKDAY_SHORT,
    "weekend_full": WEEKEND_FULL,
    "weekend_half_a": WEEKEND_HALF_A,
    "weekend_half_b": WEEKEND_HALF_B,
}

ROTATION = {
    "weekday_long": {"start": "06:00", "end": "22:00"},
    "weekday_short": {"start": "22:00", "end": "06:00"},
    "weekend_full": {"start": "06:00"},
    "weekend_half_a": {"start": "06:00", "end": "18:00"},
    "weekend_half_b": {"start": "18:00", "end": "06:00"},
}

# 2026-08-03 is a Monday (weekday), 2026-08-08 is a Saturday (weekend).
WEEKDAY = 3
SATURDAY = 8


def _shop_with_rotation():
    shop = ShopConfig(2026, 8)
    loc = LocationConfig(key="site1", name="Site 1")
    loc.set_duty_rotation(ROTATION)
    shop.locations["site1"] = loc
    return shop


def _model_and_x(employees, days):
    model = cp_model.CpModel()
    x = {(e, d, s): model.NewBoolVar(f"x_{e}_{d}_{s}") for e in range(len(employees)) for d in days for s in ALL_SHIFTS}
    return model, x


class TestDutyRotationManualShift:
    def test_locked_weekday_long_hours_force_that_shift(self):
        shop = _shop_with_rotation()
        emp = Employee(last_name="Guard", first_name="A", location_key="site1")
        schedule = MonthSchedule(2026, 8)
        schedule.add_employee(emp)
        schedule.set_day_hours(emp, WEEKDAY, "06:00", "22:00")
        schedule.get_day(emp, WEEKDAY).is_locked = True

        model, x = _model_and_x([emp], [WEEKDAY])
        add_duty_rotation_gate_constraint(model, x, [emp], [WEEKDAY], shop, DUTY_SHIFTS, ALL_SHIFTS)
        add_duty_rotation_manual_shift_constraint(model, x, [emp], [WEEKDAY], schedule, shop, DUTY_SHIFTS)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.OPTIMAL

        solver = cp_model.CpSolver()
        solver.Solve(model)
        assert solver.Value(x[0, WEEKDAY, WEEKDAY_LONG]) == 1
        for s in ALL_SHIFTS:
            if s != WEEKDAY_LONG:
                assert solver.Value(x[0, WEEKDAY, s]) == 0

    def test_locking_a_different_duty_shift_on_top_is_infeasible(self):
        """Sanity check that the constraint is actually a hard lock, not a
        no-op: forcing a conflicting shift on the same day must fail."""
        shop = _shop_with_rotation()
        emp = Employee(last_name="Guard", first_name="A", location_key="site1")
        schedule = MonthSchedule(2026, 8)
        schedule.add_employee(emp)
        schedule.set_day_hours(emp, WEEKDAY, "06:00", "22:00")
        schedule.get_day(emp, WEEKDAY).is_locked = True

        model, x = _model_and_x([emp], [WEEKDAY])
        add_duty_rotation_gate_constraint(model, x, [emp], [WEEKDAY], shop, DUTY_SHIFTS, ALL_SHIFTS)
        add_duty_rotation_manual_shift_constraint(model, x, [emp], [WEEKDAY], schedule, shop, DUTY_SHIFTS)
        model.Add(x[0, WEEKDAY, WEEKDAY_SHORT] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE

    def test_locked_full_day_forces_weekend_full(self):
        shop = _shop_with_rotation()
        emp = Employee(last_name="Guard", first_name="A", location_key="site1")
        schedule = MonthSchedule(2026, 8)
        schedule.add_employee(emp)
        schedule.set_day_full_day_shift(emp, SATURDAY, "06:00")
        schedule.get_day(emp, SATURDAY).is_locked = True

        model, x = _model_and_x([emp], [SATURDAY])
        add_duty_rotation_gate_constraint(model, x, [emp], [SATURDAY], shop, DUTY_SHIFTS, ALL_SHIFTS)
        add_duty_rotation_manual_shift_constraint(model, x, [emp], [SATURDAY], schedule, shop, DUTY_SHIFTS)

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        assert status == cp_model.OPTIMAL
        assert solver.Value(x[0, SATURDAY, WEEKEND_FULL]) == 1

    def test_locked_hours_matching_no_duty_shift_blocks_all_duty_shifts(self):
        shop = _shop_with_rotation()
        emp = Employee(last_name="Guard", first_name="A", location_key="site1")
        schedule = MonthSchedule(2026, 8)
        schedule.add_employee(emp)
        # 10:00-14:00 nie odpowiada żadnej z pięciu zmian tej rotacji.
        schedule.set_day_hours(emp, WEEKDAY, "10:00", "14:00")
        schedule.get_day(emp, WEEKDAY).is_locked = True

        model, x = _model_and_x([emp], [WEEKDAY])
        add_duty_rotation_gate_constraint(model, x, [emp], [WEEKDAY], shop, DUTY_SHIFTS, ALL_SHIFTS)
        add_duty_rotation_manual_shift_constraint(model, x, [emp], [WEEKDAY], schedule, shop, DUTY_SHIFTS)

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        assert status == cp_model.OPTIMAL
        for s in DUTY_SHIFTS.values():
            assert solver.Value(x[0, WEEKDAY, s]) == 0

    def test_unlocked_day_is_left_free(self):
        shop = _shop_with_rotation()
        emp = Employee(last_name="Guard", first_name="A", location_key="site1")
        schedule = MonthSchedule(2026, 8)
        schedule.add_employee(emp)

        model, x = _model_and_x([emp], [WEEKDAY])
        add_duty_rotation_gate_constraint(model, x, [emp], [WEEKDAY], shop, DUTY_SHIFTS, ALL_SHIFTS)
        add_duty_rotation_manual_shift_constraint(model, x, [emp], [WEEKDAY], schedule, shop, DUTY_SHIFTS)
        model.Add(x[0, WEEKDAY, WEEKDAY_LONG] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.OPTIMAL

    def test_employee_without_rotation_is_untouched(self):
        shop = ShopConfig(2026, 8)  # no locations, no rotation
        emp = Employee(last_name="Clerk", first_name="A")
        schedule = MonthSchedule(2026, 8)
        schedule.add_employee(emp)
        schedule.set_day_hours(emp, WEEKDAY, "06:00", "22:00")
        schedule.get_day(emp, WEEKDAY).is_locked = True

        model, x = _model_and_x([emp], [WEEKDAY])
        add_duty_rotation_manual_shift_constraint(model, x, [emp], [WEEKDAY], schedule, shop, DUTY_SHIFTS)

        # Brak lokalizacji z duty_rotation -> funkcja nic nie dodaje - każda
        # zmiana wciąż swobodnie przypisywalna.
        model.Add(x[0, WEEKDAY, WEEKDAY_LONG] == 1)
        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.OPTIMAL


def _duty_shop_and_schedule(locked_day, start, end=None, full_day=False):
    profile = CustomBusinessProfile(key=f"test_ochrona_{locked_day}_{full_day}", display_name="Test Ochrona", roles=[], rules=[])
    register_custom_profile(profile)

    shop = ShopConfig(2026, 3)
    shop.business_type = profile.key
    shop.set_duty_rotation(ROTATION)
    shop.constraint_policies.update(default_policies(profile))

    schedule = MonthSchedule(2026, 3)
    employees = [Employee(last_name=n, first_name=n, employment_fraction=1.0) for n in "ABCD"]
    for e in employees:
        schedule.add_employee(e)

    if full_day:
        schedule.set_day_full_day_shift(employees[0], locked_day, start)
    else:
        schedule.set_day_hours(employees[0], locked_day, start, end)
    schedule.get_day(employees[0], locked_day).is_locked = True

    return shop, schedule, employees


class TestDutyRotationManualShiftEndToEnd:
    """Reprodukcja przez pełny AutoScheduleGenerator, nie tylko izolowany
    ConstraintSpec - dokładnie ten scenariusz, który przed poprawką kończył
    się INFEASIBLE dla całego miesiąca (nie tylko zablokowanego dnia)."""

    def test_locked_weekday_long_day_still_generates_a_full_schedule(self):
        # 2026-03-02 is a Monday.
        shop, schedule, employees = _duty_shop_and_schedule(2, "06:00", "22:00")

        buf = io.StringIO()
        with redirect_stdout(buf):
            result = AutoScheduleGenerator(shop=shop, schedule=schedule).generate(solver_time_limit_seconds=20)

        assert result["success"], result
        ds = schedule.get_day(employees[0], 2)
        assert (ds.start, ds.end, ds.is_locked) == ("06:00", "22:00", True)

    def test_locked_full_day_shift_still_generates_a_full_schedule(self):
        # 2026-03-07 is a Saturday.
        shop, schedule, employees = _duty_shop_and_schedule(7, "06:00", full_day=True)

        buf = io.StringIO()
        with redirect_stdout(buf):
            result = AutoScheduleGenerator(shop=shop, schedule=schedule).generate(solver_time_limit_seconds=20)

        assert result["success"], result
        ds = schedule.get_day(employees[0], 7)
        assert (ds.start, ds.is_full_day, ds.is_locked) == ("06:00", True, True)
