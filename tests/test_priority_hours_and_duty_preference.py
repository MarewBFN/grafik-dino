"""Dwa nowe, czysto dodatkowe mechanizmy w warstwie Enyo (custom_profile_wiring
build_objective_terms) - żaden nie dotyka kodu Dino:

- priority_hours_constraint.py: flaga "Umowa" - pracownicy z tą rolą mają
  pierwszeństwo w dobijaniu do nominalnego czasu pracy (bardzo ważony
  term miękki, nie MANDATORY - generator ma zawsze znaleźć rozwiązanie).
- duty_rotation_preference.py: miękka preferencja 12h+12h zamiast 24h w
  weekend, gdy oba warianty pokrycia są równie osiągalne.
"""

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
from logic.generator.duty_rotation_constraint import add_duty_rotation_coverage_constraint, add_duty_rotation_gate_constraint
from logic.generator.duty_rotation_preference import add_prefer_weekend_split_over_full_penalty
from logic.generator.priority_hours_constraint import UMOWA_ROLE_KEY, add_priority_hours_shortfall_penalty
from model.business_profile import register_custom_profile
from model.constraint_policy import ConstraintPolicy
from model.custom_profile import CustomBusinessProfile, RoleDefinition
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig

WEEKDAY_LONG, WEEKDAY_SHORT, WEEKEND_FULL, WEEKEND_HALF_A, WEEKEND_HALF_B = 15, 16, 17, 18, 19
ALL_SHIFTS = (WEEKDAY_LONG, WEEKDAY_SHORT, WEEKEND_FULL, WEEKEND_HALF_A, WEEKEND_HALF_B)
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

# 2026-08-08/09 is a Saturday/Sunday.
SATURDAY = 8


def _shop_with_rotation():
    shop = ShopConfig(2026, 8)
    loc = LocationConfig(key="site1", name="Site 1")
    loc.set_duty_rotation(ROTATION)
    shop.locations["site1"] = loc
    return shop


class TestPreferWeekendSplitOverFull:
    def test_solver_prefers_split_when_both_are_equally_achievable(self):
        shop = _shop_with_rotation()
        employees = [Employee(last_name="Guard", first_name=n, location_key="site1") for n in "AB"]

        model = cp_model.CpModel()
        x = {(e, d, s): model.NewBoolVar(f"x_{e}_{d}_{s}") for e in range(2) for d in [SATURDAY] for s in ALL_SHIFTS}

        add_duty_rotation_gate_constraint(model, x, employees, [SATURDAY], shop, DUTY_SHIFTS, ALL_SHIFTS)
        add_duty_rotation_coverage_constraint(model, x, employees, [SATURDAY], shop, DUTY_SHIFTS, soft=False)
        penalty = add_prefer_weekend_split_over_full_penalty(model, x, employees, [SATURDAY], shop, DUTY_SHIFTS)
        model.Minimize(sum(penalty))

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        assert status == cp_model.OPTIMAL
        assert solver.Value(x[0, SATURDAY, WEEKEND_FULL]) == 0
        assert solver.Value(x[1, SATURDAY, WEEKEND_FULL]) == 0
        assert solver.Value(x[0, SATURDAY, WEEKEND_HALF_A]) + solver.Value(x[1, SATURDAY, WEEKEND_HALF_A]) == 1
        assert solver.Value(x[0, SATURDAY, WEEKEND_HALF_B]) + solver.Value(x[1, SATURDAY, WEEKEND_HALF_B]) == 1

    def test_full_still_used_when_split_is_not_achievable(self):
        """Jeden pracownik nie może pokryć obu połówek tego samego dnia
        (add_one_shift_per_day_constraint) - z jednym pracownikiem jedynym
        wykonalnym wariantem jest weekend_full, mimo kary preferencji."""
        shop = _shop_with_rotation()
        employees = [Employee(last_name="Guard", first_name="A", location_key="site1")]

        model = cp_model.CpModel()
        x = {(0, SATURDAY, s): model.NewBoolVar(f"x_{s}") for s in ALL_SHIFTS}

        add_duty_rotation_gate_constraint(model, x, employees, [SATURDAY], shop, DUTY_SHIFTS, ALL_SHIFTS)
        model.Add(sum(x[0, SATURDAY, s] for s in ALL_SHIFTS) <= 1)  # one_shift_per_day
        add_duty_rotation_coverage_constraint(model, x, employees, [SATURDAY], shop, DUTY_SHIFTS, soft=False)
        penalty = add_prefer_weekend_split_over_full_penalty(model, x, employees, [SATURDAY], shop, DUTY_SHIFTS)
        model.Minimize(sum(penalty))

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        assert status == cp_model.OPTIMAL
        assert solver.Value(x[0, SATURDAY, WEEKEND_FULL]) == 1

    def test_prefer_24h_flips_the_preference_to_full_day(self):
        """"Preferuj zmiany 24h" w edytorze rotacji placówki - przy dwóch
        chętnych osobach solver wybiera jedną zmianę 24h zamiast podziału."""
        shop = ShopConfig(2026, 8)
        loc = LocationConfig(key="site1", name="Site 1")
        loc.set_duty_rotation(dict(ROTATION, prefer_24h=True))
        shop.locations["site1"] = loc
        employees = [Employee(last_name="Guard", first_name=n, location_key="site1") for n in "AB"]

        model = cp_model.CpModel()
        x = {(e, d, s): model.NewBoolVar(f"x_{e}_{d}_{s}") for e in range(2) for d in [SATURDAY] for s in ALL_SHIFTS}

        add_duty_rotation_gate_constraint(model, x, employees, [SATURDAY], shop, DUTY_SHIFTS, ALL_SHIFTS)
        add_duty_rotation_coverage_constraint(model, x, employees, [SATURDAY], shop, DUTY_SHIFTS, soft=False)
        penalty = add_prefer_weekend_split_over_full_penalty(model, x, employees, [SATURDAY], shop, DUTY_SHIFTS)
        model.Minimize(sum(penalty))

        solver = cp_model.CpSolver()
        assert solver.Solve(model) == cp_model.OPTIMAL
        assert solver.Value(x[0, SATURDAY, WEEKEND_FULL]) + solver.Value(x[1, SATURDAY, WEEKEND_FULL]) == 1
        assert all(
            solver.Value(x[e, SATURDAY, s]) == 0 for e in range(2) for s in (WEEKEND_HALF_A, WEEKEND_HALF_B)
        )


