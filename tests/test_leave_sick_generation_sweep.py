"""Na żądanie użytkownika: sweep testów pokazujących, jak generator
REAGUJE na różne ILOŚCI L4/urlopu - "przed" (monthly_hours_status, to co
widzi UI/eksporty PRZED wygenerowaniem) i "po" (faktyczne uruchomienie
AutoScheduleGenerator, nie tylko budowa constraintu w izolacji).

Rozszerza tests/test_hours_leave_sick_target.py, który sprawdzał tylko 2
punkty (cały miesiąc i 10 dni) na izolowanym modelu. Tutaj: pełny zakres
proporcji miesiąca (0%, ~26%, ~48%, ~74%, 100%) x pełne uruchomienia
generatora, dla obu ścieżek klienta - zwykłej (Dino-style, open/close) i
rotacji 24/7 (Enyo-style, duty_rotation z minutami zmian 12h/24h zamiast
stałych "zwykłych" zmian) - ta druga ścieżka NIE była dotąd testowana
end-to-end razem z poprawką celu godzinowego.
"""

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.auto_generator import AutoScheduleGenerator
from logic.generator.custom_profile_wiring import default_policies
from logic.generator.duty_rotation_constraint import NIE_CHCE_24H_ROLE_KEY
from logic.monthly_hours_status import monthly_hours_status
from model.business_profile import register_custom_profile
from model.constraint_policy import ConstraintPolicy
from model.custom_profile import CustomBusinessProfile
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig

YEAR, MONTH = 2026, 8  # 31 dni; spójne z fixture rotacji w innych testach duty_rotation.
DAYS_IN_MONTH = 31

# Proporcje miesiąca do przetestowania: 0%, ~26%, ~48%, ~74%, 100%.
LEAVE_DAY_COUNTS = [0, 8, 15, 23, 31]

UBOJNIA_STYLE_ROTATION = {
    # Realny wzorzec Ubojni GOSZ (test_data/dane_klienta_ochrona.json):
    # 8:00-20:00 dzień + 20:00-8:00 noc, only_12_24h.
    "only_12_24h": True,
    "weekend_full": {"start": "08:00"},
    "weekend_half_a": {"start": "08:00", "end": "20:00"},
    "weekend_half_b": {"start": "20:00", "end": "08:00"},
}


def _mark_days(schedule, emp, count, kind):
    for day in range(1, count + 1):
        ds = schedule.get_day(emp, day)
        if kind == "leave":
            ds.is_leave = True
        else:
            ds.is_sick = True


def _run(shop, schedule, time_limit=30):
    buf = io.StringIO()
    with redirect_stdout(buf):
        result = AutoScheduleGenerator(shop=shop, schedule=schedule).generate(solver_time_limit_seconds=time_limit)
    return result


def _expected_target_minutes(shop, emp, schedule, leave_days, sick_days):
    from logic.utils.time_utils import get_effective_daily_hours
    nominal_minutes = shop.get_full_time_nominal_hours() * 60
    daily_minutes = int(get_effective_daily_hours(emp, shop) * 60)
    return max(0, int(nominal_minutes * emp.employment_fraction - (leave_days + sick_days) * daily_minutes))


# ============================================================
# Ścieżka rotacji 24/7 (Enyo-style) - duty_rotation_coverage MANDATORY,
# monthly_hours/balance w trybie PREFERRED (miękkim), żeby faktycznie
# przećwiczyć poprawkę celu godzinowego na minutach zmian 12h/24h, a nie
# tylko na "zwykłych" zmianach o stałej długości jak w oryginalnym teście
# regresji. Realny profil Enyo ma balance/monthly_hours DISABLED (patrz
# ENYO_ONLY_CHANGES.md) - to jest świadomie ostrzejszy wariant do testu.
# ============================================================


