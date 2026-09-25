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

from logic.generator.duty_rotation_manual_coverage import planned_minutes_expr
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
            + planned_minutes_expr(x, e, emp, days, duty_shifts)
        )

        under = model.NewIntVar(0, 50000, f"priority_hours_under_e{e}")
        model.Add(total_minutes + under >= target_minutes)
        penalties.append(under)

    return [PRIORITY_WEIGHT * p for p in penalties]


# ---------------------------------------------------------------------------
# "Wyrównanie godzin umowa/bez" (zasada w Konfiguracji -> ustawienia
# zaawansowane, decyzja użytkownika 2026-09-25). Klient wyłączył
# balance/monthly_hours (liczy się wyłącznie pełne pokrycie), przez co w
# danych klienta rozkład godzin w jednej placówce był dowolny - np. Ubojnia
# (7 pełnych etatów, bez umowy): Krefft 60h, Szyca 144h.
#
# Wyrównuje godziny osobno w każdej grupie (placówka, ma "Umowa" / nie ma)
# - priorytet "Umowa" (dobicie do nominału, wyżej) działa dalej niezależnie.
# Zawsze wyłącznie term celu: "Preferowane" i "Wymagane" różnią się tylko
# wagą, żadne z nich nie może zablokować pokrycia (zasada "pokrycie >
# nadgodziny, ZAWSZE"). Kara dopiero za rozrzut większy niż najdłuższa
# zmiana dostępna w grupie - rozrzut mniejszy niż jedna zmiana jest przy
# zmianach 12h/24h nieunikniony i nie powinien przebijać np. "Preferuj
# zmiany 24h".
#
# Urlop/L4 wlicza się jako "przepracowany" udział w obsadzie (dla rotacji
# 24h/liczba osób placówki na dzień, dla zwykłych zmian - dzienny wymiar
# pracownika), a niepełny etat liczy się proporcjonalnie (1/2 etatu =
# połowa godzin pełnego etatu).
# ---------------------------------------------------------------------------

HOURS_EQUALIZATION_POLICY = "hours_equalization"
HOURS_EQUALIZATION_LABEL = "Wyrównanie godzin umowa/bez"
HOURS_EQUALIZATION_WEIGHT = 1
HOURS_EQUALIZATION_MANDATORY_FACTOR = 10
_FULL_TIME_SCALE = 10


def hours_equalization_weight(policy) -> int:
    """Waga termu wg ustawienia zasady; 0 = wyłączone (także gdy projekt
    nie ma jeszcze tej zasady w ogóle - domyślnie wyłączona)."""
    from model.constraint_policy import ConstraintPolicy

    if policy == ConstraintPolicy.PREFERRED:
        return HOURS_EQUALIZATION_WEIGHT
    if policy == ConstraintPolicy.MANDATORY:
        return HOURS_EQUALIZATION_WEIGHT * HOURS_EQUALIZATION_MANDATORY_FACTOR
    return 0


def _duty_tolerance_minutes(rotation, emp) -> int:
    from logic.generator.duty_rotation_constraint import NIE_CHCE_24H_ROLE_KEY
    from logic.generator.night_shift_constraint import night_shift_duration_minutes

    keys = ["weekend_half_a", "weekend_half_b"]
    if not rotation.get("only_12_24h"):
        keys += ["weekday_long", "weekday_short"]
    lengths = [
        night_shift_duration_minutes((rotation[k]["start"], rotation[k]["end"]))
        for k in keys if rotation.get(k)
    ]
    if not emp.custom_roles.get(NIE_CHCE_24H_ROLE_KEY, False):
        lengths.append(24 * 60)
    return max(lengths, default=24 * 60)


def add_hours_equalization_penalty(
    model,
    x,
    employees,
    days,
    schedule,
    shop,
    all_shifts,
    shift_night=None,
    duty_shifts=None,
    weight=HOURS_EQUALIZATION_WEIGHT,
    role_key=UMOWA_ROLE_KEY,
):
    if weight <= 0:
        return []

    location_sizes: dict[str, int] = {}
    groups: dict[tuple[str, bool], list[int]] = {}
    for e, emp in enumerate(employees):
        key = emp.location_key or ""
        location_sizes[key] = location_sizes.get(key, 0) + 1
        groups.setdefault((key, emp.has_role(role_key)), []).append(e)

    penalties = []
    for (location_key, has_role), indices in groups.items():
        if len(indices) < 2:
            continue

        norms = []
        tolerance = 0
        for e in indices:
            emp = employees[e]
            unavailable = sum(
                1 for d in days
                if schedule.get_day(emp, d).is_leave or getattr(schedule.get_day(emp, d), "is_sick", False)
            )
            if unavailable >= len(days):
                continue

            daily_minutes = int(get_effective_daily_hours(emp, shop) * 60)
            rotation = shop.get_location(emp).get_duty_rotation()
            if rotation:
                share_per_day = (24 * 60) // max(location_sizes[location_key], 1)
                shift_tolerance = _duty_tolerance_minutes(rotation, emp)
            else:
                share_per_day = daily_minutes
                shift_tolerance = daily_minutes

            minutes_by_shift = _shift_minutes_by_type(
                all_shifts, daily_minutes, _duration_overrides_for_employee(shop, emp, shift_night, duty_shifts),
            )
            fraction = min(max(emp.employment_fraction, 0.01), 1.0)
            scale = max(1, round(_FULL_TIME_SCALE / fraction))

            norm = model.NewIntVar(0, 10_000_000, f"equalize_norm_e{e}")
            model.Add(
                norm == scale * (
                    sum(x[e, d, s] * minutes_by_shift[s] for d in days for s in all_shifts)
                    + planned_minutes_expr(x, e, emp, days, duty_shifts)
                    + unavailable * share_per_day
                )
            )
            norms.append(norm)
            tolerance = max(tolerance, shift_tolerance * _FULL_TIME_SCALE)

        if len(norms) < 2:
            continue

        tag = f"{location_key}_{int(has_role)}"
        highest = model.NewIntVar(0, 10_000_000, f"equalize_max_{tag}")
        lowest = model.NewIntVar(0, 10_000_000, f"equalize_min_{tag}")
        model.AddMaxEquality(highest, norms)
        model.AddMinEquality(lowest, norms)
        excess = model.NewIntVar(0, 10_000_000, f"equalize_excess_{tag}")
        model.Add(excess >= highest - lowest - tolerance)
        penalties.append(excess)

    return [weight * p for p in penalties]
