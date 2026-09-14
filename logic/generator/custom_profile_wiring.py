"""Turns a CustomBusinessProfile (built by the profile wizard) into the same
(setup_context, specs, weights, build_objective_terms) shape
dino_retail_profile.py exposes, so AutoScheduleGenerator.generate() can treat
either the same way. Every custom profile gets the branch-neutral base specs
(rest/balance/availability/max_consecutive/monthly_hours + always-on calendar
mechanics) plus one ConstraintSpec per RuleInstance, built from the small
rule catalog in generic_rules.py.
"""

import functools

from logic.generator import base_specs, generic_rules
from logic.generator.constraint_registry import ConstraintSpec
from logic.generator.objective import (
    add_open_close_penalty,
    add_work_balance_penalty,
    add_workload_balance_penalty,
)
from model.custom_profile import CustomBusinessProfile


def setup_context(ctx) -> None:
    # No shared cross-constraint state (like Dino's meat-light budget) exists
    # for custom profiles today.
    pass


def build_specs(custom: CustomBusinessProfile) -> list[ConstraintSpec]:
    specs = list(base_specs.ALWAYS_ON_SPECS) + list(base_specs.GENERIC_POLICY_SPECS)

    for rule in custom.rules:
        builder = generic_rules.RULE_BUILDERS.get(rule.type)
        if builder is None:
            continue
        specs.append(ConstraintSpec(
            name=custom.rule_policy_key(rule),
            build=functools.partial(builder, role_key=rule.role_key, **rule.params),
        ))

    return specs


def build_weights(custom: CustomBusinessProfile) -> dict:
    weights = dict(base_specs.GENERIC_WEIGHTS)
    for rule in custom.rules:
        weights[custom.rule_policy_key(rule)] = rule.weight
    return weights


def default_policies(custom: CustomBusinessProfile) -> dict:
    """Policy defaults for a freshly-selected custom profile: MANDATORY rest,
    PREFERRED for the rest of the generic base, and whatever policy each rule
    was configured with in the wizard."""
    from model.constraint_policy import ConstraintPolicy

    policies = {
        "rest_11h": ConstraintPolicy.MANDATORY,
        "balance": ConstraintPolicy.PREFERRED,
        "availability": ConstraintPolicy.PREFERRED,
        "max_consecutive": ConstraintPolicy.PREFERRED,
        "monthly_hours": ConstraintPolicy.PREFERRED,
    }
    for rule in custom.rules:
        try:
            policies[custom.rule_policy_key(rule)] = ConstraintPolicy(rule.policy)
        except ValueError:
            policies[custom.rule_policy_key(rule)] = ConstraintPolicy.PREFERRED
    return policies


def build_policy_labels(custom: CustomBusinessProfile) -> tuple:
    labels = list(base_specs.GENERIC_POLICY_LABELS)
    for rule in custom.rules:
        labels.append((custom.rule_policy_key(rule), custom.rule_label(rule)))
    return tuple(labels)


def build_objective_terms(ctx, *_args, **_kwargs) -> list:
    """Branch-neutral schedule-quality terms only (spread work evenly) - no
    Dino-specific bonuses (edge-shift bonus, morning/afternoon balance)."""
    terms = []
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
