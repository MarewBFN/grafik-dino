"""Kwalifikacje liczone na konkretny dzień (Krok 1.2 migracji na
Qualification): data ważności (valid_from/valid_to) i placówki
(location_ids) decydują, czy pracownik liczy się do roli TEGO dnia - w
generatorze, kolorowaniu siatki (model/constraints.py), diagnostyce i
sztywnym wzorcu kierowniczki."""

import contextlib
import dataclasses
import io
from datetime import date

from model.qualification import (
    MEAT_LEVEL_FULL,
    MEAT_LEVEL_LIGHT,
    QUAL_MANAGER,
    QUAL_MEAT,
    QUAL_NO_24H,
    QUAL_OPENER,
    EmployeeQualification,
    can_work_24h_in_month,
    held_in_month,
    is_full_meat_on,
    is_light_meat_on,
    is_opener_on,
    refuses_24h_on,
)


def _replace_qualifications(schedule, emp, *qualifications):
    new = dataclasses.replace(emp, qualifications=tuple(qualifications))
    schedule.replace_employee(emp, new)
    return new


# ---------------------------------------------------------------------------
# Funkcje "w danym dniu"
# ---------------------------------------------------------------------------

def test_day_helpers_respect_dates_location_and_meat_levels():
    from model.employee import Employee

    emp = Employee("A", "B", location_key="sklep", qualifications=(
        EmployeeQualification(QUAL_OPENER, valid_from=date(2026, 10, 5)),
        EmployeeQualification(QUAL_MEAT, MEAT_LEVEL_LIGHT, location_ids=("inny",)),
        EmployeeQualification(QUAL_NO_24H, valid_to=date(2026, 10, 1)),
    ))
    assert not is_opener_on(emp, 2026, 10, 4)
    assert is_opener_on(emp, 2026, 10, 5)
    # Mięso obowiązuje tylko w placówce "inny" - pracownik jest w "sklep".
    assert not is_light_meat_on(emp, 2026, 10, 10)
    assert not is_full_meat_on(emp, 2026, 10, 10)
    assert refuses_24h_on(emp, 2026, 10, 1)
    assert not refuses_24h_on(emp, 2026, 10, 2)
    assert held_in_month(emp, QUAL_NO_24H, 2026, 10)
    assert not held_in_month(emp, QUAL_NO_24H, 2026, 11)
    # Nie chce 24h tylko 1. dnia - w pozostałe dni zdolny do 24h.
    assert can_work_24h_in_month(emp, 2026, 10)

    always = Employee("C", "D", qualifications=(EmployeeQualification(QUAL_NO_24H),))
    assert not can_work_24h_in_month(always, 2026, 10)

    full = Employee("E", "F", qualifications=(EmployeeQualification(QUAL_MEAT, MEAT_LEVEL_FULL),))
    assert is_full_meat_on(full, 2026, 10, 1) and not is_light_meat_on(full, 2026, 10, 1)


# ---------------------------------------------------------------------------
# Generator (end-to-end przez ScheduleController, jak przycisk "Generuj")
# ---------------------------------------------------------------------------

def _two_opener_dino_case():
    """Dino, obsada otwarcia/zamknięcia = 2 (Wymagane: każda z tych zmian ma
    mieć osobę z Otwarciem), dokładnie 2 osoby z Otwarciem - każdego dnia
    jedna otwiera, druga zamyka."""
    from tests.generator_audit_harness import build_case

    spec = {
        "name": "validity", "profile": "dino", "year": 2026, "month": 10,
        "locations": [{"key": "glowna", "open_hours": ("06:00", "22:00")}],
        "constraints": {"min_open_staff": 2, "min_close_staff": 2},
        "employees": [
            {"name": "OtwA", "opener": True, "meat": True},
            {"name": "OtwB", "opener": True, "meat": True},
            *({"name": f"M{i}", "meat": True} for i in range(4)),
        ],
    }
    return build_case(spec)


def _generate(schedule, shop, time_limit=20):
    from logic.schedule_controller import ScheduleController

    shop.constraints["solver_time_limit_seconds"] = time_limit
    controller = ScheduleController(schedule, shop)
    with contextlib.redirect_stdout(io.StringIO()):
        return controller.generate_schedule(force=True)


def test_generator_succeeds_with_both_openers_valid():
    schedule, shop = _two_opener_dino_case()
    assert _generate(schedule, shop)["success"]


def test_generator_stops_counting_expired_opener_qualification():
    schedule, shop = _two_opener_dino_case()
    opener_a = next(e for e in schedule.employees if e.last_name == "OtwA")
    _replace_qualifications(
        schedule, opener_a,
        EmployeeQualification(QUAL_OPENER, valid_to=date(2026, 10, 10)),
        EmployeeQualification(QUAL_MEAT, MEAT_LEVEL_FULL),
    )
    # Od 11.10 tylko jedna osoba z Otwarciem - nie obsadzi i otwarcia, i
    # zamknięcia (jedna zmiana dziennie), więc Wymagana obsada jest niespełnialna.
    assert not _generate(schedule, shop)["success"]


def test_generator_ignores_opener_qualification_restricted_to_other_location():
    schedule, shop = _two_opener_dino_case()
    opener_a = next(e for e in schedule.employees if e.last_name == "OtwA")
    _replace_qualifications(
        schedule, opener_a,
        EmployeeQualification(QUAL_OPENER, location_ids=("inna_placowka",)),
        EmployeeQualification(QUAL_MEAT, MEAT_LEVEL_FULL),
    )
    assert not _generate(schedule, shop)["success"]


def test_generator_counts_opener_qualification_valid_in_own_location():
    schedule, shop = _two_opener_dino_case()
    opener_a = next(e for e in schedule.employees if e.last_name == "OtwA")
    _replace_qualifications(
        schedule, opener_a,
        EmployeeQualification(QUAL_OPENER, location_ids=(opener_a.location_key,)),
        EmployeeQualification(QUAL_MEAT, MEAT_LEVEL_FULL),
    )
    assert _generate(schedule, shop)["success"]


# ---------------------------------------------------------------------------
# Kolorowanie siatki i diagnostyka
# ---------------------------------------------------------------------------

def test_grid_validation_counts_opener_only_while_valid():
    from model.constraints import opening_closing_stats

    schedule, shop = _two_opener_dino_case()
    emp = next(e for e in schedule.employees if e.last_name == "OtwA")
    emp = _replace_qualifications(schedule, emp, EmployeeQualification(QUAL_OPENER, valid_to=date(2026, 10, 10)))
    # Walidacja siatki czyta godziny otwarcia placówki pracownika (jak
    # generator). 9.10 - piątek (ważna), 12.10 - poniedziałek (po dacie ważności).
    for day in (9, 12):
        schedule.get_day(emp, day).set_hours(shop.get_location(emp).get_open_hours_for_day(day)[0], "14:30")

    assert opening_closing_stats(schedule, shop, 9, "open")["has_opener"]
    assert not opening_closing_stats(schedule, shop, 12, "open")["has_opener"]


def test_grid_uses_location_hours_not_project_hours():
    """Godziny edytowane per placówka (nowe okno Konfiguracji) trafiają tylko
    do LocationConfig - siatka ma liczyć otwarcie wg nich, jak generator."""
    from model.constraints import opening_closing_stats

    schedule, shop = _two_opener_dino_case()
    emp = next(e for e in schedule.employees if e.last_name == "OtwA")
    location_open = shop.get_location(emp).get_open_hours_for_day(9)[0]
    assert location_open != shop.get_open_hours_for_day(9)[0]  # przypadek z błędu
    schedule.get_day(emp, 9).set_hours(location_open, "14:30")
    assert opening_closing_stats(schedule, shop, 9, "open")["count"] == 1


def test_grid_meat_coverage_uses_level_valid_that_day():
    from model.constraints import meat_coverage

    schedule, shop = _two_opener_dino_case()
    for emp in list(schedule.employees):
        _replace_qualifications(schedule, emp)  # nikt nie ma mięsa ...
    emp = schedule.employees[0]
    emp = _replace_qualifications(  # ... poza jedną osobą, do 10.10
        schedule, emp, EmployeeQualification(QUAL_MEAT, MEAT_LEVEL_FULL, valid_to=date(2026, 10, 10)),
    )
    for day in (9, 12):
        schedule.get_day(emp, day).set_hours(*shop.get_location(emp).get_open_hours_for_day(day))

    assert meat_coverage(schedule, shop, 9)["ok"]
    assert not meat_coverage(schedule, shop, 12)["ok"]


def test_preflight_supply_counts_qualifications_per_day():
    from logic.generator.diagnostics import preflight_supply

    schedule, shop = _two_opener_dino_case()
    emp = next(e for e in schedule.employees if e.last_name == "OtwA")
    _replace_qualifications(schedule, emp, EmployeeQualification(QUAL_OPENER, valid_to=date(2026, 10, 10)))

    by_day = {row["day"]: row for row in preflight_supply(schedule, shop)}
    assert by_day[9]["available_openers"] == 2
    assert by_day[12]["available_openers"] == 1


# ---------------------------------------------------------------------------
# Kierowniczka
# ---------------------------------------------------------------------------

def test_manager_pattern_applies_only_while_qualification_is_valid():
    from logic.manager_schedule import apply_all_manager_schedules
    from model.employee import Employee
    from model.month_schedule import MonthSchedule
    from model.shop_config import DEFAULT_LOCATION_KEY, ShopConfig

    shop = ShopConfig(2026, 10)
    emp = Employee(
        "Kierowniczka", "", location_key=DEFAULT_LOCATION_KEY,
        qualifications=(EmployeeQualification(QUAL_MANAGER, valid_to=date(2026, 10, 15)),),
    )
    schedule = MonthSchedule(2026, 10, employees=[emp])

    apply_all_manager_schedules(schedule, shop)

    # 2026-10-13 i 2026-10-20 to wtorki (wzorzec 07:00-15:00).
    assert (schedule.get_day(emp, 13).start, schedule.get_day(emp, 13).end) == ("07:00", "15:00")
    assert schedule.get_day(emp, 20).is_blank()


# ---------------------------------------------------------------------------
# Ochrona: "Nie chce 24h" na konkretny dzień
# ---------------------------------------------------------------------------

def test_no24h_gate_only_on_days_when_qualification_is_valid():
    from ortools.sat.python import cp_model

    from logic.generator.duty_rotation_constraint import add_duty_rotation_no24h_gate_constraint
    from model.employee import Employee
    from model.shop_config import ShopConfig

    shop = ShopConfig(2026, 10)
    emp = Employee("Straż", "", qualifications=(
        EmployeeQualification(QUAL_NO_24H, valid_from=date(2026, 10, 10), valid_to=date(2026, 10, 12)),
    ))
    model = cp_model.CpModel()
    full = 17
    days = list(range(1, 32))
    x = {(0, d, full): model.NewBoolVar(f"x{d}") for d in days}

    violations = add_duty_rotation_no24h_gate_constraint(
        model, x, [emp], days, shop, {"weekend_full": full}, soft=True,
    )

    # 2026-10-10 i 11 to sobota i niedziela; 12 - poniedziałek (bez zakazu);
    # weekendy 3-4, 17-18, 24-25, 31 - poza ważnością.
    assert len(violations) == 2
