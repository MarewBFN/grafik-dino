"""logic/generator/duty_rotation_public_holiday_constraint.py - zamyka
lokalizacje z duty_rotation w polskie święta ustawowe (biblioteka
`holidays`), gdy LocationConfig.closed_on_public_holidays jest włączone
(domyślnie tak) - zgłoszenie użytkownika (2026-09-25): "traktuj te dni
jako nieczynne (grid_view i generator)", z per-lokalizacyjnym przełącznikiem.

Ta funkcja NIE zastępuje add_duty_rotation_coverage_constraint - działa
RÓWNOLEGLE obok niej (ten sam wzorzec co duty_rotation_manual_constraint.py
obok add_manual_shift_constraints): tu zerujemy przypisania zmian duty w
zamknięty dzień, a duty_rotation_coverage_constraint osobno pomija wymóg
pokrycia dla tych samych dni (patrz jej komentarz), żeby oba constrainty
się sobie nie zaprzeczały."""

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
from logic.generator.duty_rotation_constraint import add_duty_rotation_coverage_constraint
from logic.generator.duty_rotation_public_holiday_constraint import add_duty_rotation_public_holiday_constraint
from model.business_profile import register_custom_profile
from model.constraint_policy import ConstraintPolicy
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

# Styczeń 2026: 1 (czwartek) = Nowy Rok, 2 (piątek) = zwykły dzień roboczy.
YEAR, MONTH = 2026, 1
HOLIDAY_DAY = 1
REGULAR_DAY = 2


def _shop_with_rotation(closed_on_public_holidays=True):
    shop = ShopConfig(YEAR, MONTH)
    loc = LocationConfig(key="site1", name="Site 1", closed_on_public_holidays=closed_on_public_holidays)
    loc.set_duty_rotation(ROTATION)
    shop.locations["site1"] = loc
    return shop


def _model_and_x(employees, days):
    model = cp_model.CpModel()
    x = {(e, d, s): model.NewBoolVar(f"x_{e}_{d}_{s}") for e in range(len(employees)) for d in days for s in ALL_SHIFTS}
    return model, x


class TestDutyRotationPublicHolidayConstraint:
    def test_zeroes_all_duty_shifts_on_a_closed_public_holiday(self):
        shop = _shop_with_rotation()
        emp = Employee(last_name="Guard", first_name="A", location_key="site1")
        schedule = MonthSchedule(YEAR, MONTH)
        schedule.add_employee(emp)

        model, x = _model_and_x([emp], [HOLIDAY_DAY])
        add_duty_rotation_public_holiday_constraint(model, x, [emp], [HOLIDAY_DAY], schedule, shop, DUTY_SHIFTS)

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        assert status == cp_model.OPTIMAL
        for s in DUTY_SHIFTS.values():
            assert solver.Value(x[0, HOLIDAY_DAY, s]) == 0

    def test_does_not_touch_a_regular_weekday(self):
        shop = _shop_with_rotation()
        emp = Employee(last_name="Guard", first_name="A", location_key="site1")
        schedule = MonthSchedule(YEAR, MONTH)
        schedule.add_employee(emp)

        model, x = _model_and_x([emp], [REGULAR_DAY])
        add_duty_rotation_public_holiday_constraint(model, x, [emp], [REGULAR_DAY], schedule, shop, DUTY_SHIFTS)
        model.Add(x[0, REGULAR_DAY, WEEKDAY_LONG] == 1)

        solver = cp_model.CpSolver()
        assert solver.Solve(model) == cp_model.OPTIMAL

    def test_toggle_off_leaves_the_holiday_unconstrained(self):
        shop = _shop_with_rotation(closed_on_public_holidays=False)
        emp = Employee(last_name="Guard", first_name="A", location_key="site1")
        schedule = MonthSchedule(YEAR, MONTH)
        schedule.add_employee(emp)

        model, x = _model_and_x([emp], [HOLIDAY_DAY])
        add_duty_rotation_public_holiday_constraint(model, x, [emp], [HOLIDAY_DAY], schedule, shop, DUTY_SHIFTS)
        model.Add(x[0, HOLIDAY_DAY, WEEKDAY_LONG] == 1)

        solver = cp_model.CpSolver()
        assert solver.Solve(model) == cp_model.OPTIMAL

    def test_explicit_manual_assignment_on_the_holiday_wins(self):
        """Ręczne, jawne przypisanie zmiany (dwuklik na komórce w gridzie)
        wygrywa nad automatycznym zamknięciem - ten sam priorytet co
        day_overrides ma nad LocationConfig.is_closed_for_public_holiday()."""
        shop = _shop_with_rotation()
        emp = Employee(last_name="Guard", first_name="A", location_key="site1")
        schedule = MonthSchedule(YEAR, MONTH)
        schedule.add_employee(emp)
        schedule.set_day_hours(emp, HOLIDAY_DAY, "06:00", "22:00")
        schedule.get_day(emp, HOLIDAY_DAY).is_locked = True

        model, x = _model_and_x([emp], [HOLIDAY_DAY])
        add_duty_rotation_public_holiday_constraint(model, x, [emp], [HOLIDAY_DAY], schedule, shop, DUTY_SHIFTS)
        model.Add(x[0, HOLIDAY_DAY, WEEKDAY_LONG] == 1)

        solver = cp_model.CpSolver()
        assert solver.Solve(model) == cp_model.OPTIMAL

    def test_manual_off_day_still_zeroes_out_like_a_normal_closed_day(self):
        shop = _shop_with_rotation()
        emp = Employee(last_name="Guard", first_name="A", location_key="site1")
        schedule = MonthSchedule(YEAR, MONTH)
        schedule.add_employee(emp)
        schedule.get_day(emp, HOLIDAY_DAY).is_locked = True  # "OFF" w gridzie - brak start/end

        model, x = _model_and_x([emp], [HOLIDAY_DAY])
        add_duty_rotation_public_holiday_constraint(model, x, [emp], [HOLIDAY_DAY], schedule, shop, DUTY_SHIFTS)

        solver = cp_model.CpSolver()
        assert solver.Solve(model) == cp_model.OPTIMAL
        for s in DUTY_SHIFTS.values():
            assert solver.Value(x[0, HOLIDAY_DAY, s]) == 0


