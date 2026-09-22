# Ten plik odpowiada za nakładanie ograniczeń dostępności pracowników.
# Dla każdego pracownika i dnia sprawdza, jakie zmiany są dozwolone (availability),
# a następnie blokuje niedozwolone zmiany (HARD) lub dodaje kary (SOFT),
# jeśli generator mimo wszystko przypisze niedozwoloną zmianę.

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
    soft=False,
    trace=None,
    shift_night=None,
    duty_shifts=None,
    round_clock_shifts=None,
):
    if trace is not None:
        trace.log_constraint("availability", f"soft={soft}")

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

            # DEBUG: brak dostępnych zmian
            if len(allowed_set) == 0:
                print(f"[AVAIL BLOCK] emp={e} day={d} NO SHIFTS ALLOWED")

            filtered_allowed = set(allowed_set)
            duty_shift_ids = set(duty_shifts.values()) if duty_shifts else set()
            round_clock_shift_ids = set(round_clock_shifts) if round_clock_shifts else set()

            for s in all_shifts:
                # get_allowed_shifts_for_day (availability_mapper.py) nie zna
                # SHIFT_NIGHT, żadnej z pięciu zmian rotacji 24/7 Ochrony, ani
                # kafelków rotacji całodobowej "ogólnej" - nie mapuje żadnego
                # availability na nie, więc traktowanie "nieobecna w allowed"
                # jako "zakazana" źle ograniczałoby je każdemu pracownikowi z
                # jakimikolwiek ograniczeniami dostępności, niezależnie od
                # ich treści. Pomijamy je tutaj do czasu, aż dostępność
                # zacznie rozumieć te godziny (poza zakresem Etapu C zmian
                # nocnych / Etapu B rotacji 24/7 / round_clock_constraint.py).
                if s == shift_night or s in duty_shift_ids or s in round_clock_shift_ids:
                    continue

                if s in filtered_allowed:
                    continue

                if soft:
                    v = model.NewBoolVar(f"avail_violation_e{e}_d{d}_s{s}")
                    model.Add(x[e, d, s] <= v)
                    violations.append(v)
                else:
                    # W trybie twardym nadal blokujemy niedozwolone zmiany.
                    # Jeśli jednak liczba dostępnych pracowników jest bardzo mała,
                    # warto traktować to jako miękkie ograniczenie, żeby model nie
                    # stawał się natychmiast infeasible.
                    model.Add(x[e, d, s] == 0)

    return violations