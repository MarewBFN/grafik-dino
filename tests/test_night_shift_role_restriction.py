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
from datetime import datetime
from pathlib import Path

from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.auto_generator import AutoScheduleGenerator
from logic.generator.constraint_registry import ConstraintContext
from logic.generator.custom_profile_wiring import default_policies
from logic.generator.generic_rules import _shift_touches_window, build_role_time_restriction
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


class TestShiftTouchesWindow:
    """Refactoring finding (constraint plan, priority 1): _shift_touches_window
    compared the shift's end hour against `window_end_hour` and its start
    hour against `window_start_hour` - swapped relative to the window they
    describe. With the default 22:00-06:00 window that made
    `end.hour >= 6 or start.hour <= 22` true for virtually every shift in the
    day, so build_role_time_restriction forbade the role from working at
    all, not just during 22:00-06:00. No prior test caught this because the
    only existing coverage (below) only asserts on SHIFT_NIGHT, never on a
    real OPEN/CLOSE/START/END shift computed from open hours.
    """

    def test_midday_shift_does_not_touch_the_night_window(self):
        start = datetime.strptime("10:00", "%H:%M")
        end = datetime.strptime("18:00", "%H:%M")
        assert _shift_touches_window(start, end, window_start_hour=22, window_end_hour=6) is False

    def test_late_closing_shift_touches_the_night_window(self):
        start = datetime.strptime("14:30", "%H:%M")
        end = datetime.strptime("23:00", "%H:%M")
        assert _shift_touches_window(start, end, window_start_hour=22, window_end_hour=6) is True

    def test_early_opening_shift_touches_the_night_window(self):
        start = datetime.strptime("03:00", "%H:%M")
        end = datetime.strptime("11:00", "%H:%M")
        assert _shift_touches_window(start, end, window_start_hour=22, window_end_hour=6) is True


class TestShiftTouchesWindowNonWrapping:
    """Codex review finding on this PR: the fix above only handled a window
    that wraps midnight (start hour > end hour, like 22-6). For a
    non-wrapping custom window (e.g. "no work 10:00-12:00", start < end),
    `end.hour >= 10 or start.hour <= 12` is true for virtually every normal
    shift, so the rule forbade the role from working at all instead of just
    10:00-12:00."""

    def test_shift_entirely_outside_a_non_wrapping_window_is_not_forbidden(self):
        start = datetime.strptime("14:00", "%H:%M")
        end = datetime.strptime("18:00", "%H:%M")
        assert _shift_touches_window(start, end, window_start_hour=10, window_end_hour=12) is False

    def test_shift_overlapping_a_non_wrapping_window_is_forbidden(self):
        start = datetime.strptime("09:00", "%H:%M")
        end = datetime.strptime("13:00", "%H:%M")
        assert _shift_touches_window(start, end, window_start_hour=10, window_end_hour=12) is True


class TestBuildRoleTimeRestrictionDaytime:
    """End-to-end companion to TestShiftTouchesWindow above, through
    build_role_time_restriction's actual OPEN/CLOSE forbidding (not just the
    helper in isolation)."""

    def test_does_not_forbid_a_shift_that_never_touches_the_window(self):
        shop = ShopConfig(2026, 8)
        loc = LocationConfig(key="site1", name="Site 1")
        for wd in range(7):
            loc.open_hours[wd] = ("10:00", "18:00")  # midday-only site
        shop.locations["site1"] = loc
        emp = Employee(last_name="Guard", first_name="A", location_key="site1", custom_roles={"guard": True})
        ctx = _ctx(shop, [emp])

        build_role_time_restriction(ctx, soft=False, role_key="guard", window_start_hour=22, window_end_hour=6)
        ctx.model.Add(ctx.x[0, 3, SHIFT_OPEN] == 1)

        status = cp_model.CpSolver().Solve(ctx.model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def test_still_forbids_a_shift_that_genuinely_touches_the_window(self):
        shop = ShopConfig(2026, 8)
        loc = LocationConfig(key="site1", name="Site 1")
        for wd in range(7):
            loc.open_hours[wd] = ("14:30", "23:00")  # closes late, touches 22:00-06:00
        shop.locations["site1"] = loc
        emp = Employee(last_name="Guard", first_name="A", location_key="site1", custom_roles={"guard": True})
        ctx = _ctx(shop, [emp])

        build_role_time_restriction(ctx, soft=False, role_key="guard", window_start_hour=22, window_end_hour=6)
        ctx.model.Add(ctx.x[0, 3, SHIFT_CLOSE] == 1)

        status = cp_model.CpSolver().Solve(ctx.model)
        assert status == cp_model.INFEASIBLE


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
