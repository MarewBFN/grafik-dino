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