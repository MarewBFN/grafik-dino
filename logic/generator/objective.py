from datetime import datetime, timedelta

from ortools.sat.python import cp_model

from logic.utils.time_utils import classify_shift_as_morning_or_afternoon, get_effective_daily_hours


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
    shop,
    SHIFT_OPEN,
    SHIFT_CLOSE,
    START_SHIFT_MAP,
    END_SHIFT_MAP
):
    print("[OBJECTIVE] balance daily Morning vs Afternoon staff")
    penalties = []

    fmt = "%H:%M"

    for d in days:
        hours = shop.get_open_hours_for_day(d)
        if not hours:
            continue

        open_time_str, close_time_str = hours
        shop_open_dt = datetime.strptime(open_time_str, fmt)
        shop_close_dt = datetime.strptime(close_time_str, fmt)

        morning_shifts = 0
        afternoon_shifts = 0

        for e, emp in enumerate(employees):
            eff_hours = get_effective_daily_hours(emp, shop)
            shift_delta = timedelta(hours=eff_hours)

            for s in (SHIFT_OPEN, SHIFT_CLOSE) + tuple(START_SHIFT_MAP.keys()) + tuple(END_SHIFT_MAP.keys()):
                if s == SHIFT_OPEN:
                    shift_start = shop_open_dt
                    shift_end = shop_open_dt + shift_delta
                elif s == SHIFT_CLOSE:
                    shift_start = shop_close_dt - shift_delta
                    shift_end = shop_close_dt
                elif s in START_SHIFT_MAP:
                    offset = START_SHIFT_MAP[s]
                    shift_start = shop_open_dt + timedelta(minutes=offset)
                    shift_end = shift_start + shift_delta
                elif s in END_SHIFT_MAP:
                    offset = END_SHIFT_MAP[s]
                    shift_end = shop_close_dt - timedelta(minutes=offset)
                    shift_start = shift_end - shift_delta
                else:
                    continue

                classification = classify_shift_as_morning_or_afternoon(
                    shift_start,
                    shift_end,
                    shop_open_dt,
                    shop_close_dt,
                )

                if classification == "morning":
                    morning_shifts += x[e, d, s]
                elif classification == "afternoon":
                    afternoon_shifts += x[e, d, s]

        diff = model.NewIntVar(-50, 50, f"daily_balance_diff_d{d}")
        model.Add(diff == morning_shifts - afternoon_shifts)

        abs_diff = model.NewIntVar(0, 50, f"daily_balance_abs_d{d}")
        model.AddAbsEquality(abs_diff, diff)

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

        model.Add(
            sum(x[e, d, SHIFT_WORK_START_15] for e in range(len(employees))) >= 1
        ).OnlyEnforceIf(start_15_exists)

        model.Add(
            sum(x[e, d, SHIFT_WORK_START_15] for e in range(len(employees))) == 0
        ).OnlyEnforceIf(start_15_exists.Not())

        model.Add(
            sum(x[e, d, SHIFT_WORK_END_15] for e in range(len(employees))) >= 1
        ).OnlyEnforceIf(end_15_exists)

        model.Add(
            sum(x[e, d, SHIFT_WORK_END_15] for e in range(len(employees))) == 0
        ).OnlyEnforceIf(end_15_exists.Not())

        penalties.append(start_15_exists.Not())
        penalties.append(end_15_exists.Not())

    return penalties


def add_workload_balance_penalty(model, x, employees, days, all_shifts):
    penalties = []

    if len(employees) < 2:
        return penalties

    total_assignments = []
    for e in range(len(employees)):
        assignments = sum(
            x[e, d, s] for d in days for s in all_shifts
        )
        total_assignments.append(assignments)

    max_assignments = model.NewIntVar(0, 1000, "max_workload")
    min_assignments = model.NewIntVar(0, 1000, "min_workload")
    model.AddMaxEquality(max_assignments, total_assignments)
    model.AddMinEquality(min_assignments, total_assignments)

    spread = model.NewIntVar(0, 1000, "workload_spread")
    model.Add(spread == max_assignments - min_assignments)
    penalties.append(spread)
    return penalties