"""Odpoczynek 11h po kafelkach rotacji całodobowej "ogólnej"
(round_clock_constraint.py) - dołącza się do add_rest_11h_constraint (który
nie zna tych kafelków - nie buduje dla nich okien), zamiast go modyfikować,
dokładnie jak night_shift_adjacency_constraint/duty_rotation_rest_constraint
robią to dla swoich zmian.

W przeciwieństwie do duty_rotation (zmiana 24h "weekend_full" wymaga
specjalnego wzoru odpoczynku "doba za dobę"), każdy kafelek tu jest zawsze
krótszy niż doba (round_clock_tile_count >= 2), więc standardowe 11h i
sprawdzenie wyłącznie dnia d wobec d+1 zawsze wystarcza - ten sam zakres co
add_rest_11h_constraint, tylko dla kafelków zamiast OPEN/CLOSE/START/END."""

from datetime import datetime, timedelta

from logic.generator.round_clock_constraint import (
    group_employees_with_round_clock,
    round_clock_tile_count,
    round_clock_tile_start_hour,
)
from logic.utils.time_utils import get_effective_daily_hours

MIN_REST = timedelta(hours=11)
FMT = "%H:%M"


def _anchor(day_offset: int, time_str: str) -> datetime:
    t = datetime.strptime(time_str, FMT)
    return datetime(2000, 1, 1, t.hour, t.minute) + timedelta(days=day_offset)


def _tile_start_end(start_hour: str, tile_index: int, standard_daily_hours: float, eff_hours: float, day_offset: int):
    tile_start_str = round_clock_tile_start_hour(start_hour, tile_index, standard_daily_hours)
    start = _anchor(day_offset, tile_start_str)
    end = start + timedelta(hours=eff_hours)
    return start, end


def _add_previous_month_rest_constraint(
    model, x, employees, shop, round_clock_shifts, schedule, days_sorted, start_hour,
    standard_daily_hours, indices, soft, violations,
):
    """"Pamięć poprzedniego miesiąca" (model.month_schedule.PreviousMonthShiftEnd) -
    dzień 1 nie ma poprzedniego dnia W TYM MODELU, więc bez tego nic nie
    chroniłoby początku miesiąca przed zbyt wczesnym startem względem
    faktycznego końca ostatniej zmiany poprzedniego miesiąca. Ten sam wzorzec
    co rest_constraint.py/duty_rotation_rest_constraint.py."""
    if schedule is None or not days_sorted:
        return

    d1 = days_sorted[0]
    n_tiles = round_clock_tile_count(standard_daily_hours)

    for e in indices:
        emp = employees[e]
        carry = schedule.get_previous_month_end_shift(emp)
        if carry is None:
            continue

        end_prev = _anchor(0 if carry.crosses_midnight else -1, carry.end)
        eff_hours = get_effective_daily_hours(emp, shop)

        for tile_index in range(n_tiles):
            s2 = round_clock_shifts[tile_index]
            start2, _ = _tile_start_end(start_hour, tile_index, standard_daily_hours, eff_hours, 0)

            if start2 - end_prev >= MIN_REST:
                continue

            if not soft:
                model.Add(x[e, d1, s2] == 0)
            else:
                v = model.NewBoolVar(f"round_clock_rest_violation_prevmonth_e{e}_{tile_index}")
                model.Add(x[e, d1, s2] <= v)
                violations.append(v)


def add_round_clock_rest_constraint(
    model, x, employees, days, shop, round_clock_shifts, standard_daily_hours,
    schedule=None, soft=False, trace=None,
):
    if trace is not None:
        trace.log_constraint("round_clock_rest", f"soft={soft}")

    violations = []
    groups = group_employees_with_round_clock(employees, shop)
    days_sorted = sorted(days)
    n_tiles = round_clock_tile_count(standard_daily_hours)

    for _, (start_hour, indices) in groups.items():
        _add_previous_month_rest_constraint(
            model, x, employees, shop, round_clock_shifts, schedule, days_sorted, start_hour,
            standard_daily_hours, indices, soft, violations,
        )

        for i in range(len(days_sorted) - 1):
            d, d_next = days_sorted[i], days_sorted[i + 1]

            for e in indices:
                eff_hours = get_effective_daily_hours(employees[e], shop)

                for tile1 in range(n_tiles):
                    s1 = round_clock_shifts[tile1]
                    _, end1 = _tile_start_end(start_hour, tile1, standard_daily_hours, eff_hours, 0)

                    for tile2 in range(n_tiles):
                        s2 = round_clock_shifts[tile2]
                        start2, _ = _tile_start_end(start_hour, tile2, standard_daily_hours, eff_hours, 1)

                        if start2 - end1 >= MIN_REST:
                            continue

                        if not soft:
                            model.Add(x[e, d, s1] + x[e, d_next, s2] <= 1)
                        else:
                            v = model.NewBoolVar(f"round_clock_rest_violation_e{e}_d{d}_{tile1}_{tile2}")
                            model.Add(x[e, d, s1] + x[e, d_next, s2] <= 1 + v)
                            violations.append(v)

    return violations