def _priority_shop_and_schedule(n_regular_employees):
    profile = CustomBusinessProfile(
        key=f"test_priority_{n_regular_employees}", display_name="Test Priority",
        roles=[RoleDefinition(key=UMOWA_ROLE_KEY, label="Umowa", show_summary_row=False)],
        rules=[],
    )
    register_custom_profile(profile)

    shop = ShopConfig(2026, 3)
    shop.business_type = profile.key
    shop.set_duty_rotation(ROTATION)
    shop.constraint_policies.update(default_policies(profile))
    # Etap D: tak jak w prawdziwym demo Enyo - balance/monthly_hours
    # wyłączone, priorytet Umowa musi działać niezależnie od nich.
    shop.constraint_policies["balance"] = ConstraintPolicy.DISABLED
    shop.constraint_policies["monthly_hours"] = ConstraintPolicy.DISABLED

    schedule = MonthSchedule(2026, 3)
    umowa_emp = Employee(last_name="Umowa", first_name="A", employment_fraction=1.0, custom_roles={UMOWA_ROLE_KEY: True})
    schedule.add_employee(umowa_emp)
    others = []
    for i in range(n_regular_employees):
        e = Employee(last_name="Zwykly", first_name=chr(66 + i), employment_fraction=1.0)
        schedule.add_employee(e)
        others.append(e)

    return shop, schedule, umowa_emp, others


class TestUmowaPriorityEndToEnd:
    """Wystarczająco dużo pracowników (8), żeby nikt nie mógł dobić do
    pełnego nominału (176h dla marca 2026) - realny niedobór, priorytet
    musi się realnie objawić, nie tylko teoretycznie istnieć."""

    def test_umowa_employee_reaches_nominal_before_others(self):
        shop, schedule, umowa_emp, others = _priority_shop_and_schedule(7)

        buf = io.StringIO()
        with redirect_stdout(buf):
            result = AutoScheduleGenerator(shop=shop, schedule=schedule).generate(solver_time_limit_seconds=45)

        assert result["success"], result

        nominal_minutes = shop.get_full_time_nominal_hours() * 60
        umowa_total = schedule.total_minutes_for_employee(umowa_emp)
        other_totals = [schedule.total_minutes_for_employee(e) for e in others]

        assert umowa_total == nominal_minutes, (umowa_total, nominal_minutes)
        assert all(t < umowa_total for t in other_totals), (umowa_total, other_totals)


