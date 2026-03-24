from logic.generator.rest_constraint import get_effective_daily_hours

def add_open_close_penalty(x, employees, days, SHIFT_OPEN, SHIFT_CLOSE):
    print("[OBJECTIVE] penalty OPEN/CLOSE usage")
    penalties = []

    for e in range(len(employees)):
        for d in days:
            penalties.append(x[e, d, SHIFT_OPEN])
            penalties.append(x[e, d, SHIFT_CLOSE])

    return penalties


def add_work_balance_penalty(
    model,
    x,
    employees,
    days,
    START_SHIFT_MAP,
    END_SHIFT_MAP
):
    penalties = []

    for e in range(len(employees)):

        work_start = sum(
            x[e, d, s]
            for d in days
            for s in START_SHIFT_MAP.keys()
        )

        work_end = sum(
            x[e, d, s]
            for d in days
            for s in END_SHIFT_MAP.keys()
        )

        diff = model.NewIntVar(-31, 31, f"work_balance_diff_e{e}")
        model.Add(diff == work_start - work_end)

        abs_diff = model.NewIntVar(0, 31, f"work_balance_abs_e{e}")
        model.AddAbsEquality(abs_diff, diff)

        penalties.append(abs_diff)

    return penalties

def add_morning_afternoon_balance_penalty(
    model,
    x,
    employees,
    days,
    shop,
    SHIFT_OPEN,
    SHIFT_CLOSE,
    START_SHIFT_MAP,
    END_SHIFT_MAP
):
    penalties = []

    for e in range(len(employees)):
        emp = employees[e]

        shift_minutes = int(get_effective_daily_hours(emp, shop) * 60)

        morning = sum(
            x[e, d, SHIFT_OPEN] * shift_minutes
            for d in days
        ) + sum(
            x[e, d, s] * shift_minutes
            for d in days
            for s in START_SHIFT_MAP.keys()
        )

        afternoon = sum(
            x[e, d, SHIFT_CLOSE] * shift_minutes
            for d in days
        ) + sum(
            x[e, d, s] * shift_minutes
            for d in days
            for s in END_SHIFT_MAP.keys()
        )

        diff = model.NewIntVar(-50000, 50000, f"morning_afternoon_diff_e{e}")
        model.Add(diff == morning - afternoon)

        abs_diff = model.NewIntVar(0, 50000, f"morning_afternoon_abs_e{e}")
        model.AddAbsEquality(abs_diff, diff)

        penalties.append(abs_diff)

    return penalties

def add_edge_shift_bonus(
    model,
    x,
    employees,
    days,
    SHIFT_WORK_START_15,
    SHIFT_WORK_END_15
):
    penalties = []

    for d in days:

        start_15_exists = model.NewBoolVar(f"start15_exists_d{d}")
        end_15_exists = model.NewBoolVar(f"end15_exists_d{d}")

        # czy ktoś ma +15 od otwarcia
        model.Add(
            sum(x[e, d, SHIFT_WORK_START_15] for e in range(len(employees))) >= 1
        ).OnlyEnforceIf(start_15_exists)

        model.Add(
            sum(x[e, d, SHIFT_WORK_START_15] for e in range(len(employees))) == 0
        ).OnlyEnforceIf(start_15_exists.Not())

        # czy ktoś ma -15 od zamknięcia
        model.Add(
            sum(x[e, d, SHIFT_WORK_END_15] for e in range(len(employees))) >= 1
        ).OnlyEnforceIf(end_15_exists)

        model.Add(
            sum(x[e, d, SHIFT_WORK_END_15] for e in range(len(employees))) == 0
        ).OnlyEnforceIf(end_15_exists.Not())

        # kara jeśli brak
        penalties.append(start_15_exists.Not())
        penalties.append(end_15_exists.Not())

    return penalties