def add_one_shift_per_day_constraint(model, x, employees, days, all_shifts, trace=None):
    if trace is not None:
        trace.log_constraint("one_shift_per_day", "each employee can have at most one shift per day")

    for e in range(len(employees)):
        for d in days:
            model.Add(
                sum(x[e, d, s] for s in all_shifts) <= 1
            )

def add_non_trade_day_constraints(model, x, employees, days, shop, all_shifts, trace=None):
    if trace is not None:
        trace.log_constraint("non_trade_day", "block work on non-trade days")

    for e, emp in enumerate(employees):
        location = shop.get_location(emp)
        # Rotacja służby 24/7 nie korzysta z godzin otwarcia - święta ma
        # własną regułę (duty_rotation_public_holiday_constraint.py).
        uses_open_hours = not location.get_duty_rotation()
        for d in days:
            if not shop.is_trade_day(d) or not is_location_open_for_employee(shop, emp, d, uses_open_hours):
                for s in all_shifts:
                    model.Add(x[e, d, s] == 0)


def is_location_open_for_employee(shop, emp, day, uses_open_hours=None):
    """False gdy lokalizacja pracownika nie ma tego dnia godzin otwarcia -
    dzień "Nieczynne" w godzinach otwarcia, polskie święto przy
    "Zamknięte w polskie święta ustawowe" albo ręczne zamknięcie dnia w
    grafiku (patrz LocationConfig.get_open_hours_for_day()). Wcześniej
    solver przydzielał w takie dni zmiany, a save_solution je po cichu
    pomijało - te niewidoczne zmiany liczyły się mimo to do godzin,
    odpoczynku i dni pod rząd. Pracownicy rotacji służby 24/7 zawsze True
    (patrz add_non_trade_day_constraints)."""
    location = shop.get_location(emp)
    if uses_open_hours is None:
        uses_open_hours = not location.get_duty_rotation()
    if not uses_open_hours:
        return True
    return bool(location.get_open_hours_for_day(day))

def add_leave_constraints(model, x, employees, days, schedule, all_shifts, trace=None):
    if trace is not None:
        trace.log_constraint("leave", "block all shifts on leave days")

    for e in range(len(employees)):
        emp = employees[e]

        for d in days:
            day_state = schedule.get_day(emp, d)

            if day_state.is_leave or day_state.is_sick:
                for s in all_shifts:
                    model.Add(x[e, d, s] == 0)

def add_day_off_constraints(model, x, employees, days, schedule, all_shifts, trace=None):
    if trace is not None:
        trace.log_constraint("day_off", "block all shifts on day off")

    for e in range(len(employees)):
        emp = employees[e]

        for d in days:
            day_state = schedule.get_day(emp, d)

            if getattr(day_state, "is_day_off", False):
                for s in all_shifts:
                    model.Add(x[e, d, s] == 0)