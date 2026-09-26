"""Constraint wiring for the "dino_retail" business profile.

This is a declarative re-statement of what AutoScheduleGenerator.generate()
used to hard-code: the same constraint modules, same call arguments, same
weights, same order. Behavior for Dino projects must stay byte-identical -
only the wiring moved from a hand-written method body into data any other
business profile can provide its own version of.
"""

from logic.generator import base_specs
from logic.generator.constraint_registry import ConstraintContext, ConstraintSpec
from logic.generator.constraints_staff import add_fixed_staff_shift_constraints
from logic.generator.meat_constraint import add_meat_constraint, add_meat_coverage_constraint
from logic.generator.meat_light_budget import build_meat_light_duty
from logic.generator.round_clock_constraint import add_round_clock_coverage_constraint
from logic.generator.objective import (
    add_open_close_penalty,
    add_work_balance_penalty,
    add_morning_afternoon_balance_penalty,
    add_edge_shift_bonus,
    add_workload_balance_penalty,
)
from logic.generator.night_constraint import add_no_night_constraint
from logic.generator.afternoon_constraint import add_no_afternoon_constraint


CONSTRAINT_WEIGHTS = {
    **base_specs.GENERIC_WEIGHTS,
    "meat": 1000,
    "meat_coverage": 1500,
    "meat_light_usage": 400,
    "open": 200,
    "close": 200,
    "round_clock_coverage": 200,
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


def _open_close_eligible_indices(ctx):
    """Pracownicy, dla których stary model OPEN/CLOSE w ogóle ma zastosowanie -
    wyklucza rotację całodobową "ogólną" (round_clock_constraint.py) i
    służbę 24/7 (duty_rotation_constraint.py), bo obu tych grup
    x[e,d,SHIFT_OPEN/CLOSE] jest zablokowane twardo przez ich własne bramy
    (add_round_clock_gate_constraint/add_duty_rotation_gate_constraint) -
    bez tego filtra "open"/"close" (MANDATORY domyślnie) żądałyby min_staff
    od pracowników, którzy strukturalnie NIE MOGĄ go spełnić, robiąc model
    niewykonalnym za każdym razem, gdy cały projekt (albo cały min_staff)
    opiera się wyłącznie na takiej lokalizacji."""
    return [
        e for e, emp in enumerate(ctx.employees)
        if not ctx.shop.get_location(emp).get_round_clock_start_hour()
        and not ctx.shop.get_location(emp).get_duty_rotation()
    ]


def _build_open(ctx, soft):
    min_open = ctx.shop.constraints.get("min_open_staff", 3)
    return add_fixed_staff_shift_constraints(
        ctx.model, ctx.x, ctx.employees, ctx.trade_days, ctx.shift_open, min_open,
        soft=soft, trace=ctx.trace,
        meat_light_penalties=ctx.extra["meat_light_penalties"],
        shift_duty_sum=ctx.extra["shift_duty_sum"],
        employee_indices=_open_close_eligible_indices(ctx),
    )


def _build_close(ctx, soft):
    min_close = ctx.shop.constraints.get("min_close_staff", 3)
    return add_fixed_staff_shift_constraints(
        ctx.model, ctx.x, ctx.employees, ctx.trade_days, ctx.shift_close, min_close,
        soft=soft, trace=ctx.trace,
        employee_indices=_open_close_eligible_indices(ctx),
        meat_light_penalties=ctx.extra["meat_light_penalties"],
        shift_duty_sum=ctx.extra["shift_duty_sum"],
    )


def _build_no_night(ctx, soft):
    return add_no_night_constraint(
        ctx.model, ctx.x, ctx.employees, ctx.days, ctx.shop, ctx.all_shifts,
        ctx.shift_open, ctx.shift_close, ctx.start_shift_map, ctx.end_shift_map,
        soft=soft, trace=ctx.trace, shift_night=ctx.shift_night,
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


def _build_round_clock_coverage(ctx, soft):
    return add_round_clock_coverage_constraint(
        ctx.model, ctx.x, ctx.employees, ctx.trade_days, ctx.shop, ctx.round_clock_shifts,
        ctx.shop.standard_daily_hours, soft=soft, trace=ctx.trace,
        meat_light_penalties=ctx.extra["meat_light_penalties"],
        shift_duty_sum=ctx.extra["shift_duty_sum"],
    )


def _build_dino_policy_specs():
    return [
        ConstraintSpec("open", _build_open),
        ConstraintSpec("close", _build_close),
        ConstraintSpec("no_night", _build_no_night),
        ConstraintSpec("no_afternoon", _build_no_afternoon),
        ConstraintSpec("meat", _build_meat),
        ConstraintSpec("meat_coverage", _build_meat_coverage),
        # Kafelki rotacji całodobowej "ogólnej" (round_clock_constraint.py) -
        # wyłącznie dla Dino, jak "open"/"close" (is_opener/is_meat to role
        # specyficzne dla tego profilu). Świadomie NIE dla profili custom
        # (np. Ochrona ma własny, dedykowany duty_rotation).
        ConstraintSpec("round_clock_coverage", _build_round_clock_coverage),
    ]


DINO_POLICY_SPECS = _build_dino_policy_specs()

# Always-on and the branch-neutral shop-level policies (rest/balance/
# availability/max_consecutive/monthly_hours) come from base_specs, shared
# with every other business profile; only the role-flag-specific ones above
# are Dino's own.
ALL_SPECS = base_specs.ALWAYS_ON_SPECS + base_specs.GENERIC_POLICY_SPECS + DINO_POLICY_SPECS


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
