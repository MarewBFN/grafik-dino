from datetime import datetime, timedelta


def get_effective_daily_hours(emp, shop):
    # 🔴 specjalny fulltime max 8h
    if emp.employment_fraction == 1.01:
        hours = 8.0

    # 🔴 normalny fulltime z wymuszeniem 8:30
    elif shop.constraints.get("force_fulltime_845", False) and emp.employment_fraction == 1.0:
        hours = 8.50

    else:
        hours = 8.0 * emp.employment_fraction

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