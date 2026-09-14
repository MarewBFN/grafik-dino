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
from logic.generator.generic_rules import (
    _daily_windows_overlap,
    _restriction_overlaps_night_shift,
    build_role_time_restriction,
)
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


class TestDailyWindowOverlapMath:
    """Pure overlap-math coverage - no CP-SAT involved."""

    def test_identical_windows_overlap(self):
        assert _daily_windows_overlap(22 * 60, 6 * 60, 22 * 60, 6 * 60)

    def test_disjoint_windows_do_not_overlap(self):
        # 22:00-06:00 vs 08:00-16:00 - nowhere near each other.
        assert not _daily_windows_overlap(22 * 60, 6 * 60, 8 * 60, 16 * 60)

    def test_partial_overlap_at_the_edge(self):
        # 22:00-06:00 restriction vs a 05:00-13:00 night shift - 1h overlap (05:00-06:00).
        assert _daily_windows_overlap(22 * 60, 6 * 60, 5 * 60, 13 * 60)

    def test_touching_but_not_overlapping_windows_do_not_overlap(self):
        # 22:00-06:00 vs 06:00-14:00 - back-to-back, zero actual overlap.
        assert not _daily_windows_overlap(22 * 60, 6 * 60, 6 * 60, 14 * 60)

    def test_non_wrapping_restriction_overlaps_wrapping_night_window(self):
        # 20:00-23:00 restriction (same-day) vs 22:00-06:00 night shift.
        assert _daily_windows_overlap(20 * 60, 23 * 60, 22 * 60, 6 * 60)


class TestRestrictionOverlapsNightShift:
    def test_default_window_matches_default_night_shift_exactly(self):
        assert _restriction_overlaps_night_shift(22, 6, ("22:00", "06:00"))

    def test_no_overlap_when_night_shift_is_elsewhere(self):
        assert not _restriction_overlaps_night_shift(22, 6, ("13:00", "21:00"))


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
