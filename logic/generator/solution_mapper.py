from logic.generator.duty_rotation_manual_coverage import CUSTOM_KEYS, DAY_MINUTES, format_minutes, get_plan
from ortools.sat.python import cp_model
from datetime import datetime, timedelta
from model.day_schedule import calc_start, calc_end
from logic.utils.time_utils import get_effective_daily_hours

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
    END_SHIFTS,
    trace=None,
    shift_night=None,
    duty_shifts=None,
    round_clock_shifts=None,
):
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("❌ BRAK ROZWIĄZANIA")
        return False

    print("✅ ROZWIĄZANIE ZNALEZIONE")
    print("=== PODSUMOWANIE ZMIAN ===")

    # 🔥 zapis solverowych wyników do porównania
    solver_open_per_day = {}
    solver_close_per_day = {}

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

        solver_open_per_day[d] = open_count
        solver_close_per_day[d] = close_count

        night_count = 0
        if shift_night is not None:
            night_count = sum(
                solver.Value(x[e, d, shift_night])
                for e in range(len(employees))
            )

        print(f"Dzień {d}: OPEN={open_count} CLOSE={close_count} WORK={work_count} NIGHT={night_count}")

    for e in range(len(employees)):
        emp = employees[e]

        for d in trade_days:

            day_state = schedule.get_day(emp, d)

            # 🔥 DEBUG — czy solver chciał coś przypisać, a my skipujemy
            if solver.Value(x[e, d, SHIFT_OPEN]) == 1:
                print(f"[CHECK] OPEN solver: emp={e} day={d} locked={day_state.is_locked}")

            if solver.Value(x[e, d, SHIFT_CLOSE]) == 1:
                print(f"[CHECK] CLOSE solver: emp={e} day={d} locked={day_state.is_locked}")

            if (
                day_state.is_leave
                or day_state.is_locked
                or getattr(day_state, "is_day_off", False)
            ):
                if trace is not None:
                    trace.log_assignment(e, d, None, "skipped_due_to_leave_or_lock")
                if day_state.is_locked:
                    print(f"[SKIP LOCKED] emp={e} day={d}")
                continue

            # SHIFT_NIGHT (Etap C planu zmian nocnych) ma własne, stałe
            # godziny niezależne od open_hours dnia - sprawdzane przed
            # get_open_hours_for_day poniżej, żeby dzień bez zwykłych godzin
            # otwarcia (np. przyszły profil 24/7 bez "dnia handlowego") nie
            # gubił cicho przypisanej zmiany nocnej.
            if shift_night is not None and solver.Value(x[e, d, shift_night]) == 1:
                night_hours = shop.get_location(emp).get_night_shift_hours()
                if night_hours:
                    night_start, night_end = night_hours
                    schedule.set_day_hours(emp, d, night_start, night_end)
                    if trace is not None:
                        trace.log_assignment(e, d, shift_night, "solver_assignment")
                continue

            # Rotacja służby 24/7 (Etap B "plan profil ochrona") - podobnie
            # jak SHIFT_NIGHT, ma własne, stałe godziny niezależne od
            # open_hours dnia, więc sprawdzana też przed
            # get_open_hours_for_day poniżej.
            if duty_shifts is not None:
                rotation = shop.get_location(emp).get_duty_rotation()
                assigned_duty = False
                if rotation:
                    plan = get_plan(duty_shifts)
                    for key, shift_id in duty_shifts.items():
                        if solver.Value(x[e, d, shift_id]) != 1:
                            continue
                        if key in CUSTOM_KEYS:
                            # Zmiana resztkowa doby zaplanowanej wokół
                            # ręcznych wpisów (duty_rotation_manual_coverage.py).
                            piece_start, piece_end = plan.day_pieces(emp.location_key or "", d)[CUSTOM_KEYS.index(key)]
                            if piece_end - piece_start >= DAY_MINUTES:
                                schedule.set_day_full_day_shift(emp, d, format_minutes(piece_start))
                            else:
                                schedule.set_day_hours(emp, d, format_minutes(piece_start), format_minutes(piece_end))
                        elif key == "weekend_full":
                            schedule.set_day_full_day_shift(emp, d, rotation[key]["start"])
                        else:
                            window = rotation[key]
                            schedule.set_day_hours(emp, d, window["start"], window["end"])
                        if trace is not None:
                            trace.log_assignment(e, d, shift_id, "solver_assignment")
                        assigned_duty = True
                        break
                if assigned_duty:
                    continue

            # Rotacja całodobowa "ogólna" (round_clock_constraint.py) - jak
            # duty_rotation wyżej, własne, stałe (per kafelek) godziny
            # niezależne od open_hours dnia, sprawdzane przed
            # get_open_hours_for_day poniżej.
            if round_clock_shifts is not None:
                start_hour = shop.get_location(emp).get_round_clock_start_hour()
                if start_hour:
                    from logic.generator.round_clock_constraint import (
                        round_clock_tile_count,
                        round_clock_tile_start_hour,
                    )

                    n_tiles = round_clock_tile_count(shop.standard_daily_hours)
                    assigned_tile = False
                    for tile_index in range(n_tiles):
                        if solver.Value(x[e, d, round_clock_shifts[tile_index]]) != 1:
                            continue
                        tile_start = round_clock_tile_start_hour(
                            start_hour, tile_index, shop.standard_daily_hours
                        )
                        eff_hours = get_effective_daily_hours(emp, shop)
                        tile_end = calc_end(tile_start, eff_hours)
                        schedule.set_day_hours(emp, d, tile_start, tile_end)
                        if trace is not None:
                            trace.log_assignment(e, d, round_clock_shifts[tile_index], "solver_assignment")
                        assigned_tile = True
                        break
                    if assigned_tile:
                        continue

            hours = shop.get_location(emp).get_open_hours_for_day(d)
            if not hours:
                continue

            open_time, close_time = hours
            fmt = "%H:%M"

            eff_hours = get_effective_daily_hours(emp, shop)

            if solver.Value(x[e, d, SHIFT_OPEN]) == 1:
                end = calc_end(open_time, eff_hours)
                schedule.set_day_hours(emp, d, open_time, end)
                if trace is not None:
                    trace.log_assignment(e, d, SHIFT_OPEN, "solver_assignment")
                continue

            if solver.Value(x[e, d, SHIFT_CLOSE]) == 1:
                start = calc_start(close_time, eff_hours)
                schedule.set_day_hours(emp, d, start, close_time)
                if trace is not None:
                    trace.log_assignment(e, d, SHIFT_CLOSE, "solver_assignment")
                continue

            assigned = False

            for shift, offset in START_SHIFTS.items():

                if solver.Value(x[e, d, shift]) == 1:

                    start_dt = datetime.strptime(open_time, fmt) + timedelta(minutes=offset)
                    start = start_dt.strftime(fmt)

                    end = calc_end(start, eff_hours)

                    schedule.set_day_hours(emp, d, start, end)
                    if trace is not None:
                        trace.log_assignment(e, d, shift, "solver_assignment")
                    assigned = True
                    break

            if not assigned:
                for shift, offset in END_SHIFTS.items():

                    if solver.Value(x[e, d, shift]) == 1:

                        end_dt = datetime.strptime(close_time, fmt) - timedelta(minutes=offset)
                        end = end_dt.strftime(fmt)

                        start = calc_start(end, eff_hours)

                        schedule.set_day_hours(emp, d, start, end)
                        if trace is not None:
                            trace.log_assignment(e, d, shift, "solver_assignment")
                        break

    # 🔥 WERYFIKACJA PO ZAPISIE (TO CI WSZYSTKO POWIE)
    print("\n=== VERIFY AFTER SAVE ===")

    for d in trade_days:
        saved_open = 0
        saved_close = 0

        for emp in employees:
            hours = shop.get_location(emp).get_open_hours_for_day(d)
            if not hours:
                continue
            open_t, close_t = hours

            ds = schedule.get_day(emp, d)

            if not ds.start or not ds.end:
                continue

            if ds.start == open_t:
                saved_open += 1

            if ds.end == close_t:
                saved_close += 1

        print(
            f"[COMPARE] Day {d}: "
            f"solver OPEN={solver_open_per_day[d]} vs saved OPEN={saved_open} | "
            f"solver CLOSE={solver_close_per_day[d]} vs saved CLOSE={saved_close}"
        )

    print("=== KONIEC GENERATORA ===")
    return True