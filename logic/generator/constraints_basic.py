def add_one_shift_per_day_constraint(model, x, employees, days, all_shifts):
    for e in range(len(employees)):
        for d in days:
            model.Add(
                sum(x[e, d, s] for s in all_shifts) <= 1
            )

def add_non_trade_day_constraints(model, x, employees, days, shop, all_shifts):
    for e in range(len(employees)):
        for d in days:
            if not shop.is_trade_day(d):
                for s in all_shifts:
                    model.Add(x[e, d, s] == 0)

def add_leave_constraints(model, x, employees, days, schedule, all_shifts):
    for e in range(len(employees)):
        emp = employees[e]

        for d in days:
            day_state = schedule.get_day(emp, d)

            if day_state.is_leave:
                for s in all_shifts:
                    model.Add(x[e, d, s] == 0)

def add_day_off_constraints(model, x, employees, days, schedule, all_shifts):
    for e in range(len(employees)):
        emp = employees[e]

        for d in days:
            day_state = schedule.get_day(emp, d)

            if getattr(day_state, "is_day_off", False):
                for s in all_shifts:
                    model.Add(x[e, d, s] == 0)

def add_total_open_close_limit(model, x, employees, trade_days, shift_open, shift_close):
    print("[CONSTRAINT] total_open_close_limit = 6")

    for d in trade_days:
        print(f"  day={d}")

        total_open_close = sum(
            x[e, d, shift_open] + x[e, d, shift_close]
            for e in range(len(employees))
        )

        model.Add(total_open_close == 6)