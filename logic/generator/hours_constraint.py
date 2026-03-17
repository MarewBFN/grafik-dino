def add_monthly_hours_constraint(
    model,
    x,
    employees,
    days,
    schedule,
    shop,
    all_shifts,
    soft=False
):
    violations = []

    nominal_hours = shop.get_full_time_nominal_hours()
    nominal_minutes = nominal_hours * 60

    all_totals = []

    for e in range(len(employees)):

        emp = employees[e]
        shift_minutes = int(emp.daily_hours * 60)

        total_minutes = model.NewIntVar(0, 50000, f"month_total_e{e}")

        model.Add(
            total_minutes ==
            sum(
                x[e, d, s] * shift_minutes
                for d in days
                for s in all_shifts
            )
        )

        all_totals.append(total_minutes)

        leave_days = sum(
            1 for d in days
            if schedule.get_day(emp, d).is_leave
        )

        leave_minutes = leave_days * 480

        target_minutes = int(nominal_minutes * (emp.daily_hours / 8) - leave_minutes)
        max_minutes = target_minutes + (8 * 60)

        if not soft:
            model.Add(total_minutes >= target_minutes)
            model.Add(total_minutes <= max_minutes)

        else:
            under = model.NewIntVar(0, 50000, f"under_e{e}")
            model.Add(total_minutes + under >= max_minutes)

            over = model.NewIntVar(0, 50000, f"over_e{e}")
            model.Add(total_minutes <= target_minutes + over)

            violations.append(under)
            violations.append(over)

    if soft and len(all_totals) > 1:

        max_total = model.NewIntVar(0, 50000, "month_max_total")
        min_total = model.NewIntVar(0, 50000, "month_min_total")

        model.AddMaxEquality(max_total, all_totals)
        model.AddMinEquality(min_total, all_totals)

        spread = model.NewIntVar(0, 50000, "month_spread")
        model.Add(spread == max_total - min_total)

        violations.append(spread)

    return violations


def add_balance_constraint(
    model,
    x,
    employees,
    days,
    shop,
    all_shifts,
    soft=True
):
    nominal = shop.get_full_time_nominal_hours()

    if not nominal:
        return []

    nominal_minutes = int(nominal * 60)
    violations = []

    for e in range(len(employees)):

        shift_minutes = int(employees[e].daily_hours * 60)

        total_minutes = model.NewIntVar(0, 20000, f"total_minutes_e{e}")

        model.Add(
            total_minutes ==
            sum(
                sum(x[e, d, s] for s in all_shifts) * shift_minutes
                for d in days
            )
        )

        if not soft:
            model.Add(total_minutes == nominal_minutes)

        else:
            diff = model.NewIntVar(-20000, 20000, f"diff_e{e}")
            model.Add(diff == total_minutes - nominal_minutes)

            abs_diff = model.NewIntVar(0, 20000, f"abs_diff_e{e}")
            model.AddAbsEquality(abs_diff, diff)

            violations.append(abs_diff)

    return violations