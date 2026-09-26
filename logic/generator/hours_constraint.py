from logic.generator.duty_rotation_manual_coverage import planned_minutes_expr
from logic.utils.time_utils import get_effective_daily_hours
from logic.generator.night_shift_constraint import night_shift_minutes_for_employee
from logic.generator.duty_rotation_constraint import duty_rotation_minutes_for_employee


def _shift_minutes_by_type(all_shifts, standard_minutes, overrides):
    """Minuty przypisane każdej zmianie z all_shifts - stała, wspólna
    wartość dla wszystkich zwykłych zmian (tak jak dziś), z wyjątkiem
    zmian o własnym, sztywnym czasie trwania niezależnym od
    get_effective_daily_hours pracownika (SHIFT_NIGHT - Etap C planu zmian
    nocnych - i pięć zmian rotacji 24/7 - Etap B planu profilu ochrona),
    przekazanych w `overrides` jako {shift_id: minuty}."""
    return {s: overrides.get(s, standard_minutes) for s in all_shifts}


def _duration_overrides_for_employee(shop, emp, shift_night, duty_shifts):
    overrides = {}
    if shift_night is not None:
        overrides[shift_night] = night_shift_minutes_for_employee(shop, emp)
    if duty_shifts is not None:
        overrides.update(duty_rotation_minutes_for_employee(shop, emp, duty_shifts))
    return overrides


def add_monthly_hours_constraint(
    model,
    x,
    employees,
    days,
    schedule,
    shop,
    all_shifts,
    soft=False,
    trace=None,
    shift_night=None,
    duty_shifts=None,
):
    violations = []

    if trace is not None:
        trace.log_constraint("monthly_hours", f"soft={soft}")

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

        daily_hours = get_effective_daily_hours(emp, shop)

        leave_minutes = int(leave_days * daily_hours * 60)
        sick_minutes = int(sick_days * daily_hours * 60)

        total_minutes = model.NewIntVar(0, 50000, f"month_total_e{e}")

        minutes_by_shift = _shift_minutes_by_type(
            all_shifts, shift_minutes, _duration_overrides_for_employee(shop, emp, shift_night, duty_shifts),
        )

        model.Add(
            total_minutes ==
            sum(
                x[e, d, s] * minutes_by_shift[s]
                for d in days
                for s in all_shifts
            )
            + planned_minutes_expr(x, e, emp, days, duty_shifts)
        )

        all_totals.append(total_minutes)
        # Przycięte do 0 - "musisz przepracować mniej niż nic" nie ma sensu.
        # Bez tego pracownik na L4/urlopie obejmującym większość albo cały
        # miesiąc miał target_minutes ujemny, co w trybie miękkim liczyło
        # fikcyjną karę "over" (bo total_minutes=0 wypada wtedy "ponad"
        # ujemny cel), a w trybie twardym (MANDATORY) potrafiło zrobić model
        # niewykonalnym (górna granica total_minutes <= target + pasmo też
        # schodziła poniżej 0, sprzecznie z total_minutes >= 0).
        target_minutes = max(0, int(nominal_minutes * emp.employment_fraction - leave_minutes - sick_minutes))

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
    schedule,
    shop,
    all_shifts,
    soft=True,
    trace=None,
    shift_night=None,
    duty_shifts=None,
):
    if trace is not None:
        trace.log_constraint("balance", f"soft={soft}")

    nominal = shop.get_full_time_nominal_hours()

    if not nominal:
        return []

    violations = []

    for e in range(len(employees)):

        emp = employees[e]

        nominal_minutes = int(nominal * 60 * emp.employment_fraction)
        daily_hours = get_effective_daily_hours(emp, shop)
        shift_minutes = int(daily_hours * 60)

        # L4/urlop pomniejszają cel bilansu tak samo jak monthly_hours
        # (add_monthly_hours_constraint) - wcześniej ten constraint w ogóle
        # ich nie liczył, więc pracownik na dłuższym zwolnieniu zawsze
        # wypadał maksymalnie "niedobity" do nominału, niezależnie od tego,
        # ile realnie mógł przepracować. Przycięte do 0 z tego samego powodu
        # co tam - ujemny cel nie ma sensu.
        leave_days = 0
        sick_days = 0
        for d in days:
            ds = schedule.get_day(emp, d)
            if ds.is_leave:
                leave_days += 1
            if getattr(ds, "is_sick", False):
                sick_days += 1

        leave_minutes = int(leave_days * daily_hours * 60)
        sick_minutes = int(sick_days * daily_hours * 60)
        target_minutes = max(0, nominal_minutes - leave_minutes - sick_minutes)

        minutes_by_shift = _shift_minutes_by_type(
            all_shifts, shift_minutes, _duration_overrides_for_employee(shop, emp, shift_night, duty_shifts),
        )

        total_minutes = model.NewIntVar(0, 20000, f"total_minutes_e{e}")

        model.Add(
            total_minutes ==
            sum(
                sum(x[e, d, s] * minutes_by_shift[s] for s in all_shifts)
                for d in days
            )
            + planned_minutes_expr(x, e, emp, days, duty_shifts)
        )

        if not soft:
            model.Add(total_minutes == target_minutes)

        else:
            diff = model.NewIntVar(-20000, 20000, f"diff_e{e}")
            model.Add(diff == total_minutes - target_minutes)

            abs_diff = model.NewIntVar(0, 20000, f"abs_diff_e{e}")
            model.AddAbsEquality(abs_diff, diff)

            violations.append(abs_diff)

    return violations