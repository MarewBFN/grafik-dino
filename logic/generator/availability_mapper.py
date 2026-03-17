from datetime import datetime, timedelta


def get_allowed_shifts_for_day(
    emp,
    day,
    shop,
    SHIFT_OPEN,
    SHIFT_CLOSE,
    START_SHIFT_MAP,
    END_SHIFT_MAP
):
    availability = getattr(emp, "availability", {})
    weekday = shop.weekday(day)

    rules = availability.get(weekday)

    # brak preferencji → wszystko dozwolone
    if not rules:
        return None  # ważne: None = brak ograniczeń

    hours = shop.get_open_hours_for_day(day)
    if not hours:
        return []

    open_time, close_time = hours
    fmt = "%H:%M"

    open_dt = datetime.strptime(open_time, fmt)
    close_dt = datetime.strptime(close_time, fmt)

    allowed = []

    for rule in rules:
        start_pref = rule["start"]
        end_pref = rule["end"]

        pref_start = datetime.strptime(start_pref, fmt)
        pref_end = datetime.strptime(end_pref, fmt)

        # ===== OPEN =====
        if pref_start <= open_dt:
            allowed.append(SHIFT_OPEN)

        # ===== CLOSE =====
        if pref_end >= close_dt:
            allowed.append(SHIFT_CLOSE)

        # ===== START SHIFTS =====
        for shift, offset in START_SHIFT_MAP.items():
            start_dt = open_dt + timedelta(minutes=offset)
            if pref_start <= start_dt <= pref_end:
                allowed.append(shift)

        # ===== END SHIFTS =====
        for shift, offset in END_SHIFT_MAP.items():
            end_dt = close_dt - timedelta(minutes=offset)
            if pref_start <= end_dt <= pref_end:
                allowed.append(shift)

    return list(set(allowed))