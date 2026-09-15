from datetime import datetime, timedelta


def get_effective_daily_hours(emp, shop):
    # 🔴 specjalny fulltime max 8h
    if emp.employment_fraction == 1.01:
        hours = 8.0

    # 🔴 normalny fulltime z wymuszeniem 8:30
    elif shop.constraints.get("force_fulltime_845", False) and emp.employment_fraction == 1.0:
        hours = 8.50

    else:
        hours = shop.standard_daily_hours * emp.employment_fraction

    minutes = int(hours * 60)
    minutes = (minutes // 15) * 15

    return minutes / 60


def classify_shift_as_morning_or_afternoon(shift_start, shift_end, shop_open_dt, shop_close_dt):
    """Classify a shift based on the actual shop opening/closing window.

    The previous logic used a fixed noon-like assumption and misclassified
    special days such as 10:00-18:00 or 05:30-22:45. We now compare the
    midpoint of the assigned shift to the midpoint of the shop's operating
    window so that the split is based on real opening/closing hours.
    """

    if not shop_open_dt or not shop_close_dt:
        return None

    if shift_start is None or shift_end is None:
        return None

    if shift_end <= shift_start:
        return "morning"

    window = shop_close_dt - shop_open_dt
    if window <= timedelta(0):
        return "morning"

    shop_midpoint = shop_open_dt + (window / 2)
    shift_midpoint = shift_start + ((shift_end - shift_start) / 2)

    return "morning" if shift_midpoint <= shop_midpoint else "afternoon"


def daily_subintervals(start_minutes, end_minutes):
    """Splits a possibly midnight-crossing, recurring-daily [start, end)
    window (minutes-of-day) into 1 or 2 non-wrapping sub-intervals within
    [0, 1440) - the building block for comparing two such recurring windows
    (e.g. a no_night/role_time_restriction window and a location's
    night_shift window) for overlap without anchoring either to a specific
    calendar date."""
    start_minutes %= 1440
    length = (end_minutes - start_minutes) % 1440 or 1440
    end = start_minutes + length
    if end <= 1440:
        return [(start_minutes, end)]
    return [(start_minutes, 1440), (0, end - 1440)]


def daily_windows_overlap(a_start_minutes, a_end_minutes, b_start_minutes, b_end_minutes):
    """True gdy dwa powtarzające się codziennie okna [start, end) (w
    minutach dnia) pokrywają się choć częściowo - poprawne niezależnie od
    tego, które z nich (lub oba) przechodzi przez północ."""
    a_parts = daily_subintervals(a_start_minutes, a_end_minutes)
    b_parts = daily_subintervals(b_start_minutes, b_end_minutes)
    return any(a[0] < b[1] and b[0] < a[1] for a in a_parts for b in b_parts)


def hour_window_overlaps_time_range(window_start_hour, window_end_hour, hhmm_range):
    """True gdy godzinowe okno [window_start_hour, window_end_hour) pokrywa
    się choć częściowo z zakresem podanym jako para "HH:MM" (np. night_shift
    lokalizacji) - np. dla no_night (domyślnie 22-6) i lokalizacji, której
    "night_shift" jest w rzeczywistości blokiem w środku dnia, to False."""
    start_str, end_str = hhmm_range
    fmt = "%H:%M"
    start_dt = datetime.strptime(start_str, fmt)
    end_dt = datetime.strptime(end_str, fmt)
    return daily_windows_overlap(
        window_start_hour * 60, window_end_hour * 60,
        start_dt.hour * 60 + start_dt.minute, end_dt.hour * 60 + end_dt.minute,
    )