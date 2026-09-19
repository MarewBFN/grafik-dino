"""Etap C "plan profil ochrona (analiza specyfikacji klienta).md", sekcja
12: odpoczynek po zmianach rotacji 24/7 - standardowe 11h po
weekday_long/short i weekend_half_a/b, system "doba za dobę" (N-1)x24h po
weekend_full (N = pracownicy tej lokalizacji bez flagi "nie_chce_24h")."""

import sys
from pathlib import Path

from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.generator.duty_rotation_rest_constraint import add_duty_rotation_rest_constraint
from model.employee import Employee
from model.location import LocationConfig
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

# August 2026: 1=Sat, 2=Sun, 3=Mon, 4=Tue, 5=Wed, 6=Thu, 7=Fri, 8=Sat.
SAT, SUN, MON, TUE, WED = 1, 2, 3, 4, 5


ROTATION_ONLY_12_24H = {
    "only_12_24h": True,
    "weekend_full": {"start": "06:00"},
    "weekend_half_a": {"start": "06:00", "end": "18:00"},
    "weekend_half_b": {"start": "18:00", "end": "06:00"},
}


def _shop_with_rotation(rotation=ROTATION):
    shop = ShopConfig(2026, 8)
    loc = LocationConfig(key="site1", name="Site 1")
    loc.set_duty_rotation(rotation)
    shop.locations["site1"] = loc
    return shop


def _model_and_x(n_employees, days):
    model = cp_model.CpModel()
    x = {
        (e, d, s): model.NewBoolVar(f"x_{e}_{d}_{s}")
        for e in range(n_employees) for d in days for s in ALL_SHIFTS
    }
    return model, x


def _employees(n, no24h_indices=()):
    return [
        Employee(
            last_name=f"E{i}", first_name="Guard", location_key="site1",
            custom_roles={"nie_chce_24h": True} if i in no24h_indices else {},
        )
        for i in range(n)
    ]


