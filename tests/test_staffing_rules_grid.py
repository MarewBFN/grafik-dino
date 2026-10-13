"""Reguła "min. N osób z kwalifikacją X" (Krok 1.7) - jedna definicja
(model/staffing_rules.py) dla generatora i walidacji siatki: siatka
zgłasza brak dokładnie wtedy, gdy generator uznałby ten sam grafik za
niedopuszczalny."""

import contextlib
import io
import os
import random
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ortools.sat.python import cp_model
from PySide6.QtWidgets import QApplication

from logic.constraint_presenter import ConstraintPresenter
from logic.generator.constraint_registry import ConstraintContext
from logic.generator.generic_rules import build_min_staff_with_role
from model.business_profile import get_profile, register_custom_profile
from model.constraint_policy import ConstraintPolicy
from model.constraints import ConstraintEngine
from model.custom_profile import CustomBusinessProfile, RoleDefinition, RuleInstance
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.qualification import EmployeeQualification
from model.shop_config import ShopConfig
from model.staffing_rules import cell_in_scope, check_min_staff
from ui import theme

_app = QApplication.instance() or QApplication([])

YEAR, MONTH = 2026, 8
SHIFT_OPEN, SHIFT_CLOSE = 0, 1
SHIFT_HOURS = {SHIFT_OPEN: ("06:00", "14:00"), SHIFT_CLOSE: ("14:00", "22:00")}
DAYS = (3, 4, 5)  # pon.-śr.


def _shop():
    shop = ShopConfig(YEAR, MONTH)
    shop.locations = {"site1": LocationConfig(key="site1", name="Site 1", open_hours={wd: ("06:00", "22:00") for wd in range(7)})}
    return shop


def _employees():
    return [
        Employee("A", "", location_key="site1", qualifications=(EmployeeQualification("kasa", 2),)),
        Employee("B", "", location_key="site1", qualifications=(EmployeeQualification("kasa", 1),)),
        Employee("C", "", location_key="site1", qualifications=(EmployeeQualification("kasa", 2, valid_to=date(2026, 8, 4)),)),
        Employee("D", "", location_key="site1", qualifications=(EmployeeQualification("kasa", 3),)),
        Employee("E", "", location_key="site1"),
    ]


def _generator_accepts(employees, assignment, params):
    """Czy generator (ograniczenia twarde) dopuszcza grafik `assignment`
    ({(e, d): zmiana albo None})."""
    shop = _shop()
    model = cp_model.CpModel()
    shifts = (SHIFT_OPEN, SHIFT_CLOSE)
    days = list(range(1, 32))
    x = {(e, d, s): model.NewBoolVar(f"x{e}_{d}_{s}") for e in range(len(employees)) for d in days for s in shifts}
    for (e, d, s), var in x.items():
        model.Add(var == (1 if assignment.get((e, d)) == s else 0))
    ctx = ConstraintContext(
        model=model, x=x, employees=employees, days=days, trade_days=list(DAYS),
        schedule=None, shop=shop, all_shifts=shifts, shift_open=SHIFT_OPEN, shift_close=SHIFT_CLOSE,
        start_shift_map={}, end_shift_map={}, trace=None,
    )
    build_min_staff_with_role(ctx, soft=False, qualification_key="kasa", rule_key="rule:x", **params)
    return cp_model.CpSolver().Solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def _grid_accepts(employees, assignment, params):
    shop = _shop()
    schedule = MonthSchedule(YEAR, MONTH, employees=employees)
    for (e, d), s in assignment.items():
        if s is not None:
            schedule.get_day(employees[e], d).set_hours(*SHIFT_HOURS[s])
    # Grafik tylko w dniach testu - pozostałe dni poza regułą (jak trade_days generatora).
    return [day for day, _ in check_min_staff(schedule, shop, "rule:x", "kasa", params) if day in DAYS] == []