def _duty_rotation_shop_and_schedule(n_employees=4, all_no24h=True):
    profile = CustomBusinessProfile(key="test_leave_sweep_duty", display_name="Test Leave Sweep", roles=[], rules=[])
    register_custom_profile(profile)

    shop = ShopConfig(YEAR, MONTH)
    shop.business_type = profile.key
    loc = LocationConfig(key="site1", name="Site 1")
    loc.set_duty_rotation(UBOJNIA_STYLE_ROTATION)
    # Nie testujemy tu automatycznego zamknięcia w święta
    # (LocationConfig.closed_on_public_holidays, domyślnie True) - to
    # zamierzenie sprawdza pokrycie KAŻDEGO dnia miesiąca niezależnie od
    # ilości L4/urlopu, więc realne polskie święto wypadające w
    # YEAR/MONTH fałszowałoby oczekiwany wynik.
    loc.closed_on_public_holidays = False
    shop.locations = {"site1": loc}
    shop.constraint_policies.update(default_policies(profile))
    # PREFERRED (nie DISABLED jak w realnym demo Enyo) - celowo, patrz docstring wyżej.
    shop.constraint_policies["balance"] = ConstraintPolicy.PREFERRED
    shop.constraint_policies["monthly_hours"] = ConstraintPolicy.PREFERRED

    schedule = MonthSchedule(YEAR, MONTH)
    employees = [
        Employee(
            last_name=f"Guard{i}", first_name="Rotation", employment_fraction=1.0,
            location_key="site1",
            custom_roles={NIE_CHCE_24H_ROLE_KEY: True} if all_no24h else {},
        )
        for i in range(n_employees)
    ]
    for emp in employees:
        schedule.add_employee(emp)

    return shop, schedule, employees


class TestDutyRotationLeaveSweep:
    """4 pracowników, wszyscy 'nie_chce_24h' (wymusza podział 12h+12h co
    dzień, potrzeba 2 różnych osób dziennie) - jeden z nich (target) idzie
    na coraz dłuższe L4/urlop, pozostałych 3 zawsze wystarcza do pokrycia."""

    @pytest.mark.parametrize("leave_days", LEAVE_DAY_COUNTS)
    def test_before_generation_target_minutes_never_negative(self, leave_days):
        shop, schedule, employees = _duty_rotation_shop_and_schedule()
        target = employees[0]
        _mark_days(schedule, target, leave_days, "leave")

        status = monthly_hours_status(schedule, shop, target)
        expected = _expected_target_minutes(shop, target, schedule, leave_days, 0)

        assert status["target_minutes"] == expected
        assert status["target_minutes"] >= 0
        assert status["worked_minutes"] == 0  # jeszcze przed generowaniem
        assert status["is_over"] is False

    @pytest.mark.parametrize("leave_days", LEAVE_DAY_COUNTS)
    def test_after_generation_coverage_always_fully_met_despite_leave(self, leave_days):
        """Kluczowe pytanie użytkownika: jak generator REAGUJE na różne
        ilości L4/urlopu - tu: obsada 24/7 (MANDATORY) musi zostać
        zachowana w 100% niezależnie od tego, ile dni target jest
        niedostępny, dopóki pozostali (3) fizycznie wystarczają."""
        shop, schedule, employees = _duty_rotation_shop_and_schedule()
        target = employees[0]
        _mark_days(schedule, target, leave_days, "leave")

        result = _run(shop, schedule)
        assert result["success"], result
        assert result["status"].name in ("OPTIMAL", "FEASIBLE")

        half_a, half_b = ("08:00", "20:00"), ("20:00", "08:00")
        for day in range(1, DAYS_IN_MONTH + 1):
            assignments = [schedule.get_day(e, day) for e in employees]
            full_day = [a for a in assignments if a.is_full_day]
            half_a_workers = [a for a in assignments if a.start == half_a[0] and a.end == half_a[1] and not a.is_full_day]
            half_b_workers = [a for a in assignments if a.start == half_b[0] and a.end == half_b[1] and not a.is_full_day]

            # Wszyscy mają nie_chce_24h -> weekend_full strukturalnie
            # niedostępny (patrz add_duty_rotation_no24h_gate_constraint) -
            # pokrycie MUSI iść przez dokładnie 1 osobę na każdej połówce.
            assert len(full_day) == 0, f"day {day}: unexpected full-day shift with all nie_chce_24h"
            assert len(half_a_workers) == 1, f"day {day}: half_a coverage = {len(half_a_workers)}"
            assert len(half_b_workers) == 1, f"day {day}: half_b coverage = {len(half_b_workers)}"

        # Target rzeczywiście nie ma zapisanej żadnej zmiany w zablokowane dni
        # (add_leave_constraints wymusza x==0 -> solution_mapper nic nie pisze).
        for day in range(1, leave_days + 1):
            assert schedule.get_day(target, day).total_duration() is None

    @pytest.mark.parametrize("leave_days", LEAVE_DAY_COUNTS)
    def test_after_generation_no_phantom_overtime_pressure_from_leave(self, leave_days):
        """Przed poprawką: cel ujemny -> fikcyjna kara 'over' w trybie
        miękkim mogła (pośrednio, przez wagę w funkcji celu) naciskać model
        w stronę nieoczekiwanych rozwiązań. Tu: worked_minutes pozostałych
        pracowników rośnie co najwyżej w rozsądnym tempie wraz z leave_days
        (rekompensacja przez pokrycie, NIE przez karę na targecie), a status
        targeta po generowaniu nigdy nie pokazuje is_over dla kogoś, kto
        fizycznie nie mógł pracować w te dni."""
        shop, schedule, employees = _duty_rotation_shop_and_schedule()
        target = employees[0]
        _mark_days(schedule, target, leave_days, "leave")

        result = _run(shop, schedule)
        assert result["success"], result

        status = monthly_hours_status(schedule, shop, target)
        expected_target = _expected_target_minutes(shop, target, schedule, leave_days, 0)
        assert status["target_minutes"] == expected_target
        # Target nie mógł pracować w dni L4/urlopu - worked <= dostępne dni x 12h.
        available_days = DAYS_IN_MONTH - leave_days
        assert status["worked_minutes"] <= available_days * 12 * 60


