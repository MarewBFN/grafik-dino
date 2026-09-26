from ortools.sat.python import cp_model
from datetime import datetime, timedelta
from model.day_schedule import calc_start, calc_end
from logic.utils.time_utils import get_effective_daily_hours


def _build_shift_windows(fmt, open_t, close_t, eff_hours, START_SHIFTS, END_SHIFTS):
    """Zwraca {shift_id: (start_str, end_str)} dla wszystkich wariantów zmiany
    w danym dniu, przy danych godzinach sklepu i efektywnych godzinach pracownika.
    """
    windows = {}

    windows["OPEN"] = (open_t, calc_end(open_t, eff_hours))
    windows["CLOSE"] = (calc_start(close_t, eff_hours), close_t)

    for shift, off in START_SHIFTS.items():
        start = (datetime.strptime(open_t, fmt) + timedelta(minutes=off)).strftime(fmt)
        windows[shift] = (start, calc_end(start, eff_hours))

    for shift, off in END_SHIFTS.items():
        end = (datetime.strptime(close_t, fmt) - timedelta(minutes=off)).strftime(fmt)
        windows[shift] = (calc_start(end, eff_hours), end)

    return windows


def _anchor(day_offset, time_str, fmt="%H:%M"):
    """Umieszcza `time_str` na wirtualnej osi czasu, `day_offset` dni od
    dnia 1 tego miesiąca - ten sam wzorzec co
    logic/generator/duty_rotation_rest_constraint.py::_anchor, potrzebny
    do porównania końca zmiany z POPRZEDNIEGO miesiąca (dzień -1, albo
    dzień 0 gdy zmiana już wchodziła w dzień 1 - patrz
    PreviousMonthShiftEnd.crosses_midnight) ze startem zmiany w dniu 1."""
    t = datetime.strptime(time_str, fmt)
    return datetime(2000, 1, 1, t.hour, t.minute) + timedelta(days=day_offset)


def _make_windows_for(fmt, START_SHIFTS, END_SHIFTS, SHIFT_OPEN, SHIFT_CLOSE):
    """Fabryka memoizowanej `windows_for(location, location_key, day,
    eff_hours)` - identyczna logika potrzebna zarówno w
    add_rest_11h_constraint, jak i (dla samej granicy z poprzednim
    miesiącem, patrz _add_previous_month_rest_constraint) w
    add_rest_11h_constraint_simplified."""
    windows_cache = {}

    def windows_for(location, location_key, day, eff_hours):
        key = (location_key, day, eff_hours)
        cached = windows_cache.get(key)
        if cached is not None:
            return cached

        hours = location.get_open_hours_for_day(day)
        if not hours:
            windows_cache[key] = None
            return None

        open_t, close_t = hours
        raw = _build_shift_windows(fmt, open_t, close_t, eff_hours, START_SHIFTS, END_SHIFTS)
        # normalizuj nazwy OPEN/CLOSE na prawdziwe id-ki shift'ów
        raw[SHIFT_OPEN] = raw.pop("OPEN")
        raw[SHIFT_CLOSE] = raw.pop("CLOSE")

        windows_cache[key] = raw
        return raw

    return windows_for


def _add_previous_month_rest_constraint(model, x, employees, days, trade_days, shop, schedule, windows_for, soft, violations):
    """"Pamięć poprzedniego miesiąca" (PreviousMonthShiftEnd) - dzień 1 nie
    ma poprzedniego dnia W TYM MODELU (pierwsza para w pętli niżej zaczyna
    się od days[0]/days[1]), więc bez tego nic nie chroniłoby początku
    miesiąca przed zbyt wczesnym startem względem faktycznego końca
    ostatniej zmiany poprzedniego miesiąca."""
    if schedule is None or not days:
        return

    day1 = days[0]
    if day1 not in trade_days:
        return

    for e in range(len(employees)):
        emp = employees[e]
        carry = schedule.get_previous_month_end_shift(emp)
        if carry is None:
            continue

        shifts_day1 = windows_for(shop.get_location(emp), emp.location_key, day1, get_effective_daily_hours(emp, shop))
        if not shifts_day1:
            continue

        end_prev = _anchor(0 if carry.crosses_midnight else -1, carry.end)

        for s2, (start_next_str, _) in shifts_day1.items():
            start_next = _anchor(0, start_next_str)

            if start_next - end_prev >= timedelta(hours=11):
                continue

            if not soft:
                model.Add(x[e, day1, s2] == 0)
            else:
                violation = model.NewBoolVar(f"rest_violation_prevmonth_e{e}_{s2}")
                model.Add(x[e, day1, s2] <= violation)
                violations.append(violation)


