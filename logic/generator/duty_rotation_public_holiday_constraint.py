"""Zamyka lokalizacje z duty_rotation w polskie święta ustawowo wolne od
pracy, gdy LocationConfig.closed_on_public_holidays jest włączone
(domyślnie tak) - patrz LocationConfig.is_closed_for_public_holiday() - oraz
w dni ręcznie oznaczone "Nieczynne tego dnia" (nagłówek dnia w grafiku,
day_overrides bez godzin) - patrz LocationConfig.is_duty_day_closed().

Lokalizacje z duty_rotation w ogóle nie korzystają z open_hours/kalendarza
handlowego (patrz duty_rotation_constraint.py) - `add_non_trade_day_constraints`
(constraints_basic.py, oparte o shop.is_trade_day - poziom całego projektu)
nigdy więc dla nich nie zadziała, i to niezależnie od tego, czy profil w
ogóle ma kalendarz handlowy (uses_trade_calendar). Ten mechanizm jest z tego
powodu jego odpowiednikiem PER LOKALIZACJA, niezależnym od obu.

Wpięta RÓWNOLEGLE do add_duty_rotation_coverage_constraint
(duty_rotation_constraint.py, patrz base_specs.py) - ta funkcja zeruje
przypisania zmian duty w zamknięty dzień, a add_duty_rotation_coverage_constraint
osobno pomija wymóg pokrycia dla tych samych dni, żeby nie zbudować modelu
sprzecznego z samym sobą (twarde `count == 1` obok twardego `count == 0`)."""


from logic.generator.duty_rotation_manual_coverage import custom_shift_ids


def add_duty_rotation_public_holiday_constraint(
    model, x, employees, days, schedule, shop, duty_shifts, trace=None,
):
    if trace is not None:
        trace.log_constraint(
            "duty_rotation_public_holiday",
            "closes duty-rotation locations on PL public holidays per the location's own setting",
        )

    # Bez zmian resztkowych (duty_rotation_manual_coverage.py) - kawałek po
    # północy w zamknięty dzień należy do doby dnia poprzedniego, a brama
    # rotacji i tak blokuje każdą zmianę resztkową, której plan nie wyznaczył.
    duty_shift_ids = set(duty_shifts.values()) - set(custom_shift_ids(duty_shifts))

    for e, emp in enumerate(employees):
        rotation = shop.get_location(emp).get_duty_rotation()
        if not rotation:
            continue

        location = shop.locations.get(emp.location_key)
        if location is None:
            continue

        for d in days:
            if not location.is_duty_day_closed(shop.year, shop.month, d):
                continue

            # Ręczne, jawne zablokowanie/przypisanie zmiany tego dnia
            # (dwuklik na komórce w gridzie) wygrywa - ten sam priorytet co
            # day_overrides ma nad automatycznym zamknięciem w
            # LocationConfig.is_closed_for_public_holiday() - inaczej ręczne
            # wymuszenie zmiany w automatycznie zamknięty dzień budowałoby
            # model sprzeczny z samym sobą (x==1 tu, x==0 przez ten
            # constraint). Wolny/pusty dzień (is_locked bez start) i tak
            # trafia w pętlę niżej - to samo zero, co i tak by tu wyszło.
            day_state = schedule.get_day(emp, d)
            if day_state.is_locked and getattr(day_state, "start", None):
                continue

            for s in duty_shift_ids:
                model.Add(x[e, d, s] == 0)
