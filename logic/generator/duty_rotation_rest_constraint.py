"""Odpoczynek po zmianach rotacji 24/7 (Etap C "plan profil ochrona
(analiza specyfikacji klienta).md", sekcja 12) - dołącza się do
add_rest_11h_constraint (który w ogóle nie zna tych pięciu zmian - nie
buduje dla nich okien), zamiast go modyfikować, dokładnie jak
night_shift_adjacency_constraint robi to dla SHIFT_NIGHT.

Zasady (potwierdzone przez klienta):
- Po weekday_long/weekday_short/weekend_half_a/weekend_half_b: standardowe
  11h.
- Po weekend_full (zmiana 24h): system "doba za dobę" - (N-1)x24h, gdzie
  N = liczba pracowników TEJ lokalizacji zdolnych/chętnych robić 24h (bez
  flagi "nie_chce_24h" - oni i tak nigdy jej nie dostają, więc nie powinni
  wydłużać cyklu odpoczynku tym, którzy faktycznie rotują). Nigdy mniej
  niż 24h nawet przy N<=1 (dolna granica, klient: "nie mniej niż 24h").

Gdy lokalizacja ma `duty_rotation["only_12_24h"]` (toggle "Używaj tylko
zmian 12/24h" w Konfiguracji), powyższe zasady dla weekend_full/half_a/
half_b obowiązują KAŻDEGO dnia tygodnia (patrz `_keys_for_day`) -
weekday_long/weekday_short nigdy się wtedy nie przydzielają.

Zakres: tylko przejścia między kolejnymi dniami TEGO SAMEGO pracownika
(x[e,d,s1] + x[e,d_next,s2] <= 1, ten sam wzorzec co night_shift_adjacency).
Ponieważ zmiany rotacji i stary model zmian są wzajemnie wyłączne per
pracownik (add_duty_rotation_gate_constraint), a zmiany dnia roboczego
istnieją tylko w tygodniu i zmiany weekendowe tylko w weekend (ta sama
brama), wystarczy sprawdzić WSZYSTKIE pary (typ ważny w dniu d, typ ważny
w dniu d+1) - nie trzeba osobno traktować "starych" zmian w ogóle.

Ręczne wpisy liczone jako pokrycie (duty_rotation_manual_coverage.py): w
dobach zaplanowanych wokół nich zamiast standardowych typów sprawdzane są
zmiany resztkowe tej doby, a same ręczne wpisy są stałymi przedziałami -
generator nie przydzieli ich autorowi zmiany, która nie zostawia wymaganego
odpoczynku przed albo po ręcznym wpisie (ani na nią nie zachodzi).
"""

from datetime import datetime, timedelta

from logic.generator.duty_rotation_constraint import NIE_CHCE_24H_ROLE_KEY
from logic.generator.duty_rotation_manual_coverage import (
    CUSTOM_KEYS,
    DAY_MINUTES,
    get_plan,
    window_offsets,
)

MIN_REST = timedelta(hours=11)
FMT = "%H:%M"

_WEEKDAY_KEYS = ("weekday_long", "weekday_short")
_WEEKEND_KEYS = ("weekend_full", "weekend_half_a", "weekend_half_b")


def _keys_for_day(rotation: dict, weekday: int) -> tuple:
    """Które typy zmian są w ogóle ważne tego dnia - zawsze weekendowe, gdy
    `only_12_24h` (toggle "Używaj tylko zmian 12/24h"), inaczej zależnie od
    dnia tygodnia jak dotąd."""
    if rotation.get("only_12_24h") or weekday >= 5:
        return _WEEKEND_KEYS
    return _WEEKDAY_KEYS


def _required_rest(key: str, rotation_capable_count: int) -> timedelta:
    if key != "weekend_full":
        return MIN_REST
    # "nie mniej niż 24h" - dolna granica nawet przy rotacji 1-2-osobowej,
    # gdzie (N-1)x24h dałoby 0h albo 24h dokładnie na granicy.
    return timedelta(hours=24 * max(rotation_capable_count - 1, 1))


def _day_windows(rotation, weekday, duty_shifts, plan, location_key, day):
    """[(id zmiany, czy 24h, start, koniec)] - minuty od północy dnia:
    standardowe zmiany doby (gdy nie jest zaplanowana wokół ręcznych
    wpisów) + zmiany resztkowe zaczynające się tego dnia."""
    windows = []
    if plan is None or not plan.is_planned(location_key, day):
        windows += [
            (duty_shifts[key], key == "weekend_full", *window_offsets(rotation, key))
            for key in _keys_for_day(rotation, weekday)
        ]
    if plan is not None:
        windows += [
            (duty_shifts[CUSTOM_KEYS[i]], False, start, end)
            for i, (start, end) in enumerate(plan.day_pieces(location_key, day))
        ]
    return windows


