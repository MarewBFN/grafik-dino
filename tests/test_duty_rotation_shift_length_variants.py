"""Na żądanie użytkownika: dotychczasowe testy duty_rotation
(test_duty_rotation_constraint.py, test_duty_rotation_rest_constraint.py,
test_priority_hours_and_duty_preference.py) używają WYŁĄCZNIE jednego,
zahardkodowanego zestawu godzin (06:00/18:00/22:00 - zawsze 16h/8h w
tygodniu, 12h/12h w weekend). Ten plik sprawdza, że gate/coverage/rest/
kalkulacja minut nie są przypadkiem przywiązane do tych konkretnych liczb -
różne godziny startu (7:00, 8:00, 8:30, 9:00) i różne długości zmian (24h,
12h+12h, 8h+16h), w tym warianty dokładnie odpowiadające notacji "X/Y"
(godzina startu/końca) z realnych danych klienta
(test_data/dane_klienta_ochrona.json):

- "8/8" -> zmiana 24h zaczynająca się o 8:00 (PGE Ustka - obserwowana ZAWSZE).
- "7/7" -> to samo, inny anchor (7:00) - nigdzie indziej nie testowane.
- "8/16" / "9/17" -> podział 8h+16h (asymetryczny, w przeciwieństwie do
  zawsze używanego 12h/12h albo 16h/8h) przy dwóch różnych anchorach.
"""

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.auto_generator import AutoScheduleGenerator
from logic.generator.custom_profile_wiring import default_policies
from logic.generator.duty_rotation_constraint import (
    add_duty_rotation_coverage_constraint,
    add_duty_rotation_gate_constraint,
    duty_rotation_minutes_for_employee,
)
from logic.generator.duty_rotation_preference import add_prefer_weekend_split_over_full_penalty
from logic.generator.duty_rotation_rest_constraint import add_duty_rotation_rest_constraint
from model.business_profile import register_custom_profile
from model.constraint_policy import ConstraintPolicy
from model.custom_profile import CustomBusinessProfile
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig

WEEKDAY_LONG, WEEKDAY_SHORT, WEEKEND_FULL, WEEKEND_HALF_A, WEEKEND_HALF_B = 15, 16, 17, 18, 19
ALL_SHIFTS = (WEEKDAY_LONG, WEEKDAY_SHORT, WEEKEND_FULL, WEEKEND_HALF_A, WEEKEND_HALF_B)
DUTY_SHIFTS = {
    "weekday_long": WEEKDAY_LONG, "weekday_short": WEEKDAY_SHORT,
    "weekend_full": WEEKEND_FULL, "weekend_half_a": WEEKEND_HALF_A, "weekend_half_b": WEEKEND_HALF_B,
}

# August 2026: 1=Sat, 2=Sun, 3=Mon, 4=Tue, 5=Wed.
SAT, SUN, MON, TUE, WED = 1, 2, 3, 4, 5
DAYS_IN_MONTH = 31

SHAPES = [
    pytest.param(
        {"only_12_24h": True, "weekend_full": {"start": "08:00"},
         "weekend_half_a": {"start": "08:00", "end": "20:00"},
         "weekend_half_b": {"start": "20:00", "end": "08:00"}},
        {"weekend_full": 24 * 60, "weekend_half_a": 12 * 60, "weekend_half_b": 12 * 60},
        id="8_8_full_and_12_12_split",
    ),
    pytest.param(
        {"only_12_24h": True, "weekend_full": {"start": "07:00"},
         "weekend_half_a": {"start": "07:00", "end": "19:00"},
         "weekend_half_b": {"start": "19:00", "end": "07:00"}},
        {"weekend_full": 24 * 60, "weekend_half_a": 12 * 60, "weekend_half_b": 12 * 60},
        id="7_7_different_anchor",
    ),
    pytest.param(
        {"only_12_24h": True, "weekend_full": {"start": "08:00"},
         "weekend_half_a": {"start": "08:00", "end": "16:00"},
         "weekend_half_b": {"start": "16:00", "end": "08:00"}},
        {"weekend_full": 24 * 60, "weekend_half_a": 8 * 60, "weekend_half_b": 16 * 60},
        id="8_16_asymmetric_split",
    ),
    pytest.param(
        {"only_12_24h": True, "weekend_full": {"start": "09:00"},
         "weekend_half_a": {"start": "09:00", "end": "17:00"},
         "weekend_half_b": {"start": "17:00", "end": "09:00"}},
        {"weekend_full": 24 * 60, "weekend_half_a": 8 * 60, "weekend_half_b": 16 * 60},
        id="9_17_asymmetric_split",
    ),
    pytest.param(
        {"only_12_24h": True, "weekend_full": {"start": "08:30"},
         "weekend_half_a": {"start": "08:30", "end": "16:30"},
         "weekend_half_b": {"start": "16:30", "end": "08:30"}},
        {"weekend_full": 24 * 60, "weekend_half_a": 8 * 60, "weekend_half_b": 16 * 60},
        id="half_hour_anchor",
    ),
]


