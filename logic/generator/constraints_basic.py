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

    for e in range(len(employees)):
        for d in days:
            if not shop.is_trade_day(d):
                for s in all_shifts:
                    model.Add(x[e, d, s] == 0)

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