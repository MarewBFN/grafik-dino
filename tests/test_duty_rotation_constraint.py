"""Etap B "plan profil ochrona (analiza specyfikacji klienta).md", sekcja
12: reguła pokrycia (dokładnie 1 osoba/zmiana, przełącznik 24h vs
12h+12h dla weekendu) + brama nie_chce_24h + brama wzajemnej wyłączności
ze starym modelem zmian."""

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.auto_generator import AutoScheduleGenerator
from logic.generator.duty_rotation_constraint import (
    add_duty_rotation_coverage_constraint,
    add_duty_rotation_gate_constraint,
    add_duty_rotation_no24h_gate_constraint,
)
from logic.generator.constraints_basic import add_one_shift_per_day_constraint
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig

SHIFT_OPEN, SHIFT_CLOSE = 0, 1
SHIFT_NIGHT = 14
WEEKDAY_LONG, WEEKDAY_SHORT, WEEKEND_FULL, WEEKEND_HALF_A, WEEKEND_HALF_B = 15, 16, 17, 18, 19
ALL_SHIFTS = (SHIFT_OPEN, SHIFT_CLOSE, SHIFT_NIGHT, WEEKDAY_LONG, WEEKDAY_SHORT, WEEKEND_FULL, WEEKEND_HALF_A, WEEKEND_HALF_B)
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


def _location_with_rotation(key="site1"):
    loc = LocationConfig(key=key, name="Site 1")
    loc.set_duty_rotation(ROTATION)
    return loc


def _model_and_x(employees, days):
    model = cp_model.CpModel()
    x = {(e, d, s): model.NewBoolVar(f"x_{e}_{d}_{s}") for e in range(len(employees)) for d in days for s in ALL_SHIFTS}
    return model, x


# 2026-08-03 is a Monday (weekday), 2026-08-08/09 is Sat/Sun (weekend).
WEEKDAY = 3
SATURDAY = 8
SUNDAY = 9


