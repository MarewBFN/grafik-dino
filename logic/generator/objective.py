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
    shop, # Zostawiam dla zachowania sygnatury, choć w tej logice nie jest używane
    SHIFT_OPEN,
    SHIFT_CLOSE,
    START_SHIFT_MAP,
    END_SHIFT_MAP
):
    print("[OBJECTIVE] balance daily Morning vs Afternoon staff")
    penalties = []

    # Iterujemy po dniach, a nie po pracownikach!
    for d in days:
        
        # Sumujemy wszystkie poranne zmiany (Otwarcie + przesunięcia od otwarcia) w danym dniu
        morning_shifts = sum(
            x[e, d, s]
            for e in range(len(employees))
            for s in [SHIFT_OPEN] + list(START_SHIFT_MAP.keys())
        )

        # Sumujemy wszystkie popołudniowe zmiany (Zamknięcie + przesunięcia do zamknięcia) w danym dniu
        afternoon_shifts = sum(
            x[e, d, s]
            for e in range(len(employees))
            for s in [SHIFT_CLOSE] + list(END_SHIFT_MAP.keys())
        )

        # Obliczamy różnicę między rano a popo
        diff = model.NewIntVar(-50, 50, f"daily_balance_diff_d{d}")
        model.Add(diff == morning_shifts - afternoon_shifts)

        # Pobieramy wartość absolutną różnicy (aby karać za odchylenia w obie strony)
        abs_diff = model.NewIntVar(0, 50, f"daily_balance_abs_d{d}")
        model.AddAbsEquality(abs_diff, diff)

        # Dodajemy różnicę do ogólnej puli kar (im większa różnica, tym gorzej)
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