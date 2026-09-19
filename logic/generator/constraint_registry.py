"""Generic wiring between ShopConfig.constraint_policies and constraint builders.

Before this module, AutoScheduleGenerator.generate() called every constraint
builder by name with a hand-written MANDATORY/PREFERRED/DISABLED branch
(_apply_policy). That meant adding a constraint for a new business type meant
editing generate() directly. ConstraintContext bundles the shared solver state
so a ConstraintSpec.build callable only needs (ctx, soft) - business profiles
can then declare their own ordered list of ConstraintSpec objects and hand it
to apply_registry, without touching AutoScheduleGenerator.
"""

from dataclasses import dataclass, field
from typing import Callable

from model.constraint_policy import ConstraintPolicy


@dataclass
class ConstraintContext:
    model: object
    x: dict
    employees: list
    days: list
    trade_days: list
    schedule: object
    shop: object
    all_shifts: tuple
    shift_open: int
    shift_close: int
    start_shift_map: dict
    end_shift_map: dict
    trace: object
    # SHIFT_NIGHT (patrz logic/generator/night_shift_constraint.py) - None
    # dla dowolny kod konstruujący ConstraintContext sprzed Etapu C zmian
    # nocnych; AutoScheduleGenerator zawsze przekazuje tu konkretną wartość.
    shift_night: int | None = None
    # Pięć typów zmian rotacji 24/7 (np. ochrona) - patrz
    # logic/generator/duty_rotation_constraint.py i "plan profil ochrona
    # (analiza specyfikacji klienta).md", sekcja 12. Klucze:
    # "weekday_long"/"weekday_short"/"weekend_full"/"weekend_half_a"/
    # "weekend_half_b" (te same nazwy co w LocationConfig.duty_rotation).
    # None dla kodu sprzed tego mechanizmu; AutoScheduleGenerator zawsze
    # przekazuje tu konkretny słownik.
    duty_shifts: dict | None = None
    # Shared state a profile's constraints pass between each other (e.g. Dino's
    # meat-light duty budget). Empty/unused for profiles that don't need it.
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ConstraintSpec:
    name: str
    build: Callable[[ConstraintContext, bool], list]
    # Always executed as a hard constraint, outside the MANDATORY/PREFERRED/
    # DISABLED policy system (mirrors today's "always-on" calls in generate()).
    always_on: bool = False


def apply_registry(ctx: ConstraintContext, specs, weights: dict) -> list:
    """Run every ConstraintSpec against ctx.shop.constraint_policies.

    Returns the flat list of weighted soft-violation terms to feed into the
    objective, same shape _apply_policy used to return per-call.
    """
    all_soft_terms = []

    for spec in specs:
        if spec.always_on:
            print(f"[ALWAYS-ON] {spec.name}")
            spec.build(ctx, False)
            continue

        policy = ctx.shop.constraint_policies.get(spec.name)
        weight = weights.get(spec.name, 1)
        print(f"[POLICY] {spec.name} -> {policy}")

        if policy == ConstraintPolicy.MANDATORY:
            print(f"[HARD] {spec.name}")
            spec.build(ctx, False)
        elif policy == ConstraintPolicy.PREFERRED:
            print(f"[SOFT] {spec.name} weight={weight}")
            violations = spec.build(ctx, True)
            all_soft_terms.extend(weight * v for v in violations)
        # DISABLED (or unknown policy) -> constraint skipped entirely.

    return all_soft_terms
