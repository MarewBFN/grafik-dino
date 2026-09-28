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

import pytest

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


def _coverage(outcome, key="p"):
    return outcome["report"].metrics["opening_coverage"][key]


def _assert_exact_coverage(outcome, key="p"):
    """Każdy kwadrans okien placówki obsadzony, nigdy ponad „Maks. obsada
    naraz” (domyślnie 1 osoba), bez twardych naruszeń walidatora."""
    assert outcome["success"], outcome["reasons"]
    assert _hard_rules(outcome) == []
    metrics = _coverage(outcome, key)
    assert metrics["gap_slots"] == 0, metrics
    assert metrics["over_cap_slots"] == 0, metrics
    assert metrics["double_slots"] == 0, metrics


def test_ochrona_store_closing_at_2245_gets_no_rigid_night_shift_and_full_coverage():
    """Wcześniej: placówka 05:30-22:45 dostawała sztywną nockę 22:00-06:00
    (ok. 7 h po zamknięciu) i nie miała żadnej reguły obsady. Teraz: jedna
    osoba na całe okno dnia (decyzja użytkownika 2026-09-28)."""
    outcome = run_case(_ochrona_regular("och_no_night", ("05:30", "22:45"), 5), time_limit=15)

    _assert_exact_coverage(outcome)
    for _name, day, (start, end) in _shift_intervals(outcome):
        base = (day - 1) * 1440
        assert (start - base, end - base) == (5 * 60 + 30, 22 * 60 + 45)


def test_ochrona_short_day_is_one_whole_window_shift_even_with_8h30():
    """10:00-18:00 przy "8h 30 min" (istniejący projekt): wcześniej zmiany
    wychodziły poza godziny (10:45-19:15, 09:00-17:30). Teraz jedna zmiana
    na całe okno, dokładnie 10:00-18:00."""
    outcome = run_case(
        _ochrona_regular("och_short", ("10:00", "18:00"), 4, constraints={"force_fulltime_845": True}),
        time_limit=15,
    )

    _assert_exact_coverage(outcome)
    for name, day, (start, end) in _shift_intervals(outcome):
        base = (day - 1) * 1440
        assert (start - base, end - base) == (600, 1080), (name, day, start, end)


def test_ochrona_full_day_after_day_window_is_24h_or_two_halves_from_midnight():
    """Weekend 00:00-23:45 (doba), tydzień 08:00-16:00: piątek kończy się
    przed północą, więc doba sob/nd to 00:00-24:00 - jedna zmiana 24 h albo
    połówki 00-12 / 12-24."""
    import calendar

    hours = {wd: ("08:00", "16:00") for wd in range(5)}
    hours.update({5: ("00:00", "23:45"), 6: ("00:00", "23:45")})
    outcome = run_case(_ochrona_regular("och_mixed_doba", hours, 5), time_limit=20)

    _assert_exact_coverage(outcome)
    for name, day, (start, end) in _shift_intervals(outcome):
        base = (day - 1) * 1440
        if calendar.weekday(2026, 10, day) >= 5:
            assert (start - base, end - base) in ((0, 1440), (0, 720), (720, 1440)), (name, day)
        else:
            assert (start - base, end - base) == (480, 960), (name, day)


GZUK_HOURS = {**{wd: ("15:00", "07:00") for wd in range(5)}, 5: ("00:00", "23:45"), 6: ("00:00", "23:45")}


