"""Constraint wiring for the "dino_retail" business profile.

This is a declarative re-statement of what AutoScheduleGenerator.generate()
used to hard-code: the same constraint modules, same call arguments, same
weights, same order. Behavior for Dino projects must stay byte-identical -
only the wiring moved from a hand-written method body into data any other
business profile can provide its own version of.
"""

from logic.generator.constraint_registry import ConstraintContext, ConstraintSpec
from logic.generator.constraints_basic import (
    add_one_shift_per_day_constraint,
    add_non_trade_day_constraints,
    add_leave_constraints,
    add_day_off_constraints,
)
from logic.generator.constraints_staff import (
    add_fixed_staff_shift_constraints,
    add_max_consecutive_constraint,
)
from logic.generator.rest_constraint import (
    add_rest_11h_constraint,
    add_rest_11h_constraint_simplified,
)
from logic.generator.meat_constraint import add_meat_constraint, add_meat_coverage_constraint
from logic.generator.meat_light_budget import build_meat_light_duty
from logic.generator.hours_constraint import add_monthly_hours_constraint, add_balance_constraint
from logic.generator.manual_constraint import add_manual_shift_constraints
from logic.generator.constraints_logic import add_work_dependency_constraint
from logic.generator.objective import (
    add_open_close_penalty,
    add_work_balance_penalty,
    add_morning_afternoon_balance_penalty,
    add_edge_shift_bonus,
    add_workload_balance_penalty,
)
from logic.generator.availability_constraint import add_availability_constraint
from logic.generator.night_constraint import add_no_night_constraint
from logic.generator.afternoon_constraint import add_no_afternoon_constraint


CONSTRAINT_WEIGHTS = {
    "meat": 1000,
    "meat_coverage": 1500,
    "meat_light_usage": 400,
    "rest_11h": 5000,
    "balance": 1000,
    "max_consecutive": 100,
    "open": 200,
    "close": 200,
    "monthly_hours": 250,
    "availability": 5000,
    "no_night": 5000,
    "no_afternoon": 5000,
    "morning_afternoon_balance": 10000,
    "add_edge_shift_bonus": 1000,
}


def setup_context(ctx: ConstraintContext) -> None:
    """Build the shared meat-light duty budget shared by open/close/meat/
    meat_coverage, exactly like generate() used to do right before applying
    those policies."""
    slot_duty_sum, shift_duty_sum = build_meat_light_duty(
        ctx.model, ctx.x, ctx.employees, ctx.trade_days, ctx.shop,
        ctx.shift_open, ctx.shift_close, ctx.start_shift_map, ctx.end_shift_map,
    )
    ctx.extra["slot_duty_sum"] = slot_duty_sum
    ctx.extra["shift_duty_sum"] = shift_duty_sum
    ctx.extra["meat_light_penalties"] = []


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


def _build_open(ctx, soft):
    min_open = ctx.shop.constraints.get("min_open_staff", 3)
    return add_fixed_staff_shift_constraints(
        ctx.model, ctx.x, ctx.employees, ctx.trade_days, ctx.shift_open, min_open,
        soft=soft, trace=ctx.trace,
        meat_light_penalties=ctx.extra["meat_light_penalties"],
        shift_duty_sum=ctx.extra["shift_duty_sum"],
    )


def _build_close(ctx, soft):
    min_close = ctx.shop.constraints.get("min_close_staff", 3)
    return add_fixed_staff_shift_constraints(
        ctx.model, ctx.x, ctx.employees, ctx.trade_days, ctx.shift_close, min_close,
        soft=soft, trace=ctx.trace,
        meat_light_penalties=ctx.extra["meat_light_penalties"],
        shift_duty_sum=ctx.extra["shift_duty_sum"],
    )


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


def _build_no_night(ctx, soft):
    return add_no_night_constraint(
        ctx.model, ctx.x, ctx.employees, ctx.days, ctx.shop, ctx.all_shifts,
        ctx.shift_open, ctx.shift_close, ctx.start_shift_map, ctx.end_shift_map,
        soft=soft, trace=ctx.trace,
    )


