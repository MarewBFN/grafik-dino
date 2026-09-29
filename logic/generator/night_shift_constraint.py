"""Etap C planu zmian nocnych: SHIFT_NIGHT jako prawdziwa, samodzielna
zmiana przechodząca przez północ (patrz "plan zmiany nocne (24-7).md").

Dwa constrainty:

- add_night_shift_gate_constraint: twardo blokuje SHIFT_NIGHT dla
  pracowników, których lokalizacja nie ma skonfigurowanego night_shift
  (Etap B) - to fakt strukturalny ("ta zmiana nie istnieje tutaj"), nie
  preferencja biznesowa, więc zawsze hard, poza systemem polityk
  MANDATORY/PREFERRED/DISABLED (tak samo jak np. add_non_trade_day_constraints).

- add_night_shift_adjacency_constraint: odpoczynek 11h między SHIFT_NIGHT
  a sąsiednimi dniami. Dokłada się do istniejącego add_rest_11h_constraint
  (który w ogóle nie zna SHIFT_NIGHT - nie buduje dla niego okien), zamiast
  go modyfikować, żeby nie ruszać już zweryfikowanej logiki dla zwykłych
  zmian. Liczy rzeczywisty upływ czasu przez zakotwiczenie obu dni w
  jednej, wspólnej osi (dzień 0 / dzień 1) zamiast heurystyki "ujemna
  różnica => dodaj dobę" z rest_constraint.py, która przy zmianie nocnej
  (koniec z definicji leży w kolejnej doby) dawałaby błędny wynik.
"""

from datetime import datetime, timedelta

from logic.generator.rest_constraint import _build_shift_windows
from logic.utils.time_utils import get_effective_daily_hours

FMT = "%H:%M"
MIN_REST = timedelta(hours=11)


def night_shift_duration_minutes(window: tuple[str, str]) -> int:
    """Długość zmiany nocnej w minutach, licząc przejście przez północ."""
    start_dt = datetime.strptime(window[0], FMT)
    end_dt = datetime.strptime(window[1], FMT)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    return int((end_dt - start_dt).total_seconds() // 60)


def night_shift_minutes_for_employee(shop, employee) -> int:
    """0, gdy lokalizacja pracownika nie ma zmiany nocnej - spójne z
    add_night_shift_gate_constraint, które i tak nie pozwoli jej przydzielić."""
    window = shop.get_location(employee).get_night_shift_hours()
    if not window:
        return 0
    return night_shift_duration_minutes(window)


def add_night_shift_gate_constraint(model, x, employees, days, shop, shift_night, trace=None):
    if trace is not None:
        trace.log_constraint("night_shift_gate", "block SHIFT_NIGHT where no night_shift window is configured")

    for e, emp in enumerate(employees):
        if shop.get_location(emp).get_night_shift_hours():
            continue
        for d in days:
            model.Add(x[e, d, shift_night] == 0)


def _anchor(day_offset: int, time_str: str) -> datetime:
    t = datetime.strptime(time_str, FMT)
    return datetime(2000, 1, 1, t.hour, t.minute) + timedelta(days=day_offset)


def _night_window_end_anchored(night_start: str, night_end: str, day_offset: int) -> datetime:
    start = _anchor(day_offset, night_start)
    end = _anchor(day_offset, night_end)
    if end <= start:
        end += timedelta(days=1)
    return end


def _other_shift_start_end(shop, employee, day, eff_hours, start_shift_map, end_shift_map, shift_open, shift_close):
    """{shift_id: (start_str, end_str)} dla zwykłych zmian (OPEN/CLOSE/
    START/END) tego dnia - pusty dict, gdy lokalizacja nie ma godzin
    otwarcia na ten dzień (SHIFT_NIGHT nigdy stąd nie pochodzi, ma własne,
    niezależne od open_hours okno)."""
    hours = shop.get_location(employee).get_open_hours_for_day(day)
    if not hours:
        return {}

    open_t, close_t = hours
    raw = _build_shift_windows(FMT, open_t, close_t, eff_hours, start_shift_map, end_shift_map)
    raw[shift_open] = raw.pop("OPEN")
    raw[shift_close] = raw.pop("CLOSE")
    return raw


def _add_pair_rest(model, x, e, d, s1, d_next, s2, soft, violations):
    if not soft:
        model.Add(x[e, d, s1] + x[e, d_next, s2] <= 1)
    else:
        v = model.NewBoolVar(f"night_rest_violation_e{e}_d{d}_{s1}_d{d_next}_{s2}")
        model.Add(x[e, d, s1] + x[e, d_next, s2] <= 1 + v)
        violations.append(v)


def add_night_shift_adjacency_constraint(
    model,
    x,
    employees,
    days,
    shop,
    shift_night,
    shift_open,
    shift_close,
    start_shift_map,
    end_shift_map,
    soft=False,
    trace=None,
):
    if trace is not None:
        trace.log_constraint("night_shift_adjacency", f"soft={soft}")

    violations = []

    for e, emp in enumerate(employees):
        window = shop.get_location(emp).get_night_shift_hours()
        if not window:
            continue

        night_start, night_end = window
        eff_hours = get_effective_daily_hours(emp, shop)

        for i in range(len(days) - 1):
            d = days[i]
            d_next = days[i + 1]

            night_end_today_dt = _night_window_end_anchored(night_start, night_end, 0)
            night_start_next_dt = _anchor(1, night_start)

            # (a) SHIFT_NIGHT zaczęta w dniu d (kończy się w d+1) vs
            # zwykłe zmiany dnia d+1.
            for s2, (start2_str, _) in _other_shift_start_end(
                shop, emp, d_next, eff_hours, start_shift_map, end_shift_map, shift_open, shift_close
            ).items():
                start2_dt = _anchor(1, start2_str)
                if start2_dt - night_end_today_dt >= MIN_REST:
                    continue
                _add_pair_rest(model, x, e, d, shift_night, d_next, s2, soft, violations)

            # (b) zwykłe zmiany dnia d vs SHIFT_NIGHT zaczęta w dniu d+1.
            for s1, (_, end1_str) in _other_shift_start_end(
                shop, emp, d, eff_hours, start_shift_map, end_shift_map, shift_open, shift_close
            ).items():
                end1_dt = _anchor(0, end1_str)
                if night_start_next_dt - end1_dt >= MIN_REST:
                    continue
                _add_pair_rest(model, x, e, d, s1, d_next, shift_night, soft, violations)

            # (c) SHIFT_NIGHT w dniu d vs SHIFT_NIGHT w dniu d+1.
            if night_start_next_dt - night_end_today_dt < MIN_REST:
                _add_pair_rest(model, x, e, d, shift_night, d_next, shift_night, soft, violations)

    return violations