def test_gzuk_weeknights_and_weekend_24h_are_one_continuous_coverage():
    """Klient GZUK: pn-pt 15:00-07:00, sob-nd 24h. Wcześniej doba liczona
    00:00-24:00 - piątkowa nocka nachodziła na sobotę 00:00-07:00, a
    poniedziałek 00:00-07:00 zostawał bez ochrony; do tego zmiany 8 h i
    sztywna nocka 22-06 (59% godzin bez nikogo, 4-6 osób naraz na nocce, a
    wynik OPTIMAL). Decyzja: ciągle od pt 15:00 do pn 07:00 (sob/nd
    07:00-07:00), jedna osoba na całe okno."""
    import calendar

    outcome = run_case(_ochrona_regular("gzuk", GZUK_HOURS, 5), time_limit=30)

    _assert_exact_coverage(outcome)
    covered = sorted(iv for _n, _d, iv in _shift_intervals(outcome))
    # Ciągłość od piątku 2.10 15:00 do poniedziałku 5.10 07:00 (bez przerwy).
    t = 1 * 1440 + 15 * 60
    while t < 4 * 1440 + 7 * 60:
        t = next(end for start, end in covered if start <= t < end)
    assert t == 4 * 1440 + 7 * 60
    for name, day, (start, end) in _shift_intervals(outcome):
        base = (day - 1) * 1440
        weekday = calendar.weekday(2026, 10, day)
        if weekday < 5:
            # pn-pt: tylko całe okno 15:00-07:00 (druga połówka niedzielnej
            # doby, 19:00-07:00, należy do komórki niedzieli - dnia, w którym
            # się zaczyna).
            assert (start - base, end - base) == (900, 1860), (name, day)
        else:
            assert (start - base, end - base) in ((420, 1860), (420, 1140), (1140, 1860)), (name, day)


def test_gzuk_profile_with_nie_chce_24h_role_uses_the_opening_hours_model():
    """Plik klienta (test1.myp) ma profil „ochrona_dane_klienta_test”, a demo -
    „ochrona_enyo”: model godzin otwarcia działał tylko dla klucza
    „custom_ochrona”, więc te projekty szły starą ścieżką. Teraz: każdy
    profil custom z rolą „Nie chce 24h” (decyzja użytkownika)."""
    from demo.install_client_sample_data import build_profile
    from logic.generator.opening_hours_coverage import profile_uses_opening_hours_model
    from model.business_profile import register_custom_profile, unregister_custom_profile
    from model.custom_profile import CustomBusinessProfile, RoleDefinition

    profile = build_profile()
    register_custom_profile(profile)
    other = CustomBusinessProfile(
        key="audit_no_role", display_name="Bez roli",
        roles=[RoleDefinition(key="umowa", label="Umowa")], rules=[],
    )
    register_custom_profile(other)
    try:
        assert profile_uses_opening_hours_model(profile.key)
        assert not profile_uses_opening_hours_model(other.key)
        assert not profile_uses_opening_hours_model("dino_retail")
        outcome = run_case(dict(_ochrona_regular("gzuk_client", GZUK_HOURS, 5), profile=profile.key), time_limit=30)
        _assert_exact_coverage(outcome)
    finally:
        unregister_custom_profile(other.key)


def test_nie_chce_24h_gets_weekend_halves_not_24h():
    """„Nie chce 24h” (sob/nd): doba dzielona na dwie połówki po 12 h."""
    spec = _ochrona_regular("gzuk_no24", GZUK_HOURS, 5)
    for emp in spec["employees"]:
        emp["roles"] = {"nie_chce_24h": True}
    outcome = run_case(spec, time_limit=30)

    _assert_exact_coverage(outcome)
    for name, day, (start, end) in _shift_intervals(outcome):
        assert end - start < 1440, (name, day)


def test_manual_partial_night_leaves_a_residual_shift_not_a_double():
    """Ręczny wpis 15:00-23:00 w oknie 15:00-07:00: reszta nocy (23:00-07:00)
    idzie jako zmiana resztkowa innej osoby - bez dwóch osób naraz."""
    cells = [(0, 6, "hours", "15:00", "23:00")]
    outcome = run_case(_ochrona_regular("gzuk_manual", GZUK_HOURS, 5, cells=cells), time_limit=30)

    _assert_exact_coverage(outcome)
    rows = [(n, d, iv) for n, d, iv in _shift_intervals(outcome) if iv[0] == 5 * 1440 + 23 * 60]
    assert rows and rows[0][2][1] == 6 * 1440 + 7 * 60, rows