def _build_no_afternoon(ctx, soft):
    return add_no_afternoon_constraint(
        ctx.model, ctx.x, ctx.employees, ctx.days, ctx.all_shifts,
        ctx.shift_open, ctx.shift_close, ctx.start_shift_map, ctx.end_shift_map,
        soft=soft, trace=ctx.trace,
    )


def _build_meat(ctx, soft):
    return add_meat_constraint(
        ctx.model, ctx.x, ctx.employees, ctx.days, ctx.trade_days, ctx.all_shifts,
        ctx.shift_open, ctx.shift_close, soft=soft, trace=ctx.trace,
        meat_light_penalties=ctx.extra["meat_light_penalties"],
        shift_duty_sum=ctx.extra["shift_duty_sum"],
    )


def _build_meat_coverage(ctx, soft):
    return add_meat_coverage_constraint(
        ctx.model, ctx.x, ctx.employees, ctx.trade_days, ctx.shop,
        ctx.shift_open, ctx.shift_close, ctx.start_shift_map, ctx.end_shift_map,
        soft=soft, trace=ctx.trace,
        meat_light_penalties=ctx.extra["meat_light_penalties"],
        slot_duty_sum=ctx.extra["slot_duty_sum"],
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


def _build_policy_specs():
    return [
        ConstraintSpec("open", _build_open),
        ConstraintSpec("close", _build_close),
        ConstraintSpec("rest_11h", _build_rest_11h),
        ConstraintSpec("balance", _build_balance),
        ConstraintSpec("availability", _build_availability),
        ConstraintSpec("no_night", _build_no_night),
        ConstraintSpec("no_afternoon", _build_no_afternoon),
        ConstraintSpec("meat", _build_meat),
        ConstraintSpec("meat_coverage", _build_meat_coverage),
        ConstraintSpec("max_consecutive", _build_max_consecutive),
        ConstraintSpec("monthly_hours", _build_monthly_hours),
    ]


ALWAYS_ON_SPECS = _build_always_on_specs()
POLICY_SPECS = _build_policy_specs()

# Every spec in the order generate() should run them: always-on first (they
# don't depend on ctx.extra), then the policy-gated ones (which do).
ALL_SPECS = ALWAYS_ON_SPECS + POLICY_SPECS


def build_objective_terms(ctx: ConstraintContext, shift_work_start_15: int, shift_work_end_15: int) -> list:
    """Soft objective terms that run unconditionally (outside the
    MANDATORY/PREFERRED/DISABLED policy system), same as generate() used to
    tack on after _apply_policy calls. Includes the meat-light usage penalty,
    which depends on ctx.extra populated by the policy specs above."""
    terms = []

    meat_light_penalties = ctx.extra.get("meat_light_penalties") or []
    if meat_light_penalties:
        weight = CONSTRAINT_WEIGHTS.get("meat_light_usage", 400)
        terms.extend(weight * t for t in meat_light_penalties)

    terms.extend(add_edge_shift_bonus(
        ctx.model, ctx.x, ctx.employees, ctx.trade_days, shift_work_start_15, shift_work_end_15
    ))
    terms.extend(add_morning_afternoon_balance_penalty(
        ctx.model, ctx.x, ctx.employees, ctx.days, ctx.shop,
        ctx.shift_open, ctx.shift_close, ctx.start_shift_map, ctx.end_shift_map,
    ))
    terms.extend(add_work_balance_penalty(
        ctx.model, ctx.x, ctx.employees, ctx.trade_days, ctx.start_shift_map, ctx.end_shift_map
    ))
    terms.extend(add_workload_balance_penalty(
        ctx.model, ctx.x, ctx.employees, ctx.days, ctx.all_shifts
    ))
    terms.extend(add_open_close_penalty(
        ctx.x, ctx.employees, ctx.trade_days, ctx.shift_open, ctx.shift_close
    ))

    return terms
