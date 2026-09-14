"""Constraint wiring that has no business-specific role logic in it at all -
calendar/leave mechanics plus the shop-level rules (rest, hours, balance,
availability, consecutive days). Every business profile gets these for free;
only Dino's role-flag-specific constraints (meat, opener/closer staffing,
no_night/no_afternoon) live in dino_retail_profile.py instead.

This module is a pure extraction of what was already generic inside
dino_retail_profile.py - no behavior change for Dino, which now imports these
same specs instead of duplicating them.
"""

from logic.generator.constraint_registry import ConstraintSpec
from logic.generator.constraints_basic import (
    add_one_shift_per_day_constraint,
    add_non_trade_day_constraints,
    add_leave_constraints,
    add_day_off_constraints,
)
from logic.generator.constraints_staff import add_max_consecutive_constraint
from logic.generator.rest_constraint import (
    add_rest_11h_constraint,
    add_rest_11h_constraint_simplified,
)
from logic.generator.hours_constraint import add_monthly_hours_constraint, add_balance_constraint
from logic.generator.manual_constraint import add_manual_shift_constraints
from logic.generator.constraints_logic import add_work_dependency_constraint
from logic.generator.availability_constraint import add_availability_constraint


GENERIC_WEIGHTS = {
    "rest_11h": 5000,
    "balance": 1000,
    "max_consecutive": 100,
    "monthly_hours": 250,
    "availability": 5000,
}

GENERIC_POLICY_LABELS = (
    ("rest_11h", "Odpoczynek 11 h"),
    ("availability", "Dostępność pracownika"),
    ("monthly_hours", "Godziny miesięczne"),
    ("balance", "Bilans godzin"),
    ("max_consecutive", "Dni pod rząd"),
)


def _build_always_on_specs():
    return [
        ConstraintSpec(
            "non_trade_day",
            lambda ctx, soft: add_non_trade_day_constraints(
                ctx.model, ctx.x, ctx.employees, ctx.days, ctx.shop, ctx.all_shifts, trace=ctx.trace
            ),
            always_on=True,
        ),
        ConstraintSpec(
            "leave",
            lambda ctx, soft: add_leave_constraints(
                ctx.model, ctx.x, ctx.employees, ctx.days, ctx.schedule, ctx.all_shifts, trace=ctx.trace
            ),
            always_on=True,
        ),
        ConstraintSpec(
            "day_off",
            lambda ctx, soft: add_day_off_constraints(
                ctx.model, ctx.x, ctx.employees, ctx.days, ctx.schedule, ctx.all_shifts, trace=ctx.trace
            ),
            always_on=True,
        ),
        ConstraintSpec(
            "manual_shift",
            lambda ctx, soft: add_manual_shift_constraints(
                ctx.model, ctx.x, ctx.employees, ctx.days, ctx.schedule, ctx.shop, ctx.all_shifts,
                ctx.shift_open, ctx.shift_close, ctx.start_shift_map, ctx.end_shift_map, trace=ctx.trace,
            ),
            always_on=True,
        ),
        ConstraintSpec(
            "work_dependency",
            lambda ctx, soft: add_work_dependency_constraint(
                ctx.model, ctx.x, ctx.employees, ctx.days, ctx.shift_open, ctx.shift_close, ctx.all_shifts,
                trace=ctx.trace,
            ),
            always_on=True,
        ),
        ConstraintSpec(
            "one_shift_per_day",
            lambda ctx, soft: add_one_shift_per_day_constraint(
                ctx.model, ctx.x, ctx.employees, ctx.days, ctx.all_shifts, trace=ctx.trace
            ),
            always_on=True,
        ),
    ]


def _build_rest_11h(ctx, soft):
    mode = ctx.shop.constraints.get("rest_11h_mode", "standard")
    if mode == "simplified":
        return add_rest_11h_constraint_simplified(
            ctx.model, ctx.x, ctx.employees, ctx.days, ctx.trade_days,
            ctx.shift_open, ctx.shift_close, ctx.start_shift_map, ctx.end_shift_map,
            soft=soft, trace=ctx.trace,
        )
    return add_rest_11h_constraint(
        ctx.model, ctx.x, ctx.employees, ctx.days, ctx.trade_days, ctx.shop,
        ctx.shift_open, ctx.shift_close, ctx.start_shift_map, ctx.end_shift_map,
        soft=soft, trace=ctx.trace,
    )


def _build_balance(ctx, soft):
    return add_balance_constraint(
        ctx.model, ctx.x, ctx.employees, ctx.days, ctx.shop, ctx.all_shifts, soft=soft, trace=ctx.trace
    )


def _build_availability(ctx, soft):
    return add_availability_constraint(
        ctx.model, ctx.x, ctx.employees, ctx.days, ctx.shop, ctx.all_shifts,
        ctx.shift_open, ctx.shift_close, ctx.start_shift_map, ctx.end_shift_map,
        soft=soft, trace=ctx.trace,
    )


def _build_max_consecutive(ctx, soft):
    max_consecutive = ctx.shop.constraints.get("max_consecutive_days", 4)
    return add_max_consecutive_constraint(
        ctx.model, ctx.x, ctx.employees, ctx.days, max_consecutive, ctx.all_shifts, soft=soft, trace=ctx.trace
    )


def _build_monthly_hours(ctx, soft):
    return add_monthly_hours_constraint(
        ctx.model, ctx.x, ctx.employees, ctx.days, ctx.schedule, ctx.shop, ctx.all_shifts, soft=soft, trace=ctx.trace
    )


def _build_generic_policy_specs():
    return [
        ConstraintSpec("rest_11h", _build_rest_11h),
        ConstraintSpec("balance", _build_balance),
        ConstraintSpec("availability", _build_availability),
        ConstraintSpec("max_consecutive", _build_max_consecutive),
        ConstraintSpec("monthly_hours", _build_monthly_hours),
    ]


ALWAYS_ON_SPECS = _build_always_on_specs()
GENERIC_POLICY_SPECS = _build_generic_policy_specs()
