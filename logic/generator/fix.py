from logic.generator.manual_constraint import resolve_manual_shift
import datetime


def get_iso_week(year, month, day):
    return datetime.date(year, month, day).isocalendar()[1]


def setup_fix_hints_and_penalties(
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
    """
    FIX MODE — stabilna wersja:
    - HARD blokuje rzeczy krytyczne (OPEN/CLOSE, manuale)
    - kontroluje nominal (z marginesem)
    - ogranicza ilość hintów (żeby solver się nie wieszał)
    """

    penalties = []

    # ==================================================
    # 🔒 HARD: popo → brak OPEN następnego dnia
    # ==================================================
    afternoon_shifts = [SHIFT_CLOSE] + list(END_SHIFT_MAP.keys())

    for e in range(len(employees)):
        for d in days[:-1]:
            worked_afternoon = model.NewBoolVar(f"aft_e{e}_d{d}")

            model.Add(
                sum(x[e, d, s] for s in afternoon_shifts) >= 1
            ).OnlyEnforceIf(worked_afternoon)

            model.Add(
                sum(x[e, d, s] for s in afternoon_shifts) == 0
            ).OnlyEnforceIf(worked_afternoon.Not())

            # 🔥 HARD
            model.Add(x[e, d + 1, SHIFT_OPEN] == 0).OnlyEnforceIf(worked_afternoon)

    # ==================================================
    # 📅 znajdź edytowane tygodnie
    # ==================================================
    edited_weeks = set()

    for emp in employees:
        for d in days:
            day_state = schedule.get_day(emp, d)
            if day_state.is_locked:
                week_num = get_iso_week(schedule.year, schedule.month, d)
                edited_weeks.add(week_num)

    # ==================================================
    # ⏱️ NOMINAL (ważne — ale nie HARD)
    # ==================================================
    from logic.utils.time_utils import get_effective_daily_hours

    nominal_hours = shop.get_full_time_nominal_hours()
    nominal_minutes = nominal_hours * 60

    for e, emp in enumerate(employees):

        shift_minutes = int(get_effective_daily_hours(emp, shop) * 60)

        leave_days = 0
        sick_days = 0

        for d in days:
            ds = schedule.get_day(emp, d)
            if ds.is_leave:
                leave_days += 1
            if getattr(ds, "is_sick", False):
                sick_days += 1

        daily_hours = get_effective_daily_hours(emp, shop)

        leave_minutes = int(leave_days * daily_hours * 60)
        sick_minutes = int(sick_days * daily_hours * 60)

        target_minutes = int(
            nominal_minutes * emp.employment_fraction
            - leave_minutes
            - sick_minutes
        )

        total_worked = model.NewIntVar(0, 50000, f"fix_total_e{e}")

        model.Add(
            total_worked ==
            sum(
                x[e, d, s] * shift_minutes
                for d in days
                for s in all_shifts
                if s != 14
            )
        )

        # 🔥 TWARDY LIMIT (mały margines)
        max_over = int(emp.daily_hours * 60)
        model.Add(total_worked <= target_minutes + max_over)

        # 🔥 SOFT niedobór (mocny)
        under = model.NewIntVar(0, 50000, f"fix_under_e{e}")
        model.Add(total_worked + under >= target_minutes)

        penalties.append(under * 4000)

    # ==================================================
    # 🔄 SHIFT MATCHING (LEKKIE, NIE AGRESYWNE)
    # ==================================================
    start_map_rev = {v: k for k, v in START_SHIFT_MAP.items()}
    end_map_rev = {v: k for k, v in END_SHIFT_MAP.items()}

    for e, emp in enumerate(employees):
        for d in days:

            day_state = schedule.get_day(emp, d)

            # ==================================================
            # 🔒 HARD: urlop / sick
            # ==================================================
            if day_state.is_leave or getattr(day_state, "is_sick", False):
                for s in all_shifts:
                    model.Add(x[e, d, s] == 0)
                continue

            # ==================================================
            # 🔒 HARD: locked → NIE RUSZAJ
            # ==================================================
            if day_state.is_locked:
                continue

            week_num = get_iso_week(schedule.year, schedule.month, d)
            is_edited_week = week_num in edited_weeks

            weight = 300 if is_edited_week else 1200

            # ==================================================
            # 🧠 rozpoznanie obecnej zmiany
            # ==================================================
            current_shift = None

            start = getattr(day_state, "start", None)
            end = getattr(day_state, "end", None)

            if start and end:
                hours = shop.get_open_hours_for_day(d)
                if hours:
                    open_time, close_time = hours

                    shift_name = resolve_manual_shift(
                        start,
                        end,
                        open_time,
                        close_time,
                        start_map_rev,
                        end_map_rev
                    )

                    if shift_name == "OPEN":
                        current_shift = SHIFT_OPEN
                    elif shift_name == "CLOSE":
                        current_shift = SHIFT_CLOSE
                    elif shift_name is not None:
                        current_shift = shift_name

            # ==================================================
            # ⚠️ tylko JEDEN hint (ważne!)
            # ==================================================
            if current_shift is not None:
                model.AddHint(x[e, d, current_shift], 1)

                penalties.append(weight * (1 - x[e, d, current_shift]))

                # 🔥 OPEN/CLOSE ważniejsze
                if current_shift in (SHIFT_OPEN, SHIFT_CLOSE):
                    penalties.append(2000 * (1 - x[e, d, current_shift]))

    return penalties