def add_rest_11h_constraint(
    model,
    x,
    employees,
    days,
    trade_days,
    shop,
    SHIFT_OPEN,
    SHIFT_CLOSE,
    START_SHIFTS,
    END_SHIFTS,
    schedule=None,
    soft=False,
    trace=None
):
    """Dokładny wariant: sprawdza rzeczywisty odstęp w minutach między
    każdą parą wariantów zmiany dwóch kolejnych dni. Wyniki budowy okien
    czasowych (`shifts_today`/`shifts_next`) są memoizowane po kluczu
    (dzień, efektywne godziny pracownika), bo zależą wyłącznie od tych
    dwóch wartości i inaczej są liczone od zera dla każdej pary
    pracownik×dzień — bez zmiany semantyki, tylko szybciej.
    """
    fmt = "%H:%M"

    if trace is not None:
        trace.log_constraint("rest_11h", f"soft={soft}")

    violations = []
    rest_constraints = 0
    windows_for = _make_windows_for(fmt, START_SHIFTS, END_SHIFTS, SHIFT_OPEN, SHIFT_CLOSE)

    for e in range(len(employees)):
        emp = employees[e]
        eff_hours = get_effective_daily_hours(emp, shop)
        location = shop.get_location(emp)

        for i in range(len(days) - 1):
            d = days[i]
            d_next = days[i + 1]

            if d not in trade_days or d_next not in trade_days:
                continue

            shifts_today = windows_for(location, emp.location_key, d, eff_hours)
            shifts_next = windows_for(location, emp.location_key, d_next, eff_hours)

            if not shifts_today or not shifts_next:
                continue

            for s1, (_, end_today_str) in shifts_today.items():
                end_today = datetime.strptime(end_today_str, fmt)

                for s2, (start_next_str, _) in shifts_next.items():
                    start_next = datetime.strptime(start_next_str, fmt)

                    rest = start_next - end_today
                    if rest.total_seconds() < 0:
                        rest += timedelta(days=1)

                    if rest >= timedelta(hours=11):
                        continue

                    if not soft:
                        model.Add(x[e, d, s1] + x[e, d_next, s2] <= 1)
                    else:
                        violation = model.NewBoolVar(
                            f"rest_violation_e{e}_d{d}_{s1}_{s2}"
                        )
                        model.Add(
                            x[e, d, s1] + x[e, d_next, s2] <= 1 + violation
                        )
                        violations.append(violation)

                    rest_constraints += 1

    print("Constrainty 11h rest (standard):", rest_constraints)

    _add_previous_month_rest_constraint(model, x, employees, days, trade_days, shop, schedule, windows_for, soft, violations)

    return violations


def add_rest_11h_constraint_simplified(
    model,
    x,
    employees,
    days,
    trade_days,
    SHIFT_OPEN,
    SHIFT_CLOSE,
    START_SHIFT_MAP,
    END_SHIFT_MAP,
    shop=None,
    schedule=None,
    soft=False,
    trace=None
):
    """Uproszczony wariant dla sklepów z dokładnie dwoma typami zmian
    (rano/popołudnie): jeśli pracownik pracuje dziś na zmianie popołudniowej,
    jutro może mieć tylko zmianę popołudniową (albo nic). Zmiana poranna dziś
    nie nakłada żadnego ograniczenia na jutro. Działa na klasie zmiany, nie na
    dokładnych godzinach — O(pracownicy × dni) constraintów zamiast O(pracownicy
    × dni × warianty²), bez żadnego parsowania dat.

    Wyjątek: granica z poprzednim miesiącem (patrz
    _add_previous_month_rest_constraint) liczona jest zawsze DOKŁADNYMI
    godzinami, nie klasą zmiany - mamy tam prawdziwy zapisany koniec zmiany
    (PreviousMonthShiftEnd), więc nie ma powodu go zgrubnie przybliżać, i
    ta granica akurat nie ma kosztu O(dni) tej uproszczonej wersji (liczona
    tylko raz, dla dnia 1). Wymaga `shop`/`schedule` - bez nich (stare
    wywołania) granica z poprzednim miesiącem jest po prostu pomijana.
    """
    if trace is not None:
        trace.log_constraint("rest_11h", f"soft={soft} mode=simplified")

    morning_shifts = {SHIFT_OPEN, *START_SHIFT_MAP.keys()}
    afternoon_shifts = {SHIFT_CLOSE, *END_SHIFT_MAP.keys()}

    violations = []
    rest_constraints = 0

    for e in range(len(employees)):
        for i in range(len(days) - 1):
            d = days[i]
            d_next = days[i + 1]

            if d not in trade_days or d_next not in trade_days:
                continue

            is_afternoon_today = sum(x[e, d, s] for s in afternoon_shifts)
            is_morning_next = sum(x[e, d_next, s] for s in morning_shifts)

            if not soft:
                model.Add(is_afternoon_today + is_morning_next <= 1)
            else:
                violation = model.NewBoolVar(f"rest_violation_simplified_e{e}_d{d}")
                model.Add(is_afternoon_today + is_morning_next <= 1 + violation)
                violations.append(violation)

            rest_constraints += 1

    print("Constrainty 11h rest (simplified):", rest_constraints)

    if shop is not None:
        windows_for = _make_windows_for("%H:%M", START_SHIFT_MAP, END_SHIFT_MAP, SHIFT_OPEN, SHIFT_CLOSE)
        _add_previous_month_rest_constraint(model, x, employees, days, trade_days, shop, schedule, windows_for, soft, violations)

    return violations
