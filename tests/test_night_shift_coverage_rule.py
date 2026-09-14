"""Etap F planu zmian nocnych: "min. N osób z rolą X na zmianie nocnej" -
a generic custom-profile rule (no hardcoded, speculative "security"
business profile - the real client's roles/hours/thresholds aren't known
yet, see "plan zmiany nocne (24-7).md"). Reuses the existing
min_staff_with_role rule type with a new scope="night" option, exactly
the same mechanism as scope="open"/"close" already use.
"""

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.auto_generator import AutoScheduleGenerator
from logic.generator.custom_profile_wiring import default_policies
from logic.generator.generic_rules import build_min_staff_with_role
from model.business_profile import register_custom_profile
from model.constraint_policy import ConstraintPolicy
from model.custom_profile import (
    RULE_TYPE_MIN_STAFF_WITH_ROLE,
    CustomBusinessProfile,
    RoleDefinition,
    RuleInstance,
)
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from ui.profile_wizard_dialog import SCOPE_OPTIONS


class TestBuildMinStaffWithRoleNightScope:
    """Isolated CP-SAT-level coverage (no full generator run)."""

    SHIFT_OPEN, SHIFT_CLOSE, SHIFT_NIGHT = 0, 1, 14
    ALL_SHIFTS = (SHIFT_OPEN, SHIFT_CLOSE, SHIFT_NIGHT)

    def _ctx(self, shop, employees, trade_days=(3,)):
        from logic.generator.constraint_registry import ConstraintContext

        model = cp_model.CpModel()
        x = {(e, d, s): model.NewBoolVar(f"x_{e}_{d}_{s}") for e in range(len(employees)) for d in trade_days for s in self.ALL_SHIFTS}
        return ConstraintContext(
            model=model, x=x, employees=employees, days=list(trade_days), trade_days=list(trade_days),
            schedule=None, shop=shop, all_shifts=self.ALL_SHIFTS,
            shift_open=self.SHIFT_OPEN, shift_close=self.SHIFT_CLOSE,
            start_shift_map={}, end_shift_map={}, trace=None, shift_night=self.SHIFT_NIGHT,
        )

    def test_night_scope_only_counts_shift_night(self):
        shop = ShopConfig(2026, 8)
        loc = LocationConfig(key="site1", name="Site 1")
        loc.set_night_shift("22:00", "06:00")
        shop.locations["site1"] = loc
        emp = Employee(last_name="Guard", first_name="A", location_key="site1", custom_roles={"guard": True})
        ctx = self._ctx(shop, [emp])

        build_min_staff_with_role(ctx, soft=False, role_key="guard", rule_key="rule:x", min_count=1, scope="night")

        # Assigning OPEN (not NIGHT) must not satisfy a night-scoped rule.
        ctx.model.Add(ctx.x[0, 3, self.SHIFT_OPEN] == 1)
        ctx.model.Add(ctx.x[0, 3, self.SHIFT_NIGHT] == 0)
        status = cp_model.CpSolver().Solve(ctx.model)
        assert status == cp_model.INFEASIBLE

    def test_night_scope_satisfied_by_shift_night(self):
        shop = ShopConfig(2026, 8)
        loc = LocationConfig(key="site1", name="Site 1")
        loc.set_night_shift("22:00", "06:00")
        shop.locations["site1"] = loc
        emp = Employee(last_name="Guard", first_name="A", location_key="site1", custom_roles={"guard": True})
        ctx = self._ctx(shop, [emp])

        build_min_staff_with_role(ctx, soft=False, role_key="guard", rule_key="rule:x", min_count=1, scope="night")
        ctx.model.Add(ctx.x[0, 3, self.SHIFT_NIGHT] == 1)

        status = cp_model.CpSolver().Solve(ctx.model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def test_ui_exposes_night_scope_option():
    values = {value for _, value in SCOPE_OPTIONS}
    assert "night" in values


def test_rule_label_describes_night_scope():
    rule = RuleInstance(
        type=RULE_TYPE_MIN_STAFF_WITH_ROLE, role_key="guard",
        params={"min_count": 2, "scope": "night"},
    )
    profile = CustomBusinessProfile(
        key="custom_test_night_label",
        display_name="Test",
        roles=[RoleDefinition(key="guard", label="Ochroniarz")],
        rules=[rule],
    )
    assert "nocnej" in profile.rule_label(rule)


def test_end_to_end_night_coverage_rule_requires_enough_guards():
    """A 24/7-style custom profile (no OPEN/CLOSE at all) with a MANDATORY
    "min. 2 guards on the night shift" rule - the real shape of the
    security-company use case this whole plan exists for."""
    rule = RuleInstance(
        type=RULE_TYPE_MIN_STAFF_WITH_ROLE, role_key="guard",
        policy="MANDATORY", params={"min_count": 2, "scope": "night"},
    )
    profile = CustomBusinessProfile(
        key="custom_test_night_coverage",
        display_name="Test Ochrona",
        roles=[RoleDefinition(key="guard", label="Ochroniarz")],
        rules=[rule],
    )
    register_custom_profile(profile)
    rule_key = profile.rule_policy_key(rule)

    def build(guard_count):
        shop = ShopConfig(2026, 3)
        shop.business_type = profile.key
        shop.constraint_policies.update(default_policies(profile))
        shop.constraint_policies[rule_key] = ConstraintPolicy.MANDATORY

        loc = LocationConfig(key="site1", name="Obiekt")
        loc.set_night_shift("22:00", "06:00")
        shop.locations = {"site1": loc}

        schedule = MonthSchedule(2026, 3)
        for i in range(guard_count):
            emp = Employee(last_name=f"Guard{i}", first_name="A", location_key="site1", custom_roles={"guard": True})
            schedule.add_employee(emp)

        with redirect_stdout(io.StringIO()):
            result = AutoScheduleGenerator(schedule, shop).generate(
                solver_time_limit_seconds=15, solver_workers=1
            )
        return result, schedule

    result_ok, schedule_ok = build(2)
    assert result_ok["success"], result_ok["infeasibility_reasons"]

    night_days = [
        day for day in range(1, schedule_ok.days_in_month + 1)
        if all(schedule_ok.get_day(emp, day).crosses_midnight() for emp in schedule_ok.employees)
    ]
    assert night_days, "expected every day to be covered by night shifts with exactly enough guards"

    result_bad, _ = build(1)
    assert result_bad["success"] is False, "one guard can never satisfy a 2-guard night threshold"