def test_shift_class_w_forces_a_shift_for_opening_hours_employee():
    """Typ zmiany „W” (może pracować) był dla pracowników placówek z
    godzinami otwarcia ignorowany (manual_shift pomija ich indeksy)."""
    cells = [(0, d, "class", "W") for d in (6, 13, 20)]
    outcome = run_case(_ochrona_regular("gzuk_w", GZUK_HOURS, 5, cells=cells), time_limit=30)

    _assert_exact_coverage(outcome)
    worked = {d for n, d, _iv in _shift_intervals(outcome) if n == "P00"}
    assert {6, 13, 20} <= worked


@pytest.mark.parametrize("hours", [
    ("22:00", "06:00"),
    ("18:00", "06:00"),
    ("23:00", "07:00"),
    ("15:00", "07:00"),
    ("04:00", "23:00"),
    ("00:00", "00:00"),
    ("07:00", "07:00"),
    {**{wd: ("20:00", "08:00") for wd in range(5)}, 5: ("08:00", "20:00"), 6: ("08:00", "20:00")},
    {**{wd: ("06:00", "14:00") for wd in range(5)}, 5: ("00:00", "23:45"), 6: ("00:00", "23:45")},
])
def test_weird_opening_hours_get_exact_coverage(hours):
    """Godziny przez północ, doba zapisana jako 00:00-00:00/07:00-07:00
    (plik projektu), okna pn-pt inne niż weekend - każdy kwadrans okien
    obsadzony dokładnie 1 osobą, każda zmiana to całe okno/doba/połówka
    (sprawdza niezależny walidator)."""
    outcome = run_case(_ochrona_regular("weird", hours, 6), time_limit=30)

    _assert_exact_coverage(outcome)


def test_max_staff_policy_modes():
    """„Maks. obsada naraz” (decyzja użytkownika: nakładki dozwolone, ale
    edytowalne - liczba osób i Wymagana/Preferowana/Wyłączona). 4 osoby z
    „Umową” na 08:00-16:00: Preferowana (domyślnie, waga wyższa niż
    „Umowa”) - 1 osoba naraz, godziny niedobite; Wyłączona - druga osoba
    dokładana, żeby dobić godziny; Wymagana z limitem 2 - najwyżej 2."""
    spec = _ochrona_regular("max_staff", ("08:00", "16:00"), 4)
    for emp in spec["employees"]:
        emp["roles"] = {"umowa": True}

    preferred = run_case(dict(spec, name="max_staff_p"), time_limit=15)
    _assert_exact_coverage(preferred)

    disabled = run_case(dict(spec, name="max_staff_d", policies={"max_staff_at_once": "DISABLED"}), time_limit=15)
    assert disabled["success"], disabled["reasons"]
    assert _coverage(disabled)["double_slots"] > 0
    assert "max_staff_at_once" not in _hard_rules(disabled)

    capped = run_case(
        dict(spec, name="max_staff_m2", policies={"max_staff_at_once": "MANDATORY"},
             constraints={"max_staff_at_once": 2}),
        time_limit=15,
    )
    assert capped["success"], capped["reasons"]
    assert _hard_rules(capped) == []
    assert _coverage(capped)["over_cap_slots"] == 0
    assert _coverage(capped)["double_slots"] > 0


def test_ochrona_unmatched_manual_shift_counts_for_rest_and_coverage():
    """Ręczny wpis 14:00-23:00 (nie pasuje do okna 06:00-23:00) był dla
    generatora niewidoczny: następnego dnia ta sama osoba mogła dostać
    zmianę od 06:00 (7 h odpoczynku przy Wymaganym 11 h)."""
    cells = [(0, d, "hours", "14:00", "23:00") for d in range(2, 30, 3)]
    outcome = run_case(_ochrona_regular("och_manual_rest", ("06:00", "23:00"), 4, cells=cells), time_limit=15)

    _assert_exact_coverage(outcome)
    assert not outcome["report"].by_rule("rest_11h")