class TestManualClosedDayOverride:
    """"Nieczynne tego dnia" (nagłówek dnia w grafiku -> day_overrides bez
    godzin) zamyka dobę rotacji tak samo jak zamknięte święto - wcześniej
    siatka pokazywała dzień jako szary/pusty, a generator go obsadzał."""

    def test_is_duty_day_closed_for_manual_override(self):
        loc = LocationConfig(key="site1", name="Site 1", closed_on_public_holidays=False)
        loc.set_duty_rotation(ROTATION)
        loc.day_overrides[REGULAR_DAY] = (None, None)
        assert loc.is_duty_day_closed(YEAR, MONTH, REGULAR_DAY) is True
        assert loc.is_duty_day_closed(YEAR, MONTH, REGULAR_DAY + 1) is False

    def test_override_with_hours_reopens_a_closed_holiday(self):
        loc = LocationConfig(key="site1", name="Site 1")
        loc.set_duty_rotation(ROTATION)
        assert loc.is_duty_day_closed(YEAR, MONTH, HOLIDAY_DAY) is True
        loc.day_overrides[HOLIDAY_DAY] = ("00:00", "23:45")
        assert loc.is_duty_day_closed(YEAR, MONTH, HOLIDAY_DAY) is False

    def test_generator_leaves_manually_closed_day_empty(self):
        profile = CustomBusinessProfile(key="test_manual_closed_day", display_name="T", roles=[], rules=[])
        register_custom_profile(profile)
        shop = ShopConfig(YEAR, MONTH)
        shop.business_type = profile.key
        loc = LocationConfig(key="site1", name="Site 1", closed_on_public_holidays=False)
        loc.set_duty_rotation(ROTATION)
        loc.day_overrides[14] = (None, None)
        shop.locations["site1"] = loc
        shop.constraint_policies.update(default_policies(profile))
        shop.constraint_policies["balance"] = ConstraintPolicy.DISABLED
        shop.constraint_policies["monthly_hours"] = ConstraintPolicy.DISABLED
        schedule = MonthSchedule(YEAR, MONTH)
        employees = [Employee(last_name=f"E{i}", first_name="G", location_key="site1") for i in range(3)]
        for emp in employees:
            schedule.add_employee(emp)

        with redirect_stdout(io.StringIO()):
            result = AutoScheduleGenerator(schedule, shop).generate(solver_time_limit_seconds=30)

        assert result["success"], result
        assert all(schedule.get_day(emp, 14).is_empty() for emp in employees)
        assert any(not schedule.get_day(emp, 13).is_empty() for emp in employees)
        assert any(not schedule.get_day(emp, 15).is_empty() for emp in employees)


