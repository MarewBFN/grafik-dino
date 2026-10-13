"""Reguła min_staff_with_role z zakresem "w każdej chwili okna godzin"
(Krok 1.3b): "wymagaj min. N osób z kwalifikacją X na poziomie >= L w oknie
godzin Y" - generator (generic_rules.py, scope="window"), etykieta reguły,
kreator profili i niezależny walidator."""

import contextlib
import io
import os

from ortools.sat.python import cp_model

from logic.generator.constraint_registry import ConstraintContext
from logic.generator.generic_rules import build_min_staff_with_role
from logic.generator.shift_intervals import segments
from model.custom_profile import (
    PARAM_MIN_LEVEL,
    RULE_TYPE_MIN_STAFF_WITH_ROLE,
    CustomBusinessProfile,
    RoleDefinition,
    RuleInstance,
)
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.qualification import EmployeeQualification
from model.shop_config import ShopConfig

SHIFT_OPEN, SHIFT_CLOSE, SHIFT_NIGHT = 0, 1, 2
DAY = 3  # 2026-08-03, poniedziałek


def _ctx(employees, days=(DAY,), trade_days=None, night=False, schedule=None):
    shop = ShopConfig(2026, 8)
    shop.locations = {"site1": LocationConfig(
        key="site1", name="Site 1", open_hours={wd: ("06:00", "22:00") for wd in range(7)}, is_24_7=night,
    )}
    shifts = (SHIFT_OPEN, SHIFT_CLOSE, SHIFT_NIGHT) if night else (SHIFT_OPEN, SHIFT_CLOSE)
    model = cp_model.CpModel()
    x = {(e, d, s): model.NewBoolVar(f"x_{e}_{d}_{s}") for e in range(len(employees)) for d in days for s in shifts}
    for e in range(len(employees)):
        for d in days:
            model.Add(sum(x[e, d, s] for s in shifts) <= 1)  # jedna zmiana dziennie
    return ConstraintContext(
        model=model, x=x, employees=employees, days=list(days),
        trade_days=list(trade_days if trade_days is not None else days),
        schedule=schedule, shop=shop, all_shifts=shifts,
        shift_open=SHIFT_OPEN, shift_close=SHIFT_CLOSE,
        start_shift_map={}, end_shift_map={}, trace=None,
        shift_night=SHIFT_NIGHT if night else None,
    )


def _emp(name, level=2, key="kasa"):
    return Employee(last_name=name, first_name="", location_key="site1",
                    qualifications=(EmployeeQualification(key, level),))


def _window_rule(ctx, start, end, min_count=2, min_level=2, soft=False):
    return build_min_staff_with_role(
        ctx, soft=soft, qualification_key="kasa", rule_key="rule:w", min_count=min_count,
        scope="window", min_level=min_level, window_start=start, window_end=end,
    )


def _solve(ctx):
    solver = cp_model.CpSolver()
    return solver, solver.Solve(ctx.model)


FEASIBLE = (cp_model.OPTIMAL, cp_model.FEASIBLE)


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def test_segments_split_at_interval_boundaries():
    assert segments(600, 840, [(360, 840), (720, 1320), (0, 100)]) == [(600, 720), (720, 840)]


def test_window_inside_opening_shift_requires_both_on_it():
    # Otwarcie 06:00-14:00, zamknięcie 14:00-22:00 (8 h): okno 10:00-14:00
    # pokrywa tylko otwarcie - obie osoby muszą na nim być.
    ctx = _ctx([_emp("A"), _emp("B")])
    _window_rule(ctx, "10:00", "14:00")
    solver, status = _solve(ctx)
    assert status in FEASIBLE
    assert all(solver.Value(ctx.x[e, DAY, SHIFT_OPEN]) for e in (0, 1))


def test_window_spanning_shift_change_needs_people_on_both_sides():
    # 12:00-16:00 - dwie osoby, każda tylko jedna zmiana: nie da się mieć
    # dwóch osób i przed, i po 14:00.
    ctx = _ctx([_emp("A"), _emp("B")])
    _window_rule(ctx, "12:00", "16:00")
    assert _solve(ctx)[1] == cp_model.INFEASIBLE

    ctx = _ctx([_emp(n) for n in "ABCD"])
    _window_rule(ctx, "12:00", "16:00")
    assert _solve(ctx)[1] in FEASIBLE


def test_window_counts_only_required_level():
    ctx = _ctx([_emp("A", level=2), _emp("B", level=1)])
    _window_rule(ctx, "10:00", "14:00")
    assert _solve(ctx)[1] == cp_model.INFEASIBLE

    ctx = _ctx([_emp("A", level=2), _emp("B", level=1)])
    _window_rule(ctx, "10:00", "14:00", min_level=1)
    assert _solve(ctx)[1] in FEASIBLE


def test_window_outside_any_shift_is_infeasible_when_hard():
    ctx = _ctx([_emp("A"), _emp("B")])
    _window_rule(ctx, "23:00", "23:30", min_count=1)
    assert _solve(ctx)[1] == cp_model.INFEASIBLE


def test_locked_manual_entry_counts_as_fixed_coverage():
    a, b = _emp("A"), _emp("B")
    schedule = MonthSchedule(2026, 8, employees=[a, b])
    ds = schedule.get_day(a, DAY)
    ds.set_hours("09:00", "15:00")
    ds.is_locked = True

    ctx = _ctx([a, b], schedule=schedule)
    _window_rule(ctx, "10:00", "14:00")
    # A ma ręczny wpis (stały) - wystarczy, że B weźmie otwarcie ...
    ctx.model.Add(ctx.x[0, DAY, SHIFT_OPEN] == 0)
    ctx.model.Add(ctx.x[0, DAY, SHIFT_CLOSE] == 0)
    assert _solve(ctx)[1] in FEASIBLE

    # ... ale bez B na otwarciu jedna osoba to za mało.
    ctx = _ctx([a, b], schedule=schedule)
    _window_rule(ctx, "10:00", "14:00")
    ctx.model.Add(ctx.x[1, DAY, SHIFT_OPEN] == 0)
    assert _solve(ctx)[1] == cp_model.INFEASIBLE