def _shop_with_rotation(rotation):
    shop = ShopConfig(2026, 8)
    loc = LocationConfig(key="site1", name="Site 1")
    loc.set_duty_rotation(rotation)
    # Nie testujemy tu automatycznego zamknięcia w święta (domyślnie True) -
    # patrz ten sam komentarz w _shop_schedule_with_profile() niżej.
    loc.closed_on_public_holidays = False
    shop.locations["site1"] = loc
    return shop


def _employees(n, no24h_indices=()):
    return [
        Employee(last_name=f"E{i}", first_name="Guard", location_key="site1",
                 custom_roles={"nie_chce_24h": True} if i in no24h_indices else {})
        for i in range(n)
    ]


def _model_and_x(n_employees, days):
    model = cp_model.CpModel()
    x = {(e, d, s): model.NewBoolVar(f"x_{e}_{d}_{s}") for e in range(n_employees) for d in days for s in ALL_SHIFTS}
    return model, x


class TestMinutesComputationAcrossShapes:
    @pytest.mark.parametrize("rotation, expected_minutes", SHAPES)
    def test_duty_rotation_minutes_match_configured_window_lengths(self, rotation, expected_minutes):
        shop = _shop_with_rotation(rotation)
        emp = _employees(1)[0]

        minutes = duty_rotation_minutes_for_employee(shop, emp, DUTY_SHIFTS)

        assert minutes[WEEKEND_FULL] == expected_minutes["weekend_full"]
        assert minutes[WEEKEND_HALF_A] == expected_minutes["weekend_half_a"]
        assert minutes[WEEKEND_HALF_B] == expected_minutes["weekend_half_b"]
        # only_12_24h: weekday_long/short nie są skonfigurowane dla tych
        # kształtów, więc w ogóle nie ma ich w słowniku minut (patrz "continue"
        # na window is None w duty_rotation_minutes_for_employee).
        assert WEEKDAY_LONG not in minutes
        assert WEEKDAY_SHORT not in minutes


