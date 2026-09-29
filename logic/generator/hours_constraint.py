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


def _duration_overrides_for_employee(shop, emp, shift_night, duty_shifts, opening_model=None):
    overrides = {}
    if shift_night is not None:
        overrides[shift_night] = night_shift_minutes_for_employee(shop, emp)
    if duty_shifts is not None:
        overrides.update(duty_rotation_minutes_for_employee(shop, emp, duty_shifts))
    if opening_model is not None:
        # Kafelki doby modelu godzin otwarcia (opening_hours_coverage.py).
        overrides.update(opening_model.duration_overrides(emp))
    return overrides


def _opening_minutes(x, emp, opening_model):
    """Minuty z modelu godzin otwarcia (opening_hours_coverage.py): zmiany
    o długości zależnej od dnia (całe okno 16 h, doba 24 h, połówka 12 h -
    w ogólnej sumie mają 0, patrz duration_overrides) i ręczne wpisy
    niepasujące do żadnego kształtu (stałe przedziały - bez zmiennej x, a
    realna praca)."""
    return opening_model.minutes_expr(x, emp) if opening_model is not None else 0


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
    opening_model=None,
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
            all_shifts, shift_minutes,
            _duration_overrides_for_employee(shop, emp, shift_night, duty_shifts, opening_model),
        )

        model.Add(
            total_minutes ==
            sum(
                x[e, d, s] * minutes_by_shift[s]
                for d in days
                for s in all_shifts
            )
            + planned_minutes_expr(x, e, emp, days, duty_shifts)
            + _opening_minutes(x, emp, opening_model)
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
    opening_model=None,
):
    if trace is not None:
        trace.log_constraint("balance", f"soft={soft}")

    nominal = shop.get_full_time_nominal_hours()

    if not nominal:
        return []

    violations = []

    # Górna granica sumy minut pracownika = pełna doba każdego dnia miesiąca
    # (+1 doba na zmianę przechodzącą w następny miesiąc). Wcześniej stałe
    # 20000 min (333 h) - za mało dla małej placówki 24/7 (2 osoby = ok.
    # 372 h każda), więc sam zakres zmiennej robił model niewykonalnym,
    # mimo że bilans jest tylko miękki (audyt 2026-09-28).
    max_minutes = (len(days) + 1) * 24 * 60

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
            all_shifts, shift_minutes,
            _duration_overrides_for_employee(shop, emp, shift_night, duty_shifts, opening_model),
        )

        total_minutes = model.NewIntVar(0, max_minutes, f"total_minutes_e{e}")

        model.Add(
            total_minutes ==
            sum(
                sum(x[e, d, s] * minutes_by_shift[s] for s in all_shifts)
                for d in days
            )
            + planned_minutes_expr(x, e, emp, days, duty_shifts)
            + _opening_minutes(x, emp, opening_model)
        )

        if not soft:
            model.Add(total_minutes == target_minutes)

        else:
            # Różnica sięga od -cel (nic nie przepracowane) do max_minutes.
            diff_bound = max(max_minutes, target_minutes)
            diff = model.NewIntVar(-diff_bound, diff_bound, f"diff_e{e}")
            model.Add(diff == total_minutes - target_minutes)

            abs_diff = model.NewIntVar(0, diff_bound, f"abs_diff_e{e}")
            model.AddAbsEquality(abs_diff, diff)

            violations.append(abs_diff)

    return violations