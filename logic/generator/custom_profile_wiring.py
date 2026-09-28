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
from logic.generator.afternoon_constraint import add_no_afternoon_constraint
from logic.generator.constraint_registry import ConstraintSpec
from logic.generator.duty_rotation_preference import add_prefer_weekend_split_over_full_penalty
from logic.generator.night_constraint import add_no_night_constraint
from logic.generator.objective import (
    add_open_close_penalty,
    add_work_balance_penalty,
    add_workload_balance_penalty,
)
from logic.generator.priority_hours_constraint import (
    HOURS_EQUALIZATION_LABEL,
    HOURS_EQUALIZATION_POLICY,
    NOMINAL_HOURS_NO_CONTRACT_LABEL,
    NOMINAL_HOURS_NO_CONTRACT_POLICY,
    add_hours_equalization_penalty,
    add_priority_hours_shortfall_penalty,
    hours_equalization_weight,
    nominal_hours_no_contract_weight,
)
from model.custom_profile import RULE_TYPE_MIN_STAFF_WITH_ROLE, CustomBusinessProfile


def setup_context(ctx) -> None:
    # No shared cross-constraint state (like Dino's meat-light budget) exists
    # for custom profiles today.
    pass


def _build_no_night(ctx, soft):
    return add_no_night_constraint(
        ctx.model, ctx.x, ctx.employees, ctx.days, ctx.shop, ctx.all_shifts,
        ctx.shift_open, ctx.shift_close, ctx.start_shift_map, ctx.end_shift_map,
        soft=soft, trace=ctx.trace, shift_night=ctx.shift_night, schedule=ctx.schedule,
    )


def _build_no_afternoon(ctx, soft):
    return add_no_afternoon_constraint(
        ctx.model, ctx.x, ctx.employees, ctx.days, ctx.all_shifts,
        ctx.shift_open, ctx.shift_close, ctx.start_shift_map, ctx.end_shift_map,
        soft=soft, trace=ctx.trace, schedule=ctx.schedule,
    )


def build_specs(custom: CustomBusinessProfile) -> list[ConstraintSpec]:
    specs = list(base_specs.ALWAYS_ON_SPECS) + list(base_specs.GENERIC_POLICY_SPECS)

    # "Nie pracuje w godzinach nocnych"/"Nie pracuje na popołudniu" -
    # przywrócone dla profili custom (Employee.no_night/no_afternoon,
    # patrz ui/employee_dialog.py) - te same constrainty co Dino
    # (dino_retail_profile.py), tylko wpięte tu zamiast tam. Zawsze no-opy
    # dla pracowników rotacji 24/7 (add_duty_rotation_gate_constraint i tak
    # zeruje im SHIFT_OPEN/CLOSE/START/END/NIGHT niezależnie od tego), więc
    # bezpieczne wpięcie niezależnie od tego, czy projekt używa duty_rotation.
    specs.append(ConstraintSpec("no_night", _build_no_night))
    specs.append(ConstraintSpec("no_afternoon", _build_no_afternoon))

    for rule in custom.rules:
        builder = generic_rules.RULE_BUILDERS.get(rule.type)
        if builder is None:
            continue
        rule_key = custom.rule_policy_key(rule)
        extra = {"rule_key": rule_key} if rule.type == RULE_TYPE_MIN_STAFF_WITH_ROLE else {}
        specs.append(ConstraintSpec(
            name=rule_key,
            build=functools.partial(builder, role_key=rule.role_key, **rule.params, **extra),
        ))

    return specs


