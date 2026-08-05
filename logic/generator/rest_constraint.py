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
    windows_cache = {}

    def windows_for(day, eff_hours):
        key = (day, eff_hours)
        cached = windows_cache.get(key)
        if cached is not None:
            return cached

        hours = shop.get_open_hours_for_day(day)
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

    for e in range(len(employees)):
        emp = employees[e]
        eff_hours = get_effective_daily_hours(emp, shop)

        for i in range(len(days) - 1):
            d = days[i]
            d_next = days[i + 1]

            if d not in trade_days or d_next not in trade_days:
                continue

            shifts_today = windows_for(d, eff_hours)
            shifts_next = windows_for(d_next, eff_hours)

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
    soft=False,
    trace=None
):
    """Uproszczony wariant dla sklepów z dokładnie dwoma typami zmian
    (rano/popołudnie): jeśli pracownik pracuje dziś na zmianie popołudniowej,
    jutro może mieć tylko zmianę popołudniową (albo nic). Zmiana poranna dziś
    nie nakłada żadnego ograniczenia na jutro. Działa na klasie zmiany, nie na
    dokładnych godzinach — O(pracownicy × dni) constraintów zamiast O(pracownicy
    × dni × warianty²), bez żadnego parsowania dat.
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

    return violations
