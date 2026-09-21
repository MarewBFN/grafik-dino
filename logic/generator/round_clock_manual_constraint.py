"""Ręczne blokowanie dnia dla pracowników rotacji całodobowej "ogólnej"
(round_clock_constraint.py) - odpowiednik add_manual_shift_constraints
(manual_constraint.py) dla kafelków round-clock zamiast starego modelu
OPEN/CLOSE/START/END, tym samym wzorcem co
duty_rotation_manual_constraint.py (patrz jej docstring dla pełnego
uzasadnienia, czemu stary model nie może obsłużyć tych zmian - identyczny
powód: add_round_clock_gate_constraint zeruje OPEN/CLOSE/START/END/NIGHT
dla tych pracowników, więc próba dopasowania ręcznej blokady do niego
byłaby zawsze sprzeczna z tamtą bramą).

Dopasowanie: TYLKO po godzinie startu (jak "OPEN" w resolve_manual_shift
dzisiaj) - koniec zmiany wynika z efektywnych godzin pracownika, nie z
samego kafelka, więc nie ma sensu go osobno sprawdzać."""

from logic.generator.round_clock_constraint import (
    round_clock_tile_count,
    round_clock_tile_start_hour,
)


def _match_round_clock_tile(day_state, start_hour, n_tiles, standard_daily_hours):
    start = getattr(day_state, "start", None)
    if not start:
        return None

    for tile_index in range(n_tiles):
        if round_clock_tile_start_hour(start_hour, tile_index, standard_daily_hours) == start:
            return tile_index
    return None


def add_round_clock_manual_shift_constraint(
    model, x, employees, days, schedule, shop, round_clock_shifts, standard_daily_hours, trace=None,
):
    if trace is not None:
        trace.log_constraint(
            "round_clock_manual_shift",
            "apply locked/manual day assignments for round-clock employees",
        )

    n_tiles = round_clock_tile_count(standard_daily_hours)
    active_ids = set(round_clock_shifts[:n_tiles])

    for e, emp in enumerate(employees):
        start_hour = shop.get_location(emp).get_round_clock_start_hour()
        if not start_hour:
            continue

        for d in days:
            day_state = schedule.get_day(emp, d)

            # urlop/chorobowe/dzień wolny - już obsłużone generycznie przez
            # always-on "leave"/"day_off" (zerują KAŻDĄ zmianę, w tym
            # kafelki round-clock), nic dodatkowego do zrobienia tutaj.
            if day_state.is_leave or getattr(day_state, "is_sick", False):
                continue

            if not day_state.is_locked:
                continue

            if not getattr(day_state, "start", None):
                # Zablokowany jako "wolne" (puste godziny) - musi wymusić
                # zero na każdym kafelku tego pracownika/dnia, ten sam
                # powód co duty_rotation_manual_constraint.py.
                for s in active_ids:
                    model.Add(x[e, d, s] == 0)
                continue

            tile_index = _match_round_clock_tile(day_state, start_hour, n_tiles, standard_daily_hours)

            if tile_index is None:
                for s in active_ids:
                    model.Add(x[e, d, s] == 0)
                continue

            shift = round_clock_shifts[tile_index]
            model.Add(x[e, d, shift] == 1)
            for s in active_ids:
                if s != shift:
                    model.Add(x[e, d, s] == 0)
