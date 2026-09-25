from datetime import datetime

from logic.generator.constraints_basic import is_location_open_for_employee


def resolve_manual_shift(
    start,
    end,
    open_time,
    close_time,
    start_map,
    end_map
):
    fmt = "%H:%M"

    if start == open_time:
        return "OPEN"

    if end == close_time:
        return "CLOSE"

    open_dt = datetime.strptime(open_time, fmt)
    start_dt = datetime.strptime(start, fmt)

    diff = int((start_dt - open_dt).total_seconds() / 60)

    if diff in start_map:
        return start_map[diff]

    close_dt = datetime.strptime(close_time, fmt)
    end_dt = datetime.strptime(end, fmt)

    diff = int((close_dt - end_dt).total_seconds() / 60)

    if diff in end_map:
        return end_map[diff]

    return None


def add_manual_shift_constraints(
    model,
    x,
    employees,
    days,
    schedule,
    shop,
    all_shifts,
    SHIFT_OPEN,
    SHIFT_CLOSE,
    START_SHIFT_MAP,
    END_SHIFT_MAP,
    trace=None,
    shift_night=None,
):
    if trace is not None:
        trace.log_constraint("manual_shift", "apply locked/manual day assignments")

    for e in range(len(employees)):
        emp = employees[e]

        # Pracownicy rotacji 24/7 (duty_rotation) mają swoją, równoległą
        # wersję tego constraintu - logic/generator/duty_rotation_manual_constraint.py
        # (patrz jej docstring dla pełnego uzasadnienia). Ten stary model
        # OPEN/CLOSE/START/END/NIGHT nie zna pięciu zmian duty_rotation, a
        # próba dopasowania ręcznej blokady do niego dawała model sprzeczny
        # z add_duty_rotation_gate_constraint. Zero zmiany zachowania dla
        # każdego projektu bez duty_rotation (czyli każdego dzisiejszego
        # projektu Dino) - get_duty_rotation() zawsze zwraca None/pusty
        # słownik dla lokalizacji bez tej konfiguracji.
        if shop.get_location(emp).get_duty_rotation():
            continue

        # Analogicznie: pracownicy rotacji całodobowej "ogólnej" (round-clock,
        # patrz logic/generator/round_clock_constraint.py) mają swoją,
        # równoległą wersję tego constraintu -
        # round_clock_manual_constraint.py. Zero zmiany zachowania dla
        # każdej lokalizacji bez ustawionej round_clock_start_hour.
        if shop.get_location(emp).get_round_clock_start_hour():
            continue

        for d in days:

            day_state = schedule.get_day(emp, d)

            # 🔵 Zablokowany typ zmiany (1=rano/2=popołudnie) — solver sam
            # dobiera konkretny slot z odpowiedniej grupy.
            shift_class = getattr(day_state, "shift_class", None)
            if shift_class in ("1", "2") and not is_location_open_for_employee(shop, emp, d):
                # Dzień zamknięty w lokalizacji pracownika ("Nieczynne",
                # święto) - typ zmiany ustawiony, zanim dzień stał się
                # zamknięty, nie ma czego wymuszać (add_non_trade_day_constraints
                # i tak zeruje dzień; wymuszenie robiło cały miesiąc
                # niewykonalnym, a wcześniej dawało niewidoczną zmianę).
                continue
            if shift_class in ("1", "2"):
                if shift_class == "1":
                    allowed = {SHIFT_OPEN, *START_SHIFT_MAP.keys()}
                else:
                    allowed = {SHIFT_CLOSE, *END_SHIFT_MAP.keys()}

                model.Add(sum(x[e, d, s] for s in allowed) == 1)
                for s in all_shifts:
                    if s not in allowed:
                        model.Add(x[e, d, s] == 0)
                continue

            # 🔴 URLop
            if day_state.is_leave:
                for s in all_shifts:
                    model.Add(x[e, d, s] == 0)
                continue

            if not day_state.is_locked:
                continue

            start = getattr(day_state, "start", None)
            end = getattr(day_state, "end", None)

            # 🔴 wolne
            if not start or not end:
                for s in all_shifts:
                    model.Add(x[e, d, s] == 0)
                continue

            # 🌙 zmiana nocna (Etap D planu zmian nocnych) - rozpoznawana po
            # dokładnym dopasowaniu do skonfigurowanego okna tej lokalizacji
            # (jedyny wariant, jaki UI w ogóle pozwala zablokować, patrz
            # logic/schedule_controller.py). Sprawdzana przed
            # get_open_hours_for_day, bo okno nocne nie zależy od zwykłych
            # godzin otwarcia i dzień bez nich nie powinien tracić locka.
            shift = None
            if shift_night is not None:
                night_hours = shop.get_location(emp).get_night_shift_hours()
                if night_hours and (start, end) == night_hours:
                    shift = shift_night

            if shift is None:
                hours = shop.get_location(emp).get_open_hours_for_day(d)
                if not hours:
                    # Dzień zamknięty - add_non_trade_day_constraints zostawia
                    # zablokowaną zmianę tego dnia tej funkcji, a bez godzin
                    # otwarcia nie da się jej dopasować: blokujemy wszystko
                    # (inaczej solver mógłby tu przydzielić niewidoczną zmianę).
                    for s in all_shifts:
                        model.Add(x[e, d, s] == 0)
                    continue

                open_time, close_time = hours

                shift = resolve_manual_shift(
                    start,
                    end,
                    open_time,
                    close_time,
                    {v: k for k, v in START_SHIFT_MAP.items()},
                    {v: k for k, v in END_SHIFT_MAP.items()}
                )

                if shift == "OPEN":
                    shift = SHIFT_OPEN
                elif shift == "CLOSE":
                    shift = SHIFT_CLOSE

            # 🔥 KLUCZOWA POPRAWKA:
            # jeśli nie umiemy dopasować zmiany → blokujemy wszystko
            if shift is None:
                for s in all_shifts:
                    model.Add(x[e, d, s] == 0)
                continue

            # 🔥 HARD LOCK — solver MUSI to ustawić
            model.Add(x[e, d, shift] == 1)

            for s in all_shifts:
                if s != shift:
                    model.Add(x[e, d, s] == 0)