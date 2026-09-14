def add_work_dependency_constraint(
    model,
    x,
    employees,
    days,
    SHIFT_OPEN,
    SHIFT_CLOSE,
    ALL_SHIFTS,
    trace=None,
    shift_night=None,
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

                # SHIFT_NIGHT (Etap C planu zmian nocnych) to samodzielna
                # zmiana, niezależna od OPEN/CLOSE - dla profilu 24/7 bez
                # żadnej obsady OPEN/CLOSE total_open_close jest zawsze 0,
                # co bez tego wyjątku blokowałoby ją całkowicie. Pozostałe
                # WORK_START/END nadal zależą od OPEN/CLOSE tak jak dziś
                # (u Dino to zmiany "doraźne", sensowne tylko obok
                # otwarcia/zamknięcia).
                if s == shift_night:
                    continue

                model.Add(
                    x[e, d, s] <= total_open_close
                )