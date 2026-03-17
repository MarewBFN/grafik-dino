from datetime import datetime


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
    END_SHIFT_MAP
):
    for e in range(len(employees)):
        emp = employees[e]

        for d in days:

            day_state = schedule.get_day(emp, d)

            start = getattr(day_state, "start_time", None)
            end = getattr(day_state, "end_time", None)

            if not start or not end:
                continue

            hours = shop.get_open_hours_for_day(d)
            if not hours:
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

            if shift is None:
                continue

            model.Add(x[e, d, shift] == 1)

            for s in all_shifts:
                if s != shift:
                    model.Add(x[e, d, s] == 0)