"""Ręczne blokowanie dnia dla pracowników rotacji 24/7 (np. ochrona) -
odpowiednik `add_manual_shift_constraints` (manual_constraint.py) dla
pięciu zmian duty_rotation zamiast starego modelu OPEN/CLOSE/START/END.

Ta funkcja NIE zastępuje add_manual_shift_constraints - działa RÓWNOLEGLE
obok niej, dokładnie tak samo jak `duty_rotation_rest_constraint` dokłada
się obok `add_rest_11h_constraint` (patrz base_specs.py::_build_rest_11h).
Jedyna zmiana w istniejącym kodzie: add_manual_shift_constraints teraz
pomija pracowników przypisanych do lokalizacji z duty_rotation (patrz
komentarz tam) - dla każdego projektu BEZ duty_rotation (czyli każdego
dzisiejszego projektu Dino) to zero różnicy w zachowaniu, bo
LocationConfig.get_duty_rotation() zawsze zwraca None/pusty słownik dla
takiej lokalizacji.

Powód istnienia: przed tą funkcją ręczne zablokowanie dnia pracownikowi
rotacji 24/7 (dwuklik na komórce w gridzie albo "Cała doba (24h)" w
Ustawieniach trybu szybkiego) próbowało dopasować zablokowane godziny do
starego modelu zmian (add_manual_shift_constraints), co albo cicho
zerowało cały dzień, albo (częściej, bo zmiany duty_rotation typowo
zaczynają się o tej samej godzinie co otwarcie lokalizacji) wymuszało
x[e,d,SHIFT_OPEN/CLOSE]==1 w bezpośredniej sprzeczności z
add_duty_rotation_gate_constraint (który dla tych pracowników zawsze
zeruje SHIFT_OPEN/CLOSE/START/END/NIGHT) - model stawał się INFEASIBLE
dla całego miesiąca. Zweryfikowane empirycznie (reprodukcja na żywym
AutoScheduleGenerator) przed napisaniem tej poprawki - patrz
ENYO_ONLY_CHANGES.md.
"""

FULL_DAY_KEY = "weekend_full"
_EXACT_MATCH_KEYS = ("weekday_long", "weekday_short", "weekend_half_a", "weekend_half_b")


def _match_duty_shift(day_state, rotation, duty_shifts):
    """Który z pięciu typów zmian duty_rotation tej lokalizacji odpowiada
    zablokowanym godzinom tego dnia (None gdy żaden) - dokładne dopasowanie
    start/end (albo is_full_day+start dla zmiany 24h "weekend_full"),
    odpowiednik resolve_manual_shift() w manual_constraint.py dla starego
    modelu zmian."""
    start = getattr(day_state, "start", None)
    if not start:
        return None

    if getattr(day_state, "is_full_day", False):
        window = rotation.get(FULL_DAY_KEY)
        if window and window.get("start") == start:
            return duty_shifts.get(FULL_DAY_KEY)
        return None

    end = getattr(day_state, "end", None)
    if not end:
        return None

    for key in _EXACT_MATCH_KEYS:
        window = rotation.get(key)
        if window and window.get("start") == start and window.get("end") == end:
            return duty_shifts.get(key)

    return None


def add_duty_rotation_manual_shift_constraint(
    model,
    x,
    employees,
    days,
    schedule,
    shop,
    duty_shifts,
    trace=None,
):
    if trace is not None:
        trace.log_constraint(
            "duty_rotation_manual_shift",
            "apply locked/manual day assignments for duty-rotation employees",
        )

    duty_shift_ids = set(duty_shifts.values())

    for e, emp in enumerate(employees):
        rotation = shop.get_location(emp).get_duty_rotation()
        if not rotation:
            continue

        for d in days:
            day_state = schedule.get_day(emp, d)

            # urlop/chorobowe/dzień wolny - już obsłużone generycznie przez
            # always-on "leave"/"day_off" (zerują KAŻDĄ zmianę, w tym te
            # pięć duty), nic dodatkowego do zrobienia tutaj.
            if day_state.is_leave or getattr(day_state, "is_sick", False):
                continue

            if not day_state.is_locked:
                continue

            if not getattr(day_state, "start", None):
                # Zablokowany jako "wolne" (puste godziny) - zero przypisań
                # tego dnia i tak jest dozwolonym stanem dla
                # duty_rotation_coverage (miękkie/twarde pokrycie sprawdza
                # to na poziomie całej lokalizacji, nie pojedynczego
                # pracownika), więc nie trzeba nic wymuszać.
                continue

            shift = _match_duty_shift(day_state, rotation, duty_shifts)

            if shift is None:
                # Zablokowane godziny nie odpowiadają żadnej z pięciu zmian
                # tej lokalizacji - tak jak w manual_constraint.py: blokujemy
                # wszystkie zmiany duty tego dnia zamiast zgadywać, żeby nie
                # zbudować modelu sprzecznego z innymi constraintami.
                for s in duty_shift_ids:
                    model.Add(x[e, d, s] == 0)
                continue

            model.Add(x[e, d, shift] == 1)
            for s in duty_shift_ids:
                if s != shift:
                    model.Add(x[e, d, s] == 0)
