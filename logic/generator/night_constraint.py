from datetime import datetime, timedelta
from logic.utils.time_utils import get_effective_daily_hours, hour_window_overlaps_time_range

# Sprawdza, czy pracownik ma zaznaczony checkbox "Brak pracy w godziach nocnych" i nakłada ograniczenia, jeśli tak

# Godziny, które ten checkbox opisuje użytkownikowi wprost (patrz
# ui/employee_dialog.py): "przed 6:00 i po 22:00". Te same wartości steruje
# już heurystyka OPEN/CLOSE/START/END poniżej (end.hour >= 22 lub
# start.hour <= 6) - wydzielone jako stałe tylko dla sprawdzenia SHIFT_NIGHT,
# żeby nie hardkodować ich osobno drugi raz.
NIGHT_WINDOW_START_HOUR = 22
NIGHT_WINDOW_END_HOUR = 6


def add_no_night_constraint(
    model,
    x,
    employees,
    days,
    shop,
    all_shifts,
    SHIFT_OPEN,
    SHIFT_CLOSE,
    START_SHIFT_MAP,
    END_SHIFT_MAP,
    soft=False,
    trace=None,
    shift_night=None,
):
    if trace is not None:
        trace.log_constraint("no_night", f"soft={soft}")

    violations = []

    fmt = "%H:%M"

    for e in range(len(employees)):
        emp = employees[e]

        # 🔴 tylko dla pracowników z ograniczeniem
        if not getattr(emp, "no_night", False):
            continue

        eff_hours = get_effective_daily_hours(emp, shop)
        shift_delta = timedelta(hours=eff_hours)

        # 🌙 SHIFT_NIGHT (Etap C/D planu zmian nocnych) ma własne, stałe okno
        # niezależne od godzin otwarcia konkretnego dnia (w odróżnieniu od
        # OPEN/CLOSE/START/END poniżej), więc sprawdzane raz, poza pętlą po
        # dniach. no_night wyklucza je tylko wtedy, gdy to skonfigurowane
        # okno faktycznie pokrywa się z porą nocną (przed 6:00/po 22:00) -
        # "night_shift" nazwą sugeruje noc, ale model na to nie wymusza
        # (normalize_night_shift przyjmuje dowolną parę godzin), więc
        # lokalizacja mogłaby w zasadzie użyć go pod dowolny, stały blok w
        # środku dnia; taki blok nie powinien być objęty tym zakazem.
        night_hours = shop.get_location(emp).get_night_shift_hours() if shift_night is not None else None
        night_restricted = night_hours is not None and hour_window_overlaps_time_range(
            NIGHT_WINDOW_START_HOUR, NIGHT_WINDOW_END_HOUR, night_hours
        )

        for d in days:

            forbidden_shifts = set()

            if night_restricted:
                forbidden_shifts.add(shift_night)

            hours = shop.get_open_hours_for_day(d)
            if hours:
                open_time, close_time = hours
                open_dt = datetime.strptime(open_time, fmt)
                close_dt = datetime.strptime(close_time, fmt)

                # ===== OPEN =====
                start = open_dt
                end = start + shift_delta
                if end.hour >= 22 or start.hour <= 6:
                    forbidden_shifts.add(SHIFT_OPEN)

                # ===== CLOSE =====
                end = close_dt
                if end.hour >= 22 or start.hour <= 6:
                    forbidden_shifts.add(SHIFT_CLOSE)

                # ===== START SHIFTS =====
                for shift, offset in START_SHIFT_MAP.items():
                    start = open_dt + timedelta(minutes=offset)
                    end = start + shift_delta

                    if end.hour >= 22 or start.hour <= 6:
                        forbidden_shifts.add(shift)

                # ===== END SHIFTS =====
                for shift, offset in END_SHIFT_MAP.items():
                    end = close_dt - timedelta(minutes=offset)

                    if end.hour >= 22 or start.hour <= 6:
                        forbidden_shifts.add(shift)

            # ===== nakładamy constraint =====
            for s in forbidden_shifts:

                if soft:
                    v = model.NewBoolVar(f"night_violation_e{e}_d{d}_s{s}")
                    # A violation must be paid *when the forbidden shift is used*.
                    # The previous implication only said ``v => assigned`` and let
                    # CP-SAT choose a forbidden shift with v=0 at no cost.
                    model.Add(x[e, d, s] <= v)
                    violations.append(v)
                else:
                    model.Add(x[e, d, s] == 0)

    return violations
