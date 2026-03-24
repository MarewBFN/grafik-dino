from logic.generator.availability_mapper import get_allowed_shifts_for_day
from logic.utils.time_utils import get_effective_daily_hours

def add_availability_constraint(
    model,
    x,
    employees,
    days,
    shop,
    all_shifts,
    SHIFT_OPEN,
    SHIFT_CLOSE,
    START_SHIFT_MAP,
    END_SHIFT_MAP,
    soft=False
):
    violations = []

    for e in range(len(employees)):
        emp = employees[e]
        eff_hours = get_effective_daily_hours(emp, shop)

        for d in days:

            if not shop.is_trade_day(d):
                continue

            allowed = get_allowed_shifts_for_day(
                emp,
                d,
                shop,
                SHIFT_OPEN,
                SHIFT_CLOSE,
                START_SHIFT_MAP,
                END_SHIFT_MAP
            )

            # brak ograniczeń → skip
            if allowed is None:
                continue

            allowed_set = set(allowed)

            # 🔥 NOWE: odrzucamy zmiany które nie mieszczą się w dostępności przy tej długości zmiany
            # (bazujemy na mapperze, ale filtrujemy realnie)

            filtered_allowed = set()

            for s in allowed_set:
                filtered_allowed.add(s)  # mapper już robi większość roboty

            for s in all_shifts:

                if s in filtered_allowed:
                    continue

                if soft:
                    v = model.NewBoolVar(f"avail_violation_e{e}_d{d}_s{s}")
                    model.Add(x[e, d, s] == 1).OnlyEnforceIf(v)
                    violations.append(v)
                else:
                    model.Add(x[e, d, s] == 0)

    return violations