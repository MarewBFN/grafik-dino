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
    duty_shifts=None,
    round_clock_shifts=None,
):
    if trace is not None:
        trace.log_constraint("work_dependency", "work shifts depend on open/close coverage")

    print("[CONSTRAINT] work_dependency")

    duty_shift_ids = set(duty_shifts.values()) if duty_shifts else set()
    round_clock_shift_ids = set(round_clock_shifts) if round_clock_shifts else set()

    for d in days:

        total_open_close = sum(
            x[e, d, SHIFT_OPEN] + x[e, d, SHIFT_CLOSE]
            for e in range(len(employees))
        )

        for e in range(len(employees)):
            for s in ALL_SHIFTS:

                if s in (SHIFT_OPEN, SHIFT_CLOSE):
                    continue

                # SHIFT_NIGHT (Etap C planu zmian nocnych), pięć zmian
                # rotacji 24/7 dla Ochrony (Etap B planu profilu ochrona) i
                # kafelki rotacji całodobowej "ogólnej" (round_clock_constraint.py)
                # to samodzielne zmiany, niezależne od OPEN/CLOSE - dla
                # lokalizacji 24/7 bez żadnej obsady OPEN/CLOSE
                # total_open_close jest zawsze 0, co bez tego wyjątku
                # blokowałoby je całkowicie. Pozostałe WORK_START/END nadal
                # zależą od OPEN/CLOSE tak jak dziś (u Dino to zmiany
                # "doraźne", sensowne tylko obok otwarcia/zamknięcia).
                if s == shift_night or s in duty_shift_ids or s in round_clock_shift_ids:
                    continue

                model.Add(
                    x[e, d, s] <= total_open_close
                )