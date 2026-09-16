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

Zakres: tylko przejścia między kolejnymi dniami TEGO SAMEGO pracownika
(x[e,d,s1] + x[e,d_next,s2] <= 1, ten sam wzorzec co night_shift_adjacency).
Ponieważ zmiany rotacji i stary model zmian są wzajemnie wyłączne per
pracownik (add_duty_rotation_gate_constraint), a zmiany dnia roboczego
istnieją tylko w tygodniu i zmiany weekendowe tylko w weekend (ta sama
brama), wystarczy sprawdzić WSZYSTKIE pary (typ ważny w dniu d, typ ważny
w dniu d+1) - nie trzeba osobno traktować "starych" zmian w ogóle.
"""

from datetime import datetime, timedelta

MIN_REST = timedelta(hours=11)
FMT = "%H:%M"

_WEEKDAY_KEYS = ("weekday_long", "weekday_short")
_WEEKEND_KEYS = ("weekend_full", "weekend_half_a", "weekend_half_b")


def _anchor(day_offset: int, time_str: str) -> datetime:
    t = datetime.strptime(time_str, FMT)
    return datetime(2000, 1, 1, t.hour, t.minute) + timedelta(days=day_offset)


def _shift_start_end_anchored(key: str, window: dict, day_offset: int) -> tuple[datetime, datetime]:
    start = _anchor(day_offset, window["start"])
    if key == "weekend_full":
        return start, start + timedelta(hours=24)
    end = _anchor(day_offset, window["end"])
    if end <= start:
        end += timedelta(days=1)
    return start, end


def _required_rest(key: str, rotation_capable_count: int) -> timedelta:
    if key != "weekend_full":
        return MIN_REST
    # "nie mniej niż 24h" - dolna granica nawet przy rotacji 1-2-osobowej,
    # gdzie (N-1)x24h dałoby 0h albo 24h dokładnie na granicy.
    return timedelta(hours=24 * max(rotation_capable_count - 1, 1))


def add_duty_rotation_rest_constraint(model, x, employees, days, shop, duty_shifts, soft=False, trace=None):
    """Sprawdza nie tylko dzień d wobec d+1, ale d wobec każdego późniejszego
    dnia w obrębie widoku (`_lookahead_days_for`) - (N-1)x24h po weekend_full
    może przekraczać 24h już przy N>=3, więc samo "jutro" (jak wystarcza
    night_shift_adjacency_constraint dla 11h/19h) by nie wystarczyło."""
    if trace is not None:
        trace.log_constraint("duty_rotation_rest", f"soft={soft}")

    from logic.generator.duty_rotation_constraint import _group_employees_with_duty_rotation

    violations = []
    groups = _group_employees_with_duty_rotation(employees, shop)
    days_sorted = sorted(days)
    day_index = {d: i for i, d in enumerate(days_sorted)}

    for _, (rotation, indices) in groups.items():
        rotation_capable_count = sum(
            1 for e in indices if not employees[e].custom_roles.get("nie_chce_24h", False)
        )
        max_required = _required_rest("weekend_full", rotation_capable_count)
        # +2 dni marginesu na przesunięcia z zaokrąglania godzin/zmian
        # przechodzących przez północ - taniej sprawdzić kilka dni za dużo
        # niż zgubić realny konflikt na granicy.
        lookahead_days = int(max_required.total_seconds() // 86400) + 2

        for i, d in enumerate(days_sorted):
            keys_today = _WEEKDAY_KEYS if shop.weekday(d) < 5 else _WEEKEND_KEYS

            for key1 in keys_today:
                s1 = duty_shifts[key1]
                _, end1 = _shift_start_end_anchored(key1, rotation[key1], 0)
                required = _required_rest(key1, rotation_capable_count)

                for j in range(i + 1, min(i + 1 + lookahead_days, len(days_sorted))):
                    d_future = days_sorted[j]
                    day_offset = day_index[d_future] - day_index[d]
                    keys_future = _WEEKDAY_KEYS if shop.weekday(d_future) < 5 else _WEEKEND_KEYS

                    reached_beyond_required = True
                    for key2 in keys_future:
                        s2 = duty_shifts[key2]
                        start2, _ = _shift_start_end_anchored(key2, rotation[key2], day_offset)

                        if start2 - end1 >= required:
                            continue
                        reached_beyond_required = False

                        for e in indices:
                            if not soft:
                                model.Add(x[e, d, s1] + x[e, d_future, s2] <= 1)
                            else:
                                v = model.NewBoolVar(
                                    f"duty_rest_violation_e{e}_d{d}_{key1}_d{d_future}_{key2}"
                                )
                                model.Add(x[e, d, s1] + x[e, d_future, s2] <= 1 + v)
                                violations.append(v)

                    if reached_beyond_required:
                        # Nawet najwcześniejsza zmiana tego dnia już mieści
                        # wymagany odpoczynek - każdy kolejny dzień tym
                        # bardziej, więc nie ma sensu iść dalej w przyszłość
                        # dla tego (d, key1).
                        break

    return violations