def test_grid_and_generator_agree_on_random_schedules():
    employees = _employees()
    rng = random.Random(7)
    scopes = [
        {"min_count": 1, "scope": "open"},
        {"min_count": 2, "scope": "close"},
        {"min_count": 2, "scope": "any_shift", "min_level": 2},
        {"min_count": 2, "scope": "window", "window_start": "12:00", "window_end": "16:00"},
        {"min_count": 1, "scope": "window", "window_start": "13:00", "window_end": "15:00", "min_level": 2},
    ]
    checked = {True: 0, False: 0}
    for params in scopes:
        for _ in range(40):
            assignment = {
                (e, d): rng.choice((None, SHIFT_OPEN, SHIFT_CLOSE))
                for e in range(len(employees)) for d in DAYS
            }
            expected = _generator_accepts(employees, assignment, params)
            assert _grid_accepts(employees, assignment, params) == expected, (params, assignment)
            checked[expected] += 1
    # Losowanie dało i grafiki dopuszczalne, i niedopuszczalne.
    assert checked[True] and checked[False]


# ---------------------------------------------------------------------------
# Zakres na wpisanych godzinach
# ---------------------------------------------------------------------------

def _location_view(config):
    shop = ShopConfig(YEAR, MONTH)
    shop.locations = {config.key: config}
    return shop.get_location(Employee("X", "", location_key=config.key))


def test_cell_in_scope():
    location = _location_view(LocationConfig(key="s", name="S", open_hours={wd: ("07:00", "21:00") for wd in range(7)}))
    assert cell_in_scope("open", location, 3, (7 * 60, 15 * 60))
    assert not cell_in_scope("open", location, 3, (8 * 60, 16 * 60))
    assert cell_in_scope("close", location, 3, (13 * 60, 21 * 60))
    assert cell_in_scope("any_shift", location, 3, (10 * 60, 12 * 60))
    assert not cell_in_scope("night", location, 3, (22 * 60, 30 * 60))  # placówka bez nocki

    night = _location_view(LocationConfig(key="n", name="N", is_24_7=True))
    assert cell_in_scope("night", night, 3, (22 * 60, 30 * 60))


# ---------------------------------------------------------------------------
# Siatka: kolor wiersza kwalifikacji
# ---------------------------------------------------------------------------

PROFILE_KEY = "custom_test_grid_rules"


def _register(show_row=False, policy="MANDATORY", **params):
    rule = RuleInstance(
        type="min_staff_with_role", qualification_key="kasa", id="r1", policy=policy,
        params={"min_count": 2, "scope": "any_shift", **params},
    )
    register_custom_profile(CustomBusinessProfile(
        key=PROFILE_KEY, display_name="T",
        roles=[RoleDefinition(key="kasa", label="Kasa", show_summary_row=show_row)], rules=[rule],
    ))
    return rule


def _custom_case(policy=ConstraintPolicy.MANDATORY):
    shop = _shop()
    shop.business_type = PROFILE_KEY
    shop.constraint_policies["rule:r1"] = policy
    employees = _employees()[:2]
    schedule = MonthSchedule(YEAR, MONTH, employees=employees)
    schedule.get_day(employees[0], 3).set_hours("06:00", "14:00")
    schedule.get_day(employees[1], 3).set_hours("14:00", "22:00")
    schedule.get_day(employees[0], 4).set_hours("06:00", "14:00")
    return schedule, shop


def test_rule_qualification_always_gets_summary_row():
    _register(show_row=False)
    assert ("Kasa", "role:kasa") in get_profile(PROFILE_KEY).summary_rows


def test_mandatory_shortfall_is_red_on_role_row():
    _register()
    schedule, shop = _custom_case()
    presenter = ConstraintPresenter(schedule, shop)
    ok, short = presenter.get_validation_cell_view("role:kasa", 3), presenter.get_validation_cell_view("role:kasa", 4)
    assert ok.bg == theme.BG_MAIN
    assert short.bg == theme.ERR_RED
    assert short.tooltip == "Kasa: min. 2 os. w ciągu dnia – jest 1 z 2 os."


