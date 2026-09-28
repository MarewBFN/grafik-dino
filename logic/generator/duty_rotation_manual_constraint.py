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

from logic.generator.duty_rotation_manual_coverage import get_plan, match_duty_key


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

            # "W" (może pracować, patrz ui/main_window.py "Może pracować") -
            # NIE ustawia is_locked (jak "1"/"2", DaySchedule.set_shift_class),
            # więc sprawdzane PRZED is_locked poniżej. Rekomendacja, nie
            # dokładna zmiana: w placówce z rotacją 24/7 oznacza "przydziel
            # całą dobę" tam, gdzie faktycznie jest to możliwe dla jednej
            # osoby (weekend_full - weekend, albo KAŻDY dzień przy
            # only_12_24h); w zwykły dzień roboczy bez only_12_24h (doba
            # dzielona 16h+8h między dwie różne osoby, nikt nie bierze jej
            # solo) - jedna z dwóch ról tego dnia, generator wybiera którą.
            shift_class = getattr(day_state, "shift_class", None)
            if shift_class == "W":
                location = shop.locations.get(emp.location_key)
                if location is not None and location.is_duty_day_closed(shop.year, shop.month, d):
                    # Dzień zamknięty (święto/"Nieczynne") - nic do wymuszenia,
                    # add_duty_rotation_public_holiday_constraint i tak zeruje
                    # wszystkie zmiany duty tego dnia.
                    continue

                plan = get_plan(duty_shifts)
                if plan is not None and plan.is_planned(emp.location_key or "", d):
                    # Doba objęta planem zmian resztkowych (cudzy ręczny
                    # wpis) - standardowe zmiany w ogóle nie istnieją tego
                    # dnia dla nikogo w tej lokalizacji, nie ma czego wymusić.
                    continue

                only_12_24h = rotation.get("only_12_24h", False)
                if only_12_24h or shop.weekday(d) >= 5:
                    weekend_full = duty_shifts["weekend_full"]
                    model.Add(x[e, d, weekend_full] == 1)
                    for s in duty_shift_ids:
                        if s != weekend_full:
                            model.Add(x[e, d, s] == 0)
                else:
                    weekday_ids = (duty_shifts["weekday_long"], duty_shifts["weekday_short"])
                    model.Add(sum(x[e, d, s] for s in weekday_ids) == 1)
                    for s in duty_shift_ids:
                        if s not in weekday_ids:
                            model.Add(x[e, d, s] == 0)
                continue

            if not day_state.is_locked:
                continue

            if not getattr(day_state, "start", None):
                # Zablokowany jako "wolne" (puste godziny) - MUSI wymusić
                # zero na każdej zmianie duty tego pracownika/dnia, tak jak
                # robi to add_manual_shift_constraints (manual_constraint.py)
                # dla starego modelu. Wcześniejszy komentarz zakładał, że to
                # "już obsłużone generycznie" przez add_day_off_constraints
                # (sprawdza is_day_off) - błędnie: ui/grid_view.py ma DRUGĄ,
                # niezależną ścieżkę ustawiania "wolne" (akcja "OFF" w
                # dropdownie), która czyści start/end i ustawia is_locked,
                # ale NIE ustawia is_day_off. Bez tego wymuszenia solver miał
                # wolną rękę przypisać temu pracownikowi zmianę duty (spełniał
                # sobie tak coverage WEWNĘTRZNIE, model raportował OPTIMAL),
                # a solution_mapper i tak nie zapisywał tego do wyniku (bo
                # is_locked=True) - efekt: pozornie kompletny grafik z
                # niepokrytym dniem. Zweryfikowane empirycznie na
                # last_project.json użytkownika.
                for s in duty_shift_ids:
                    model.Add(x[e, d, s] == 0)
                continue

            # Doba zaplanowana wokół ręcznych wpisów (duty_rotation_manual_
            # coverage.py) - ręczny wpis jest tam stałym przedziałem planu
            # (liczy się do pokrycia, godzin i odpoczynku), więc temu
            # pracownikowi nie przydziela się tego dnia żadnej zmiany.
            plan = get_plan(duty_shifts)
            if plan is not None and plan.is_fixed(emp, d):
                for s in duty_shift_ids:
                    model.Add(x[e, d, s] == 0)
                continue

            key = match_duty_key(day_state, rotation, shop.weekday(d))
            shift = duty_shifts.get(key) if key is not None else None

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
