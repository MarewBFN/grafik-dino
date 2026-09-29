"""Repeatable, human-readable diagnostics for the CP-SAT schedule generator.

The solver does not expose a "constraint changed this assignment" event.  This
module therefore solves progressively larger versions of the model and records
the difference between consecutive solutions.  The report deliberately calls
that a *stage impact*, rather than a proof of causality: CP-SAT may have several
equally good schedules.
"""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta
import io
import json
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

from ortools.sat.python import cp_model

from logic.utils.time_utils import get_effective_daily_hours
from model.constraint_policy import ConstraintPolicy


POLICY_STAGES = (
    "open",
    "close",
    "rest_11h",
    "balance",
    "availability",
    "no_night",
    "no_afternoon",
    "meat",
    "meat_coverage",
    "max_consecutive",
    "monthly_hours",
    "opening_hours_coverage",
    "max_staff_at_once",
)


def _status_name(status: int) -> str:
    return {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.MODEL_INVALID: "MODEL_INVALID",
        cp_model.UNKNOWN: "UNKNOWN",
    }.get(status, str(status))


def _cell_value(day_state: Any) -> str:
    if day_state.is_leave:
        return "LEAVE"
    if getattr(day_state, "is_sick", False):
        return "SICK"
    if getattr(day_state, "is_day_off", False):
        return "DAY_OFF"
    if day_state.start and day_state.end:
        return f"{day_state.start}-{day_state.end}"
    if day_state.is_locked:
        return "LOCKED_OFF"
    return "OFF"


def schedule_snapshot(schedule) -> dict[str, dict[str, str]]:
    """Return an employee/day matrix that is easy to inspect in JSON."""
    return {
        employee.display_name(): {
            str(day): _cell_value(schedule.get_day(employee, day))
            for day in range(1, schedule.days_in_month + 1)
        }
        for employee in schedule.employees
    }


