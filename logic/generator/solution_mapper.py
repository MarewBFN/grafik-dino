from ortools.sat.python import cp_model
from datetime import datetime, timedelta
from model.day_schedule import calc_start, calc_end


def save_solution(
    schedule,
    shop,
    solver,
    status,
    x,
    employees,
    trade_days,
    SHIFT_OPEN,
    SHIFT_CLOSE,
    START_SHIFTS,
    END_SHIFTS
):
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("❌ BRAK ROZWIĄZANIA")
        return False

    print("✅ ROZWIĄZANIE ZNALEZIONE")
    print("=== PODSUMOWANIE ZMIAN ===")

    for d in trade_days:

        open_count = sum(
            solver.Value(x[e, d, SHIFT_OPEN])
            for e in range(len(employees))
        )

        close_count = sum(
            solver.Value(x[e, d, SHIFT_CLOSE])
            for e in range(len(employees))
        )

        work_count = sum(
            solver.Value(x[e, d, s])
            for e in range(len(employees))
            for s in list(START_SHIFTS.keys()) + list(END_SHIFTS.keys())
        )

        print(f"Dzień {d}: OPEN={open_count} CLOSE={close_count} WORK={work_count}")

    for e in range(len(employees)):
        emp = employees[e]

        for d in trade_days:

            day_state = schedule.get_day(emp, d)

            if (
                day_state.is_leave
                or day_state.is_locked
                or getattr(day_state, "is_day_off", False)
            ):
                continue

            hours = shop.get_open_hours_for_day(d)
            if not hours:
                continue

            open_time, close_time = hours
            fmt = "%H:%M"

            if solver.Value(x[e, d, SHIFT_OPEN]) == 1:
                end = calc_end(open_time, emp.daily_hours)
                schedule.set_day_hours(emp, d, open_time, end)
                continue

            if solver.Value(x[e, d, SHIFT_CLOSE]) == 1:
                start = calc_start(close_time, emp.daily_hours)
                schedule.set_day_hours(emp, d, start, close_time)
                continue

            for shift, offset in START_SHIFTS.items():

                if solver.Value(x[e, d, shift]) == 1:

                    start_dt = datetime.strptime(open_time, fmt) + timedelta(minutes=offset)
                    start = start_dt.strftime(fmt)

                    end = calc_end(start, emp.daily_hours)

                    schedule.set_day_hours(emp, d, start, end)
                    break

            for shift, offset in END_SHIFTS.items():

                if solver.Value(x[e, d, shift]) == 1:

                    end_dt = datetime.strptime(close_time, fmt) - timedelta(minutes=offset)
                    end = end_dt.strftime(fmt)

                    start = calc_start(end, emp.daily_hours)

                    schedule.set_day_hours(emp, d, start, end)
                    break

    print("=== KONIEC GENERATORA ===")
    return True