from datetime import datetime, timedelta
from logic.utils.time_utils import get_effective_daily_hours

# Sprawdza, czy pracownik ma zaznaczony checkbox "Brak pracy w godziach nocnych" i nakłada ograniczenia, jeśli tak

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
    soft=False
):
    violations = []

    fmt = "%H:%M"

    for e in range(len(employees)):
        emp = employees[e]

        # 🔴 tylko dla pracowników z ograniczeniem
        if not getattr(emp, "no_night", False):
            continue

        eff_hours = get_effective_daily_hours(emp, shop)
        shift_delta = timedelta(hours=eff_hours)

        for d in days:

            hours = shop.get_open_hours_for_day(d)
            if not hours:
                continue

            open_time, close_time = hours
            open_dt = datetime.strptime(open_time, fmt)
            close_dt = datetime.strptime(close_time, fmt)

            forbidden_shifts = set()

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
                    model.Add(x[e, d, s] == 1).OnlyEnforceIf(v)
                    violations.append(v)
                else:
                    model.Add(x[e, d, s] == 0)

    return violations