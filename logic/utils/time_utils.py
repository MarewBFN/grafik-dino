def get_effective_daily_hours(emp, shop):
    # 🔴 tylko full-time dostaje 8:45
    if shop.constraints.get("force_fulltime_845", False) and emp.employment_fraction == 1.0:
        hours = 8.50
    else:
        # 🔴 zawsze bazujemy na 8h dla ułamków
        hours = 8.0 * emp.employment_fraction

    minutes = int(hours * 60)
    minutes = (minutes // 15) * 15

    return minutes / 60