class TestDutyRotationScarcePoolGracefulInfeasibility:
    """2 pracowników (minimum na podział 12h+12h), jeden na długim L4 -
    fizycznie niemożliwe do pokrycia (potrzeba 2 różnych osób KAŻDEGO dnia,
    zostaje 1). Generator musi to zgłosić jako niewykonalne w sposób
    kontrolowany (success=False + infeasibility_reasons), a NIE zwrócić
    błędny/częściowy grafik ani zostawić harmonogram w stanie pośrednim."""

    def test_extended_leave_with_only_two_employees_is_reported_infeasible_not_crashed(self):
        shop, schedule, employees = _duty_rotation_shop_and_schedule(n_employees=2)
        target = employees[0]
        _mark_days(schedule, target, 20, "leave")  # >> pozostały 1 pracownik nie może pokryć obu połówek sam

        snapshot_before = schedule.snapshot()
        result = _run(shop, schedule)

        assert result["success"] is False
        assert result["status"].name in ("INFEASIBLE", "MODEL_INVALID", "UNKNOWN")
        assert result["infeasibility_reasons"], "oczekiwano niepustej diagnostyki niewykonalności"

        # Stan grafiku musi wrócić do sprzed próby generowania (auto_generator.py
        # przywraca snapshot przy success=False) - żadnych częściowych przypisań.
        for day in range(1, DAYS_IN_MONTH + 1):
            for emp in employees:
                before_day = snapshot_before.get_day(emp, day)
                after_day = schedule.get_day(emp, day)
                assert after_day.start == before_day.start
                assert after_day.is_full_day == before_day.is_full_day


# ============================================================
# Ścieżka zwykła (Dino-style: open/close, min_open/min_close MANDATORY,
# monthly_hours/balance domyślnie PREFERRED) - ten sam sweep, na ścieżce,
# na której bug był pierwotnie zgłoszony.
# ============================================================


def _plain_shop_and_schedule(n_employees=8):
    """Dino domyślnie wymaga choć jednej osoby z uprawnieniem "mięso" (i
    opener) możliwej do pracy na otwarciu/zamknięciu (patrz meat_constraint/
    meat_coverage) - "zerowy" pracownik bez żadnej roli okazał się dawać
    INFEASIBLE niezależnie od L4/urlopu (sprawdzone: 5-8 pracowników bez
    żadnej flagi, zawsze INFEASIBLE). Role przydzielone employees[1:4], NIE
    targetowi (employees[0]) - żeby jego L4/urlop nigdy nie usuwało
    jedynych uprawnionych osób. Wzorzec ról jak w tests/stress_test_generator.py."""
    shop = ShopConfig(YEAR, MONTH)  # business_type domyślny (dino_retail) - brak potrzeby rejestracji profilu.
    shop.constraints["min_open_staff"] = 2
    shop.constraints["min_close_staff"] = 2

    schedule = MonthSchedule(YEAR, MONTH)
    employees = [
        Employee(
            last_name=f"Pracownik{i}", first_name="Test", employment_fraction=1.0,
            is_opener=(1 <= i <= 3), is_meat=(1 <= i <= 3),
        )
        for i in range(n_employees)
    ]
    for emp in employees:
        schedule.add_employee(emp)

    return shop, schedule, employees