class TestDutyRotationGate:
    def test_employee_without_rotation_cannot_get_any_duty_shift(self):
        shop = ShopConfig(2026, 8)  # no locations at all
        emp = Employee(last_name="Guard", first_name="A")
        model, x = _model_and_x([emp], [WEEKDAY])

        add_duty_rotation_gate_constraint(model, x, [emp], [WEEKDAY], shop, DUTY_SHIFTS, ALL_SHIFTS)
        model.Add(x[0, WEEKDAY, WEEKDAY_LONG] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE

    def test_employee_with_rotation_cannot_get_old_shift_types(self):
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_rotation()
        emp = Employee(last_name="Guard", first_name="A", location_key="site1")
        model, x = _model_and_x([emp], [WEEKDAY])

        add_duty_rotation_gate_constraint(model, x, [emp], [WEEKDAY], shop, DUTY_SHIFTS, ALL_SHIFTS)
        model.Add(x[0, WEEKDAY, SHIFT_OPEN] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE

    def test_employee_with_rotation_can_get_a_duty_shift(self):
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_rotation()
        emp = Employee(last_name="Guard", first_name="A", location_key="site1")
        model, x = _model_and_x([emp], [WEEKDAY])

        add_duty_rotation_gate_constraint(model, x, [emp], [WEEKDAY], shop, DUTY_SHIFTS, ALL_SHIFTS)
        model.Add(x[0, WEEKDAY, WEEKDAY_LONG] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def test_weekend_shift_types_forbidden_on_a_weekday(self):
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_rotation()
        emp = Employee(last_name="Guard", first_name="A", location_key="site1")
        model, x = _model_and_x([emp], [WEEKDAY])

        add_duty_rotation_gate_constraint(model, x, [emp], [WEEKDAY], shop, DUTY_SHIFTS, ALL_SHIFTS)
        model.Add(x[0, WEEKDAY, WEEKEND_FULL] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE

    def test_weekday_shift_types_forbidden_on_a_weekend_day(self):
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_rotation()
        emp = Employee(last_name="Guard", first_name="A", location_key="site1")
        model, x = _model_and_x([emp], [SATURDAY])

        add_duty_rotation_gate_constraint(model, x, [emp], [SATURDAY], shop, DUTY_SHIFTS, ALL_SHIFTS)
        model.Add(x[0, SATURDAY, WEEKDAY_LONG] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE


class TestDutyRotationNo24hGate:
    def test_nie_chce_24h_employee_cannot_get_weekend_full(self):
        emp = Employee(last_name="Guard", first_name="A", custom_roles={"nie_chce_24h": True})
        model, x = _model_and_x([emp], [SATURDAY])

        add_duty_rotation_no24h_gate_constraint(model, x, [emp], [SATURDAY], DUTY_SHIFTS, soft=False)
        model.Add(x[0, SATURDAY, WEEKEND_FULL] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE

    def test_regular_employee_can_get_weekend_full(self):
        emp = Employee(last_name="Guard", first_name="A")
        model, x = _model_and_x([emp], [SATURDAY])

        add_duty_rotation_no24h_gate_constraint(model, x, [emp], [SATURDAY], DUTY_SHIFTS, soft=False)
        model.Add(x[0, SATURDAY, WEEKEND_FULL] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)


class TestDutyRotationCoverage:
    def test_weekday_needs_exactly_one_person_per_shift_type(self):
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_rotation()
        emp_a = Employee(last_name="A", first_name="A", location_key="site1")
        emp_b = Employee(last_name="B", first_name="B", location_key="site1")
        employees = [emp_a, emp_b]
        model, x = _model_and_x(employees, [WEEKDAY])

        add_one_shift_per_day_constraint(model, x, employees, [WEEKDAY], ALL_SHIFTS)
        add_duty_rotation_coverage_constraint(model, x, employees, [WEEKDAY], shop, DUTY_SHIFTS, soft=False)

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

        long_count = sum(solver.Value(x[e, WEEKDAY, WEEKDAY_LONG]) for e in range(2))
        short_count = sum(solver.Value(x[e, WEEKDAY, WEEKDAY_SHORT]) for e in range(2))
        assert long_count == 1
        assert short_count == 1
        # one_shift_per_day forces the two roles onto two different people.
        assert solver.Value(x[0, WEEKDAY, WEEKDAY_LONG]) != solver.Value(x[1, WEEKDAY, WEEKDAY_LONG])

    def test_weekday_more_than_one_person_on_same_shift_is_infeasible(self):
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_rotation()
        emp_a = Employee(last_name="A", first_name="A", location_key="site1")
        emp_b = Employee(last_name="B", first_name="B", location_key="site1")
        employees = [emp_a, emp_b]
        model, x = _model_and_x(employees, [WEEKDAY])

        add_duty_rotation_coverage_constraint(model, x, employees, [WEEKDAY], shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, WEEKDAY, WEEKDAY_LONG] == 1)
        model.Add(x[1, WEEKDAY, WEEKDAY_LONG] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE

    def test_weekend_uses_either_full_day_or_both_halves_never_a_mix(self):
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_rotation()
        emp_a = Employee(last_name="A", first_name="A", location_key="site1")
        emp_b = Employee(last_name="B", first_name="B", location_key="site1")
        employees = [emp_a, emp_b]
        model, x = _model_and_x(employees, [SATURDAY])

        add_one_shift_per_day_constraint(model, x, employees, [SATURDAY], ALL_SHIFTS)
        add_duty_rotation_coverage_constraint(model, x, employees, [SATURDAY], shop, DUTY_SHIFTS, soft=False)

        # Force a mix: one person on the full 24h AND one on a half - must
        # be infeasible, this is exactly the "never a mix" guarantee.
        model.Add(x[0, SATURDAY, WEEKEND_FULL] == 1)
        model.Add(x[1, SATURDAY, WEEKEND_HALF_A] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE

    def test_weekend_full_day_variant_is_feasible(self):
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_rotation()
        emp = Employee(last_name="A", first_name="A", location_key="site1")
        model, x = _model_and_x([emp], [SATURDAY])

        add_one_shift_per_day_constraint(model, x, [emp], [SATURDAY], ALL_SHIFTS)
        add_duty_rotation_coverage_constraint(model, x, [emp], [SATURDAY], shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, SATURDAY, WEEKEND_FULL] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def test_weekend_forced_to_halves_when_nobody_can_take_24h(self):
        """The exact scenario the client asked for: an employee who doesn't
        want 24h shifts on weekends must still be schedulable then, just
        split 12h/12h with someone else."""
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_rotation()
        emp_a = Employee(last_name="A", first_name="A", location_key="site1", custom_roles={"nie_chce_24h": True})
        emp_b = Employee(last_name="B", first_name="B", location_key="site1", custom_roles={"nie_chce_24h": True})
        employees = [emp_a, emp_b]
        model, x = _model_and_x(employees, [SATURDAY])

        add_one_shift_per_day_constraint(model, x, employees, [SATURDAY], ALL_SHIFTS)
        add_duty_rotation_coverage_constraint(model, x, employees, [SATURDAY], shop, DUTY_SHIFTS, soft=False)
        add_duty_rotation_no24h_gate_constraint(model, x, employees, [SATURDAY], DUTY_SHIFTS, soft=False)

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        assert solver.Value(x[0, SATURDAY, WEEKEND_FULL]) == 0
        assert solver.Value(x[1, SATURDAY, WEEKEND_FULL]) == 0
        assert sum(solver.Value(x[e, SATURDAY, WEEKEND_HALF_A]) for e in range(2)) == 1
        assert sum(solver.Value(x[e, SATURDAY, WEEKEND_HALF_B]) for e in range(2)) == 1


def test_end_to_end_generation_covers_a_full_week_with_duty_rotation():
    """Real AutoScheduleGenerator.generate() run, not a hand-built model -
    confirms the wiring in base_specs.py/auto_generator.py actually works
    together, not just each builder in isolation."""
    from model.business_profile import register_custom_profile
    from model.custom_profile import CustomBusinessProfile

    profile = CustomBusinessProfile(key="custom_test_duty_rotation_e2e", display_name="Test Ochrona")
    register_custom_profile(profile)

    shop = ShopConfig(2026, 8)
    shop.business_type = profile.key
    shop.locations["site1"] = _location_with_rotation()

    schedule = MonthSchedule(2026, 8)
    employees = [
        Employee(last_name="A", first_name="A", location_key="site1"),
        Employee(last_name="B", first_name="B", location_key="site1"),
        Employee(last_name="C", first_name="C", location_key="site1", custom_roles={"nie_chce_24h": True}),
    ]
    for emp in employees:
        schedule.add_employee(emp)

    with redirect_stdout(io.StringIO()):
        result = AutoScheduleGenerator(schedule, shop).generate(solver_time_limit_seconds=20, solver_workers=1)

    assert result["success"] is True

    for day in range(1, 8):  # 2026-08-01..07: Sat, Sun, then a full working week
        ds_list = [schedule.get_day(emp, day) for emp in employees]
        assigned = [ds for ds in ds_list if not ds.is_empty()]
        wd = shop.weekday(day)

        if wd < 5:
            assert len(assigned) == 2, f"day {day} (weekday) should have exactly 2 people on duty"
        else:
            if any(ds.is_full_day for ds in assigned):
                assert len(assigned) == 1, f"day {day} (weekend, 24h variant) should have exactly 1 person"
            else:
                assert len(assigned) == 2, f"day {day} (weekend, 12h+12h variant) should have exactly 2 people"

        # Nobody with "nie_chce_24h" ever gets the 24h shift.
        for emp, ds in zip(employees, ds_list):
            if emp.custom_roles.get("nie_chce_24h") and ds.is_full_day:
                assert False, f"day {day}: {emp.display_name()} has nie_chce_24h but got a 24h shift"