def test_window_after_midnight_counts_previous_day_night_shift():
    # Okno 00:00-04:00 dnia DAY+1 pokrywa tylko nocka zaczęta w dniu DAY.
    ctx = _ctx([_emp("A")], days=(DAY, DAY + 1), trade_days=(DAY + 1,), night=True)
    _window_rule(ctx, "00:00", "04:00", min_count=1)
    solver, status = _solve(ctx)
    assert status in FEASIBLE
    assert solver.Value(ctx.x[0, DAY, SHIFT_NIGHT]) == 1


def test_window_crossing_midnight_is_covered_by_night_shift():
    # 23:00-02:00 (koniec < początek = przez północ) - nocka 22:00-06:00.
    ctx = _ctx([_emp("A")], night=True)
    _window_rule(ctx, "23:00", "02:00", min_count=1)
    solver, status = _solve(ctx)
    assert status in FEASIBLE
    assert solver.Value(ctx.x[0, DAY, SHIFT_NIGHT]) == 1


def test_soft_window_penalty_counts_missing_quarter_hours():
    ctx = _ctx([_emp("A")])
    violations = _window_rule(ctx, "10:00", "14:00", soft=True)
    ctx.model.Minimize(sum(violations))
    solver, status = _solve(ctx)
    assert status == cp_model.OPTIMAL
    # Brakuje jednej osoby przez 4 h = 16 kwadransów.
    assert solver.ObjectiveValue() == 16


# ---------------------------------------------------------------------------
# Etykieta, zapis reguły, kreator
# ---------------------------------------------------------------------------

def _rule(**params):
    return RuleInstance(type=RULE_TYPE_MIN_STAFF_WITH_ROLE, qualification_key="kasa", params=params)


def test_window_rule_label_and_round_trip():
    profile = CustomBusinessProfile(key="p", display_name="P", roles=[RoleDefinition(key="kasa", label="Kasa")])
    rule = _rule(min_count=2, scope="window", window_start="10:00", window_end="14:00", **{PARAM_MIN_LEVEL: 2})
    assert profile.rule_label(rule) == "Kasa (poziom ≥ 2): min. 2 os. w godz. 10:00–14:00"

    again = RuleInstance.from_dict(rule.to_dict())
    assert again.params == rule.params
    assert again.qualification_key == "kasa"


def test_wizard_params_widget_round_trips_window():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])
    from ui.profile_wizard_dialog import _RuleParamsWidget

    widget = _RuleParamsWidget()
    widget.set_params(RULE_TYPE_MIN_STAFF_WITH_ROLE, {"min_count": 3, "scope": "window",
                                                      "window_start": "22:00", "window_end": "06:00"})
    params = widget.params_for_type(RULE_TYPE_MIN_STAFF_WITH_ROLE)
    assert params["scope"] == "window"
    assert (params["window_start"], params["window_end"]) == ("22:00", "06:00")
    assert params["min_count"] == 3

    widget.set_params(RULE_TYPE_MIN_STAFF_WITH_ROLE, {"min_count": 1, "scope": "open"})
    assert "window_start" not in widget.params_for_type(RULE_TYPE_MIN_STAFF_WITH_ROLE)


# ---------------------------------------------------------------------------
# End-to-end: profil custom z regułą okna, jak przycisk "Generuj"
# ---------------------------------------------------------------------------

WINDOW_PROFILE = {
    "key": "test_window_profile",
    "display_name": "Test: okno godzin",
    "roles": [{"key": "kasa", "label": "Kasa", "show_summary_row": True, "icon": ""}],
    "rules": [
        {"id": "win00001", "type": "min_staff_with_role", "qualification_key": "kasa",
         "policy": "MANDATORY", "weight": 1000,
         "params": {"min_count": 2, "scope": "window", "window_start": "11:00", "window_end": "17:00"}},
    ],
    "enabled_summary_rows": ["open", "close"],
}


def test_generated_schedule_satisfies_window_rule():
    from logic.schedule_controller import ScheduleController
    from model.business_profile import get_custom_profile, register_custom_profile
    from tests.generator_audit_harness import build_case
    from tests.schedule_validator import evaluate, validate

    if get_custom_profile(WINDOW_PROFILE["key"]) is None:
        register_custom_profile(CustomBusinessProfile.from_dict(WINDOW_PROFILE))

    schedule, shop = build_case({
        "name": "window", "profile": WINDOW_PROFILE["key"], "year": 2026, "month": 10,
        "locations": [{"key": "s", "open_hours": ("07:00", "21:00")}],
        "employees": [{"name": f"K{i:02d}", "location": "s", "roles": {"kasa": i < 6}} for i in range(9)],
    })
    shop.constraints["solver_time_limit_seconds"] = 30
    before = schedule.snapshot()
    controller = ScheduleController(schedule, shop)
    with contextlib.redirect_stdout(io.StringIO()):
        result = controller.generate_schedule(force=True)
    assert result["success"]

    def window_violations(after):
        ev = evaluate(validate(before, after, shop, generation_succeeded=True), shop)
        return [v for v in ev["hard"] + ev["soft"] if "[okno]" in v.message]

    assert window_violations(controller.schedule) == []
    # Walidator naprawdę sprawdza okno: pusty grafik je łamie.
    assert window_violations(before)
