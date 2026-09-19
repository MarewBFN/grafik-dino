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

    def test_locked_off_without_is_day_off_flag_still_blocks_all_duty_shifts(self):
        """Reprodukcja realnego bugu zgłoszonego przez użytkownika: ui/grid_view.py
        ma DRUGĄ, niezależną ścieżkę ustawiania "wolne" (akcja "OFF" w
        dropdownie na komórce) - czyści start/end i ustawia is_locked, ale
        NIE ustawia is_day_off (w odróżnieniu od ScheduleController.set_day_free()).
        Przed poprawką ta funkcja zakładała, że is_day_off jest zawsze
        ustawione dla "wolne zablokowane" i nic nie wymuszała - solver miał
        wolną rękę przypisać temu pracownikowi zmianę duty (spełniając sobie
        coverage WEWNĘTRZNIE -> model raportował OPTIMAL), a solution_mapper
        i tak nie zapisywał wyniku (bo is_locked=True) - efekt: pozornie
        kompletny grafik z niepokrytym dniem, mimo statusu OPTIMAL."""
        shop = _shop_with_rotation()
        emp = Employee(last_name="Guard", first_name="A", location_key="site1")
        schedule = MonthSchedule(2026, 8)
        schedule.add_employee(emp)
        ds = schedule.get_day(emp, WEEKDAY)
        # Dokładnie to, co robi ui/grid_view.py (linie ok. 1337-1361) - NIE
        # ScheduleController.set_day_free(), które ustawia is_day_off=True.
        ds.start = None
        ds.end = None
        ds.is_leave = False
        ds.is_sick = False
        ds.is_locked = True
        assert not getattr(ds, "is_day_off", False)

        model, x = _model_and_x([emp], [WEEKDAY])
        add_duty_rotation_gate_constraint(model, x, [emp], [WEEKDAY], shop, DUTY_SHIFTS, ALL_SHIFTS)
        add_duty_rotation_manual_shift_constraint(model, x, [emp], [WEEKDAY], schedule, shop, DUTY_SHIFTS)

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        assert status == cp_model.OPTIMAL
        for s in DUTY_SHIFTS.values():
            assert solver.Value(x[0, WEEKDAY, s]) == 0

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

    def test_two_employees_locked_off_via_grid_view_off_action_still_covers_the_day(self):
        """Reprodukcja end-to-end zgłoszonego przez użytkownika bugu: 4-osobowa
        placówka only_12_24h (wszyscy "nie_chce_24h" - podział wymuszony),
        2 z 4 pracowników zablokowane jako "wolne" przez akcję "OFF" z
        ui/grid_view.py (is_locked=True, start/end=None, is_day_off NIE
        ustawione). Przed poprawką: status OPTIMAL, ale dzień pozostawał
        NIEPOKRYTY (solver wewnętrznie "wykorzystywał" zablokowanego
        pracownika do spełnienia coverage, a solution_mapper nic nie zapisywał
        z powodu locka). Po poprawce: OPTIMAL I faktycznie zapisane pokrycie
        przez 2 pozostałych, wolnych pracowników."""
        profile = CustomBusinessProfile(key="test_off_action_gap", display_name="Test", roles=[], rules=[])
        register_custom_profile(profile)

        shop = ShopConfig(2026, 10)
        shop.business_type = profile.key
        loc = LocationConfig(key="site1", name="Site 1")
        loc.set_duty_rotation({
            "only_12_24h": True,
            "weekend_full": {"start": "08:00"},
            "weekend_half_a": {"start": "08:00", "end": "20:00"},
            "weekend_half_b": {"start": "20:00", "end": "08:00"},
        })
        shop.locations = {"site1": loc}
        shop.constraint_policies.update(default_policies(profile))

        schedule = MonthSchedule(2026, 10)
        employees = [
            Employee(last_name=f"E{i}", first_name="Guard", employment_fraction=1.0,
                      location_key="site1", custom_roles={"nie_chce_24h": True})
            for i in range(4)
        ]
        for e in employees:
            schedule.add_employee(e)

        locked_day = 8
        for emp in employees[:2]:
            ds = schedule.get_day(emp, locked_day)
            # Dokładnie akcja "OFF" z ui/grid_view.py, NIE ScheduleController.set_day_free().
            ds.start = None
            ds.end = None
            ds.is_leave = False
            ds.is_sick = False
            ds.is_locked = True
            assert not getattr(ds, "is_day_off", False)

        buf = io.StringIO()
        with redirect_stdout(buf):
            result = AutoScheduleGenerator(shop=shop, schedule=schedule).generate(solver_time_limit_seconds=30)

        assert result["success"], result
        assert result["status"].name in ("OPTIMAL", "FEASIBLE")

        half_a = [e for e in employees[2:] if schedule.get_day(e, locked_day).start == "08:00"]
        half_b = [e for e in employees[2:] if schedule.get_day(e, locked_day).start == "20:00"]
        assert len(half_a) == 1, "half_a musi być pokryte przez jednego z 2 wolnych pracowników"
        assert len(half_b) == 1, "half_b musi być pokryte przez jednego z 2 wolnych pracowników"
        for emp in employees[:2]:
            ds = schedule.get_day(emp, locked_day)
            assert ds.start is None and ds.end is None, "zablokowany pracownik musi zostać nietknięty"
