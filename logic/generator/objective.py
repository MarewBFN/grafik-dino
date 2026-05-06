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
    print("[OBJECTIVE] balance daily Morning vs Afternoon staff")
    penalties = []

    for d in days:

        # 🔥 tylko zmiany blisko otwarcia = rano
        morning_shifts = sum(
            x[e, d, s]
            for e in range(len(employees))
            for s in (
                [SHIFT_OPEN] +
                [k for k, v in START_SHIFT_MAP.items() if v <= 60]
            )
        )

        # 🔥 tylko zmiany blisko zamknięcia = popo
        afternoon_shifts = sum(
            x[e, d, s]
            for e in range(len(employees))
            for s in (
                [SHIFT_CLOSE] +
                [k for k, v in END_SHIFT_MAP.items() if v <= 60]
            )
        )

        diff = model.NewIntVar(-50, 50, f"daily_balance_diff_d{d}")
        model.Add(diff == morning_shifts - afternoon_shifts)

        abs_diff = model.NewIntVar(0, 50, f"daily_balance_abs_d{d}")
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

        model.Add(
            sum(x[e, d, SHIFT_WORK_START_15] for e in range(len(employees))) >= 1
        ).OnlyEnforceIf(start_15_exists)

        model.Add(
            sum(x[e, d, SHIFT_WORK_START_15] for e in range(len(employees))) == 0
        ).OnlyEnforceIf(start_15_exists.Not())

        model.Add(
            sum(x[e, d, SHIFT_WORK_END_15] for e in range(len(employees))) >= 1
        ).OnlyEnforceIf(end_15_exists)

        model.Add(
            sum(x[e, d, SHIFT_WORK_END_15] for e in range(len(employees))) == 0
        ).OnlyEnforceIf(end_15_exists.Not())

        penalties.append(start_15_exists.Not())
        penalties.append(end_15_exists.Not())

    return penalties