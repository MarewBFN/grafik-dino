"""Priorytet wypełniania nominalnego czasu pracy dla pracowników z flagą
"Umowa" (rola `umowa` - patrz demo/install_demo.py) - klient: tacy
pracownicy są brani pod uwagę jako pierwsi co do wypełnienia miesięcznego
nominału, pozostali "w razie możliwości".

Realizacja: NIE twardy wymóg (MANDATORY zawsze ryzykowałby niewykonalność
całego miesiąca, gdyby fizycznie zabrakło dla nich godzin - np. przez
L4/urlopy innych) - bardzo mocno ważony term miękki w celu (patrz
PRIORITY_WEIGHT), osobny od zwykłego balance/monthly_hours (które mogą być
dla tego profilu w ogóle wyłączone - Etap D planu profilu ochrona), więc
solver w pierwszej kolejności stara się zasypać niedobór TYCH pracowników,
zanim zajmie się bilansem/celami pozostałych. Działa niezależnie od tego,
czy polityki "balance"/"monthly_hours" są włączone.

Cel (target_minutes) liczony tym samym wzorem co
logic/generator/hours_constraint.py::add_monthly_hours_constraint (nominał
pełnego etatu razy wymiar etatu, pomniejszony o L4/urlop, przycięty do 0
- patrz ENYO_ONLY_CHANGES.md) i logic/monthly_hours_status.py - trzy
miejsca, które trzeba trzymać w synchronizacji, gdyby któreś się zmieniło.
"""

from logic.generator.hours_constraint import _duration_overrides_for_employee, _shift_minutes_by_type
from logic.utils.time_utils import get_effective_daily_hours

UMOWA_ROLE_KEY = "umowa"

# Wyraźnie ponad typowe wagi generycznych constraintów (rest_11h/
# availability/duty_rotation_coverage = 5000 w base_specs.GENERIC_WEIGHTS)
# - "pierwsi brani pod uwagę" ma być silniejsze niż zwykłe priorytety,
# żeby solver realnie próbował ich dobić do nominału przed czymkolwiek
# innym miękkim.
PRIORITY_WEIGHT = 10000


def add_priority_hours_shortfall_penalty(
    model,
    x,
    employees,
    days,
    schedule,
    shop,
    all_shifts,
    shift_night=None,
    duty_shifts=None,
    role_key=UMOWA_ROLE_KEY,
):
    """Lista ważonych IntVar (niedobór poniżej celu, w minutach) TYLKO dla
    pracowników z rolą `role_key` - do dołożenia wprost do funkcji celu
    (nie przez system polityk MANDATORY/PREFERRED/DISABLED, to term zawsze
    aktywny dla oflagowanych pracowników, niezależnie od ustawień
    balance/monthly_hours)."""
    penalties = []

    for e, emp in enumerate(employees):
        if not emp.has_role(role_key):
            continue

        daily_hours = get_effective_daily_hours(emp, shop)

        leave_days = 0
        sick_days = 0
        for d in days:
            ds = schedule.get_day(emp, d)
            if ds.is_leave:
                leave_days += 1
            if getattr(ds, "is_sick", False):
                sick_days += 1

        nominal_minutes = int(shop.get_full_time_nominal_hours() * 60 * emp.employment_fraction)
        leave_minutes = int(leave_days * daily_hours * 60)
        sick_minutes = int(sick_days * daily_hours * 60)
        target_minutes = max(0, nominal_minutes - leave_minutes - sick_minutes)

        if target_minutes == 0:
            # Cały miesiąc i tak L4/urlop (albo wymiar etatu efektywnie 0)
            # - nie ma czego dobijać, a IntVar z górną granicą 0 tylko
            # zaśmiecałby model.
            continue

        shift_minutes = int(daily_hours * 60)
        minutes_by_shift = _shift_minutes_by_type(
            all_shifts, shift_minutes, _duration_overrides_for_employee(shop, emp, shift_night, duty_shifts),
        )

        total_minutes = model.NewIntVar(0, 50000, f"priority_hours_total_e{e}")
        model.Add(
            total_minutes ==
            sum(x[e, d, s] * minutes_by_shift[s] for d in days for s in all_shifts)
        )

        under = model.NewIntVar(0, 50000, f"priority_hours_under_e{e}")
        model.Add(total_minutes + under >= target_minutes)
        penalties.append(under)

    return [PRIORITY_WEIGHT * p for p in penalties]
