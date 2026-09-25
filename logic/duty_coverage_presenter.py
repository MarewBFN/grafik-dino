"""Dzień-po-dniu status obłożenia rotacji 24/7 (np. ochrona) - używane
przez ui/grid_view.py do wyświetlenia wiersza podsumowania "Obłożenie"
zamiast Dino'wego "Otwarcie"/"Zamknięcie" dla projektów, które faktycznie
używają LocationConfig.duty_rotation (patrz "plan profil ochrona (analiza
specyfikacji klienta).md", sekcja 12).

Sprawdza dokładnie tę samą regułę co
logic/generator/duty_rotation_constraint.py::add_duty_rotation_coverage_constraint,
ale na już zapisanym grafiku (DaySchedule), nie na zmiennych solvera - więc
działa też dla dni sprzed wygenerowania, po ręcznej edycji, albo gdy
generowanie się nie powiodło.
"""

from logic.generator.duty_rotation_constraint import group_employees_with_duty_rotation


def project_uses_duty_rotation(shop, employees) -> bool:
    return bool(group_employees_with_duty_rotation(employees, shop))


def _matches_window(ds, window: dict) -> bool:
    return not ds.is_full_day and ds.start == window["start"] and ds.end == window["end"]


def is_day_fully_covered(schedule, shop, employees, day: int) -> bool:
    """True gdy KAŻDA lokalizacja z duty_rotation ma tego dnia pełne
    pokrycie 24h - dokładnie 1 osoba na weekday_long i 1 na weekday_short
    w tygodniu; w weekend albo 1 na weekend_full, albo po 1 na obu
    połówkach. Zwraca False, gdy żadna lokalizacja projektu nie używa tego
    mechanizmu (wywołujący powinien wtedy w ogóle nie pokazywać tego
    wiersza - patrz project_uses_duty_rotation)."""
    groups = group_employees_with_duty_rotation(employees, shop)
    if not groups:
        return False

    wd = shop.weekday(day)

    for location_key, (rotation, indices) in groups.items():
        location = shop.locations.get(location_key)
        if location is not None and location.is_duty_day_closed(shop.year, shop.month, day):
            # Zamknięta w to konkretne święto (LocationConfig.
            # closed_on_public_holidays) - generator nikogo tu nie wymaga
            # (patrz add_duty_rotation_coverage_constraint), więc brak
            # obsady tego dnia nie jest błędem - pomijamy tę lokalizację
            # zamiast liczyć ją jako niepokrytą.
            continue

        assigned = [schedule.get_day(employees[e], day) for e in indices]
        assigned = [ds for ds in assigned if not ds.is_empty()]

        if wd < 5 and not rotation.get("only_12_24h"):
            long_ok = any(_matches_window(ds, rotation["weekday_long"]) for ds in assigned)
            short_ok = any(_matches_window(ds, rotation["weekday_short"]) for ds in assigned)
            if not (long_ok and short_ok):
                return False
        else:
            if any(ds.is_full_day for ds in assigned):
                continue
            half_a_ok = any(_matches_window(ds, rotation["weekend_half_a"]) for ds in assigned)
            half_b_ok = any(_matches_window(ds, rotation["weekend_half_b"]) for ds in assigned)
            if not (half_a_ok and half_b_ok):
                return False

    return True
