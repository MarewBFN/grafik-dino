"""Regresja: cel godzinowy (monthly_hours/balance) nie może zejść poniżej
0 dla pracownika na długim L4/urlopie. Przed tą poprawką target_minutes
mógł wyjść ujemny (nominał pomniejszony o więcej godzin L4/urlopu niż sam
wynosi), co w trybie miękkim liczyło fikcyjną karę "over" dla kogoś, kto
faktycznie przepracował 0 godzin w pełni zasadnie, a w trybie twardym
(MANDATORY) potrafiło zrobić cały model niewykonalnym. add_balance_constraint
dodatkowo w ogóle nie odejmowało L4/urlopu od celu przed tą poprawką."""

import sys
from pathlib import Path

from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.generator.hours_constraint import add_balance_constraint, add_monthly_hours_constraint
from logic.monthly_hours_status import monthly_hours_status
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig

SHIFT_OPEN, SHIFT_CLOSE = 0, 1
ALL_SHIFTS = (SHIFT_OPEN, SHIFT_CLOSE)


def _full_month_leave_setup(year=2026, month=3):
    """Pracownik pełnoetatowy na urlopie/L4 przez CAŁY miesiąc - żadna
    zmiana nie jest mu dostępna (add_leave_constraints w pełnym
    generatorze wymusza x==0 na każdy dzień; tutaj budujemy to samo ręcznie
    do izolowanego testu constraintu)."""
    shop = ShopConfig(year, month)
    emp = Employee(last_name="Kowalski", first_name="Jan", employment_fraction=1.0)
    schedule = MonthSchedule(year, month)
    schedule.add_employee(emp)

    for day in range(1, schedule.days_in_month + 1):
        schedule.get_day(emp, day).is_leave = True

    days = list(range(1, schedule.days_in_month + 1))
    model = cp_model.CpModel()
    x = {(0, d, s): model.NewBoolVar(f"x_{d}_{s}") for d in days for s in ALL_SHIFTS}
    # Zablokuj wszystkie zmiany na każdy dzień - to samo co robi
    # add_leave_constraints w pełnym generatorze.
    for d in days:
        for s in ALL_SHIFTS:
            model.Add(x[0, d, s] == 0)

    return shop, emp, schedule, days, model, x


class TestMonthlyHoursFullMonthLeave:
    def test_target_minutes_status_does_not_go_negative(self):
        shop, emp, schedule, _, _, _ = _full_month_leave_setup()
        status = monthly_hours_status(schedule, shop, emp)
        assert status["target_minutes"] == 0
        assert status["worked_minutes"] == 0
        assert status["over_minutes"] == 0
        assert status["is_over"] is False

    def test_soft_monthly_hours_has_no_phantom_over_penalty(self):
        shop, emp, schedule, days, model, x = _full_month_leave_setup()

        violations = add_monthly_hours_constraint(
            model, x, [emp], days, schedule, shop, ALL_SHIFTS, soft=True,
        )
        model.Minimize(sum(violations))

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        # Suma wszystkich violation (under+over+spread) musi wynosić 0 -
        # pracownik w pełni na urlopie nie powinien generować JAKIEJKOLWIEK
        # kary, bo cel i tak wynosi 0, a on ma 0 godzin.
        assert solver.ObjectiveValue() == 0

    def test_hard_monthly_hours_is_feasible_not_infeasible(self):
        """Przed poprawką: MANDATORY monthly_hours + cały miesiąc L4/urlopu
        dawało total_minutes <= (ujemny target + pasmo), co przy
        total_minutes >= 0 było zawsze sprzeczne - model INFEASIBLE."""
        shop, emp, schedule, days, model, x = _full_month_leave_setup()

        add_monthly_hours_constraint(
            model, x, [emp], days, schedule, shop, ALL_SHIFTS, soft=False,
        )

        status = cp_model.CpSolver().Solve(model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def test_soft_balance_has_no_phantom_penalty_and_accounts_for_leave(self):
        shop, emp, schedule, days, model, x = _full_month_leave_setup()

        violations = add_balance_constraint(
            model, x, [emp], days, schedule, shop, ALL_SHIFTS, soft=True,
        )
        model.Minimize(sum(violations))

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        assert solver.ObjectiveValue() == 0


class TestMonthlyHoursPartialLeaveUnaffected:
    """10 dni L4/urlopu (nie cały miesiąc) - target dodatni, klamra do 0
    nie powinna nic zmieniać względem zachowania sprzed poprawki."""

    def test_partial_leave_target_matches_manual_calculation(self):
        shop = ShopConfig(2026, 3)
        emp = Employee(last_name="Nowak", first_name="Anna", employment_fraction=1.0)
        schedule = MonthSchedule(2026, 3)
        schedule.add_employee(emp)
        for day in range(1, 11):
            schedule.get_day(emp, day).is_leave = True

        status = monthly_hours_status(schedule, shop, emp)

        nominal_minutes = shop.get_full_time_nominal_hours() * 60
        from logic.utils.time_utils import get_effective_daily_hours
        daily_minutes = int(get_effective_daily_hours(emp, shop) * 60)
        expected_target = nominal_minutes - 10 * daily_minutes
        assert expected_target > 0  # sanity: to nie jest przypadek klamrowania
        assert status["target_minutes"] == expected_target