def test_previous_month_night_blocks_the_first_evening():
    """Nocka z końca poprzedniego miesiąca (do 07:00 dnia 1) - ta sama osoba
    nie może zacząć o 15:00 dnia 1 (8 h odpoczynku)."""
    spec = _ochrona_regular("gzuk_carry", GZUK_HOURS, 5, prev_month={0: ("07:00", True)})
    outcome = run_case(spec, time_limit=30)

    _assert_exact_coverage(outcome)
    assert all(not (n == "P00" and d == 1) for n, d, _iv in _shift_intervals(outcome))


def test_ochrona_opening_hours_coverage_policy_modes_change_the_result():
    """MANDATORY: pełne obłożenie (albo brak grafiku). DISABLED: generator
    przestaje go pilnować - przy 1 osobie na 16 h dziennie zostają luki."""
    base = _ochrona_regular("och_cov", ("06:00", "22:00"), 1)

    mandatory = run_case(dict(base, name="och_cov_m"), time_limit=10)
    assert not mandatory["success"]  # 1 osoba nie pokryje 16 h każdego dnia (odpoczynek 8 h)

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


def test_ochrona_simplified_rest_mode_still_guarantees_11h_when_hours_differ():
    """Tryb "Uproszczony" odpoczynku zakazuje tylko przejścia popołudnie ->
    rano. Przy różnych godzinach w kolejne dni (np. zamknięcie 22:00, a
    następnego dnia zmiana od 06:00) to za mało - wynik łamał Wymagany
    odpoczynek 11 h (w Dino: 8,5 h)."""
    hours = {wd: ("06:00", "22:00") for wd in range(7)}
    hours.update({1: ("06:00", "14:00"), 3: ("06:00", "14:00"), 5: ("06:00", "14:00")})
    outcome = run_case(
        _ochrona_regular("och_simplified_rest", hours, 5, constraints={"rest_11h_mode": "simplified"}),
        time_limit=15,
    )

    assert outcome["success"], outcome["reasons"]
    assert not [v for v in outcome["report"].by_rule("rest_11h") if v.source == "generator"]


def test_ochrona_too_few_people_for_opening_hours_is_explained():
    """1 osoba na 15:00-07:00 codziennie - kolejne okna dzieli 8 h, a
    odpoczynek to 11 h: komunikat ma podać przyczynę (za mało osób), nie
    "sprzeczne zasady"."""
    outcome = run_case(_ochrona_regular("och_capacity", ("15:00", "07:00"), 1), time_limit=10)

    assert not outcome["success"]
    assert any("za mało osób" in r for r in outcome["reasons"]), outcome["reasons"]


def test_grid_coverage_row_checks_opening_hours_windows():
    """Wiersz „Obłożenie” w siatce liczył tylko rotację 24/7 - dla placówki
    z godzinami (GZUK) pokazywał ❌ każdego dnia mimo pełnej obsady."""
    import calendar

    from logic.duty_coverage_presenter import is_day_fully_covered

    outcome = run_case(_ochrona_regular("gzuk_grid", GZUK_HOURS, 5), time_limit=30)
    _assert_exact_coverage(outcome)
    schedule, shop = outcome["schedule"], outcome["shop"]
    employees = list(schedule.employees)
    days = range(1, schedule.days_in_month + 1)
    assert all(is_day_fully_covered(schedule, shop, employees, d) for d in days)

    # Usunięcie jednej nocki (pn-pt) = luka tylko w tym dniu.
    day = next(d for d in days if calendar.weekday(2026, 10, d) == 2)
    emp = next(e for e in employees if schedule.get_day(e, day).start == "15:00")
    schedule.get_day(emp, day).start = None
    schedule.get_day(emp, day).end = None
    assert not is_day_fully_covered(schedule, shop, employees, day)
    assert is_day_fully_covered(schedule, shop, employees, day + 1)