class TestStandardElevenHourRest:
    def test_same_employee_cannot_repeat_weekday_long_next_day(self):
        shop = _shop_with_rotation()
        employees = _employees(1)
        days = [MON, TUE]
        model, x = _model_and_x(1, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, MON, WEEKDAY_LONG] == 1)
        model.Add(x[0, TUE, WEEKDAY_LONG] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE

    def test_same_employee_cannot_go_straight_from_short_to_long(self):
        """weekday_short ends 06:00 next day; weekday_long starts 06:00 the
        very same calendar day - 0h rest, must be blocked."""
        shop = _shop_with_rotation()
        employees = _employees(1)
        days = [MON, TUE]
        model, x = _model_and_x(1, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, MON, WEEKDAY_SHORT] == 1)
        model.Add(x[0, TUE, WEEKDAY_LONG] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE

    def test_different_employees_can_split_weekday_long_across_days(self):
        shop = _shop_with_rotation()
        employees = _employees(2)
        days = [MON, TUE]
        model, x = _model_and_x(2, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, MON, WEEKDAY_LONG] == 1)
        model.Add(x[1, TUE, WEEKDAY_LONG] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def test_weekend_half_b_to_weekday_long_has_enough_rest(self):
        """half_b ends 06:00 Monday (started Sunday 18:00); weekday_long
        also starts 06:00 Monday - 0h rest, must be blocked."""
        shop = _shop_with_rotation()
        employees = _employees(1)
        days = [SUN, MON]
        model, x = _model_and_x(1, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, SUN, WEEKEND_HALF_B] == 1)
        model.Add(x[0, MON, WEEKDAY_LONG] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE


class TestFullDayRotationRest:
    def test_two_capable_employees_need_24h_rest_between_full_day_shifts(self):
        shop = _shop_with_rotation()
        employees = _employees(2)  # both capable of 24h -> N=2 -> 24h rest
        days = [SAT, SUN]
        model, x = _model_and_x(2, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, SAT, WEEKEND_FULL] == 1)
        model.Add(x[0, SUN, WEEKEND_FULL] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE

    def test_two_capable_employees_can_alternate_full_day_shifts(self):
        shop = _shop_with_rotation()
        employees = _employees(2)
        days = [SAT, SUN]
        model, x = _model_and_x(2, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, SAT, WEEKEND_FULL] == 1)
        model.Add(x[1, SUN, WEEKEND_FULL] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def test_three_capable_employees_need_48h_so_monday_is_still_too_early(self):
        shop = _shop_with_rotation()
        employees = _employees(3)  # N=3 -> (3-1)*24h = 48h rest
        days = [SAT, SUN, MON]
        model, x = _model_and_x(3, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, SAT, WEEKEND_FULL] == 1)
        # Full day shift ends Sunday 06:00; Monday's weekday_long starts
        # Monday 06:00 - only 24h later, still short of the 48h required.
        model.Add(x[0, MON, WEEKDAY_LONG] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE

    def test_three_capable_employees_can_return_on_tuesday_exactly_at_48h(self):
        shop = _shop_with_rotation()
        employees = _employees(3)
        days = [SAT, SUN, MON, TUE]
        model, x = _model_and_x(3, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, SAT, WEEKEND_FULL] == 1)
        # Ends Sunday 06:00; Tuesday's weekday_long starts Tuesday 06:00 -
        # exactly 48h later, right at the boundary, must be allowed.
        model.Add(x[0, TUE, WEEKDAY_LONG] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def test_no24h_employees_are_excluded_from_the_headcount(self):
        """3 employees at the location, but one has "nie_chce_24h" - only
        the other 2 ever rotate on weekend_full, so N=2 (24h rest), not
        N=3 (48h) - Monday should already be fine."""
        shop = _shop_with_rotation()
        employees = _employees(3, no24h_indices=(2,))
        days = [SAT, SUN, MON]
        model, x = _model_and_x(3, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, SAT, WEEKEND_FULL] == 1)
        model.Add(x[0, MON, WEEKDAY_LONG] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def test_single_person_rotation_still_gets_a_minimum_24h_rest(self):
        """N=1 (only one capable employee) would give (1-1)*24h = 0h by the
        raw formula - the client's floor ("nie mniej niż 24h") must still
        apply."""
        shop = _shop_with_rotation()
        employees = _employees(1)
        days = [SAT, SUN]
        model, x = _model_and_x(1, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, SAT, WEEKEND_FULL] == 1)
        model.Add(x[0, SUN, WEEKEND_FULL] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE


class TestOnly1224hToggleRest:
    """Z toggle'em "Używaj tylko zmian 12/24h" te same zasady (24h dla
    weekend_full, 11h dla połówek) obowiązują w KAŻDY dzień tygodnia, nie
    tylko w weekend."""

    def test_24h_shift_on_a_weekday_still_requires_full_rest(self):
        shop = _shop_with_rotation(rotation=ROTATION_ONLY_12_24H)
        employees = _employees(2)  # N=2 -> 24h rest
        days = [MON, TUE]
        model, x = _model_and_x(2, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, MON, WEEKEND_FULL] == 1)
        # 24h shift started Monday 06:00 ends Tuesday 06:00 - a second 24h
        # shift starting right then for the SAME employee is 0h rest.
        model.Add(x[0, TUE, WEEKEND_FULL] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE

    def test_different_employee_can_take_the_next_weekday_24h_shift(self):
        shop = _shop_with_rotation(rotation=ROTATION_ONLY_12_24H)
        employees = _employees(2)
        days = [MON, TUE]
        model, x = _model_and_x(2, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, MON, WEEKEND_FULL] == 1)
        model.Add(x[1, TUE, WEEKEND_FULL] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def test_three_capable_employees_need_48h_rest_across_weekdays_too(self):
        shop = _shop_with_rotation(rotation=ROTATION_ONLY_12_24H)
        employees = _employees(3)  # N=3 -> 48h rest
        days = [MON, TUE, WED]
        model, x = _model_and_x(3, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, MON, WEEKEND_FULL] == 1)
        # Ends Tuesday 06:00; Wednesday 06:00 is only 24h later - still
        # short of the 48h required with a 3-person rotation.
        model.Add(x[0, WED, WEEKEND_HALF_A] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE
