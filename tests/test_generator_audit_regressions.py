"""Testy regresyjne błędów znalezionych w audycie generatora przed wydaniem
(tests/generator_audit_harness.py + niezależny walidator
tests/schedule_validator.py).

Każdy test buduje konfigurację dokładnie tak jak GUI, uruchamia prawdziwy
generator (ScheduleController.generate_schedule, jak przycisk "Generuj
grafik") i sprawdza RZECZYWISTY wynik walidatorem niezależnym od kodu
generatora - nie sam status solvera.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.generator_audit_harness import run_case


def _hard_rules(outcome):
    return sorted({v.rule for v in outcome["eval"]["hard"]})


def test_small_24_7_location_is_not_infeasible_because_of_balance_domain():
    """2 osoby na placówce 24/7 muszą przepracować ok. 372 h w miesiącu.
    Zmienna sumy minut w add_balance_constraint miała sztywny zakres 0-20000
    min (333 h), więc sam zakres zmiennej robił model niewykonalnym - mimo
    że "Bilans godzin" jest tylko Preferowany (domyślnie dla Ochrony), a
    klient dostawał komunikat o sprzecznych zasadach Wymaganych."""
    outcome = run_case({
        "name": "balance_domain_2_guards",
        "profile": "ochrona",
        "year": 2026, "month": 10,
        "locations": [{"key": "o", "duty": ("08:00", "20:00", False)}],
        "employees": [dict(location="o"), dict(location="o")],
    }, time_limit=10)

    assert outcome["success"], outcome["reasons"]
    assert _hard_rules(outcome) == []
    assert outcome["report"].metrics["duty_coverage"]["o"] == {
        "gap_slots": 0, "double_slots": 0, "manual_double_slots": 0,
    }


# ---------------------------------------------------------------------------
# Profil Ochrona - placówki BEZ rotacji 24/7 ("model godzin otwarcia",
# decyzja użytkownika 2026-09-28: pakiet pełnego obłożenia)
# ---------------------------------------------------------------------------

def _ochrona_regular(name, hours, n, **extra):
    spec = {
        "name": name,
        "profile": "ochrona",
        "year": 2026, "month": 10,
        "locations": [{"key": "p", "open_hours": hours}],
        "employees": [dict(location="p") for _ in range(n)],
    }
    spec.update(extra)
    return spec


def _shift_intervals(outcome):
    from tests.schedule_validator import cell_interval

    schedule = outcome["schedule"]
    rows = []
    for emp in schedule.employees:
        for day in range(1, schedule.days_in_month + 1):
            iv = cell_interval(schedule.get_day(emp, day), day)
            if iv:
                rows.append((emp.last_name, day, iv))
    return rows


def test_ochrona_store_closing_at_2245_gets_no_rigid_night_shift_and_full_coverage():
    """Wcześniej: placówka 05:30-22:45 dostawała sztywną nockę 22:00-06:00
    (ok. 7 h po zamknięciu) i nie miała żadnej reguły obsady."""
    outcome = run_case(_ochrona_regular("och_no_night", ("05:30", "22:45"), 5), time_limit=15)

    assert outcome["success"], outcome["reasons"]
    assert _hard_rules(outcome) == []
    assert not outcome["report"].by_rule("opening_hours_coverage")
    for _name, _day, (start, end) in _shift_intervals(outcome):
        assert (start % 1440) >= 5 * 60 + 30 and end - (start - start % 1440) <= 22 * 60 + 45


def test_ochrona_short_day_offset_shifts_stay_inside_opening_hours():
    """10:00-18:00 przy zmianie 8,5 h (istniejący projekt z "8h 30 min"):
    wcześniej np. 10:45-19:15 albo 09:00-17:30. Teraz warianty przesunięte
    muszą się mieścić; OPEN/CLOSE zostają (zmiana dłuższa niż dzień)."""
    outcome = run_case(
        _ochrona_regular("och_short", ("10:00", "18:00"), 4, constraints={"force_fulltime_845": True}),
        time_limit=15,
    )

    assert outcome["success"], outcome["reasons"]
    for name, day, (start, end) in _shift_intervals(outcome):
        base = (day - 1) * 1440
        assert (start, end) in ((base + 600, base + 1110), (base + 570, base + 1080)), (name, day, start, end)
    assert not outcome["report"].by_rule("opening_hours_coverage")


def test_ochrona_full_day_is_split_into_consecutive_shifts_from_midnight():
    """Weekend 00:00-23:45 (doba), tydzień 08:00-16:00: doba dzielona na
    00-08, 08-16, 16-24; pełne obłożenie całego miesiąca."""
    hours = {wd: ("08:00", "16:00") for wd in range(5)}
    hours.update({5: ("00:00", "23:45"), 6: ("00:00", "23:45")})
    outcome = run_case(_ochrona_regular("och_mixed_doba", hours, 7), time_limit=20)

    assert outcome["success"], outcome["reasons"]
    assert _hard_rules(outcome) == []
    assert not outcome["report"].by_rule("opening_hours_coverage")
    import calendar
    for name, day, (start, end) in _shift_intervals(outcome):
        base = (day - 1) * 1440
        if calendar.weekday(2026, 10, day) >= 5:
            assert (start - base, end - base) in ((0, 480), (480, 960), (960, 1440)), (name, day)
        else:
            assert (start - base, end - base) == (480, 960), (name, day)


def test_ochrona_unmatched_manual_shift_counts_for_rest_and_coverage():
    """Ręczny wpis 14:00-23:00 (nie pasuje do żadnego wzorca przy 06:00-23:00)
    był dla generatora niewidoczny: następnego dnia ta sama osoba mogła
    dostać zmianę od 06:00 (7 h odpoczynku przy Wymaganym 11 h)."""
    cells = [(0, d, "hours", "14:00", "23:00") for d in range(2, 30, 3)]
    outcome = run_case(_ochrona_regular("och_manual_rest", ("06:00", "23:00"), 4, cells=cells), time_limit=15)

    assert outcome["success"], outcome["reasons"]
    assert _hard_rules(outcome) == []
    assert not outcome["report"].by_rule("rest_11h")


def test_ochrona_opening_hours_coverage_policy_modes_change_the_result():
    """MANDATORY: pełne obłożenie (albo brak grafiku). DISABLED: generator
    przestaje go pilnować - przy 1 osobie na 16 h dziennie zostają luki."""
    base = _ochrona_regular("och_cov", ("06:00", "22:00"), 1)

    mandatory = run_case(dict(base, name="och_cov_m"), time_limit=10)
    assert not mandatory["success"]  # 1 osoba nie pokryje 16 h każdego dnia

    disabled = run_case(dict(base, name="och_cov_d", policies={"opening_hours_coverage": "DISABLED"}), time_limit=10)
    assert disabled["success"], disabled["reasons"]
    assert disabled["report"].by_rule("opening_hours_coverage")  # luki są, ale nie łamią zasad
    assert "opening_hours_coverage" not in _hard_rules(disabled)


def test_ochrona_coverage_diagnostics_names_the_day_nobody_can_work():
    cells = [(i, 12, "leave") for i in range(2)]
    outcome = run_case(_ochrona_regular("och_cov_diag", ("08:00", "16:00"), 2, cells=cells), time_limit=10)

    assert not outcome["success"]
    assert any("dzień 12" in r and "Obłożenie godzin otwarcia" in r for r in outcome["reasons"]), outcome["reasons"]
    # nieudane generowanie nie zmienia grafiku
    assert not outcome["report"].violations


# ---------------------------------------------------------------------------
# Komunikat przy limicie czasu (status UNKNOWN != sprzeczne zasady)
# ---------------------------------------------------------------------------

def test_solver_timeout_is_not_reported_as_contradictory_rules(monkeypatch):
    import io
    from contextlib import redirect_stdout

    from ortools.sat.python import cp_model

    import logic.auto_generator as auto_generator
    from tests.generator_audit_harness import build_case

    def fake_solve(model, time_limit_seconds=60, num_search_workers=1):
        # Prawdziwy solver (statystyki NumConflicts itd. muszą działać), ale
        # wynik jak po upływie limitu czasu bez żadnego rozwiązania.
        solver = cp_model.CpSolver()
        solver.Solve(cp_model.CpModel())
        return solver, cp_model.UNKNOWN

    monkeypatch.setattr(auto_generator, "solve_model", fake_solve)
    schedule, shop = build_case({
        "profile": "dino",
        "locations": [{"key": "glowna", "open_hours": ("06:00", "22:00")}],
        "employees": [dict(opener=True, meat=True) for _ in range(8)],
    })
    shop.constraints["solver_time_limit_seconds"] = 42
    with redirect_stdout(io.StringIO()):
        result = auto_generator.AutoScheduleGenerator(schedule, shop).generate(solver_time_limit_seconds=42)

    assert not result["success"]
    assert any("limicie czasu (42 s)" in r for r in result["infeasibility_reasons"]), result["infeasibility_reasons"]
    assert not any("sprzeczne" in r for r in result["infeasibility_reasons"])


# ---------------------------------------------------------------------------
# Nowy projekt Ochrony: zmiana 8 h (decyzja użytkownika), Dino bez zmian
# ---------------------------------------------------------------------------

def test_new_ochrona_project_defaults_to_8h_shifts_and_mandatory_coverage():
    from logic.generator.custom_profile_wiring import apply_new_project_defaults
    from model.business_profile import DEFAULT_OCHRONA_PROFILE_KEY, get_custom_profile
    from model.constraint_policy import ConstraintPolicy
    from model.shop_config import ShopConfig

    shop = ShopConfig(2026, 10)
    shop.business_type = DEFAULT_OCHRONA_PROFILE_KEY
    apply_new_project_defaults(shop, get_custom_profile(DEFAULT_OCHRONA_PROFILE_KEY))

    assert shop.constraints["force_fulltime_845"] is False
    assert shop.constraint_policies["opening_hours_coverage"] == ConstraintPolicy.MANDATORY
    # Dino-owy ShopConfig nadal startuje z "8h 30 min"
    assert ShopConfig(2026, 10).constraints["force_fulltime_845"] is True


def test_missing_opening_hours_coverage_policy_is_treated_as_mandatory():
    """Projekt zapisany przed dodaniem zasady nie ma jej wpisu - generator
    traktuje brak wpisu jak Wymaganą (to samo pokazuje Konfiguracja)."""
    spec = _ochrona_regular("och_cov_missing", ("06:00", "22:00"), 1)
    from tests.generator_audit_harness import build_case

    schedule, shop = build_case(spec)
    shop.constraint_policies.pop("opening_hours_coverage")
    assert "opening_hours_coverage" not in shop.constraint_policies

    import io
    from contextlib import redirect_stdout
    from logic.auto_generator import AutoScheduleGenerator

    with redirect_stdout(io.StringIO()):
        result = AutoScheduleGenerator(schedule, shop).generate(solver_time_limit_seconds=10)
    assert not result["success"]  # 1 osoba nie pokryje 16 h dziennie


def test_config_dialog_shows_opening_hours_coverage_rule_for_ochrona(monkeypatch):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    import ui.config_dialog as config_dialog
    from model.constraint_policy import ConstraintPolicy
    from tests.generator_audit_harness import build_case

    QApplication.instance() or QApplication([])
    schedule, shop = build_case(_ochrona_regular("gui", ("06:00", "22:00"), 1))
    shop.constraint_policies.pop("opening_hours_coverage")
    monkeypatch.setattr(config_dialog.ConfigDialog, "_maybe_show_tutorial", lambda self: None)

    dialog = config_dialog.ConfigDialog(None, shop, location_key="p")
    selector = dialog.policy_selectors["opening_hours_coverage"]
    assert selector.currentData() == ConstraintPolicy.MANDATORY

    selector.setCurrentIndex(selector.findData(ConstraintPolicy.PREFERRED))
    dialog._save()
    assert shop.constraint_policies["opening_hours_coverage"] == ConstraintPolicy.PREFERRED


# ---------------------------------------------------------------------------
# Profil Dino - znane błędy, TYLKO RAPORT (decyzja użytkownika 2026-09-28:
# na gałęzi Enyo nie zmieniamy zachowania constraintów Dino). Reproducery
# jako xfail(strict=True): gdy błąd zostanie naprawiony, test zacznie
# przechodzić i xfail trzeba będzie zdjąć. Szczegóły: GENERATOR_AUDIT.md.
# ---------------------------------------------------------------------------

import pytest  # noqa: E402

DINO_REPORT_ONLY = "Dino - tylko raport (GENERATOR_AUDIT.md), decyzja użytkownika 2026-09-28"


@pytest.mark.xfail(strict=True, reason=DINO_REPORT_ONLY)
def test_dino_min_open_close_is_enforced_per_location():
    """2 sklepy Dino, min. 3 na otwarciu/zamknięciu: generator liczy obsadę
    łącznie dla obu (np. A=0, B=3) zamiast osobno dla każdego sklepu."""
    team = [dict(opener=True, meat=True, location="A") for _ in range(6)] + \
           [dict(opener=True, meat=True, location="B") for _ in range(6)]
    outcome = run_case({
        "name": "dino_two_locations", "profile": "dino",
        "locations": [{"key": "A", "open_hours": ("06:00", "22:00")}, {"key": "B", "open_hours": ("06:00", "22:00")}],
        "policies": {"max_consecutive": "DISABLED"},
        "employees": team,
    }, time_limit=15)
    assert outcome["success"]
    assert not outcome["report"].by_rule("open") and not outcome["report"].by_rule("close")


@pytest.mark.xfail(strict=True, reason=DINO_REPORT_ONLY)
def test_dino_trade_sunday_selected_in_config_gets_staff():
    """Niedziela handlowa zaznaczona w Konfiguracji trafia tylko do
    ShopConfig.trade_sundays, a generator czyta LocationConfig.trade_sundays
    - wynik: 0 osób w tę niedzielę."""
    outcome = run_case({
        "name": "dino_trade_sunday", "profile": "dino", "trade_sundays": [11],
        "locations": [{"key": "glowna", "open_hours": ("06:00", "22:00")}],
        "employees": [dict(opener=True, meat=True) for _ in range(8)],
    }, time_limit=15)
    staffed = sum(1 for e in outcome["schedule"].employees if outcome["schedule"].get_day(e, 11).start)
    assert staffed >= 6


@pytest.mark.xfail(strict=True, reason=DINO_REPORT_ONLY)
def test_dino_store_closing_2245_gets_no_shift_after_closing():
    """Automatyczna nocka 22:00-06:00 dla sklepu czynnego do 22:45."""
    outcome = run_case({
        "name": "dino_auto_night", "profile": "dino",
        "employees": [dict(opener=i < 4, meat=i % 3 == 0) for i in range(10)],
    }, time_limit=10)
    assert not outcome["report"].by_rule("night_outside_hours")


@pytest.mark.xfail(strict=True, reason=DINO_REPORT_ONLY)
def test_dino_short_day_offset_shifts_stay_inside_opening_hours():
    """10:00-18:00 przy 8,5 h: zmiany typu 10:45-19:15 / 09:00-17:30."""
    outcome = run_case({
        "name": "dino_short_day", "profile": "dino",
        "locations": [{"key": "glowna", "open_hours": ("10:00", "18:00")}],
        "constraints": {"min_open_staff": 2, "min_close_staff": 2},
        "employees": [dict(opener=True, meat=True) for _ in range(8)],
    }, time_limit=10)
    assert not outcome["report"].by_rule("opening_hours")


@pytest.mark.xfail(strict=True, reason=DINO_REPORT_ONLY)
def test_dino_unmatched_manual_shift_is_respected_by_rest_11h():
    """Ręczna zmiana 13:00-21:00 nie pasuje do wzorców przy 06:00-22:30 i
    jest dla generatora niewidoczna: następnego dnia ta sama osoba dostaje
    zmianę od 06:00 (9 h odpoczynku przy Wymaganym 11 h)."""
    cells = [(0, d, "hours", "13:00", "21:00") for d in range(5, 20, 2)]
    outcome = run_case({
        "name": "dino_manual_rest", "profile": "dino", "cells": cells,
        "locations": [{"key": "glowna", "open_hours": ("06:00", "22:30")}],
        "constraints": {"min_open_staff": 2, "min_close_staff": 2},
        "employees": [dict(opener=True, meat=True) for _ in range(8)],
    }, time_limit=10)
    assert not [v for v in outcome["report"].by_rule("rest_11h") if v.source == "generator"]


@pytest.mark.xfail(strict=True, reason=DINO_REPORT_ONLY)
def test_dino_meat_coverage_uses_the_locations_opening_hours():
    """"Mięso przez cały dzień" (Wymagane) liczy obsadę wg ukrytych godzin
    projektu (05:30-22:45), nie godzin lokalizacji z Konfiguracji
    (06:00-22:00) - 2 osoby z mięsem nie "pokryją" 17,25 h i generator
    zwraca brak rozwiązania, choć 16 h da się pokryć."""
    outcome = run_case({
        "name": "dino_meat_hours", "profile": "dino",
        "locations": [{"key": "glowna", "open_hours": ("06:00", "22:00")}],
        "constraints": {"min_open_staff": 2, "min_close_staff": 2},
        "policies": {"meat_coverage": "MANDATORY"},
        "employees": [dict(opener=i < 3, meat=i in (3, 4)) for i in range(8)],
    }, time_limit=15)
    assert outcome["success"], outcome["reasons"]


@pytest.mark.xfail(strict=True, reason=DINO_REPORT_ONLY)
def test_dino_max_consecutive_from_config_reaches_the_generator():
    """"Maksymalna liczba dni pod rząd" z Konfiguracji zapisuje się do
    ShopConfig.constraints, a generator czyta wartość lokalizacji (ukryte
    pole, zawsze 4) - ustawienie 2 nie ma wpływu na wynik."""
    outcome = run_case({
        "name": "dino_max_consec", "profile": "dino",
        "locations": [{"key": "glowna", "open_hours": ("06:00", "22:00")}],
        "constraints": {"min_open_staff": 1, "min_close_staff": 1, "max_consecutive_days": 2},
        "policies": {"max_consecutive": "MANDATORY"},
        "employees": [dict(opener=True, meat=True) for _ in range(8)],
    }, time_limit=10)
    from tests.schedule_validator import cell_interval

    schedule = outcome["schedule"]
    for emp in schedule.employees:
        streak = 0
        for day in range(1, schedule.days_in_month + 1):
            streak = streak + 1 if cell_interval(schedule.get_day(emp, day), day) else 0
            assert streak <= 2, (emp.last_name, day)