class TestCoverageAndPreferenceAcrossShapes:
    """Powtórka test_priority_hours_and_duty_preference.py::TestPreferWeekendSplitOverFull
    dla KAŻDEGO kształtu - dowód, że coverage/gate/preferencja nie są
    przypadkiem przywiązane do jedynego dotąd testowanego zestawu godzin."""

    @pytest.mark.parametrize("rotation, expected_minutes", SHAPES)
    def test_split_is_chosen_over_full_when_both_employees_available(self, rotation, expected_minutes):
        shop = _shop_with_rotation(rotation)
        employees = _employees(2)
        days = [SAT]
        model, x = _model_and_x(2, days)

        add_duty_rotation_gate_constraint(model, x, employees, days, shop, DUTY_SHIFTS, ALL_SHIFTS)
        add_duty_rotation_coverage_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        penalty = add_prefer_weekend_split_over_full_penalty(model, x, employees, days, shop, DUTY_SHIFTS)
        model.Minimize(sum(penalty))

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        assert status == cp_model.OPTIMAL
        assert solver.Value(x[0, SAT, WEEKEND_FULL]) == 0
        assert solver.Value(x[1, SAT, WEEKEND_FULL]) == 0
        assert solver.Value(x[0, SAT, WEEKEND_HALF_A]) + solver.Value(x[1, SAT, WEEKEND_HALF_A]) == 1
        assert solver.Value(x[0, SAT, WEEKEND_HALF_B]) + solver.Value(x[1, SAT, WEEKEND_HALF_B]) == 1

    @pytest.mark.parametrize("rotation, expected_minutes", SHAPES)
    def test_full_is_forced_when_only_one_employee_available(self, rotation, expected_minutes):
        shop = _shop_with_rotation(rotation)
        employees = _employees(1)
        days = [SAT]
        model, x = _model_and_x(1, days)

        add_duty_rotation_gate_constraint(model, x, employees, days, shop, DUTY_SHIFTS, ALL_SHIFTS)
        model.Add(sum(x[0, SAT, s] for s in ALL_SHIFTS) <= 1)  # one_shift_per_day
        add_duty_rotation_coverage_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        penalty = add_prefer_weekend_split_over_full_penalty(model, x, employees, days, shop, DUTY_SHIFTS)
        model.Minimize(sum(penalty))

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        assert status == cp_model.OPTIMAL
        assert solver.Value(x[0, SAT, WEEKEND_FULL]) == 1


ROTATION_7 = {
    "only_12_24h": True,
    "weekend_full": {"start": "07:00"},
    "weekend_half_a": {"start": "07:00", "end": "19:00"},
    "weekend_half_b": {"start": "19:00", "end": "07:00"},
}

# only_12_24h=False (domyślne) - weekday_long/short DO istnieją, ale przy
# innym anchorze (09:00/17:00) niż wszędzie indziej testowany (06:00/22:00),
# i z ODWRÓCONĄ asymetrią: tu krótsza (8h) zmiana idzie PIERWSZA (dzień),
# dłuższa (16h) DRUGA (noc) - w oryginalnej fixture jest odwrotnie.
ROTATION_9_17_WEEKDAY = {
    "weekday_long": {"start": "09:00", "end": "17:00"},
    "weekday_short": {"start": "17:00", "end": "09:00"},
    "weekend_full": {"start": "06:00"},
    "weekend_half_a": {"start": "06:00", "end": "18:00"},
    "weekend_half_b": {"start": "18:00", "end": "06:00"},
}