class TestCoverageSkipsClosedHolidays:
    def test_coverage_constraint_does_not_require_staff_on_a_closed_holiday(self):
        shop = _shop_with_rotation()
        emp = Employee(last_name="Guard", first_name="A", location_key="site1")
        schedule = MonthSchedule(YEAR, MONTH)
        schedule.add_employee(emp)

        model, x = _model_and_x([emp], [HOLIDAY_DAY])
        add_duty_rotation_public_holiday_constraint(model, x, [emp], [HOLIDAY_DAY], schedule, shop, DUTY_SHIFTS)
        add_duty_rotation_coverage_constraint(model, x, [emp], [HOLIDAY_DAY], shop, DUTY_SHIFTS)

        # Gdyby coverage nie pomijał tego dnia, powyższe dwa constrainty
        # (count==0 kontra count==1) zrobiłyby model INFEASIBLE.
        solver = cp_model.CpSolver()
        assert solver.Solve(model) == cp_model.OPTIMAL

    def test_coverage_constraint_still_required_on_a_regular_day(self):
        shop = _shop_with_rotation()
        long_emp = Employee(last_name="Long", first_name="A", location_key="site1")
        short_emp = Employee(last_name="Short", first_name="B", location_key="site1")
        schedule = MonthSchedule(YEAR, MONTH)
        schedule.add_employee(long_emp)
        schedule.add_employee(short_emp)

        model, x = _model_and_x([long_emp, short_emp], [REGULAR_DAY])
        add_duty_rotation_coverage_constraint(model, x, [long_emp, short_emp], [REGULAR_DAY], shop, DUTY_SHIFTS)

        solver = cp_model.CpSolver()
        assert solver.Solve(model) == cp_model.OPTIMAL
        assert solver.Value(x[0, REGULAR_DAY, WEEKDAY_LONG]) + solver.Value(x[1, REGULAR_DAY, WEEKDAY_LONG]) == 1
        assert solver.Value(x[0, REGULAR_DAY, WEEKDAY_SHORT]) + solver.Value(x[1, REGULAR_DAY, WEEKDAY_SHORT]) == 1


class TestEndToEndFullMonthGeneration:
    """Pełny AutoScheduleGenerator na całym miesiącu ze świętami wliczonymi
    (styczeń 2026: dni 1 i 6 to polskie święta ustawowe) - potwierdza, że
    oba nowe constrainty (public_holiday zero-out + coverage skip) faktycznie
    współpracują w realnym pipeline, nie tylko w izolacji wyżej."""

    def _build_month(self):
        profile = CustomBusinessProfile(
            key="test_public_holiday_e2e", display_name="Test Public Holiday", roles=[], rules=[],
        )
        register_custom_profile(profile)

        shop = ShopConfig(YEAR, MONTH)
        shop.business_type = profile.key
        loc = LocationConfig(key="site1", name="Site 1")  # closed_on_public_holidays=True (domyślnie)
        loc.set_duty_rotation(ROTATION)
        shop.locations["site1"] = loc
        shop.constraint_policies.update(default_policies(profile))
        shop.constraint_policies["balance"] = ConstraintPolicy.DISABLED
        shop.constraint_policies["monthly_hours"] = ConstraintPolicy.DISABLED

        schedule = MonthSchedule(YEAR, MONTH)
        employees = [
            Employee(last_name=f"E{i}", first_name="Guard", location_key="site1")
            for i in range(3)
        ]
        for emp in employees:
            schedule.add_employee(emp)
        return shop, schedule, employees

    def test_holidays_stay_empty_and_other_days_get_full_coverage(self):
        shop, schedule, employees = self._build_month()

        buf = io.StringIO()
        with redirect_stdout(buf):
            result = AutoScheduleGenerator(shop=shop, schedule=schedule).generate(solver_time_limit_seconds=60)
        assert result["success"], result

        holiday_days = {1, 6}  # Nowy Rok, Trzech Króli
        for day in holiday_days:
            for emp in employees:
                assert schedule.get_day(emp, day).is_empty(), f"day {day} should stay empty (public holiday)"

        for day in range(1, schedule.days_in_month + 1):
            if day in holiday_days:
                continue
            assigned = [emp for emp in employees if not schedule.get_day(emp, day).is_empty()]
            assert len(assigned) >= 1, f"day {day} should have at least one duty assignment"
