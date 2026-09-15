"""Codex review finding on PR #2: build_role_time_restriction
(logic/generator/generic_rules.py) never accounted for ctx.shift_night, so
a "role X forbidden 22:00-06:00" rule silently did not apply to SHIFT_NIGHT
at all. Combined with a scope="night" min_staff_with_role rule (Etap F) for
the same role, the generator could - and would - assign the night shift to
exactly the employee another MANDATORY rule was supposed to forbid from it,
with no conflict raised.
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
from logic.generator.constraint_registry import ConstraintContext
from logic.generator.custom_profile_wiring import default_policies
from logic.generator.generic_rules import build_role_time_restriction
from model.business_profile import register_custom_profile
from model.constraint_policy import ConstraintPolicy
from model.custom_profile import (
    RULE_TYPE_MIN_STAFF_WITH_ROLE,
    RULE_TYPE_ROLE_TIME_RESTRICTION,
    CustomBusinessProfile,
    RoleDefinition,
    RuleInstance,
)
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig

SHIFT_OPEN, SHIFT_CLOSE, SHIFT_NIGHT = 0, 1, 14
ALL_SHIFTS = (SHIFT_OPEN, SHIFT_CLOSE, SHIFT_NIGHT)


def _location_with_night(start="22:00", end="06:00"):
    loc = LocationConfig(key="site1", name="Site 1")
    loc.set_night_shift(start, end)
    return loc


def _ctx(shop, employees, days=(3,)):
    model = cp_model.CpModel()
    x = {(e, d, s): model.NewBoolVar(f"x_{e}_{d}_{s}") for e in range(len(employees)) for d in days for s in ALL_SHIFTS}
    return ConstraintContext(
        model=model, x=x, employees=employees, days=list(days), trade_days=list(days),
        schedule=None, shop=shop, all_shifts=ALL_SHIFTS,
        shift_open=SHIFT_OPEN, shift_close=SHIFT_CLOSE,
        start_shift_map={}, end_shift_map={}, trace=None, shift_night=SHIFT_NIGHT,
    )


class TestBuildRoleTimeRestrictionNight:
    def test_night_shift_forbidden_when_window_overlaps(self):
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_night("22:00", "06:00")
        emp = Employee(last_name="Guard", first_name="A", location_key="site1", custom_roles={"guard": True})
        ctx = self._ctx = _ctx(shop, [emp])

        build_role_time_restriction(ctx, soft=False, role_key="guard", window_start_hour=22, window_end_hour=6)
        ctx.model.Add(ctx.x[0, 3, SHIFT_NIGHT] == 1)

        status = cp_model.CpSolver().Solve(ctx.model)
        assert status == cp_model.INFEASIBLE

    def test_night_shift_allowed_when_window_does_not_overlap(self):
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_night("22:00", "06:00")
        emp = Employee(last_name="Guard", first_name="A", location_key="site1", custom_roles={"guard": True})
        ctx = _ctx(shop, [emp])

        # Restriction is 13:00-21:00 - doesn't touch the 22:00-06:00 night window at all.
        build_role_time_restriction(ctx, soft=False, role_key="guard", window_start_hour=13, window_end_hour=21)
        ctx.model.Add(ctx.x[0, 3, SHIFT_NIGHT] == 1)

        status = cp_model.CpSolver().Solve(ctx.model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def test_no_restriction_applied_without_night_shift_configured(self):
        shop = ShopConfig(2026, 8)  # no locations at all
        emp = Employee(last_name="Guard", first_name="A", custom_roles={"guard": True})
        ctx = _ctx(shop, [emp])

        violations = build_role_time_restriction(ctx, soft=False, role_key="guard", window_start_hour=22, window_end_hour=6)
        assert violations == []
        # SHIFT_NIGHT is untouched by this rule (still gated elsewhere by
        # add_night_shift_gate_constraint, not this rule's job).
        ctx.model.Add(ctx.x[0, 3, SHIFT_NIGHT] == 1)
        status = cp_model.CpSolver().Solve(ctx.model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def test_end_to_end_night_coverage_rule_conflicts_with_role_time_restriction():
    """The exact scenario from the Codex comment: a MANDATORY "guards can't
    work 22:00-06:00" rule and a MANDATORY "min. 1 guard on the night shift"
    rule for the same role/employee, with no one else able to cover it -
    must be infeasible, not silently solved by assigning the forbidden shift
    to the very employee who shouldn't have it."""
    restriction_rule = RuleInstance(
        type=RULE_TYPE_ROLE_TIME_RESTRICTION, role_key="guard",
        policy="MANDATORY", params={"window_start_hour": 22, "window_end_hour": 6},
    )
    coverage_rule = RuleInstance(
        type=RULE_TYPE_MIN_STAFF_WITH_ROLE, role_key="guard",
        policy="MANDATORY", params={"min_count": 1, "scope": "night"},
    )
    profile = CustomBusinessProfile(
        key="custom_test_night_restriction_conflict",
        display_name="Test Conflict",
        roles=[RoleDefinition(key="guard", label="Ochroniarz")],
        rules=[restriction_rule, coverage_rule],
    )
    register_custom_profile(profile)

    shop = ShopConfig(2026, 3)
    shop.business_type = profile.key
    shop.constraint_policies.update(default_policies(profile))
    shop.constraint_policies[profile.rule_policy_key(restriction_rule)] = ConstraintPolicy.MANDATORY
    shop.constraint_policies[profile.rule_policy_key(coverage_rule)] = ConstraintPolicy.MANDATORY

    loc = _location_with_night("22:00", "06:00")
    shop.locations = {"site1": loc}

    schedule = MonthSchedule(2026, 3)
    emp = Employee(last_name="Guard", first_name="A", location_key="site1", custom_roles={"guard": True})
    schedule.add_employee(emp)

    with redirect_stdout(io.StringIO()):
        result = AutoScheduleGenerator(schedule, shop).generate(solver_time_limit_seconds=10, solver_workers=1)

    assert result["success"] is False, (
        "the only 'guard' is both required to cover the night shift and forbidden from working it - "
        "this must be infeasible"
    )


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
