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
from logic.generator.night_shift_constraint import (
    add_night_shift_gate_constraint,
    add_night_shift_adjacency_constraint,
)
from logic.generator.duty_rotation_constraint import (
    add_duty_rotation_gate_constraint,
    add_duty_rotation_no24h_gate_constraint,
    add_duty_rotation_coverage_constraint,
)
from logic.generator.duty_rotation_rest_constraint import add_duty_rotation_rest_constraint
from logic.generator.duty_rotation_manual_constraint import add_duty_rotation_manual_shift_constraint
from logic.generator.duty_rotation_manual_coverage import get_plan
from logic.generator.duty_rotation_public_holiday_constraint import add_duty_rotation_public_holiday_constraint
from logic.generator.round_clock_constraint import add_round_clock_gate_constraint
from logic.generator.round_clock_rest_constraint import add_round_clock_rest_constraint
from logic.generator.round_clock_manual_constraint import add_round_clock_manual_shift_constraint
from model.month_schedule import PREVIOUS_MONTH_MEMORY_ENABLED


GENERIC_WEIGHTS = {
    "rest_11h": 5000,
    "balance": 1000,
    "max_consecutive": 100,
    "monthly_hours": 250,
    "availability": 5000,
    "duty_rotation_coverage": 5000,
    "duty_rotation_no24h": 5000,
}

GENERIC_POLICY_LABELS = (
    ("rest_11h", "Odpoczynek 11 h"),
    ("availability", "Dostępność pracownika"),
    ("monthly_hours", "Godziny miesięczne"),
    ("balance", "Bilans godzin"),
    ("max_consecutive", "Dni pod rząd"),
    # duty_rotation_coverage/duty_rotation_no24h (GENERIC_WEIGHTS wyżej)
    # celowo NIE mają tu wpisu - to no-opy dla każdego projektu bez
    # skonfigurowanej duty_rotation (patrz komentarz w
    # ShopConfig.__init__), a pokazywanie tego przełącznika w "Zasadach
    # generatora" KAŻDEGO profilu (w tym Dino) byłoby myleniem UI czymś
    # nieistotnym dla niego - dokładnie to, czemu ma zapobiegać
    # RoleDef.linked_policy. Ekran do edycji tych dwóch polityk to zadanie
    # osobnego etapu UI (Etap D/E planu), na razie edytowalne tylko
    # programowo (ShopConfig.constraint_policies), domyślnie MANDATORY.
)