def test_day_edit_accepts_overnight_and_24h_for_opening_hours_location():
    """Okno edycji dnia odrzucało 15:00-07:00 („Koniec musi być później niż
    start”) i nie miało „Cała doba (24h)” w placówce z godzinami - nie dało
    się nawet ponownie zapisać zmiany wygenerowanej przez generator."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from logic.schedule_controller import ScheduleController
    from tests.generator_audit_harness import build_case
    from ui.day_edit_dialog import DayEditDialog

    QApplication.instance() or QApplication([])
    dialog = DayEditDialog(start="15:00", end="07:00", open_start="15:00", open_end="07:00", overnight=True)
    dialog.accept = lambda: None
    assert dialog.duration_label.text() == "Czas pracy: 16:00"
    assert not dialog.full_day_check.isHidden()
    dialog._save()
    assert (dialog.result_mode, dialog.result_start, dialog.result_end) == ("hours", "15:00", "07:00")

    dialog.full_day_check.setChecked(True)
    dialog._save()
    assert dialog.result_mode == "full_day"

    schedule, shop = build_case(_ochrona_regular("gzuk_edit", GZUK_HOURS, 2))
    controller = ScheduleController(schedule, shop)
    emp = schedule.employees[0]
    controller.set_day_hours(emp, 5, "15:00", "07:00")
    ds = schedule.get_day(emp, 5)
    assert (ds.start, ds.end, ds.is_locked) == ("15:00", "07:00", True)


def test_employee_dialog_shows_nie_chce_24h_for_ochrona_without_rotation():
    """„Nie chce pracować zmian 24h” było widoczne tylko w projektach z
    rotacją 24/7 - a doba sob/nd w placówce z godzinami też jest zmianą 24h."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from tests.generator_audit_harness import build_case
    from ui.employee_dialog import EmployeeDialog

    QApplication.instance() or QApplication([])
    schedule, shop = build_case(_ochrona_regular("gzuk_emp", GZUK_HOURS, 1))
    dialog = EmployeeDialog(None, employee=schedule.employees[0], shop_config=shop)
    assert dialog.no_24h_check is not None


def test_shift_class_conflicting_with_no_night_is_explained():
    """„W” (musi pracować) w dzień roboczy GZUK (jedyna zmiana 15:00-07:00)
    u osoby z „Nie pracuje w nocy” (Wymagane) - wcześniej tylko „Wymagane
    zasady są ze sobą sprzeczne” (kampania weird_hours: 8 z 8 takich
    przypadków bez konkretnej przyczyny)."""
    spec = _ochrona_regular("gzuk_w_night", GZUK_HOURS, 5, cells=[(0, 6, "class", "W")])
    spec["employees"][0]["no_night"] = True
    outcome = run_case(spec, time_limit=15)

    assert not outcome["success"]
    assert any(
        "dzień 6" in r and "„W”" in r and "Nie pracuje w godzinach nocnych" in r for r in outcome["reasons"]
    ), outcome["reasons"]
    assert not outcome["report"].violations


def test_ochrona_long_day_is_one_shift_not_a_gap():
    """04:00-23:00 (19 h): wcześniej zmiany 8 h zakotwiczone przy otwarciu/
    zamknięciu zostawiały lukę w środku dnia (brak rozwiązania). Teraz jedna
    osoba na całe okno."""
    outcome = run_case(_ochrona_regular("och_long_day", ("04:00", "23:00"), 8), time_limit=15)

    _assert_exact_coverage(outcome)


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
    assert shop.constraint_policies["max_staff_at_once"] == ConstraintPolicy.PREFERRED
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