def build_weights(custom: CustomBusinessProfile) -> dict:
    weights = dict(base_specs.GENERIC_WEIGHTS)
    # Te same wagi co Dino (dino_retail_profile.CONSTRAINT_WEIGHTS) - tylko
    # istotne gdy polityka poniżej zostanie ręcznie przełączona na PREFERRED.
    weights["no_night"] = 5000
    weights["no_afternoon"] = 5000
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
        # "Wyrównanie godzin umowa/bez" - domyślnie wyłączone (decyzja
        # użytkownika 2026-09-25), patrz priority_hours_constraint.py.
        HOURS_EQUALIZATION_POLICY: ConstraintPolicy.DISABLED,
        # "Nie pracuje w godzinach nocnych"/"Nie pracuje na popołudniu" -
        # MANDATORY: generator sam nigdy nie przydziela taką zmianę temu
        # pracownikowi (decyzja użytkownika 2026-09-28) - ręczne wpisy
        # nadal działają, patrz schedule=ctx.schedule w night_constraint.py/
        # afternoon_constraint.py.
        "no_night": ConstraintPolicy.MANDATORY,
        "no_afternoon": ConstraintPolicy.MANDATORY,
        # "Nominalny czas pracowników bez umowy" - domyślnie Preferowane
        # (decyzja użytkownika 2026-09-28), patrz priority_hours_constraint.py.
        NOMINAL_HOURS_NO_CONTRACT_POLICY: ConstraintPolicy.PREFERRED,
    }
    for rule in custom.rules:
        try:
            policies[custom.rule_policy_key(rule)] = ConstraintPolicy(rule.policy)
        except ValueError:
            policies[custom.rule_policy_key(rule)] = ConstraintPolicy.PREFERRED
    return policies


def build_policy_labels(custom: CustomBusinessProfile) -> tuple:
    labels = list(base_specs.GENERIC_POLICY_LABELS)
    labels.append((HOURS_EQUALIZATION_POLICY, HOURS_EQUALIZATION_LABEL))
    labels.append(("no_night", "Zakaz pracy nocnej"))
    labels.append(("no_afternoon", "Zakaz pracy popołudniami"))
    labels.append((NOMINAL_HOURS_NO_CONTRACT_POLICY, NOMINAL_HOURS_NO_CONTRACT_LABEL))
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

    # Priorytet "Umowa" (patrz priority_hours_constraint.py) - działa
    # niezależnie od tego, czy balance/monthly_hours są w ogóle włączone
    # dla tego profilu.
    terms.extend(add_priority_hours_shortfall_penalty(
        ctx.model, ctx.x, ctx.employees, ctx.days, ctx.schedule, ctx.shop, ctx.all_shifts,
        shift_night=ctx.shift_night, duty_shifts=ctx.duty_shifts,
    ))

    # "Nominalny czas pracowników bez umowy" (Konfiguracja -> Zasady
    # generatora, domyślnie Preferowane) - ten sam mechanizm co "Umowa"
    # wyżej (dobicie do nominału = nominał pełnego etatu * Wymiar etatu),
    # tylko dla pracowników BEZ roli "Umowa" i z niższą wagą (zawsze
    # "kolejni w kolejności" - patrz NOMINAL_HOURS_NO_CONTRACT_WEIGHT) oraz
    # przełączalne (Wyłączone = 0 = no-op).
    no_contract_weight = nominal_hours_no_contract_weight(
        ctx.shop.constraint_policies.get(NOMINAL_HOURS_NO_CONTRACT_POLICY)
    )
    if no_contract_weight:
        terms.extend(add_priority_hours_shortfall_penalty(
            ctx.model, ctx.x, ctx.employees, ctx.days, ctx.schedule, ctx.shop, ctx.all_shifts,
            shift_night=ctx.shift_night, duty_shifts=ctx.duty_shifts,
            invert=True, weight=no_contract_weight,
        ))

    # "Wyrównanie godzin umowa/bez" - zawsze miękkie (także "Wymagane",
    # tylko z większą wagą), brak wpisu w projekcie = wyłączone.
    terms.extend(add_hours_equalization_penalty(
        ctx.model, ctx.x, ctx.employees, ctx.days, ctx.schedule, ctx.shop, ctx.all_shifts,
        shift_night=ctx.shift_night, duty_shifts=ctx.duty_shifts,
        weight=hours_equalization_weight(ctx.shop.constraint_policies.get(HOURS_EQUALIZATION_POLICY)),
    ))

    # Preferencja 12h+12h zamiast 24h w weekend dla lokalizacji z rotacją
    # 24/7 (patrz duty_rotation_preference.py) - no-op dla projektów bez
    # duty_rotation (grupa pusta).
    if ctx.duty_shifts is not None:
        terms.extend(add_prefer_weekend_split_over_full_penalty(
            ctx.model, ctx.x, ctx.employees, ctx.days, ctx.shop, ctx.duty_shifts,
        ))

    return terms
