"""Generic, data-driven constraint builders for custom (user-authored)
business profiles - the fixed catalog of rule "templates" the profile wizard
lets a client compose from. Each function has the same (ctx, soft, ...)
shape as a ConstraintSpec.build callable (see constraint_registry.py) and is
parameterized by role key / thresholds / time window instead of any
hard-coded Dino role.

These intentionally do NOT touch or reuse constraints_staff.py /
night_constraint.py / afternoon_constraint.py, which stay Dino-only - keeping
this module fully separate means nothing here can regress the already
verified dino_retail behavior.
"""

from datetime import datetime, timedelta

from logic.generator.constraints_basic import is_location_open_for_employee
from logic.utils.time_utils import (
    daily_windows_overlap,
    get_effective_daily_hours,
    hour_window_overlaps_time_range,
)

FMT = "%H:%M"


def _role_employee_indices(ctx, role_key):
    return [e for e, emp in enumerate(ctx.employees) if emp.has_role(role_key)]


def build_min_staff_with_role(ctx, soft, role_key, rule_key, min_count=1, scope="open"):
    """"At least `min_count` employees with role `role_key` [on open / on
    close / working at any point that day]." Generalizes the is_opener/
    is_meat >= 1 checks baked into constraints_staff.add_fixed_staff_shift_constraints.

    A location can override the threshold for this specific rule via
    LocationConfig.constraints[rule_key] (rule_key = the same "rule:<id>"
    string used as this ConstraintSpec's policy name) - same per-location
    override mechanism as max_consecutive_days
    (base_specs._build_max_consecutive). Employees are grouped by their
    resolved threshold so e.g. "min. 2 uzbrojonych" can differ per obiekt.
    """
    violations = []
    role_employees = _role_employee_indices(ctx, role_key)

    if scope == "open":
        shifts_by_day = lambda d: (ctx.shift_open,)
    elif scope == "close":
        shifts_by_day = lambda d: (ctx.shift_close,)
    elif scope == "night":
        # Etap F planu zmian nocnych - liczy wyłącznie SHIFT_NIGHT, nie
        # "any_shift" (który już i tak liczy noc razem z dniem). Dla
        # lokalizacji bez skonfigurowanego night_shift SHIFT_NIGHT jest
        # zawsze 0 (bramka z Etapu C) - reguła wtedy słusznie sygnalizuje
        # niespełnialność zamiast cicho nic nie sprawdzać.
        shifts_by_day = lambda d: (ctx.shift_night,)
    else:  # "any_shift"
        shifts_by_day = lambda d: ctx.all_shifts

    if role_employees:
        groups: dict[int, list[int]] = {}
        for e in role_employees:
            threshold = ctx.shop.get_location(ctx.employees[e]).constraints.get(rule_key, min_count)
            groups.setdefault(threshold, []).append(e)
    else:
        # No employee has this role at all - still enforce (or flag) the
        # base threshold against zero people, same as before per-location
        # grouping existed.
        groups = {min_count: []}

    for threshold, indices in groups.items():
        for d in ctx.trade_days:
            # Dzień zostaje w trade_days, gdy czynna jest KTÓRAKOLWIEK
            # lokalizacja - ale gdy placówki wszystkich osób z tej grupy są
            # tego dnia zamknięte, add_non_trade_day_constraints blokuje im
            # każdą zmianę i wymóg byłby niespełnialny (cały miesiąc bez
            # rozwiązania). Pusta grupa (nikt nie ma roli) nadal sygnalizuje
            # brak, tak jak wcześniej.
            if indices and not any(
                is_location_open_for_employee(ctx.shop, ctx.employees[e], d) for e in indices
            ):
                continue
            shifts = shifts_by_day(d)
            terms = [ctx.x[e, d, s] for e in indices for s in shifts]
            count = sum(terms) if terms else ctx.model.NewConstant(0)

            if not soft:
                ctx.model.Add(count >= threshold)
            else:
                violation = ctx.model.NewIntVar(0, threshold, f"role_staff_v_{role_key}_{scope}_d{d}_t{threshold}")
                ctx.model.Add(count + violation >= threshold)
                violations.append(violation)

    return violations


def _shift_touches_window(start_dt, end_dt, window_start_hour, window_end_hour):
    """True gdy zmiana [start_dt, end_dt) (bez zawijania - zob. moduł
    time_utils.py) pokrywa się choć trochę z powtarzającym się codziennie
    oknem [window_start_hour, window_end_hour) - poprawne niezależnie od
    tego, czy TO okno zawija się przez północ (np. 22-6, jak domyślne
    no_night) czy nie (np. 10-12, dowolne okno z kreatora profili custom).
    Deleguje do daily_windows_overlap (tej samej pary funkcji co
    hour_window_overlaps_time_range używane niżej dla SHIFT_NIGHT) zamiast
    osobnej heurystyki godzinowej.

    Codex review finding on this PR: poprzednia wersja porównywała tylko
    end.hour/start.hour względem progów (nawet po naprawieniu zamienionych
    miejscami progów) - poprawna wyłącznie dla okien zawijających się przez
    północ. Dla niezawijającego się okna (np. "brak pracy 10:00-12:00")
    `end.hour >= 10 or start.hour <= 12` jest prawdą dla niemal każdej
    normalnej zmiany, więc reguła zabraniałaby roli pracy w ogóle.
    """
    start_minutes = start_dt.hour * 60 + start_dt.minute
    end_minutes = end_dt.hour * 60 + end_dt.minute
    return daily_windows_overlap(
        start_minutes, end_minutes,
        window_start_hour * 60, window_end_hour * 60,
    )