def _build_always_on_specs():
    return [
        ConstraintSpec(
            "non_trade_day",
            lambda ctx, soft: add_non_trade_day_constraints(
                ctx.model, ctx.x, ctx.employees, ctx.days, ctx.shop, ctx.all_shifts, trace=ctx.trace,
                schedule=ctx.schedule,
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
                ctx.shift_open, ctx.shift_close, ctx.start_shift_map, ctx.end_shift_map,
                trace=ctx.trace, shift_night=ctx.shift_night,
            ),
            always_on=True,
        ),
        ConstraintSpec(
            "work_dependency",
            lambda ctx, soft: add_work_dependency_constraint(
                ctx.model, ctx.x, ctx.employees, ctx.days, ctx.shift_open, ctx.shift_close, ctx.all_shifts,
                trace=ctx.trace, shift_night=ctx.shift_night, duty_shifts=ctx.duty_shifts,
                round_clock_shifts=ctx.round_clock_shifts,
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
        ConstraintSpec(
            # Structural fact ("this shift doesn't exist here"), not a
            # business preference - always hard, like non_trade_day above.
            # Etap C planu zmian nocnych.
            "night_shift_gate",
            lambda ctx, soft: add_night_shift_gate_constraint(
                ctx.model, ctx.x, ctx.employees, ctx.days, ctx.shop, ctx.shift_night, trace=ctx.trace
            ) if ctx.shift_night is not None else None,
            always_on=True,
        ),
        ConstraintSpec(
            # Structural fact (duty-rotation shift types and the old
            # OPEN/CLOSE/START/END/NIGHT model are mutually exclusive per
            # employee) - "plan profil ochrona", sekcja 12, Etap B.
            "duty_rotation_gate",
            lambda ctx, soft: add_duty_rotation_gate_constraint(
                ctx.model, ctx.x, ctx.employees, ctx.days, ctx.shop, ctx.duty_shifts, ctx.all_shifts, trace=ctx.trace
            ) if ctx.duty_shifts is not None else None,
            always_on=True,
        ),
        ConstraintSpec(
            # Ręczna blokada dnia dla pracowników rotacji 24/7 - równoległa
            # do "manual_shift" wyżej (ten sam wzorzec co
            # duty_rotation_rest_constraint obok add_rest_11h_constraint) -
            # patrz logic/generator/duty_rotation_manual_constraint.py.
            "duty_rotation_manual_shift",
            lambda ctx, soft: add_duty_rotation_manual_shift_constraint(
                ctx.model, ctx.x, ctx.employees, ctx.days, ctx.schedule, ctx.shop, ctx.duty_shifts, trace=ctx.trace
            ) if ctx.duty_shifts is not None else None,
            always_on=True,
        ),
        ConstraintSpec(
            # Zamyka lokalizacje z duty_rotation w polskie święta ustawowe,
            # per lokalizacja (LocationConfig.closed_on_public_holidays) -
            # patrz logic/generator/duty_rotation_public_holiday_constraint.py.
            "duty_rotation_public_holiday",
            lambda ctx, soft: add_duty_rotation_public_holiday_constraint(
                ctx.model, ctx.x, ctx.employees, ctx.days, ctx.schedule, ctx.shop, ctx.duty_shifts, trace=ctx.trace
            ) if ctx.duty_shifts is not None else None,
            always_on=True,
        ),
        ConstraintSpec(
            # Strukturalny fakt (jak duty_rotation_gate wyżej) - kafelki
            # rotacji całodobowej "ogólnej" (round_clock_constraint.py) i
            # stary model OPEN/CLOSE/START/END/NIGHT są wzajemnie wyłączne
            # per pracownik.
            "round_clock_gate",
            lambda ctx, soft: add_round_clock_gate_constraint(
                ctx.model, ctx.x, ctx.employees, ctx.days, ctx.shop, ctx.round_clock_shifts, ctx.all_shifts,
                ctx.shop.standard_daily_hours, trace=ctx.trace,
            ) if ctx.round_clock_shifts is not None else None,
            always_on=True,
        ),
        ConstraintSpec(
            # Ręczna blokada dnia dla pracowników rotacji całodobowej
            # "ogólnej" - równoległa do "manual_shift"/"duty_rotation_manual_shift"
            # wyżej, patrz logic/generator/round_clock_manual_constraint.py.
            "round_clock_manual_shift",
            lambda ctx, soft: add_round_clock_manual_shift_constraint(
                ctx.model, ctx.x, ctx.employees, ctx.days, ctx.schedule, ctx.shop, ctx.round_clock_shifts,
                ctx.shop.standard_daily_hours, trace=ctx.trace,
            ) if ctx.round_clock_shifts is not None else None,
            always_on=True,
        ),
    ]


def _build_rest_11h(ctx, soft):
    # "Pamięć poprzedniego miesiąca" (model/month_schedule.py::
    # PREVIOUS_MONTH_MEMORY_ENABLED) - gdy wyłączona, schedule=None sprawia,
    # że _add_previous_month_rest_constraint() w obu funkcjach niżej wychodzi
    # natychmiast, bez żadnego wpływu na dzień 1.
    prev_month_schedule = ctx.schedule if PREVIOUS_MONTH_MEMORY_ENABLED else None

    mode = ctx.shop.constraints.get("rest_11h_mode", "standard")
    if mode == "simplified":
        violations = add_rest_11h_constraint_simplified(
            ctx.model, ctx.x, ctx.employees, ctx.days, ctx.trade_days,
            ctx.shift_open, ctx.shift_close, ctx.start_shift_map, ctx.end_shift_map,
            shop=ctx.shop, schedule=prev_month_schedule, soft=soft, trace=ctx.trace,
        )
    else:
        violations = add_rest_11h_constraint(
            ctx.model, ctx.x, ctx.employees, ctx.days, ctx.trade_days, ctx.shop,
            ctx.shift_open, ctx.shift_close, ctx.start_shift_map, ctx.end_shift_map,
            schedule=prev_month_schedule, soft=soft, trace=ctx.trace,
        )

    # add_rest_11h_constraint(_simplified) builds its windows purely from
    # open/close hours (START/END_SHIFT_MAP) and has no idea SHIFT_NIGHT
    # exists, so it never constrains any pair involving it. This covers
    # exactly those pairs, alongside (not instead of) the above - see
    # logic/generator/night_shift_constraint.py.
    if ctx.shift_night is not None:
        violations = list(violations) + add_night_shift_adjacency_constraint(
            ctx.model, ctx.x, ctx.employees, ctx.days, ctx.shop, ctx.shift_night,
            ctx.shift_open, ctx.shift_close, ctx.start_shift_map, ctx.end_shift_map,
            soft=soft, trace=ctx.trace,
        )

    # Rotacja służby 24/7 (Etap C "plan profil ochrona") - ten sam wzorzec:
    # add_rest_11h_constraint nie buduje okien dla tych pięciu zmian w
    # ogóle, więc to dokłada się obok, nie modyfikuje istniejącej logiki.
    if ctx.duty_shifts is not None:
        violations = list(violations) + add_duty_rotation_rest_constraint(
            ctx.model, ctx.x, ctx.employees, ctx.days, ctx.shop, ctx.duty_shifts,
            schedule=prev_month_schedule, soft=soft, trace=ctx.trace,
        )

    # Rotacja całodobowa "ogólna" (round_clock_constraint.py) - ten sam
    # wzorzec: add_rest_11h_constraint nie buduje okien dla tych kafelków w
    # ogóle, więc to dokłada się obok, nie modyfikuje istniejącej logiki.
    if ctx.round_clock_shifts is not None:
        violations = list(violations) + add_round_clock_rest_constraint(
            ctx.model, ctx.x, ctx.employees, ctx.days, ctx.shop, ctx.round_clock_shifts,
            ctx.shop.standard_daily_hours, schedule=prev_month_schedule, soft=soft, trace=ctx.trace,
        )

    return violations


def _build_balance(ctx, soft):
    return add_balance_constraint(
        ctx.model, ctx.x, ctx.employees, ctx.days, ctx.schedule, ctx.shop, ctx.all_shifts,
        soft=soft, trace=ctx.trace, shift_night=ctx.shift_night, duty_shifts=ctx.duty_shifts,
    )


def _build_availability(ctx, soft):
    return add_availability_constraint(
        ctx.model, ctx.x, ctx.employees, ctx.days, ctx.shop, ctx.all_shifts,
        ctx.shift_open, ctx.shift_close, ctx.start_shift_map, ctx.end_shift_map,
        soft=soft, trace=ctx.trace, shift_night=ctx.shift_night, duty_shifts=ctx.duty_shifts,
        round_clock_shifts=ctx.round_clock_shifts,
    )


def _build_max_consecutive(ctx, soft):
    # Group employees by their resolved (project-wide, or per-location if
    # assigned) max_consecutive_days threshold, so each group gets its own
    # value while reusing the same shared constraint function per group -
    # with no locations (or all locations sharing the default), this is one
    # group with every employee, identical to before per-location support.
    groups: dict[int, list[int]] = {}
    for e, emp in enumerate(ctx.employees):
        value = ctx.shop.get_location(emp).constraints.get("max_consecutive_days", 4)
        groups.setdefault(value, []).append(e)

    # Ręczne wpisy pracowników rotacji służby, które plan pokrycia doby
    # traktuje jako stałe przedziały (x == 0 tego dnia, patrz
    # duty_rotation_manual_coverage.py), są dalej dniami pracy.
    plan = get_plan(ctx.duty_shifts) if ctx.duty_shifts is not None else None
    fixed_work_days = {}
    if plan is not None:
        for e, emp in enumerate(ctx.employees):
            fixed_days = {d for d, _start, _end in plan.fixed_intervals(emp)}
            if fixed_days:
                fixed_work_days[e] = fixed_days

    violations = []
    for max_consecutive, indices in groups.items():
        violations.extend(add_max_consecutive_constraint(
            ctx.model, ctx.x, ctx.employees, ctx.days, max_consecutive, ctx.all_shifts,
            soft=soft, trace=ctx.trace, employee_indices=indices, fixed_work_days=fixed_work_days,
        ))
    return violations


def _build_monthly_hours(ctx, soft):
    return add_monthly_hours_constraint(
        ctx.model, ctx.x, ctx.employees, ctx.days, ctx.schedule, ctx.shop, ctx.all_shifts,
        soft=soft, trace=ctx.trace, shift_night=ctx.shift_night, duty_shifts=ctx.duty_shifts,
    )


def _build_duty_rotation_coverage(ctx, soft):
    return add_duty_rotation_coverage_constraint(
        ctx.model, ctx.x, ctx.employees, ctx.days, ctx.shop, ctx.duty_shifts,
        soft=soft, trace=ctx.trace,
    )


def _build_duty_rotation_no24h(ctx, soft):
    return add_duty_rotation_no24h_gate_constraint(
        ctx.model, ctx.x, ctx.employees, ctx.days, ctx.duty_shifts,
        soft=soft, trace=ctx.trace,
    )


def _build_generic_policy_specs():
    return [
        ConstraintSpec("rest_11h", _build_rest_11h),
        ConstraintSpec("balance", _build_balance),
        ConstraintSpec("availability", _build_availability),
        ConstraintSpec("max_consecutive", _build_max_consecutive),
        ConstraintSpec("monthly_hours", _build_monthly_hours),
        ConstraintSpec(
            "duty_rotation_coverage",
            lambda ctx, soft: _build_duty_rotation_coverage(ctx, soft) if ctx.duty_shifts is not None else [],
        ),
        ConstraintSpec(
            "duty_rotation_no24h",
            lambda ctx, soft: _build_duty_rotation_no24h(ctx, soft) if ctx.duty_shifts is not None else [],
        ),
    ]


ALWAYS_ON_SPECS = _build_always_on_specs()
GENERIC_POLICY_SPECS = _build_generic_policy_specs()
