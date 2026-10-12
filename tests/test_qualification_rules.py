"""Reguły profili custom na kwalifikacjach (Krok 1.3a): RuleInstance.
qualification_key + params["min_level"], migracja dawnego "role_key" i
custom_profiles.json (z kopią .bak), filtr na konkretny dzień w
generic_rules.py (data ważności, placówka, poziom)."""

import json
from datetime import date

from ortools.sat.python import cp_model

from logic.generator.constraint_registry import ConstraintContext
from logic.generator.generic_rules import build_min_staff_with_role, build_role_time_restriction
from model.custom_profile import (
    PARAM_MIN_LEVEL,
    RULE_TYPE_MIN_STAFF_WITH_ROLE,
    CustomBusinessProfile,
    RoleDefinition,
    RuleInstance,
)
from model.employee import Employee
from model.location import LocationConfig
from model.qualification import EmployeeQualification
from model.shop_config import ShopConfig

SHIFT_OPEN, SHIFT_CLOSE = 0, 1
ALL_SHIFTS = (SHIFT_OPEN, SHIFT_CLOSE)
DAY = 3  # 2026-08-03, poniedziałek


def _ctx(employees, days=(DAY,)):
    shop = ShopConfig(2026, 8)
    shop.locations = {"site1": LocationConfig(key="site1", name="Site 1", open_hours={wd: ("06:00", "22:00") for wd in range(7)})}
    model = cp_model.CpModel()
    x = {(e, d, s): model.NewBoolVar(f"x_{e}_{d}_{s}") for e in range(len(employees)) for d in days for s in ALL_SHIFTS}
    for e in range(len(employees)):
        for d in days:
            model.Add(sum(x[e, d, s] for s in ALL_SHIFTS) <= 1)  # jedna zmiana dziennie
    return ConstraintContext(
        model=model, x=x, employees=employees, days=list(days), trade_days=list(days),
        schedule=None, shop=shop, all_shifts=ALL_SHIFTS,
        shift_open=SHIFT_OPEN, shift_close=SHIFT_CLOSE,
        start_shift_map={}, end_shift_map={}, trace=None,
    )


def _emp(name, *qualifications):
    return Employee(last_name=name, first_name="", location_key="site1", qualifications=tuple(qualifications))


def _solve(ctx):
    return cp_model.CpSolver().Solve(ctx.model)


# ---------------------------------------------------------------------------
# Model reguły i migracja
# ---------------------------------------------------------------------------

def test_legacy_role_key_is_read_as_qualification_key():
    rule = RuleInstance.from_dict({"type": "min_staff_with_role", "role_key": "kasa", "params": {"min_count": 2}})
    assert rule.qualification_key == "kasa"
    saved = rule.to_dict()
    assert saved["qualification_key"] == "kasa"
    assert "role_key" not in saved


def test_rule_label_shows_level_only_above_one():
    profile = CustomBusinessProfile(key="p", display_name="P", roles=[RoleDefinition(key="kasa", label="Kasa")])
    plain = RuleInstance(type=RULE_TYPE_MIN_STAFF_WITH_ROLE, qualification_key="kasa",
                         params={"min_count": 2, "scope": "any_shift"})
    leveled = RuleInstance(type=RULE_TYPE_MIN_STAFF_WITH_ROLE, qualification_key="kasa",
                           params={"min_count": 2, "scope": "any_shift", PARAM_MIN_LEVEL: 2})
    assert profile.rule_label(plain) == "Kasa: min. 2 os. w ciągu dnia"
    assert profile.rule_label(leveled) == "Kasa (poziom ≥ 2): min. 2 os. w ciągu dnia"