def test_config_dialog_edits_max_staff_at_once_for_ochrona(monkeypatch):
    """„Maks. obsada naraz”: liczba osób (Ograniczenia) i tryb (Zasady
    generatora) - GUI -> konfiguracja -> generator."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    import ui.config_dialog as config_dialog
    from model.constraint_policy import ConstraintPolicy
    from tests.generator_audit_harness import build_case

    QApplication.instance() or QApplication([])
    spec = _ochrona_regular("gui_max", ("08:00", "16:00"), 4)
    for emp in spec["employees"]:
        emp["roles"] = {"umowa": True}
    schedule, shop = build_case(spec)
    shop.constraint_policies.pop("max_staff_at_once")
    monkeypatch.setattr(config_dialog.ConfigDialog, "_maybe_show_tutorial", lambda self: None)

    dialog = config_dialog.ConfigDialog(None, shop, location_key="p")
    selector = dialog.policy_selectors["max_staff_at_once"]
    assert selector.currentData() == ConstraintPolicy.PREFERRED
    assert dialog.max_staff.value() == 1
    # Pole i tryb muszą być w zakładce, którą użytkownik faktycznie widzi
    # ("Limity" w tej wersji nie jest dodawana do okna).
    rules_page = dialog.tabs.widget(dialog._tab_index_generator)
    assert rules_page.isAncestorOf(dialog.max_staff)
    assert rules_page.isAncestorOf(selector)

    selector.setCurrentIndex(selector.findData(ConstraintPolicy.MANDATORY))
    dialog.max_staff.setValue(2)
    dialog._save()
    assert shop.constraint_policies["max_staff_at_once"] == ConstraintPolicy.MANDATORY
    assert shop.constraints["max_staff_at_once"] == 2

    import contextlib
    import io

    from logic.schedule_controller import ScheduleController
    from tests.schedule_validator import evaluate, validate

    shop.constraints["solver_time_limit_seconds"] = 15
    before = schedule.snapshot()
    controller = ScheduleController(schedule, shop)
    with contextlib.redirect_stdout(io.StringIO()):
        result = controller.generate_schedule(force=True)
    assert result["success"], result["infeasibility_reasons"]
    report = validate(before, controller.schedule, shop)
    assert not evaluate(report, shop)["hard"]
    metrics = report.metrics["opening_coverage"]["p"]
    assert metrics["max_staff"] == 2 and metrics["over_cap_slots"] == 0 and metrics["double_slots"] > 0


# ---------------------------------------------------------------------------
# Profil Dino - znane błędy, TYLKO RAPORT (decyzja użytkownika 2026-09-28:
# na gałęzi Enyo nie zmieniamy zachowania constraintów Dino). Reproducery
# jako xfail(strict=True): gdy błąd zostanie naprawiony, test zacznie
# przechodzić i xfail trzeba będzie zdjąć. Szczegóły: GENERATOR_AUDIT.md.
# ---------------------------------------------------------------------------

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


@pytest.mark.xfail(strict=True, reason=DINO_REPORT_ONLY)
def test_dino_simplified_rest_mode_still_guarantees_11h_when_hours_differ():
    """Tryb "Uproszczony" odpoczynku przy różnych godzinach w kolejne dni
    (pt 06:00-22:00, sob 07:00-15:00): zamknięcie 22:00 -> "popołudnie" w
    sobotę od 06:30 = 8,5 h przy Wymaganym 11 h."""
    hours = {wd: ("06:00", "21:00") for wd in range(7)}
    hours.update({4: ("06:00", "22:00"), 5: ("07:00", "15:00"), 6: (None, None)})
    outcome = run_case({
        "name": "dino_simplified_rest", "profile": "dino",
        "locations": [{"key": "glowna", "open_hours": hours}],
        "constraints": {"min_open_staff": 2, "min_close_staff": 2, "rest_11h_mode": "simplified"},
        "employees": [dict(opener=i < 3, meat=i >= 4) for i in range(7)],
    }, time_limit=10)
    assert not [v for v in outcome["report"].by_rule("rest_11h") if v.source == "generator"]
