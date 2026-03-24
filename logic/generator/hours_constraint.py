from logic.utils.time_utils import get_effective_daily_hours


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
        shift_minutes = int(get_effective_daily_hours(emp, shop) * 60)

        leave_days = 0
        sick_days = 0

        for d in days:
            ds = schedule.get_day(emp, d)
            if ds.is_leave:
                leave_days += 1
            if getattr(ds, "is_sick", False):
                sick_days += 1

        leave_minutes = int(leave_days * emp.daily_hours * 60)
        sick_minutes = int(sick_days * emp.daily_hours * 60)

        total_minutes = model.NewIntVar(0, 50000, f"month_total_e{e}")

        model.Add(
            total_minutes ==
            sum(
                x[e, d, s] * shift_minutes
                for d in days
                for s in all_shifts
                if s != 14
            )
        )

        all_totals.append(total_minutes)
        target_minutes = int(nominal_minutes * emp.employment_fraction - leave_minutes - sick_minutes)

        if not soft:
            model.Add(total_minutes >= target_minutes)
            model.Add(total_minutes <= target_minutes + (emp.daily_hours * 60))

        else:
            under = model.NewIntVar(0, 50000, f"under_e{e}")
            model.Add(total_minutes + under >= target_minutes)

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

    violations = []

    for e in range(len(employees)):

        emp = employees[e]

        nominal_minutes = int(nominal * 60 * emp.employment_fraction)
        shift_minutes = int(get_effective_daily_hours(emp, shop) * 60)

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