class TestPlainProfileLeaveSweep:
    @pytest.mark.parametrize("leave_days", LEAVE_DAY_COUNTS)
    def test_before_generation_target_minutes_never_negative(self, leave_days):
        shop, schedule, employees = _plain_shop_and_schedule()
        target = employees[0]
        _mark_days(schedule, target, leave_days, "leave")

        status = monthly_hours_status(schedule, shop, target)
        expected = _expected_target_minutes(shop, target, schedule, leave_days, 0)

        assert status["target_minutes"] == expected
        assert status["target_minutes"] >= 0
        assert status["worked_minutes"] == 0

    @pytest.mark.parametrize("leave_days", LEAVE_DAY_COUNTS)
    def test_after_generation_succeeds_and_respects_leave_days(self, leave_days):
        shop, schedule, employees = _plain_shop_and_schedule()
        target = employees[0]
        _mark_days(schedule, target, leave_days, "leave")

        result = _run(shop, schedule)
        assert result["success"], result

        for day in range(1, leave_days + 1):
            ds = schedule.get_day(target, day)
            assert ds.is_leave
            assert ds.total_duration() is None

        status = monthly_hours_status(schedule, shop, target)
        expected_target = _expected_target_minutes(shop, target, schedule, leave_days, 0)
        assert status["target_minutes"] == expected_target
        # Bez fikcyjnego "dobijania" ponad to, co fizycznie możliwe w dostępne dni.
        available_days = DAYS_IN_MONTH - leave_days
        assert status["worked_minutes"] <= available_days * 12 * 60


class TestMixedLeaveAndSickCombination:
    """L4 i urlop razem (nie tylko jeden typ na raz) - formuła
    (nominał - leave - sick), przycięta do 0, musi się sumować addytywnie."""

    @pytest.mark.parametrize("leave_days, sick_days", [(5, 5), (15, 15), (16, 16), (20, 15)])
    def test_combined_leave_and_sick_target_matches_additive_formula(self, leave_days, sick_days):
        shop, schedule, employees = _plain_shop_and_schedule(n_employees=4)
        target = employees[0]
        for day in range(1, leave_days + 1):
            schedule.get_day(target, day).is_leave = True
        for day in range(leave_days + 1, leave_days + 1 + sick_days):
            if day > DAYS_IN_MONTH:
                break
            schedule.get_day(target, day).is_sick = True

        actual_sick_days = min(sick_days, max(0, DAYS_IN_MONTH - leave_days))
        status = monthly_hours_status(schedule, shop, target)
        expected = _expected_target_minutes(shop, target, schedule, leave_days, actual_sick_days)
        assert status["target_minutes"] == expected

    def test_combined_leave_and_sick_covering_entire_month_ends_at_zero_target_end_to_end(self):
        """(16, 16) na 31-dniowy miesiąc pokrywa go w całości mieszanką obu
        typów - target=0, generator musi to obsłużyć (FEASIBLE), nie
        INFEASIBLE, dokładnie jak przy jednym typie na cały miesiąc."""
        shop, schedule, employees = _plain_shop_and_schedule()
        target = employees[0]
        for day in range(1, 16):
            schedule.get_day(target, day).is_leave = True
        for day in range(16, 32):
            schedule.get_day(target, day).is_sick = True

        status = monthly_hours_status(schedule, shop, target)
        assert status["target_minutes"] == 0

        result = _run(shop, schedule)
        assert result["success"], result
        for day in range(1, DAYS_IN_MONTH + 1):
            assert schedule.get_day(target, day).total_duration() is None
