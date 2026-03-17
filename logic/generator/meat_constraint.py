from datetime import datetime, timedelta


def add_meat_constraint(
    model,
    x,
    employees,
    days,
    trade_days,
    all_shifts,
    SHIFT_OPEN,
    SHIFT_CLOSE,
    soft=False
):
    violations = []

    for d in trade_days:

        meat_on_open = sum(
            x[e, d, SHIFT_OPEN]
            for e in range(len(employees))
            if employees[e].is_meat
        )

        meat_on_close = sum(
            x[e, d, SHIFT_CLOSE]
            for e in range(len(employees))
            if employees[e].is_meat
        )

        meat_on_work = sum(
            x[e, d, s]
            for e in range(len(employees))
            for s in all_shifts
            if s not in (SHIFT_OPEN, SHIFT_CLOSE)
            and employees[e].is_meat
        )

        total_work = sum(
            x[e, d, s]
            for e in range(len(employees))
            for s in all_shifts
            if s not in (SHIFT_OPEN, SHIFT_CLOSE)
        )

        if not soft:
            work_exists = model.NewBoolVar(f"work_exists_d{d}")

            model.Add(total_work >= 1).OnlyEnforceIf(work_exists)
            model.Add(total_work == 0).OnlyEnforceIf(work_exists.Not())

            model.Add(
                meat_on_work >= 1
            ).OnlyEnforceIf(work_exists)

        else:
            v1 = model.NewBoolVar(f"meat_open_v_d{d}")
            model.Add(meat_on_open + v1 >= 1)
            violations.append(v1)

            v2 = model.NewBoolVar(f"meat_close_v_d{d}")
            model.Add(meat_on_close + v2 >= 1)
            violations.append(v2)

    return violations

def add_meat_coverage_constraint(
    model,
    x,
    employees,
    trade_days,
    shop,
    SHIFT_OPEN,
    SHIFT_CLOSE,
    START_SHIFT_MAP,
    END_SHIFT_MAP,
    soft=False
):
    violations = []

    for d in trade_days:

        hours = shop.get_open_hours_for_day(d)
        if not hours:
            continue

        open_time, close_time = hours

        fmt = "%H:%M"
        open_dt = datetime.strptime(open_time, fmt)
        close_dt = datetime.strptime(close_time, fmt)

        t = open_dt

        while t < close_dt:

            slot = t.strftime(fmt)
            meat_cover = []

            for e in range(len(employees)):

                if not employees[e].is_meat:
                    continue

                emp = employees[e]
                shift_len = timedelta(hours=emp.daily_hours)

                # OPEN
                start = open_dt
                end = start + shift_len

                if start <= t < end:
                    meat_cover.append(x[e, d, SHIFT_OPEN])

                # CLOSE
                end = close_dt
                start = end - shift_len

                if start <= t < end:
                    meat_cover.append(x[e, d, SHIFT_CLOSE])

                # WORK od otwarcia
                for shift, offset in START_SHIFT_MAP.items():
                    work_start = open_dt + timedelta(minutes=offset)
                    work_end = work_start + shift_len
                    if work_start <= t < work_end:
                        meat_cover.append(x[e, d, shift])

                # WORK od zamknięcia
                for shift, offset in END_SHIFT_MAP.items():
                    work_end = close_dt - timedelta(minutes=offset)
                    work_start = work_end - shift_len
                    if work_start <= t < work_end:
                        meat_cover.append(x[e, d, shift])

            if not meat_cover:
                t += timedelta(minutes=15)
                continue

            if not soft:
                model.Add(sum(meat_cover) >= 1)

            else:
                v = model.NewBoolVar(f"meat_cover_v_d{d}_{slot}")
                model.Add(sum(meat_cover) + v >= 1)
                violations.append(v)

            t += timedelta(minutes=15)

    return violations