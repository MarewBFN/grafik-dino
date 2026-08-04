from ortools.sat.python import cp_model
from datetime import datetime, timedelta
from model.day_schedule import calc_start, calc_end
from logic.utils.time_utils import get_effective_daily_hours


def add_rest_11h_constraint(
    model,
    x,
    employees,
    days,
    trade_days,
    shop,
    SHIFT_OPEN,
    SHIFT_CLOSE,
    START_SHIFTS,
    END_SHIFTS,
    soft=False,
    trace=None
):
    fmt = "%H:%M"

    if trace is not None:
        trace.log_constraint("rest_11h", f"soft={soft}")

    violations = []
    rest_constraints = 0

    # DEBUG
    blocked_pairs_per_day = {}

    for e in range(len(employees)):

        emp = employees[e]
        eff_hours = get_effective_daily_hours(emp, shop)

        for i in range(len(days) - 1):

            d = days[i]
            d_next = days[i + 1]

            if d not in trade_days or d_next not in trade_days:
                continue

            hours_d = shop.get_open_hours_for_day(d)
            hours_next = shop.get_open_hours_for_day(d_next)

            if not hours_d or not hours_next:
                continue

            open_d, close_d = hours_d
            open_next, close_next = hours_next

            shifts_today = {}

            shifts_today[SHIFT_OPEN] = (
                open_d,
                calc_end(open_d, eff_hours)
            )

            shifts_today[SHIFT_CLOSE] = (
                calc_start(close_d, eff_hours),
                close_d
            )

            for shift, off in START_SHIFTS.items():
                start = (
                    datetime.strptime(open_d, fmt)
                    + timedelta(minutes=off)
                ).strftime(fmt)

                shifts_today[shift] = (
                    start,
                    calc_end(start, eff_hours)
                )

            for shift, off in END_SHIFTS.items():
                end = (
                    datetime.strptime(close_d, fmt)
                    - timedelta(minutes=off)
                ).strftime(fmt)

                shifts_today[shift] = (
                    calc_start(end, eff_hours),
                    end
                )

            shifts_next = {}

            shifts_next[SHIFT_OPEN] = (
                open_next,
                calc_end(open_next, eff_hours)
            )

            shifts_next[SHIFT_CLOSE] = (
                calc_start(close_next, eff_hours),
                close_next
            )

            for shift, off in START_SHIFTS.items():
                start = (
                    datetime.strptime(open_next, fmt)
                    + timedelta(minutes=off)
                ).strftime(fmt)

                shifts_next[shift] = (
                    start,
                    calc_end(start, eff_hours)
                )

            for shift, off in END_SHIFTS.items():
                end = (
                    datetime.strptime(close_next, fmt)
                    - timedelta(minutes=off)
                ).strftime(fmt)

                shifts_next[shift] = (
                    calc_start(end, eff_hours),
                    end
                )

            # DEBUG: sprawdź czy pracownik ma jakąkolwiek opcję
            possible_next = 0
            total_pairs = 0

            for s1 in shifts_today:
                for s2 in shifts_next:

                    total_pairs += 1

                    end_today = datetime.strptime(shifts_today[s1][1], fmt)
                    start_next = datetime.strptime(shifts_next[s2][0], fmt)

                    rest = start_next - end_today
                    if rest.total_seconds() < 0:
                        rest += timedelta(days=1)

                    if rest < timedelta(hours=11):

                        # DEBUG: licz blokady per dzień
                        blocked_pairs_per_day.setdefault(d, 0)
                        blocked_pairs_per_day[d] += 1

                        # DEBUG: tylko krytyczne przypadki OPEN/CLOSE
                        if s1 in (SHIFT_OPEN, SHIFT_CLOSE) and s2 in (SHIFT_OPEN, SHIFT_CLOSE):
                            print(
                                f"[REST BLOCK] emp={e} day={d}->{d_next} "
                                f"{s1}->{s2} rest={rest}"
                            )

                        if not soft:
                            model.Add(
                                x[e, d, s1] + x[e, d_next, s2] <= 1
                            )
                        else:
                            violation = model.NewBoolVar(
                                f"rest_violation_e{e}_d{d}_{s1}_{s2}"
                            )
                            model.Add(
                                x[e, d, s1] + x[e, d_next, s2] <= 1 + violation
                            )
                            violations.append(violation)

                        rest_constraints += 1
                    else:
                        possible_next += 1

            # DEBUG: pracownik całkowicie zablokowany
            if possible_next == 0:
                print(
                    f"[FULL BLOCK] emp={e} day={d}->{d_next} "
                    f"NO VALID SHIFT COMBO (all violate 11h)"
                )

    print("Constrainty 11h rest:", rest_constraints)

    # DEBUG: podsumowanie per dzień
    print("\n=== REST DEBUG SUMMARY ===")
    for day, count in blocked_pairs_per_day.items():
        print(f"Day {day}: blocked_pairs={count}")

    return violations