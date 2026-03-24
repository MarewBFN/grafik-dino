from datetime import datetime, timedelta


def get_effective_daily_hours(emp, shop):
    if emp.employment_fraction == 1.0:
        hours = shop.standard_daily_hours
    else:
        hours = 8.0

    minutes = int(hours * 60)
    minutes = (minutes // 15) * 15

    return minutes / 60


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
        return None

    hours = shop.get_open_hours_for_day(day)
    if not hours:
        return []

    open_time, close_time = hours
    fmt = "%H:%M"

    open_dt = datetime.strptime(open_time, fmt)
    close_dt = datetime.strptime(close_time, fmt)

    eff_hours = get_effective_daily_hours(emp, shop)
    shift_delta = timedelta(hours=eff_hours)

    allowed = []

    for rule in rules:
        start_pref = rule["start"]
        end_pref = rule["end"]

        pref_start = datetime.strptime(start_pref, fmt)
        pref_end = datetime.strptime(end_pref, fmt)

        # ===== OPEN =====
        start = open_dt
        end = start + shift_delta
        if pref_start <= start and end <= pref_end:
            allowed.append(SHIFT_OPEN)

        # ===== CLOSE =====
        end = close_dt
        start = end - shift_delta
        if pref_start <= start and end <= pref_end:
            allowed.append(SHIFT_CLOSE)

        # ===== START SHIFTS =====
        for shift, offset in START_SHIFT_MAP.items():
            start = open_dt + timedelta(minutes=offset)
            end = start + shift_delta

            if pref_start <= start and end <= pref_end:
                allowed.append(shift)

        # ===== END SHIFTS =====
        for shift, offset in END_SHIFT_MAP.items():
            end = close_dt - timedelta(minutes=offset)
            start = end - shift_delta

            if pref_start <= start and end <= pref_end:
                allowed.append(shift)

    return list(set(allowed))