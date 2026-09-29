# Sprawdza, czy pracownik ma zaznaczony checkbox "Nie pracuje na popołudniu"
# i ogranicza go wyłącznie do zmian porannych (ten sam podział na "rano"/
# "popołudnie" co przy blokowaniu typu zmiany w manual_constraint.py:
# rano = SHIFT_OPEN + warianty startu od otwarcia,
# popołudnie = SHIFT_CLOSE + warianty końca przed zamknięciem).


def add_no_afternoon_constraint(
    model,
    x,
    employees,
    days,
    all_shifts,
    SHIFT_OPEN,
    SHIFT_CLOSE,
    START_SHIFT_MAP,
    END_SHIFT_MAP,
    soft=False,
    trace=None,
    schedule=None,
):
    if trace is not None:
        trace.log_constraint("no_afternoon", f"soft={soft}")

    violations = []

    afternoon_shifts = {SHIFT_CLOSE, *END_SHIFT_MAP.keys()}

    for e in range(len(employees)):
        emp = employees[e]

        if not getattr(emp, "no_afternoon", False):
            continue

        for d in days:
            # Patrz analogiczny komentarz w night_constraint.py - ręczny
            # wpis (is_locked) musi wygrywać, żeby wyjątkowe ręczne
            # popołudnie dla osoby z no_afternoon nie robiło modelu
            # sprzecznym.
            if schedule is not None and schedule.get_day(emp, d).is_locked:
                continue

            for s in afternoon_shifts:
                if soft:
                    v = model.NewBoolVar(f"no_afternoon_violation_e{e}_d{d}_s{s}")
                    model.Add(x[e, d, s] <= v)
                    violations.append(v)
                else:
                    model.Add(x[e, d, s] == 0)

    return violations
