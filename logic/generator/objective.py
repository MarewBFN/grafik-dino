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