class TestPriorityHoursShortfallPenaltyUnit:
    def test_no_penalty_terms_for_employees_without_the_role(self):
        shop = _shop_with_rotation()
        emp = Employee(last_name="Guard", first_name="A", location_key="site1")
        schedule = MonthSchedule(2026, 8)
        schedule.add_employee(emp)

        model = cp_model.CpModel()
        x = {(0, SATURDAY, s): model.NewBoolVar(f"x_{s}") for s in ALL_SHIFTS}

        penalties = add_priority_hours_shortfall_penalty(
            model, x, [emp], [SATURDAY], schedule, shop, ALL_SHIFTS, duty_shifts=DUTY_SHIFTS,
        )
        assert penalties == []

    def test_full_month_leave_umowa_employee_has_no_shortfall_term(self):
        """target_minutes == 0 (cały miesiąc L4/urlop) -> nic do dobijania,
        brak IntVar zamiast bezsensownego "dobij do zera"."""
        shop = ShopConfig(2026, 3)
        emp = Employee(last_name="Umowa", first_name="A", employment_fraction=1.0, custom_roles={UMOWA_ROLE_KEY: True})
        schedule = MonthSchedule(2026, 3)
        schedule.add_employee(emp)
        for day in range(1, schedule.days_in_month + 1):
            schedule.get_day(emp, day).is_leave = True

        days = list(range(1, schedule.days_in_month + 1))
        model = cp_model.CpModel()
        x = {(0, d, s): model.NewBoolVar(f"x_{d}_{s}") for d in days for s in ALL_SHIFTS}

        penalties = add_priority_hours_shortfall_penalty(
            model, x, [emp], days, schedule, shop, ALL_SHIFTS,
        )
        assert penalties == []


# --- "Wyrównanie godzin umowa/bez" (decyzja użytkownika 2026-09-25) ---

def _equalization_month(policy, umowa_count=0, n=6):
    profile = CustomBusinessProfile(
        key="test_hours_equalization", display_name="Test Equalization",
        roles=[
            RoleDefinition(key=UMOWA_ROLE_KEY, label="Umowa", show_summary_row=False),
            RoleDefinition(key="nie_chce_24h", label="Nie chce 24h", show_summary_row=False),
        ],
        rules=[],
    )
    register_custom_profile(profile)
    shop = ShopConfig(2026, 10)
    shop.business_type = profile.key
    loc = LocationConfig(key="site1", name="Site 1", closed_on_public_holidays=False)
    loc.set_24_7(True)
    loc.set_duty_rotation({
        "only_12_24h": True,
        "weekend_full": {"start": "08:00"},
        "weekend_half_a": {"start": "08:00", "end": "20:00"},
        "weekend_half_b": {"start": "20:00", "end": "08:00"},
    })
    shop.locations = {"site1": loc}
    shop.constraint_policies.update(default_policies(profile))
    shop.constraint_policies["balance"] = ConstraintPolicy.DISABLED
    shop.constraint_policies["monthly_hours"] = ConstraintPolicy.DISABLED
    if policy is not None:
        shop.constraint_policies["hours_equalization"] = policy
    schedule = MonthSchedule(2026, 10)
    employees = []
    for i in range(n):
        roles = {"nie_chce_24h": True}
        if i < umowa_count:
            roles[UMOWA_ROLE_KEY] = True
        emp = Employee(last_name=f"G{i}", first_name="X", location_key="site1", custom_roles=roles)
        schedule.add_employee(emp)
        employees.append(emp)
    return shop, schedule, employees


def _hours(schedule, emp):
    return schedule.total_minutes_for_employee(emp) / 60


class TestHoursEqualization:
    def test_default_policy_for_custom_profiles_is_disabled(self):
        shop, _, _ = _equalization_month(policy=None)
        assert shop.constraint_policies["hours_equalization"] == ConstraintPolicy.DISABLED

    def test_weight_by_policy(self):
        from logic.generator.priority_hours_constraint import hours_equalization_weight

        assert hours_equalization_weight(ConstraintPolicy.DISABLED) == 0
        assert hours_equalization_weight(None) == 0
        assert hours_equalization_weight(ConstraintPolicy.MANDATORY) > hours_equalization_weight(ConstraintPolicy.PREFERRED) > 0

    def test_preferred_spreads_hours_within_one_shift(self):
        shop, schedule, employees = _equalization_month(ConstraintPolicy.PREFERRED)
        with redirect_stdout(io.StringIO()):
            result = AutoScheduleGenerator(schedule, shop).generate(solver_time_limit_seconds=30, solver_workers=2)
        assert result["success"], result
        hours = [_hours(schedule, e) for e in employees]
        assert max(hours) - min(hours) <= 12, hours

    def test_umowa_and_non_umowa_are_equalized_separately(self):
        """Osoby z "Umowa" idą najpierw do nominału (priorytet), reszta
        dzieli pozostałe godziny równo między siebie."""
        shop, schedule, employees = _equalization_month(ConstraintPolicy.PREFERRED, umowa_count=2)
        with redirect_stdout(io.StringIO()):
            result = AutoScheduleGenerator(schedule, shop).generate(solver_time_limit_seconds=30, solver_workers=2)
        assert result["success"], result
        umowa = [_hours(schedule, e) for e in employees[:2]]
        others = [_hours(schedule, e) for e in employees[2:]]
        assert min(umowa) > max(others), (umowa, others)
        assert max(umowa) - min(umowa) <= 12, umowa
        assert max(others) - min(others) <= 12, others
