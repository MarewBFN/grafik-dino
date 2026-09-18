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


def _location_with_night():
    # Default open_hours already overlap 22:00-06:00, so this auto-detects
    # the standard night window - LocationConfig no longer has a way to
    # configure an arbitrary/custom night window (see model/location.py).
    return LocationConfig(key="site1", name="Site 1")


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
        shop.locations["site1"] = _location_with_night()
        emp = Employee(last_name="Guard", first_name="A", location_key="site1", custom_roles={"guard": True})
        ctx = self._ctx = _ctx(shop, [emp])

        build_role_time_restriction(ctx, soft=False, role_key="guard", window_start_hour=22, window_end_hour=6)
        ctx.model.Add(ctx.x[0, 3, SHIFT_NIGHT] == 1)

        status = cp_model.CpSolver().Solve(ctx.model)
        assert status == cp_model.INFEASIBLE

    def test_night_shift_allowed_when_window_does_not_overlap(self):
        shop = ShopConfig(2026, 8)
        shop.locations["site1"] = _location_with_night()
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

    loc = _location_with_night()
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


class TestBuildRoleTimeRestrictionRegularShifts:
    """_shift_touches_window previously paired window_start_hour with
    start_dt and window_end_hour with end_dt - backwards from the window's
    own clock boundaries. For the default (22, 6) "no_night"-style window
    that made end_dt.hour >= 6 (true for virtually any shift ending in the
    afternoon or evening) or start_dt.hour <= 22 (true for virtually any
    shift at all), so a role_time_restriction rule silently forbade every
    ordinary daytime OPEN/CLOSE shift too, not just ones actually touching
    22:00-06:00. Only the separate SHIFT_NIGHT branch (tested above) was
    ever covered by a test, so this regressed unnoticed."""

    def _location(self, open_hours):
        loc = LocationConfig(key="site1", name="Site 1")
        loc.open_hours = {wd: open_hours for wd in range(7)}
        return loc

    def test_daytime_shifts_not_forbidden_by_night_window(self):
        shop = ShopConfig(2026, 3)
        shop.locations["site1"] = self._location(("08:00", "20:00"))
        emp = Employee(last_name="Guard", first_name="A", location_key="site1", custom_roles={"guard": True})

        # OPEN (08:00-16:00) and CLOSE (12:00-20:00) both sit entirely
        # within the day - neither should be forced to 0 by a 22:00-06:00
        # restriction. Checked independently (each on its own fresh model
        # built the same way) since this bare ctx doesn't model "one shift
        # per day", so forcing both at once on the same model would be a
        # meaningless test.
        for shift in (SHIFT_OPEN, SHIFT_CLOSE):
            trial_ctx = _ctx(shop, [emp])
            build_role_time_restriction(trial_ctx, soft=False, role_key="guard", window_start_hour=22, window_end_hour=6)
            trial_ctx.model.Add(trial_ctx.x[0, 3, shift] == 1)
            status = cp_model.CpSolver().Solve(trial_ctx.model)
            assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE), (
                f"shift {shift} within 08:00-20:00 should not be forbidden by a 22:00-06:00 restriction"
            )

    def test_shift_touching_night_window_is_forbidden(self):
        shop = ShopConfig(2026, 3)
        # CLOSE ends exactly at 22:00 (start 14:00) - genuinely touches the
        # 22:00-06:00 window and must still be forbidden after the fix.
        shop.locations["site1"] = self._location(("08:00", "22:00"))
        emp = Employee(last_name="Guard", first_name="A", location_key="site1", custom_roles={"guard": True})
        ctx = _ctx(shop, [emp])

        build_role_time_restriction(ctx, soft=False, role_key="guard", window_start_hour=22, window_end_hour=6)
        ctx.model.Add(ctx.x[0, 3, SHIFT_CLOSE] == 1)

        status = cp_model.CpSolver().Solve(ctx.model)
        assert status == cp_model.INFEASIBLE


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