def snapshot_diff(before: dict[str, dict[str, str]] | None, after: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    if before is None:
        return []
    changes = []
    for employee, days in after.items():
        for day, value in days.items():
            old_value = before.get(employee, {}).get(day)
            if old_value != value:
                changes.append({"employee": employee, "day": day, "before": old_value, "after": value})
    return changes


def _minutes_between(end_day: int, end_time: str, next_day: int, next_time: str, year: int, month: int) -> int:
    fmt = "%Y-%m-%d %H:%M"
    end = datetime.strptime(f"{year}-{month:02d}-{end_day:02d} {end_time}", fmt)
    start = datetime.strptime(f"{year}-{month:02d}-{next_day:02d} {next_time}", fmt)
    return int((start - end).total_seconds() // 60)


def audit_schedule(schedule, shop) -> dict[str, Any]:
    """Independently verify the two most failure-prone rules after a solve."""
    nominal_minutes = shop.get_full_time_nominal_hours() * 60
    monthly = []
    rest_violations = []

    for employee in schedule.employees:
        effective_minutes = int(get_effective_daily_hours(employee, shop) * 60)
        leave_or_sick = sum(
            1
            for day in range(1, schedule.days_in_month + 1)
            if (ds := schedule.get_day(employee, day)).is_leave or getattr(ds, "is_sick", False)
        )
        target = int(nominal_minutes * employee.employment_fraction) - leave_or_sick * effective_minutes
        worked = 0
        for day in range(1, schedule.days_in_month + 1):
            duration = schedule.get_day(employee, day).total_duration()
            if duration:
                worked += int(duration.total_seconds() // 60)
        monthly.append({
            "employee": employee.display_name(),
            "worked_minutes": worked,
            "target_minutes": target,
            "difference_minutes": worked - target,
            "leave_or_sick_days": leave_or_sick,
        })

        for day in range(1, schedule.days_in_month):
            today = schedule.get_day(employee, day)
            tomorrow = schedule.get_day(employee, day + 1)
            if not (today.end and tomorrow.start):
                continue
            # Zmiana nocna kończy się w kolejnej dobie kalendarzowej z
            # definicji - bez tego przesunięcia _minutes_between liczyłby
            # odpoczynek o 24h za dużo i nigdy nie wykryłby realnego
            # naruszenia po zmianie nocnej.
            end_day = day + 1 if today.crosses_midnight() else day
            rest = _minutes_between(end_day, today.end, day + 1, tomorrow.start, schedule.year, schedule.month)
            if rest < 11 * 60:
                rest_violations.append({
                    "employee": employee.display_name(),
                    "days": f"{day}->{day + 1}",
                    "rest_minutes": rest,
                    "required_minutes": 660,
                    "shifts": f"{today.start}-{today.end} / {tomorrow.start}-{tomorrow.end}",
                })

    return {"monthly_hours": monthly, "rest_11h_violations": rest_violations}


def preflight_supply(schedule, shop) -> list[dict[str, Any]]:
    """Static input facts that commonly explain an infeasible staffing model."""
    report = []
    for day in range(1, schedule.days_in_month + 1):
        if not shop.is_trade_day(day):
            continue
        available = []
        locked = []
        for employee in schedule.employees:
            state = schedule.get_day(employee, day)
            if state.is_leave or getattr(state, "is_sick", False) or getattr(state, "is_day_off", False):
                continue
            available.append(employee)
            if state.is_locked:
                locked.append({
                    "employee": employee.display_name(),
                    "shift": _cell_value(state),
                })
        report.append({
            "day": day,
            "available_employees": len(available),
            "available_openers": sum(employee.is_opener for employee in available),
            "available_meat_staff": sum(employee.is_meat for employee in available),
            "available_meat_light_staff": sum(employee.is_meat_light for employee in available),
            "min_open_staff": shop.constraints.get("min_open_staff", 3),
            "min_close_staff": shop.constraints.get("min_close_staff", 3),
            "locked_assignments": locked,
        })
    return report


def _previous_month_rest_gap_hours(schedule, employee, target_time: str, fmt: str = "%H:%M") -> float | None:
    """Godziny odpoczynku między końcem zmiany z poprzedniego miesiąca (patrz
    model/month_schedule.py::PreviousMonthShiftEnd) a `target_time` w dniu 1
    tego miesiąca - None, gdy dla tego pracownika nie ma takiej pamięci.
    Ta sama arytmetyka co logic/generator/rest_constraint.py::_anchor."""
    carry = schedule.get_previous_month_end_shift(employee)
    if carry is None:
        return None
    end = datetime.strptime(carry.end, fmt)
    target = datetime.strptime(target_time, fmt)
    end_dt = datetime(2000, 1, 1, end.hour, end.minute) + timedelta(days=0 if carry.crosses_midnight else -1)
    target_dt = datetime(2000, 1, 1, target.hour, target.minute)
    return (target_dt - end_dt).total_seconds() / 3600


TIMEOUT_MESSAGE = (
    "Generator nie znalazł grafiku w limicie czasu ({limit} s) - to nie musi "
    "oznaczać sprzecznych zasad. Zwiększ „Limit czasu generatora” "
    "(Konfiguracja → Zasady generatora → ustawienia zaawansowane) i spróbuj ponownie."
)


def build_infeasibility_summary(schedule, shop, timed_out=False) -> list[str]:
    """Return client-readable causes that can be proven from the input data.

    timed_out=True (solver skończył limit czasu bez żadnego rozwiązania,
    status UNKNOWN - a nie udowodnił sprzeczności): gdy z danych nie da się
    dowieść żadnej konkretnej przyczyny, zamiast "Wymagane zasady są ze sobą
    sprzeczne" (nieprawda - audyt 2026-09-28) zwracany jest komunikat o
    limicie czasu."""
    messages: list[str] = []
    policies = shop.constraint_policies
    min_open = shop.constraints.get("min_open_staff", 3)
    min_close = shop.constraints.get("min_close_staff", 3)

    def add(message: str) -> None:
        if message not in messages and len(messages) < 6:
            messages.append(message)

    _add_duty_rotation_supply_messages(schedule, shop, add)
    _add_opening_hours_supply_messages(schedule, shop, add)
    _add_opening_hours_shift_class_messages(schedule, shop, add)

    # Obsada otwarcia/zamknięcia/mięsa to reguły wyłącznie profilu Dino
    # (dino_retail_profile.py) i wyłącznie pracowników bez rotacji służby /
    # rotacji całodobowej. Wcześniej te komunikaty ("brak pracownika
    # otwarcia...") pojawiały się też dla projektu ochrony, którego
    # prawdziwą przyczyną był np. urlop całej obsady jednej placówki.
    from model.business_profile import DEFAULT_BUSINESS_TYPE

    open_close_employees = [
        employee for employee in schedule.employees
        if not shop.get_location(employee).get_duty_rotation()
        and not shop.get_location(employee).get_round_clock_start_hour()
    ]
    check_open_close = shop.business_type == DEFAULT_BUSINESS_TYPE and bool(open_close_employees)

    for day in range(1, schedule.days_in_month + 1):
        if not check_open_close:
            break
        if not shop.is_trade_day(day):
            continue
        hours = shop.get_open_hours_for_day(day)
        if not hours:
            continue

        open_time, close_time = hours
        for policy_name, target_time, required, label in (
            ("open", open_time, min_open, "otwarciu"),
            ("close", close_time, min_close, "zamknięciu"),
        ):
            if policies.get(policy_name) != ConstraintPolicy.MANDATORY:
                continue

            fixed = []
            possible = []
            blocked_by_previous_month = []
            for employee in open_close_employees:
                state = schedule.get_day(employee, day)
                if state.is_leave or getattr(state, "is_sick", False) or getattr(state, "is_day_off", False):
                    continue
                matches = state.start == target_time if policy_name == "open" else state.end == target_time
                if state.is_locked:
                    if matches:
                        fixed.append(employee)
                    continue

                # Dzień 1 jest jedynym, gdzie "pamięć poprzedniego miesiąca"
                # (patrz PreviousMonthShiftEnd) może wykluczyć kogoś, kto
                # inaczej wyglądałby na "możliwego" - bez tego ta funkcja
                # nie tłumaczyła w ogóle, że to ona jest przyczyną
                # niewykonalności (patrz logic/generator/rest_constraint.py::
                # _add_previous_month_rest_constraint, ta sama arytmetyka).
                if day == 1:
                    gap = _previous_month_rest_gap_hours(schedule, employee, target_time)
                    if gap is not None and gap < 11:
                        blocked_by_previous_month.append(employee)
                        continue

                possible.append(employee)

            if len(fixed) > required:
                add(
                    f"Dzień {day}: zablokowano {len(fixed)} osoby na {label}, "
                    f"a wymagane są dokładnie {required}."
                )
            elif len(fixed) + len(possible) < required and blocked_by_previous_month:
                add(
                    f"Dzień {day}: pamięć poprzedniego miesiąca blokuje "
                    f"{len(blocked_by_previous_month)} os. z wymaganych do pracy na {label} "
                    "(przerwa do końca ich ostatniej zmiany poprzedniego miesiąca jest "
                    "krótsza niż 11h) - sprawdź Edycja -> \"Godziny zakończenia z "
                    "poprzedniego miesiąca...\"."
                )
            elif len(fixed) + len(possible) < required:
                add(
                    f"Dzień {day}: za mało osób możliwych do pracy na {label} "
                    f"({len(fixed) + len(possible)} z wymaganych {required})."
                )
            elif not any(employee.is_opener for employee in fixed + possible):
                add(f"Dzień {day}: brak pracownika otwarcia możliwego do pracy na {label}.")
            elif not any(employee.is_meat or employee.is_meat_light for employee in fixed + possible):
                add(f"Dzień {day}: brak osoby z uprawnieniem mięso (ani zastępczej) możliwej do pracy na {label}.")

        if policies.get("meat_coverage") == ConstraintPolicy.MANDATORY:
            available_meat = [
                employee for employee in open_close_employees
                if (employee.is_meat or employee.is_meat_light)
                and not schedule.get_day(employee, day).is_leave
                and not getattr(schedule.get_day(employee, day), "is_sick", False)
                and not getattr(schedule.get_day(employee, day), "is_day_off", False)
            ]
            if not available_meat:
                add(f"Dzień {day}: brak dostępnej osoby z uprawnieniem mięso (ani zastępczej) na cały dzień.")

    if policies.get("rest_11h") == ConstraintPolicy.MANDATORY:
        fmt = "%H:%M"
        for employee in schedule.employees:
            for day in range(1, schedule.days_in_month):
                if not (shop.is_trade_day(day) and shop.is_trade_day(day + 1)):
                    continue
                today = schedule.get_day(employee, day)
                tomorrow = schedule.get_day(employee, day + 1)
                if not (today.is_locked and tomorrow.is_locked and today.end and tomorrow.start):
                    continue
                end = datetime.strptime(today.end, fmt)
                start = datetime.strptime(tomorrow.start, fmt)
                rest = start - end
                if rest.total_seconds() < 0:
                    rest += timedelta(days=1)
                if rest < timedelta(hours=11):
                    hours = rest.total_seconds() / 3600
                    add(
                        f"{employee.display_name()}, dni {day}–{day + 1}: "
                        f"zablokowana przerwa wynosi tylko {hours:.2f} h (wymagane 11 h)."
                    )

    if not messages and timed_out:
        add(TIMEOUT_MESSAGE.format(limit=shop.constraints.get("solver_time_limit_seconds", 60)))
    if not messages:
        add(
            "Wymagane zasady są ze sobą sprzeczne. Sprawdź zablokowane zmiany, "
            "dostępność pracowników oraz wymagania dla danego dnia."
        )
    return messages


def _add_opening_hours_supply_messages(schedule, shop, add) -> None:
    """"Obłożenie godzin otwarcia" (Ochrona, placówki bez rotacji - patrz
    logic/generator/opening_hours_coverage.py): dowodliwe z samych danych
    przyczyny, gdy obłożenie jest Wymagane - w dniu okna nikt z placówki
    nie jest dostępny; jedyna dostępna osoba na dobę sob/nd ma „Nie chce
    24h” (a do dwóch połówek trzeba dwóch osób); dwa kolejne okna dzieli
    mniej niż 11 h odpoczynku, a dostępna jest na nie tylko jedna osoba."""
    from logic.generator.opening_hours_coverage import (
        DAY,
        MIN_REST_MINUTES,
        OPENING_HOURS_COVERAGE_POLICY,
        _has_no24h_role,
        fmt_minutes,
        is_regular_location,
        location_windows,
        uses_opening_hours_model,
    )

    if not uses_opening_hours_model(shop):
        return
    policies = shop.constraint_policies
    if policies.get(OPENING_HOURS_COVERAGE_POLICY, ConstraintPolicy.MANDATORY) != ConstraintPolicy.MANDATORY:
        return

    by_location = {}
    for employee in schedule.employees:
        if is_regular_location(shop.get_location(employee)):
            by_location.setdefault(employee.location_key, []).append(employee)

    for location_key, employees in by_location.items():
        location = shop.locations.get(location_key)
        name = location.name if location is not None else location_key
        view = shop.get_location(employees[0])
        windows = location_windows(view, shop.year, shop.month, schedule.days_in_month)
        previous = None
        for day, window in sorted(windows.items()):
            available = [e for e in employees if not _is_unavailable(schedule.get_day(e, day))]
            base = (day - 1) * DAY
            span = f"{fmt_minutes(window.start - base)}–{fmt_minutes(window.end - base)}"
            if not available:
                add(
                    f"{name}, dzień {day}: nikt z pracowników placówki nie jest dostępny "
                    f"(urlop/L4/wolne), a okno {span} wymaga obsady (zasada „Obłożenie "
                    "godzin otwarcia” jest Wymagana)."
                )
            elif (
                window.is_full_day
                and shop.weekday(day) >= 5
                and len(available) == 1
                and _has_no24h_role(available[0])
                and policies.get("duty_rotation_no24h", ConstraintPolicy.MANDATORY) == ConstraintPolicy.MANDATORY
            ):
                add(
                    f"{name}, dzień {day}: dostępna jest tylko 1 osoba "
                    f"({available[0].display_name()}), a ma zaznaczone „Nie chce zmian 24h” - "
                    "doby nie da się obsadzić (dwie połówki wymagają dwóch osób)."
                )
            if (
                previous is not None
                and policies.get("rest_11h", ConstraintPolicy.MANDATORY) == ConstraintPolicy.MANDATORY
            ):
                prev_day, prev_window, prev_available = previous
                gap = window.start - prev_window.end
                people = {e.id for e in prev_available} | {e.id for e in available}
                if gap < MIN_REST_MINUTES and len(people) == 1 and prev_available and available:
                    add(
                        f"{name}, dni {prev_day}–{day}: między oknami jest tylko {gap / 60:g} h "
                        f"przerwy, a dostępna jest wyłącznie 1 osoba ({available[0].display_name()}) - "
                        "za mało osób na obłożenie przy odpoczynku 11 h."
                    )
            previous = (day, window, available)


def _add_opening_hours_shift_class_messages(schedule, shop, add) -> None:
    """Typ zmiany „W”/„1”/„2” (musi pracować) u pracownika placówki z
    godzinami otwarcia (Ochrona), gdy żadna zmiana tego dnia nie przechodzi
    Wymaganych zasad tej osoby: „Nie pracuje w nocy”/„na popołudniu”, „Nie
    chce 24h”, odpoczynek od jej ręcznych wpisów (albo zmiany z końca
    poprzedniego miesiąca) albo „Maks. obsada naraz” zajęta ręcznymi
    wpisami innych. Te same kształty zmian co generator
    (opening_hours_coverage.OpeningHoursModel)."""
    from types import SimpleNamespace

    from logic.generator.opening_hours_coverage import (
        AFTERNOON_START,
        DAY,
        MAX_STAFF_POLICY,
        MIN_REST_MINUTES,
        OPENING_HOURS_COVERAGE_POLICY,
        OpeningHoursModel,
        _has_no24h_role,
        _minutes,
        _overlaps_night,
        uses_opening_hours_model,
    )
    from model.month_schedule import PREVIOUS_MONTH_MEMORY_ENABLED

    if not uses_opening_hours_model(shop):
        return
    policies = shop.constraint_policies

    def mandatory(name, default=ConstraintPolicy.PREFERRED):
        return policies.get(name, default) == ConstraintPolicy.MANDATORY

    ctx = SimpleNamespace(
        shop=shop, days=list(range(1, schedule.days_in_month + 1)), employees=list(schedule.employees),
        round_clock_shifts=list(range(20, 26)), schedule=schedule, extra={},
    )
    model = OpeningHoursModel(ctx)

    manual = {}  # e -> [(start, end)] ręczne wpisy (dopasowane i stałe)
    for e in model.indices:
        rows = [(s, en) for _d, s, en in model.fixed.get(e, ())]
        rows += [
            (model.shape(e, d, sid).start, model.shape(e, d, sid).end)
            for (ee, d), sid in model.manual_shift.items() if ee == e
        ]
        manual[e] = rows

    classed = {}  # e -> [(dzień, typ zmiany, {id: Shape})] - zmiany, z których generator musi wybrać
    for e in model.indices:
        emp = ctx.employees[e]
        key = model.location_of[e]
        others = [iv for o in model.members[key] if o != e for iv in manual[o]]
        carry = schedule.get_previous_month_end_shift(emp) if PREVIOUS_MONTH_MEMORY_ENABLED else None
        for d in ctx.days:
            state = schedule.get_day(emp, d)
            cls = getattr(state, "shift_class", None)
            if cls not in ("W", "1", "2") or _is_unavailable(state) or state.is_locked:
                continue
            allowed = model.allowed(e, d)
            if not allowed:
                continue
            if cls in ("1", "2"):
                base = (d - 1) * DAY
                morning = {sid for sid, sh in allowed.items() if sh.start - base < AFTERNOON_START}
                chosen = morning if cls == "1" else set(allowed) - morning
                allowed = {sid: allowed[sid] for sid in chosen} or allowed
            classed.setdefault(e, []).append((d, cls, allowed))

            reasons = set()

            def blocked(sh):
                hit = False
                if mandatory("no_night") and getattr(emp, "no_night", False) and _overlaps_night(sh.start, sh.end):
                    reasons.add("„Nie pracuje w godzinach nocnych”")
                    hit = True
                if (
                    mandatory("no_afternoon") and getattr(emp, "no_afternoon", False)
                    and sh.start - (d - 1) * DAY >= AFTERNOON_START
                ):
                    reasons.add("„Nie pracuje na popołudniu”")
                    hit = True
                if (
                    mandatory("duty_rotation_no24h", ConstraintPolicy.MANDATORY) and _has_no24h_role(emp)
                    and sh.length >= DAY and shop.weekday(sh.window_day) >= 5
                ):
                    reasons.add("„Nie chce 24h”")
                    hit = True
                if mandatory("rest_11h", ConstraintPolicy.MANDATORY):
                    for m_start, m_end in manual[e]:
                        before = model.required_rest_after(key, sh.length)
                        after = model.required_rest_after(key, m_end - m_start)
                        if (sh.start < m_end + after) and (m_start < sh.end + before):
                            reasons.add("odpoczynek od ręcznego wpisu tej osoby")
                            hit = True
                    if carry is not None and carry.end:
                        end_prev = _minutes(carry.end) - (0 if carry.crosses_midnight else DAY)
                        if sh.start - end_prev < MIN_REST_MINUTES:
                            reasons.add("odpoczynek po zmianie z końca poprzedniego miesiąca")
                            hit = True
                if mandatory(MAX_STAFF_POLICY) and others:
                    cap = model.max_staff(key)
                    points = sorted({sh.start} | {p for iv in others for p in iv if sh.start < p < sh.end})
                    for t in points:
                        if sum(1 for a, b in others if a <= t < b) >= cap:
                            reasons.add("„Maks. obsada naraz” zajęta ręcznymi wpisami innych osób")
                            hit = True
                            break
                return hit

            if all([blocked(sh) for sh in allowed.values()]):
                add(
                    f"{emp.display_name()}, dzień {d}: typ zmiany „{cls}” wymaga przydzielenia zmiany, "
                    f"a żadna zmiana tego dnia nie jest dozwolona ({', '.join(sorted(reasons))} - "
                    "zasady Wymagane)."
                )

    if mandatory("rest_11h", ConstraintPolicy.MANDATORY):
        _add_shift_class_rest_messages(model, classed, add)
        if mandatory(OPENING_HOURS_COVERAGE_POLICY, ConstraintPolicy.MANDATORY):
            _add_shift_class_coverage_messages(schedule, shop, model, classed, add)


def _rest_conflict(model, key, first, second) -> bool:
    """Czy zmiana `second` (zaczyna się po `first`) nachodzi na `first` albo
    nie zostawia po niej wymaganego odpoczynku - ta sama arytmetyka co
    opening_hours_coverage.add_opening_hours_rest_constraint."""
    return second.start < first.end + model.required_rest_after(key, first.length)


def _add_shift_class_rest_messages(model, classed, add) -> None:
    """Dwa dni z typem zmiany („W”/„1”/„2”) tej samej osoby, których zmian
    nie da się pogodzić z odpoczynkiem - np. jedyna zmiana placówki
    07:00–22:00 dzień po dniu (9 h przerwy przy wymaganych 11 h)."""
    for e, days in classed.items():
        key = model.location_of[e]
        for (d1, cls1, first), (d2, cls2, second) in combinations(days, 2):
            pairs = [(a, b) for a in first.values() for b in second.values()]
            if not all(_rest_conflict(model, key, a, b) for a, b in pairs):
                continue
            gap = max(b.start - a.end for a, b in pairs)
            classes = f"„{cls1}”" if cls1 == cls2 else f"„{cls1}” i „{cls2}”"
            add(
                f"{model.employees[e].display_name()}, dni {d1} i {d2}: typ zmiany {classes} "
                f"wymaga zmiany w oba dni, a między zmianami placówki w te dni jest najwyżej "
                f"{max(gap, 0) / 60:g} h przerwy - za mało na odpoczynek (zasada Wymagana)."
            )


def _add_shift_class_coverage_messages(schedule, shop, model, classed, add) -> None:
    """Fragment okna placówki, którego nikt nie może obsadzić: każda osoba,
    która mogłaby go wziąć, ma typ zmiany („W”/„1”/„2”) w innym dniu, a
    żadna ze zmian tamtego dnia nie zostawia odpoczynku przed/po tym
    fragmencie - np. obie osoby placówki z „W” w poniedziałek 07:00–22:00:
    we wtorek od 07:00 nie ma kto zacząć."""
    from logic.generator.opening_hours_coverage import _segments, fmt_minutes

    if not classed:
        return
    by_day = {e: {d: (cls, wanted) for d, cls, wanted in days} for e, days in classed.items()}

    def blocking(e, d, sh):
        """Opis typu zmiany osoby e, który wyklucza jej zmianę `sh` w dniu d."""
        key = model.location_of[e]
        for other, (cls, wanted) in by_day.get(e, {}).items():
            if other == d:
                if sh not in wanted.values():
                    return f"„{cls}” w dniu {other}"
            elif all(
                _rest_conflict(model, key, w, sh) if other < d else _rest_conflict(model, key, sh, w)
                for w in wanted.values()
            ):
                return f"„{cls}” w dniu {other} - odpoczynek"
        return None

    for key, members in model.members.items():
        location = shop.locations.get(key)
        name = location.name if location is not None else key
        fixed = [(s, en) for e in members for _d, s, en in model.fixed.get(e, ())]
        for day, window in sorted(model.windows_by_location[key].items()):
            shapes = [
                (e, d, sh)
                for e in members
                for d in model.days
                if not _is_unavailable(schedule.get_day(model.employees[e], d))
                for sh in model.allowed(e, d).values()
                if sh.window_day == day
            ]
            intervals = [(sh.start, sh.end) for _e, _d, sh in shapes] + fixed
            for a, b in _segments(window.start, min(window.end, model.month_end), intervals):
                if any(fs <= a and b <= fe for fs, fe in fixed):
                    continue
                coverers = [(e, d, sh) for e, d, sh in shapes if sh.start <= a and b <= sh.end]
                blockers = [blocking(e, d, sh) for e, d, sh in coverers]
                if not coverers or None in blockers:
                    continue
                people = sorted({
                    f"{model.employees[e].display_name()} ({reason})"
                    for (e, _d, _sh), reason in zip(coverers, blockers)
                })
                add(
                    f"{name}, dzień {day}: od {fmt_minutes(a)} nie ma kto pracować - każdą osobę, "
                    f"która mogłaby, wyklucza typ zmiany z grafiku: {', '.join(people)} "
                    "(zasady Wymagane)."
                )
                break


def _is_unavailable(state) -> bool:
    return (
        state.is_leave
        or getattr(state, "is_sick", False)
        or getattr(state, "is_day_off", False)
        or (state.is_locked and not state.start)
    )


def _add_duty_rotation_supply_messages(schedule, shop, add) -> None:
    """Rotacja służby 24/7: doba placówki wymaga dokładnie jednej osoby
    naraz. Dowodliwe z samych danych przyczyny braku rozwiązania - nikt z
    placówki nie jest tego dnia dostępny (urlop/L4/wolne), albo jedyna
    dostępna osoba nie może wziąć zmiany 24h, a dwóch osób do podziału
    doby nie ma."""
    from logic.generator.duty_rotation_constraint import (
        NIE_CHCE_24H_ROLE_KEY,
        group_employees_with_duty_rotation,
    )

    from logic.generator.duty_rotation_manual_coverage import build_duty_coverage_plan, match_duty_key

    employees = schedule.employees
    # Doby zaplanowane wokół ręcznych wpisów (także z dnia poprzedniego,
    # sięgających w tę dobę) nie wymagają standardowego podziału - podpowiedź
    # "tylko 1 osoba" nie jest tam dowodliwa.
    plan = build_duty_coverage_plan(schedule, shop, employees)
    for location_key, (rotation, indices) in group_employees_with_duty_rotation(employees, shop).items():
        location = shop.locations.get(location_key)
        name = location.name if location is not None else location_key
        for day in range(1, schedule.days_in_month + 1):
            # Ręcznie zablokowana zmiana 24h (dokładnie zmiana 24h rotacji)
            # osobie z "Nie chce zmian 24h", gdy ta zasada jest Wymagana -
            # blokada wymusza tę zmianę, a zasada ją zakazuje.
            if shop.constraint_policies.get("duty_rotation_no24h") == ConstraintPolicy.MANDATORY:
                for e in indices:
                    state = schedule.get_day(employees[e], day)
                    if (
                        employees[e].custom_roles.get(NIE_CHCE_24H_ROLE_KEY, False)
                        and state.is_locked
                        and not state.is_leave
                        and match_duty_key(state, rotation, shop.weekday(day)) == "weekend_full"
                        and not (plan is not None and plan.is_fixed(employees[e], day))
                    ):
                        add(
                            f"{name}, dzień {day}: {employees[e].display_name()} ma ręcznie "
                            "wpisaną zmianę 24h, a zaznaczone „Nie chce zmian 24h” "
                            "(zasada Wymagana)."
                        )
            if location is not None and location.is_duty_day_closed(shop.year, shop.month, day):
                continue
            # "W" (może pracować) - każda z tych osób musi dostać zmianę, a
            # doba ma najwyżej dwie (24h albo dwie połówki; w tygodniu bez
            # only_12_24h - skonfigurowane zmiany dnia), po jednej osobie na
            # każdej (duty_rotation_manual_constraint.py).
            if (
                shop.constraint_policies.get("duty_rotation_coverage") == ConstraintPolicy.MANDATORY
                and not (plan is not None and plan.is_planned(location_key, day))
            ):
                can_work = [
                    employees[e] for e in indices
                    if getattr(schedule.get_day(employees[e], day), "shift_class", None) == "W"
                    and not _is_unavailable(schedule.get_day(employees[e], day))
                ]
                if shop.weekday(day) < 5 and not rotation.get("only_12_24h"):
                    capacity = sum(1 for key in ("weekday_long", "weekday_short") if rotation.get(key))
                else:
                    capacity = 2
                if len(can_work) > capacity:
                    add(
                        f"{name}, dzień {day}: typ zmiany „W” ma {len(can_work)} os. "
                        f"({', '.join(e.display_name() for e in can_work)}), a doba tej placówki "
                        f"ma najwyżej {capacity} {'zmianę' if capacity == 1 else 'zmiany'} "
                        "(na każdej dokładnie 1 osoba)."
                    )
            available = [
                employees[e] for e in indices
                if not _is_unavailable(schedule.get_day(employees[e], day))
            ]
            if not available:
                add(
                    f"{name}, dzień {day}: nikt z pracowników placówki nie jest "
                    "dostępny (urlop/L4/wolne) - doby nie da się obsadzić."
                )
            elif len(available) == 1 and not (plan is not None and plan.is_planned(location_key, day)):
                only = available[0]
                weekday_split = shop.weekday(day) < 5 and not rotation.get("only_12_24h")
                if weekday_split:
                    add(
                        f"{name}, dzień {day}: dostępna jest tylko 1 osoba "
                        f"({only.display_name()}), a doba wymaga dwóch zmian."
                    )
                elif only.custom_roles.get(NIE_CHCE_24H_ROLE_KEY, False):
                    add(
                        f"{name}, dzień {day}: dostępna jest tylko 1 osoba "
                        f"({only.display_name()}), a ma zaznaczone „Nie chce "
                        "zmian 24h” - doby nie da się obsadzić."
                    )


class GeneratorDiagnostics:
    """Run isolated stage solves and locate an irreducible hard-constraint set."""

    def __init__(self, schedule, shop, time_limit_seconds: float = 5):
        self.schedule = schedule
        self.shop = shop
        self.time_limit_seconds = time_limit_seconds

    @staticmethod
    def write_report(report: dict[str, Any], path: str | Path) -> None:
        Path(path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    def _run(self, enabled: Iterable[str]) -> tuple[dict[str, Any], Any]:
        """Solve a disposable copy with only selected policy constraints active."""
        from logic.auto_generator import AutoScheduleGenerator

        schedule = deepcopy(self.schedule)
        shop = deepcopy(self.shop)
        enabled = set(enabled)
        for name in POLICY_STAGES:
            if name not in enabled:
                shop.constraint_policies[name] = ConstraintPolicy.DISABLED

        # A single worker makes stage-to-stage output reproducible for a seed.
        with redirect_stdout(io.StringIO()):
            result = AutoScheduleGenerator(schedule, shop).generate(
                solver_time_limit_seconds=self.time_limit_seconds,
                solver_workers=1,
            )
        # OR-Tools 9.15 returns a CpSolverStatus enum, which json cannot encode.
        result = dict(result)
        result["status"] = int(result["status"])
        return result, schedule

    def _find_irreducible_conflict(self, active: list[str]) -> list[str]:
        """Deletion-based MUS approximation; every returned group is necessary."""
        conflict = list(active)
        for name in list(conflict):
            candidate = [item for item in conflict if item != name]
            result, _ = self._run(candidate)
            if not result["success"] and result["status"] == cp_model.INFEASIBLE:
                conflict = candidate
        return conflict

    def run(self) -> dict[str, Any]:
        original_policies = self.shop.constraint_policies
        active = [
            name for name in POLICY_STAGES
            if original_policies.get(name, ConstraintPolicy.DISABLED) != ConstraintPolicy.DISABLED
        ]

        base_result, base_schedule = self._run(())
        stages = []
        previous_snapshot = schedule_snapshot(base_schedule) if base_result["success"] else None
        first_infeasible_at = None
        enabled: list[str] = []

        stages.append({
            "stage": "core",
            "enabled_constraints": [],
            "contained_constraints": [
                "non_trade_day", "leave", "day_off", "manual_shift",
                "work_dependency", "one_shift_per_day",
            ],
            "status": _status_name(base_result["status"]),
            "solver": base_result,
            "schedule": previous_snapshot,
            "audit": audit_schedule(base_schedule, self.shop) if base_result["success"] else None,
            "changes_from_previous_stage": [],
        })
        if not base_result["success"]:
            first_infeasible_at = "core"

        for name in POLICY_STAGES:
            policy = original_policies.get(name, ConstraintPolicy.DISABLED)
            if policy == ConstraintPolicy.DISABLED:
                stages.append({"stage": name, "policy": policy.value, "status": "DISABLED"})
                continue
            enabled.append(name)
            result, solved_schedule = self._run(enabled)
            snapshot = schedule_snapshot(solved_schedule) if result["success"] else None
            stage = {
                "stage": name,
                "policy": policy.value,
                "enabled_constraints": list(enabled),
                "status": _status_name(result["status"]),
                "solver": result,
                "schedule": snapshot,
                "audit": audit_schedule(solved_schedule, self.shop) if result["success"] else None,
                "changes_from_previous_stage": snapshot_diff(previous_snapshot, snapshot) if snapshot else [],
            }
            stages.append(stage)
            if snapshot is not None:
                previous_snapshot = snapshot
            elif first_infeasible_at is None and result["status"] == cp_model.INFEASIBLE:
                first_infeasible_at = name
                break

        infeasibility = None
        if first_infeasible_at:
            if first_infeasible_at == "core":
                conflict = ["core"]
            else:
                conflict = self._find_irreducible_conflict(enabled)
            infeasibility = {
                "first_infeasible_stage": first_infeasible_at,
                "irreducible_constraint_groups": conflict,
                "interpretation": (
                    "Removing any listed group makes this staged model feasible. "
                    "The core group contains manual assignments, leave/day-off, "
                    "non-trade-day, one-shift and work-dependency constraints."
                ),
            }

        return {
            "format": "dingo-generator-diagnostics/v1",
            "note": (
                "changes_from_previous_stage shows the observable stage impact. "
                "It is not proof that a single constraint caused an assignment, because "
                "the model can have multiple optimal schedules."
            ),
            "scenario": {"schedule": self.schedule.to_dict(), "shop_config": self.shop.to_dict()},
            "active_policy_constraints": active,
            "preflight_supply": preflight_supply(self.schedule, self.shop),
            "stages": stages,
            "infeasibility": infeasibility,
        }