class TestRestConstraintAtDifferentAnchor:
    """Te same graniczne scenariusze co
    test_duty_rotation_rest_constraint.py::TestFullDayRotationRest (tam
    zawsze anchor 06:00), tu przy 07:00 - potwierdza, że
    _anchor()/_shift_start_end_anchored() poprawnie parsują dowolną godzinę,
    nie tylko 06:00."""

    def test_two_capable_employees_need_24h_rest_between_full_day_shifts(self):
        shop = _shop_with_rotation(ROTATION_7)
        employees = _employees(2)
        days = [SAT, SUN]
        model, x = _model_and_x(2, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, SAT, WEEKEND_FULL] == 1)
        model.Add(x[0, SUN, WEEKEND_FULL] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE

    def test_different_employee_can_take_the_next_full_day_shift(self):
        shop = _shop_with_rotation(ROTATION_7)
        employees = _employees(2)
        days = [SAT, SUN]
        model, x = _model_and_x(2, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, SAT, WEEKEND_FULL] == 1)
        model.Add(x[1, SUN, WEEKEND_FULL] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def test_half_b_to_half_a_next_day_has_zero_rest_and_is_blocked(self):
        """half_b (19:00-07:00) kończy się 07:00; half_a zaczyna się 07:00
        następnego dnia kalendarzowego - 0h odpoczynku, musi być
        zablokowane (standardowe 11h dla połówek, patrz _required_rest)."""
        shop = _shop_with_rotation(ROTATION_7)
        employees = _employees(1)
        days = [SUN, MON]
        model, x = _model_and_x(1, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, SUN, WEEKEND_HALF_B] == 1)
        model.Add(x[0, MON, WEEKEND_HALF_A] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE

    def test_single_person_rotation_still_gets_minimum_24h_rest(self):
        shop = _shop_with_rotation(ROTATION_7)
        employees = _employees(1)
        days = [SAT, SUN]
        model, x = _model_and_x(1, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, SAT, WEEKEND_FULL] == 1)
        model.Add(x[0, SUN, WEEKEND_FULL] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE


class TestWeekdaySplitAtDifferentAnchorAndAsymmetricLength:
    """weekday_long/short @ 09:00/17:00 (8h/16h) zamiast wszędzie indziej
    testowanego 06:00/22:00 (16h/8h) - inny anchor I odwrócona asymetria."""

    def test_repeating_the_short_8h_gap_shift_next_day_is_blocked(self):
        """W tym kształcie to weekday_short (17:00-09:00, 16h) jest "długą"
        zmianą - powtórzenie go nazajutrz zostawia tylko 8h przerwy
        (09:00->17:00), poniżej wymaganych 11h. Odwrotnie niż w oryginalnej
        fixture (06:00-22:00/22:00-06:00), gdzie to WEEKDAY_LONG ma ciasną
        przerwę - dowód, że constraint liczy przerwę z rzeczywistych godzin
        danego kształtu, a nie z nazwy typu zmiany."""
        shop = _shop_with_rotation(ROTATION_9_17_WEEKDAY)
        employees = _employees(1)
        days = [MON, TUE]
        model, x = _model_and_x(1, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, MON, WEEKDAY_SHORT] == 1)
        model.Add(x[0, TUE, WEEKDAY_SHORT] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE

    def test_repeating_the_long_8h_shift_next_day_has_enough_rest(self):
        """Odwrotnie: weekday_long (09:00-17:00, 8h) jest tu krótką zmianą -
        powtórzenie go nazajutrz zostawia 16h przerwy (17:00->09:00),
        powyżej wymaganych 11h - dozwolone, mimo że ten sam wzorzec
        (powtórzenie "long" nazajutrz) jest ZABLOKOWANY w oryginalnej
        fixture 06:00-22:00, gdzie weekday_long trwa 16h i zostawia tylko 8h."""
        shop = _shop_with_rotation(ROTATION_9_17_WEEKDAY)
        employees = _employees(1)
        days = [MON, TUE]
        model, x = _model_and_x(1, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, MON, WEEKDAY_LONG] == 1)
        model.Add(x[0, TUE, WEEKDAY_LONG] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def test_same_employee_cannot_go_straight_from_short_to_long(self):
        """weekday_short (17:00-09:00) kończy się 09:00; weekday_long
        zaczyna się 09:00 tego samego dnia kalendarzowego - 0h odpoczynku."""
        shop = _shop_with_rotation(ROTATION_9_17_WEEKDAY)
        employees = _employees(1)
        days = [MON, TUE]
        model, x = _model_and_x(1, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, MON, WEEKDAY_SHORT] == 1)
        model.Add(x[0, TUE, WEEKDAY_LONG] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status == cp_model.INFEASIBLE

    def test_different_employees_can_split_weekday_long_across_days(self):
        shop = _shop_with_rotation(ROTATION_9_17_WEEKDAY)
        employees = _employees(2)
        days = [MON, TUE]
        model, x = _model_and_x(2, days)

        add_duty_rotation_rest_constraint(model, x, employees, days, shop, DUTY_SHIFTS, soft=False)
        model.Add(x[0, MON, WEEKDAY_LONG] == 1)
        model.Add(x[1, TUE, WEEKDAY_LONG] == 1)

        status = cp_model.CpSolver().Solve(model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def test_minutes_reflect_the_asymmetric_8h_16h_split(self):
        shop = _shop_with_rotation(ROTATION_9_17_WEEKDAY)
        emp = _employees(1)[0]
        minutes = duty_rotation_minutes_for_employee(shop, emp, DUTY_SHIFTS)
        assert minutes[WEEKDAY_LONG] == 8 * 60
        assert minutes[WEEKDAY_SHORT] == 16 * 60


# ============================================================
# Pełne uruchomienia AutoScheduleGenerator (nie tylko izolowane
# constrainty) na kształtach odpowiadających dokładnie realnym danym
# klienta - formalizacja wcześniejszej ręcznej weryfikacji
# demo/install_client_sample_data.py jako trwały test.
# ============================================================


def _run(shop, schedule, time_limit=45):
    buf = io.StringIO()
    with redirect_stdout(buf):
        result = AutoScheduleGenerator(shop=shop, schedule=schedule).generate(solver_time_limit_seconds=time_limit)
    return result


def _shop_schedule_with_profile(rotation, n_employees, no24h_indices=(), key="test_shapes"):
    profile = CustomBusinessProfile(key=key, display_name="Test Shapes", roles=[], rules=[])
    register_custom_profile(profile)

    shop = ShopConfig(2026, 8)
    shop.business_type = profile.key
    loc = LocationConfig(key="site1", name="Site 1")
    loc.set_duty_rotation(rotation)
    # Nie testujemy tu automatycznego zamknięcia w święta (domyślnie True) -
    # patrz komentarz w _shop_with_rotation() wyżej.
    loc.closed_on_public_holidays = False
    shop.locations = {"site1": loc}
    shop.constraint_policies.update(default_policies(profile))
    # Etap D (jak w realnym demo Enyo): pełne pokrycie > nominalny czas pracy.
    shop.constraint_policies["balance"] = ConstraintPolicy.DISABLED
    shop.constraint_policies["monthly_hours"] = ConstraintPolicy.DISABLED

    schedule = MonthSchedule(2026, 8)
    employees = [
        Employee(last_name=f"E{i}", first_name="Guard", employment_fraction=1.0, location_key="site1",
                 custom_roles={"nie_chce_24h": True} if i in no24h_indices else {})
        for i in range(n_employees)
    ]
    for emp in employees:
        schedule.add_employee(emp)

    return shop, schedule, employees


class TestEndToEndPgeUstkaShape:
    """"8/8" - zmiana 24h @ 08:00, only_12_24h, 4 pracowników, ŻADEN z flagą
    nie_chce_24h - dokładnie wzorzec PGE Ustka z
    test_data/dane_klienta_ochrona.json (formalizacja wcześniejszej ręcznej
    weryfikacji)."""

    ROTATION = {
        "only_12_24h": True,
        "weekend_full": {"start": "08:00"},
        "weekend_half_a": {"start": "08:00", "end": "20:00"},
        "weekend_half_b": {"start": "20:00", "end": "08:00"},
    }

    def test_full_month_generates_with_full_coverage_every_day(self):
        shop, schedule, employees = _shop_schedule_with_profile(self.ROTATION, n_employees=4, key="test_pge_shape")

        result = _run(shop, schedule)
        assert result["success"], result

        for day in range(1, DAYS_IN_MONTH + 1):
            assignments = [schedule.get_day(e, day) for e in employees]
            full_day = [a for a in assignments if a.is_full_day]
            half_a = [a for a in assignments if not a.is_full_day and a.start == "08:00" and a.end == "20:00"]
            half_b = [a for a in assignments if not a.is_full_day and a.start == "20:00" and a.end == "08:00"]

            if full_day:
                assert len(full_day) == 1, f"day {day}: {len(full_day)} full-day assignments"
                assert full_day[0].start == "08:00"
                assert not half_a and not half_b
            else:
                assert len(half_a) == 1, f"day {day}: half_a coverage = {len(half_a)}"
                assert len(half_b) == 1, f"day {day}: half_b coverage = {len(half_b)}"

            # Nikt inny nie ma żadnej zmiany tego dnia poza dokładnie
            # ustaloną kombinacją wyżej (dokładnie tyle osób ile wymaga
            # coverage, nie więcej).
            working = [a for a in assignments if a.total_duration() is not None]
            assert len(working) == (1 if full_day else 2)


class TestEndToEndUbojniaShape:
    """12h/12h @ 08:00 (8:00-20:00/20:00-8:00), only_12_24h, WSZYSCY z
    nie_chce_24h - dokładnie wzorzec Ubojni GOSZ (7 pracowników jak w
    realnych danych): weekend_full strukturalnie niedostępny dla każdego,
    podział musi wystąpić KAŻDEGO dnia."""

    ROTATION = {
        "only_12_24h": True,
        "weekend_full": {"start": "08:00"},
        "weekend_half_a": {"start": "08:00", "end": "20:00"},
        "weekend_half_b": {"start": "20:00", "end": "08:00"},
    }

    def test_full_month_never_uses_weekend_full_and_covers_every_day(self):
        shop, schedule, employees = _shop_schedule_with_profile(
            self.ROTATION, n_employees=7, no24h_indices=range(7), key="test_ubojnia_shape",
        )

        result = _run(shop, schedule)
        assert result["success"], result

        total_full_day_assignments = 0
        for day in range(1, DAYS_IN_MONTH + 1):
            assignments = [schedule.get_day(e, day) for e in employees]
            full_day = [a for a in assignments if a.is_full_day]
            half_a = [a for a in assignments if not a.is_full_day and a.start == "08:00" and a.end == "20:00"]
            half_b = [a for a in assignments if not a.is_full_day and a.start == "20:00" and a.end == "08:00"]

            total_full_day_assignments += len(full_day)
            assert len(half_a) == 1, f"day {day}: half_a coverage = {len(half_a)}"
            assert len(half_b) == 1, f"day {day}: half_b coverage = {len(half_b)}"

        assert total_full_day_assignments == 0

        # Suma minut kogoś, kto miał choć jedną zmianę 12h, jest wielokrotnością 12h.
        for emp in employees:
            worked_days = sum(
                1 for d in range(1, DAYS_IN_MONTH + 1) if schedule.get_day(emp, d).total_duration() is not None
            )
            assert schedule.total_minutes_for_employee(emp) == worked_days * 12 * 60


class TestEndToEndWeekdayShiftedAnchorShape:
    """weekday_long/short @ 09:00/17:00 (8h/16h) w tygodniu + weekend_full/
    half @ 06:00 (12h/12h) - dwa NIEZALEŻNE anchory w tym samym projekcie,
    nigdzie indziej nie testowane razem end-to-end."""

    ROTATION = ROTATION_9_17_WEEKDAY

    def test_full_month_weekday_and_weekend_coverage_both_hold(self):
        shop, schedule, employees = _shop_schedule_with_profile(self.ROTATION, n_employees=4, key="test_9_17_shape")

        result = _run(shop, schedule)
        assert result["success"], result

        for day in range(1, DAYS_IN_MONTH + 1):
            assignments = [schedule.get_day(e, day) for e in employees]
            is_weekend = shop.weekday(day) >= 5

            if is_weekend:
                full_day = [a for a in assignments if a.is_full_day]
                half_a = [a for a in assignments if not a.is_full_day and a.start == "06:00" and a.end == "18:00"]
                half_b = [a for a in assignments if not a.is_full_day and a.start == "18:00" and a.end == "06:00"]
                assert (len(full_day) == 1) != (len(half_a) == 1 == len(half_b)), f"day {day} weekend coverage broken"
            else:
                long_shift = [a for a in assignments if not a.is_full_day and a.start == "09:00" and a.end == "17:00"]
                short_shift = [a for a in assignments if not a.is_full_day and a.start == "17:00" and a.end == "09:00"]
                assert len(long_shift) == 1, f"day {day}: weekday_long coverage = {len(long_shift)}"
                assert len(short_shift) == 1, f"day {day}: weekday_short coverage = {len(short_shift)}"

        # Spot-check minut: jedna zmiana 09:00-17:00 to dokładnie 8h, jedna
        # 17:00-09:00 to dokładnie 16h - niezależnie od tego, kto ją dostał.
        for emp in employees:
            for day in range(1, DAYS_IN_MONTH + 1):
                if shop.weekday(day) >= 5:
                    continue
                ds = schedule.get_day(emp, day)
                if ds.start == "09:00" and ds.end == "17:00":
                    assert ds.total_duration().total_seconds() / 60 == 8 * 60
                elif ds.start == "17:00" and ds.end == "09:00":
                    assert ds.total_duration().total_seconds() / 60 == 16 * 60