def _required_rest_minutes(is_full_day: bool, rotation_capable_count: int) -> int:
    key = "weekend_full" if is_full_day else "weekend_half_a"
    return int(_required_rest(key, rotation_capable_count).total_seconds() // 60)


def _forbid(model, x, e, d, s, soft, violations, label):
    if not soft:
        model.Add(x[e, d, s] == 0)
    else:
        v = model.NewBoolVar(label)
        model.Add(x[e, d, s] <= v)
        violations.append(v)


def _add_previous_month_rest_constraint(model, x, employees, schedule, days_sorted, windows_by_day, indices, soft, violations):
    """"Pamięć poprzedniego miesiąca" (model.month_schedule.PreviousMonthShiftEnd)
    - dzień 1 nie ma poprzedniego dnia W TYM MODELU, więc bez tego nic nie
    chroniłoby początku miesiąca przed zbyt wczesnym startem względem
    faktycznego końca ostatniej zmiany poprzedniego miesiąca. W
    przeciwieństwie do pętli niżej, nie znamy TYPU tamtej zmiany (tylko
    koniec + czy wchodziła w dzień 1 - patrz PreviousMonthShiftEnd), więc
    zamiast ewentualnego (N-1)x24h po weekend_full stosujemy tu zawsze
    standardowe 11h (spójnie z rest_constraint.py dla trybu zwykłego)."""
    if schedule is None or not days_sorted:
        return

    d1 = days_sorted[0]
    min_rest = int(MIN_REST.total_seconds() // 60)

    for e in indices:
        carry = schedule.get_previous_month_end_shift(employees[e])
        if carry is None:
            continue

        end_time = datetime.strptime(carry.end, FMT)
        end_prev = end_time.hour * 60 + end_time.minute - (0 if carry.crosses_midnight else DAY_MINUTES)

        for s2, _full, start2, _end2 in windows_by_day[d1]:
            if start2 - end_prev >= min_rest:
                continue
            _forbid(model, x, e, d1, s2, soft, violations, f"duty_rest_violation_prevmonth_e{e}_{s2}")


def _add_fixed_interval_rest_constraint(
    model, x, employees, days_sorted, windows_by_day, indices, plan, rotation_capable_count, lookahead_days, soft, violations,
):
    """Ręczny wpis (stały przedział planu) wobec zmian przydzielanych temu
    samemu pracownikowi w sąsiednich dniach."""
    if plan is None:
        return

    for e in indices:
        for fixed_day, fixed_start, fixed_end in plan.fixed_intervals(employees[e]):
            abs_start = fixed_day * DAY_MINUTES + fixed_start
            abs_end = fixed_day * DAY_MINUTES + fixed_end
            rest_after_fixed = _required_rest_minutes(fixed_end - fixed_start >= DAY_MINUTES, rotation_capable_count)

            for d in days_sorted:
                if abs(d - fixed_day) > lookahead_days or d == fixed_day:
                    continue
                for s, is_full, start, end in windows_by_day[d]:
                    w_start = d * DAY_MINUTES + start
                    w_end = d * DAY_MINUTES + end
                    overlaps = w_start < abs_end and abs_start < w_end
                    too_soon_after = w_start >= abs_end and w_start - abs_end < rest_after_fixed
                    too_close_before = w_end <= abs_start and abs_start - w_end < _required_rest_minutes(
                        is_full, rotation_capable_count
                    )
                    if overlaps or too_soon_after or too_close_before:
                        _forbid(model, x, e, d, s, soft, violations, f"duty_rest_violation_fixed_e{e}_d{d}_{s}")


def add_duty_rotation_rest_constraint(model, x, employees, days, shop, duty_shifts, schedule=None, soft=False, trace=None):
    """Sprawdza nie tylko dzień d wobec d+1, ale d wobec każdego późniejszego
    dnia w obrębie widoku (`lookahead_days`) - (N-1)x24h po weekend_full
    może przekraczać 24h już przy N>=3, więc samo "jutro" (jak wystarcza
    night_shift_adjacency_constraint dla 11h/19h) by nie wystarczyło."""
    if trace is not None:
        trace.log_constraint("duty_rotation_rest", f"soft={soft}")

    from logic.generator.duty_rotation_constraint import group_employees_with_duty_rotation

    violations = []
    groups = group_employees_with_duty_rotation(employees, shop)
    days_sorted = sorted(days)
    plan = get_plan(duty_shifts)

    for location_key, (rotation, indices) in groups.items():
        rotation_capable_count = sum(
            1 for e in indices if not employees[e].custom_roles.get(NIE_CHCE_24H_ROLE_KEY, False)
        )
        max_required = _required_rest("weekend_full", rotation_capable_count)
        # +2 dni marginesu na przesunięcia z zaokrąglania godzin/zmian
        # przechodzących przez północ - taniej sprawdzić kilka dni za dużo
        # niż zgubić realny konflikt na granicy.
        lookahead_days = int(max_required.total_seconds() // 86400) + 2

        windows_by_day = {
            d: _day_windows(rotation, shop.weekday(d), duty_shifts, plan, location_key, d)
            for d in days_sorted
        }

        _add_previous_month_rest_constraint(model, x, employees, schedule, days_sorted, windows_by_day, indices, soft, violations)
        _add_fixed_interval_rest_constraint(
            model, x, employees, days_sorted, windows_by_day, indices, plan,
            rotation_capable_count, lookahead_days, soft, violations,
        )

        for i, d in enumerate(days_sorted):
            for s1, full1, _start1, end1 in windows_by_day[d]:
                required = _required_rest_minutes(full1, rotation_capable_count)

                for j in range(i + 1, min(i + 1 + lookahead_days, len(days_sorted))):
                    d_future = days_sorted[j]
                    day_offset = (j - i) * DAY_MINUTES

                    reached_beyond_required = True
                    for s2, _full2, start2, _end2 in windows_by_day[d_future]:
                        if day_offset + start2 - end1 >= required:
                            continue
                        reached_beyond_required = False

                        for e in indices:
                            if not soft:
                                model.Add(x[e, d, s1] + x[e, d_future, s2] <= 1)
                            else:
                                v = model.NewBoolVar(
                                    f"duty_rest_violation_e{e}_d{d}_{s1}_d{d_future}_{s2}"
                                )
                                model.Add(x[e, d, s1] + x[e, d_future, s2] <= 1 + v)
                                violations.append(v)

                    if reached_beyond_required:
                        # Nawet najwcześniejsza zmiana tego dnia już mieści
                        # wymagany odpoczynek - każdy kolejny dzień tym
                        # bardziej, więc nie ma sensu iść dalej w przyszłość
                        # dla tego (d, s1).
                        break

    return violations
