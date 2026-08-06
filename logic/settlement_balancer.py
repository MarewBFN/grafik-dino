"""Okres rozliczeniowy: dostrajanie długości już przypisanych zmian, żeby
zbliżyć sumę godzin pracownika w miesiącu do ręcznie ustalonego celu.

To CELOWO nie jest część generatora CP-SAT (logic/generator/*) — nie
negocjuje obsady, mięsa ani odpoczynku 11h. Działa wyłącznie na już
wygenerowanym/ustalonym grafiku, przesuwając "bezpieczną" krawędź zmiany
(tę, która nie jest godziną otwarcia ani zamknięcia sklepu) w krokach po
15 minut, a przy dużej nadwyżce — zwalniając całe dni.
"""

from datetime import datetime, timedelta

from logic.utils.time_utils import classify_shift_as_morning_or_afternoon, get_effective_daily_hours

_FMT = "%H:%M"
_TRIM_STEP_MINUTES = 15
_MAX_TRIM_MINUTES = 60
_MAX_EXTEND_MINUTES = 15

# Pracownicy, którzy nie mogą przekroczyć swojej bazowej liczby godzin
# dziennych (żadnego "+15 min") — "7/8" i "1/1 max 8h".
_NO_EXTEND_FRACTIONS = (0.875, 1.01)


def compute_safe_adjustment_bounds(emp, shop):
    """Zwraca (min_delta, max_delta) w minutach dozwolonych dla jednego dnia."""
    if emp.employment_fraction in _NO_EXTEND_FRACTIONS:
        return (-_MAX_TRIM_MINUTES, 0)
    return (-_MAX_TRIM_MINUTES, _MAX_EXTEND_MINUTES)


def classify_editable_side(ds, shop, day):
    """Która krawędź zmiany jest "bezpieczna" do ruszenia w danym dniu.

    Zwraca "start", "end" albo None (dzień pusty/urlop/L4/nie-handlowy —
    nic do dostrojenia).
    """
    if ds.is_empty() or ds.is_leave or getattr(ds, "is_sick", False) or getattr(ds, "is_day_off", False):
        return None

    hours = shop.get_open_hours_for_day(day)
    if not hours:
        return None

    open_t, close_t = hours

    if ds.start == open_t:
        return "end"
    if ds.end == close_t:
        return "start"

    try:
        start_dt = datetime.strptime(ds.start, _FMT)
        end_dt = datetime.strptime(ds.end, _FMT)
        open_dt = datetime.strptime(open_t, _FMT)
        close_dt = datetime.strptime(close_t, _FMT)
    except (TypeError, ValueError):
        return None

    classification = classify_shift_as_morning_or_afternoon(start_dt, end_dt, open_dt, close_dt)
    if classification == "morning":
        return "end"
    if classification == "afternoon":
        return "start"
    return None


def _apply_edge_change(ds, side, change_minutes):
    start_dt = datetime.strptime(ds.start, _FMT)
    end_dt = datetime.strptime(ds.end, _FMT)

    if side == "end":
        new_start = ds.start
        new_end = (end_dt + timedelta(minutes=change_minutes)).strftime(_FMT)
    else:
        new_start = (start_dt - timedelta(minutes=change_minutes)).strftime(_FMT)
        new_end = ds.end

    ds.set_hours(new_start, new_end)


def balance_employee_hours(schedule, shop, employee, target_minutes):
    days = range(1, schedule.days_in_month + 1)

    # Musi się zgadzać dokładnie z tym, co pokazuje kolumna "Razem" w
    # siatce (total_with_leave_and_sick_for_employee) — inaczej cel wpisany
    # "na oko" względem tego, co widać na ekranie, generuje inną różnicę niż
    # użytkownik zamierzał (widoczne zwłaszcza u pracowników z urlopami: ta
    # kolumna liczy godziny urlopu inaczej niż DaySchedule.total_minutes()).
    current_minutes = schedule.total_with_leave_and_sick_minutes_for_employee(employee)
    delta = target_minutes - current_minutes

    summary = {
        "employee": employee.display_name(),
        "target_minutes": target_minutes,
        "starting_minutes": current_minutes,
        "days_freed": [],
        "days_trimmed": [],
    }

    if delta == 0:
        summary["final_minutes"] = current_minutes
        summary["remaining_delta"] = 0
        summary["reached_target"] = True
        return summary

    candidate_days = [
        day for day in days
        if shop.is_trade_day(day)
        and classify_editable_side(schedule.get_day(employee, day), shop, day) is not None
    ]

    # Duża nadwyżka: zamiast dłubać po 15 minut, zwolnij całe dni. Wolno
    # zwolnić dzień tylko wtedy, gdy jego RZECZYWISTA długość (a nie
    # przeciętna/założona) mieści się w tym, co jeszcze trzeba ściąć —
    # inaczej dzień dłuższy niż typowa zmiana (np. ręcznie wydłużony)
    # przestrzeliłby cel w dół.
    if delta < 0:
        threshold_minutes = int(get_effective_daily_hours(employee, shop) * 60)

        for day in list(candidate_days):
            if -delta < threshold_minutes:
                break

            ds = schedule.get_day(employee, day)
            freed_minutes = ds.total_minutes(employee, shop)

            if freed_minutes <= 0 or freed_minutes > -delta:
                continue

            ds.set_free()
            ds.is_locked = True

            delta += freed_minutes
            summary["days_freed"].append(day)
            candidate_days.remove(day)

    # Reszta (już mniejszej) różnicy: dostrojenie krawędziowe w krokach 15 min.
    min_delta, max_delta = compute_safe_adjustment_bounds(employee, shop)

    for day in candidate_days:
        if delta == 0:
            break

        ds = schedule.get_day(employee, day)
        side = classify_editable_side(ds, shop, day)
        if side is None:
            continue

        step_limit = max_delta if delta > 0 else min_delta
        if step_limit == 0:
            continue

        possible = min(abs(delta), abs(step_limit))
        possible = (possible // _TRIM_STEP_MINUTES) * _TRIM_STEP_MINUTES
        if possible <= 0:
            continue

        change = possible if delta > 0 else -possible

        _apply_edge_change(ds, side, change)
        ds.is_locked = True

        delta -= change
        summary["days_trimmed"].append({"day": day, "minutes": change})

    summary["remaining_delta"] = delta
    summary["final_minutes"] = target_minutes - delta
    summary["reached_target"] = delta == 0
    return summary


def balance_settlement_period(schedule, shop):
    results = []
    for employee, target_minutes in list(schedule.settlement_targets.items()):
        if employee not in schedule.employees:
            continue
        results.append(balance_employee_hours(schedule, shop, employee, target_minutes))

    return {"employees": results}