def test_preferred_shortfall_is_yellow_and_disabled_is_silent():
    _register(policy="PREFERRED")
    schedule, shop = _custom_case(ConstraintPolicy.PREFERRED)
    assert ConstraintPresenter(schedule, shop).get_validation_cell_view("role:kasa", 4).bg == theme.WARN_YELLOW

    schedule, shop = _custom_case(ConstraintPolicy.DISABLED)
    assert not [v for v in ConstraintEngine.evaluate(schedule, shop) if v.type == "custom_min_staff"]


def test_level_and_location_override_in_grid():
    _register(min_level=2)
    schedule, shop = _custom_case()
    # B ma poziom 1 - dzień 3 to też brak przy poziomie >= 2.
    days = {v.day for v in ConstraintEngine.evaluate(schedule, shop) if v.type == "custom_min_staff"}
    assert 3 in days and 4 in days

    shop.locations["site1"].constraints["rule:r1"] = 1  # próg placówki
    days = {v.day for v in ConstraintEngine.evaluate(schedule, shop) if v.type == "custom_min_staff"}
    assert 3 not in days and 4 not in days


def test_window_gap_message_lists_merged_gaps():
    _register(scope="window", window_start="12:00", window_end="16:00")
    schedule, shop = _custom_case()
    messages = [v.message for v in ConstraintEngine.evaluate(schedule, shop) if v.type == "custom_min_staff" and v.day == 3]
    assert messages == ["Kasa: min. 2 os. w godz. 12:00–16:00 – za mało osób: 12:00–16:00 (1 z 2)"]


# ---------------------------------------------------------------------------
# End-to-end: grafik z generatora nie świeci się na czerwono
# ---------------------------------------------------------------------------

E2E_PROFILE = {
    "key": "test_grid_rules_e2e",
    "display_name": "Test: reguły w siatce",
    "roles": [{"key": "kasa", "label": "Kasa", "show_summary_row": False, "icon": ""}],
    "rules": [
        {"id": "e2e00001", "type": "min_staff_with_role", "qualification_key": "kasa",
         "policy": "MANDATORY", "weight": 1000, "params": {"min_count": 2, "scope": "any_shift"}},
        {"id": "e2e00002", "type": "min_staff_with_role", "qualification_key": "kasa",
         "policy": "MANDATORY", "weight": 1000, "params": {"min_count": 1, "scope": "open"}},
        {"id": "e2e00003", "type": "min_staff_with_role", "qualification_key": "kasa",
         "policy": "MANDATORY", "weight": 1000,
         "params": {"min_count": 2, "scope": "window", "window_start": "11:00", "window_end": "17:00"}},
    ],
    "enabled_summary_rows": [],
}


def test_generated_schedule_has_no_custom_rule_violations_in_grid():
    from logic.schedule_controller import ScheduleController
    from model.business_profile import get_custom_profile
    from tests.generator_audit_harness import build_case

    if get_custom_profile(E2E_PROFILE["key"]) is None:
        register_custom_profile(CustomBusinessProfile.from_dict(E2E_PROFILE))
    schedule, shop = build_case({
        "name": "grid", "profile": E2E_PROFILE["key"], "year": 2026, "month": 10,
        "locations": [{"key": "s", "open_hours": ("07:00", "21:00")}],
        "employees": [{"name": f"K{i:02d}", "location": "s", "roles": {"kasa": i < 6}} for i in range(9)],
    })
    shop.constraints["solver_time_limit_seconds"] = 30
    before = schedule.snapshot()
    controller = ScheduleController(schedule, shop)
    with contextlib.redirect_stdout(io.StringIO()):
        assert controller.generate_schedule(force=True)["success"]

    def custom_violations(sched):
        return [v for v in ConstraintEngine.evaluate(sched, shop) if v.type == "custom_min_staff"]

    assert custom_violations(controller.schedule) == []
    assert custom_violations(before)  # pusty grafik łamie reguły
