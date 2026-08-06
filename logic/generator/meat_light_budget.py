from datetime import datetime, timedelta
from logic.utils.time_utils import get_effective_daily_hours

FMT = "%H:%M"
SLOT_MINUTES = 15
MAX_MEAT_LIGHT_MINUTES_PER_DAY = 60


def build_meat_light_duty(
    model,
    x,
    employees,
    trade_days,
    shop,
    SHIFT_OPEN,
    SHIFT_CLOSE,
    START_SHIFT_MAP,
    END_SHIFT_MAP,
    max_minutes=MAX_MEAT_LIGHT_MINUTES_PER_DAY,
):
    """
    Twardy budżet czasu "mięsa" dla pracowników is_meat_light: niezależnie od
    tego jak długa jest ich właściwa zmiana, mogą być liczeni jako pokrycie
    mięsa przez maksymalnie `max_minutes` minut dziennie (domyślnie 1h).

    Dla każdego pracownika/dnia/wariantu zmiany, który obejmuje dany
    15-minutowy kwadrans, tworzy zmienną `duty` ograniczoną przez faktyczne
    przypisanie zmiany (`duty <= x[e,d,shift]`), więc może być aktywna tylko
    gdy dany wariant zmiany jest naprawdę wybrany. Suma `duty` w ciągu dnia
    jest twardo ograniczona do `max_minutes / 15` kwadransów.

    Zwraca (slot_duty_sum, shift_duty_sum):
      slot_duty_sum: {(e, d, "HH:MM"): LinearExpr} - do ciągłego pokrycia dnia
        (add_meat_coverage_constraint).
      shift_duty_sum: {(e, d, shift): LinearExpr} - zagregowane do poziomu
        całego wariantu zmiany, do zgrubnych sprawdzeń obecności "mięsa" na
        danej zmianie (add_meat_constraint, add_fixed_staff_shift_constraints).
    """
    light_employees = [e for e in range(len(employees)) if employees[e].is_meat_light]

    slot_duty_sum = {}
    shift_duty_sum = {}

    if not light_employees:
        return slot_duty_sum, shift_duty_sum

    max_slots = max(0, max_minutes // SLOT_MINUTES)

    for d in trade_days:
        hours = shop.get_open_hours_for_day(d)
        if not hours:
            continue
        open_time, close_time = hours
        open_dt = datetime.strptime(open_time, FMT)
        close_dt = datetime.strptime(close_time, FMT)

        for e in light_employees:
            emp = employees[e]
            shift_len = timedelta(hours=get_effective_daily_hours(emp, shop))

            windows = {SHIFT_OPEN: (open_dt, open_dt + shift_len),
                       SHIFT_CLOSE: (close_dt - shift_len, close_dt)}
            for shift, offset in START_SHIFT_MAP.items():
                start = open_dt + timedelta(minutes=offset)
                windows[shift] = (start, start + shift_len)
            for shift, offset in END_SHIFT_MAP.items():
                end = close_dt - timedelta(minutes=offset)
                windows[shift] = (end - shift_len, end)

            day_duty_vars = []
            per_shift_terms = {}

            t = open_dt
            while t < close_dt:
                slot = t.strftime(FMT)
                slot_terms = []

                for shift, (start, end) in windows.items():
                    if not (start <= t < end):
                        continue

                    duty = model.NewBoolVar(f"meat_light_duty_e{e}_d{d}_{shift}_{slot}")
                    model.Add(duty <= x[e, d, shift])

                    day_duty_vars.append(duty)
                    slot_terms.append(duty)
                    per_shift_terms.setdefault(shift, []).append(duty)

                if slot_terms:
                    slot_duty_sum[(e, d, slot)] = sum(slot_terms)

                t += timedelta(minutes=SLOT_MINUTES)

            if day_duty_vars:
                model.Add(sum(day_duty_vars) <= max_slots)

            for shift, terms in per_shift_terms.items():
                shift_duty_sum[(e, d, shift)] = sum(terms)

    return slot_duty_sum, shift_duty_sum