def forbidden_shifts_for_time_window(
    hours_source, day, shift_delta, window_start_hour, window_end_hour,
    shift_open, shift_close, start_shift_map, end_shift_map,
):
    """Which OPEN/CLOSE/START/END shift ids on `day` touch the
    [window_start_hour, window_end_hour) o'clock window, for an employee
    whose shift lasts `shift_delta`. SHIFT_NIGHT is deliberately not handled
    here - it has its own fixed window independent of `day`/`hours_source`,
    so each caller adds it separately (see build_role_time_restriction below
    and logic/generator/night_constraint.py::add_no_night_constraint).

    Shared by both of those - before this, each carried its own copy of this
    exact computation, and the same conceptual bug ("does this constraint
    know about SHIFT_NIGHT / a locked manual shift") had to be found and
    fixed independently in each (see night_constraint.py's module history).
    `hours_source` is duck-typed (`shop` or `shop.get_location(emp)`, see
    model.shop_config._LocationView) so each caller keeps its own choice of
    whether the restriction is location-aware.
    """
    forbidden = set()

    hours = hours_source.get_open_hours_for_day(day)
    if not hours:
        return forbidden

    open_time, close_time = hours
    open_dt = datetime.strptime(open_time, FMT)
    close_dt = datetime.strptime(close_time, FMT)

    start, end = open_dt, open_dt + shift_delta
    if _shift_touches_window(start, end, window_start_hour, window_end_hour):
        forbidden.add(shift_open)

    start, end = close_dt - shift_delta, close_dt
    if _shift_touches_window(start, end, window_start_hour, window_end_hour):
        forbidden.add(shift_close)

    for shift, offset in start_shift_map.items():
        start = open_dt + timedelta(minutes=offset)
        end = start + shift_delta
        if _shift_touches_window(start, end, window_start_hour, window_end_hour):
            forbidden.add(shift)

    for shift, offset in end_shift_map.items():
        end = close_dt - timedelta(minutes=offset)
        start = end - shift_delta
        if _shift_touches_window(start, end, window_start_hour, window_end_hour):
            forbidden.add(shift)

    return forbidden


def build_role_time_restriction(ctx, soft, role_key, window_start_hour=22, window_end_hour=6):
    """Employees with role `role_key` can't be scheduled on a shift that
    touches [window_start_hour, window_end_hour) o'clock. Generalizes
    no_night/no_afternoon (night_constraint.py/afternoon_constraint.py)."""
    violations = []
    role_employees = set(_role_employee_indices(ctx, role_key))
    if not role_employees:
        return violations

    for e in role_employees:
        emp = ctx.employees[e]
        eff_hours = get_effective_daily_hours(emp, ctx.shop)
        shift_delta = timedelta(hours=eff_hours)
        location = ctx.shop.get_location(emp)

        # SHIFT_NIGHT (Etap C planu zmian nocnych) ma własne, stałe okno
        # niezależne od godzin otwarcia konkretnego dnia (w odróżnieniu od
        # OPEN/CLOSE/START/END poniżej) - sprawdzane raz, poza pętlą po
        # dniach, tak jak w add_no_night_constraint.
        night_hours = location.get_night_shift_hours() if ctx.shift_night is not None else None
        night_restricted = night_hours is not None and hour_window_overlaps_time_range(
            window_start_hour, window_end_hour, night_hours
        )

        for d in ctx.days:
            forbidden_shifts = forbidden_shifts_for_time_window(
                location, d, shift_delta, window_start_hour, window_end_hour,
                ctx.shift_open, ctx.shift_close, ctx.start_shift_map, ctx.end_shift_map,
            )

            if night_restricted:
                forbidden_shifts.add(ctx.shift_night)

            for s in forbidden_shifts:
                if soft:
                    v = ctx.model.NewBoolVar(f"role_time_v_{role_key}_e{e}_d{d}_s{s}")
                    ctx.model.Add(ctx.x[e, d, s] <= v)
                    violations.append(v)
                else:
                    ctx.model.Add(ctx.x[e, d, s] == 0)

    return violations


RULE_BUILDERS = {
    "min_staff_with_role": build_min_staff_with_role,
    "role_time_restriction": build_role_time_restriction,
}
