def add_work_dependency_constraint(
    model,
    x,
    employees,
    days,
    SHIFT_OPEN,
    SHIFT_CLOSE,
    ALL_SHIFTS,
    trace=None
):
    if trace is not None:
        trace.log_constraint("work_dependency", "work shifts depend on open/close coverage")

    print("[CONSTRAINT] work_dependency")

    for d in days:

        total_open_close = sum(
            x[e, d, SHIFT_OPEN] + x[e, d, SHIFT_CLOSE]
            for e in range(len(employees))
        )

        for e in range(len(employees)):
            for s in ALL_SHIFTS:

                if s in (SHIFT_OPEN, SHIFT_CLOSE):
                    continue

                model.Add(
                    x[e, d, s] <= total_open_close
                )