def test_custom_profile_store_migrates_with_backup(tmp_path, monkeypatch):
    import model.custom_profile_store as store

    path = tmp_path / "custom_profiles.json"
    monkeypatch.setattr(store, "_store_path", lambda: str(path))
    legacy = {"profiles": [{
        "key": "custom_sklep", "display_name": "Sklep",
        "roles": [{"key": "kasa", "label": "Kasa"}],
        "rules": [{"type": "min_staff_with_role", "role_key": "kasa", "id": "r1",
                   "params": {"min_count": 2, "scope": "open"}}],
    }]}
    path.write_text(json.dumps(legacy), encoding="utf-8")
    original = path.read_bytes()

    (profile,) = store.load_custom_profiles()
    assert profile.rules[0].qualification_key == "kasa"

    store.save_custom_profile(profile)

    assert (tmp_path / "custom_profiles.json.bak").read_bytes() == original
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["format_version"] == 2
    assert saved["profiles"][0]["rules"][0]["qualification_key"] == "kasa"
    assert "role_key" not in saved["profiles"][0]["rules"][0]

    store.save_custom_profile(profile)  # kolejny zapis nie rusza kopii
    assert (tmp_path / "custom_profiles.json.bak").read_bytes() == original


# ---------------------------------------------------------------------------
# min_staff_with_role: poziom i data ważności
# ---------------------------------------------------------------------------

def _min_two_level_two(ctx):
    build_min_staff_with_role(
        ctx, soft=False, qualification_key="kasa", rule_key="rule:x", min_count=2, scope="any_shift", min_level=2,
    )


def test_min_level_counts_only_qualifications_at_or_above_level():
    employees = [
        _emp("Ekspert", EmployeeQualification("kasa", 2)),
        _emp("Nowa", EmployeeQualification("kasa", 1)),
    ]
    ctx = _ctx(employees)
    _min_two_level_two(ctx)
    # Dwie osoby w pracy, ale tylko jedna na poziomie >= 2.
    assert _solve(ctx) == cp_model.INFEASIBLE

    employees[1] = _emp("Nowa", EmployeeQualification("kasa", 3))
    ctx = _ctx(employees)
    _min_two_level_two(ctx)
    assert _solve(ctx) in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def test_min_level_one_is_the_old_behavior():
    employees = [_emp("A", EmployeeQualification("kasa", 1)), _emp("B", EmployeeQualification("kasa", 1))]
    ctx = _ctx(employees)
    build_min_staff_with_role(ctx, soft=False, qualification_key="kasa", rule_key="rule:x", min_count=2, scope="any_shift")
    assert _solve(ctx) in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def test_expired_qualification_does_not_count_that_day():
    employees = [
        _emp("A", EmployeeQualification("kasa", 2)),
        _emp("B", EmployeeQualification("kasa", 2, valid_to=date(2026, 8, 2))),
    ]
    ctx = _ctx(employees)
    _min_two_level_two(ctx)
    assert _solve(ctx) == cp_model.INFEASIBLE


def test_qualification_for_other_location_does_not_count():
    employees = [
        _emp("A", EmployeeQualification("kasa", 2)),
        _emp("B", EmployeeQualification("kasa", 2, location_ids=("inna",))),
    ]
    ctx = _ctx(employees)
    _min_two_level_two(ctx)
    assert _solve(ctx) == cp_model.INFEASIBLE


# ---------------------------------------------------------------------------
# role_time_restriction: poziom i data ważności
# ---------------------------------------------------------------------------

def test_time_restriction_applies_only_from_min_level_and_while_valid():
    # Okno 5-7 dotyka zmiany otwarcia (06:00 + 8h) - zakaz OPEN.
    employees = [
        _emp("PoziomJeden", EmployeeQualification("student", 1)),
        _emp("PoziomDwa", EmployeeQualification("student", 2)),
        _emp("Wygasla", EmployeeQualification("student", 2, valid_to=date(2026, 8, 2))),
    ]
    ctx = _ctx(employees)
    build_role_time_restriction(
        ctx, soft=False, qualification_key="student", window_start_hour=5, window_end_hour=7, min_level=2,
    )
    for e in range(3):
        ctx.model.Add(ctx.x[e, DAY, SHIFT_OPEN] == 1)
    assert _solve(ctx) == cp_model.INFEASIBLE  # PoziomDwa nie może otwierać

    ctx = _ctx([employees[0], employees[2]])
    build_role_time_restriction(
        ctx, soft=False, qualification_key="student", window_start_hour=5, window_end_hour=7, min_level=2,
    )
    for e in range(2):
        ctx.model.Add(ctx.x[e, DAY, SHIFT_OPEN] == 1)
    assert _solve(ctx) in (cp_model.OPTIMAL, cp_model.FEASIBLE)
