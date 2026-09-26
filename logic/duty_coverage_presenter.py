"""Dzień-po-dniu status obłożenia rotacji 24/7 (np. ochrona) - używane
przez ui/grid_view.py do wyświetlenia wiersza podsumowania "Obłożenie"
zamiast Dino'wego "Otwarcie"/"Zamknięcie" dla projektów, które faktycznie
używają LocationConfig.duty_rotation (patrz "plan profil ochrona (analiza
specyfikacji klienta).md", sekcja 12).

Sprawdza faktyczne pokrycie doby w czasie (2026-09-25): od początku doby
rotacji tego dnia do początku doby następnego dnia w każdej chwili musi
pracować DOKŁADNIE jedna osoba placówki - niezależnie od tego, czy zmiany
mają standardowe godziny rotacji, czy są ręcznymi wpisami (liczonymi przez
generator jako pokrycie, patrz logic/generator/duty_rotation_manual_coverage.py).
Wcześniej wiersz sprawdzał tylko, czy istnieją zmiany o godzinach rotacji,
więc pokazywał OK także przy luce albo dwóch osobach naraz. Działa na już
zapisanym grafiku (DaySchedule), nie na zmiennych solvera - więc też dla
dni sprzed wygenerowania, po ręcznej edycji, albo gdy generowanie się nie
powiodło.
"""

from logic.generator.duty_rotation_constraint import group_employees_with_duty_rotation
from logic.generator.duty_rotation_manual_coverage import DAY_MINUTES, day_anchor, manual_offsets


def project_uses_duty_rotation(shop, employees) -> bool:
    return bool(group_employees_with_duty_rotation(employees, shop))


def _doba(shop, rotation, day: int) -> tuple[int, int]:
    """[początek doby tego dnia, początek doby następnego dnia) w minutach
    od północy dnia 0 - przy różnych początkach doby w tygodniu i w weekend
    (starszy schemat) luka/zakładka na styku wpada w dobę dnia wcześniej."""
    start = day * DAY_MINUTES + day_anchor(rotation, shop.weekday(day))
    next_weekday = (shop.weekday(day) + 1) % 7
    end = (day + 1) * DAY_MINUTES + day_anchor(rotation, next_weekday)
    return start, end


def _intervals_around(schedule, employees, indices, day: int) -> list[tuple[int, int]]:
    intervals = []
    for d in (day - 1, day, day + 1):
        if d < 1 or d > schedule.days_in_month:
            continue
        for e in indices:
            ds = schedule.get_day(employees[e], d)
            if ds.is_leave or getattr(ds, "is_sick", False):
                continue
            offsets = manual_offsets(ds)
            if offsets is not None:
                intervals.append((d * DAY_MINUTES + offsets[0], d * DAY_MINUTES + offsets[1]))
    return intervals


def _exactly_one_person(intervals, start: int, end: int) -> bool:
    points = {start, end}
    for a, b in intervals:
        if a < end and b > start:
            points.add(max(a, start))
            points.add(min(b, end))
    ordered = sorted(points)
    for a, b in zip(ordered, ordered[1:]):
        if a == b:
            continue
        count = sum(1 for s, e in intervals if s <= a and e >= b)
        if count != 1:
            return False
    return True


def is_day_fully_covered(schedule, shop, employees, day: int) -> bool:
    """True gdy KAŻDA lokalizacja z duty_rotation ma tego dnia w każdej
    chwili doby rotacji dokładnie jedną osobę w pracy. Zwraca False, gdy
    żadna lokalizacja projektu nie używa tego mechanizmu (wywołujący
    powinien wtedy w ogóle nie pokazywać tego wiersza - patrz
    project_uses_duty_rotation)."""
    groups = group_employees_with_duty_rotation(employees, shop)
    if not groups:
        return False

    for location_key, (rotation, indices) in groups.items():
        location = shop.locations.get(location_key)
        if location is not None and location.is_duty_day_closed(shop.year, shop.month, day):
            # Zamknięta tego dnia (święto przy closed_on_public_holidays albo
            # ręczne "Nieczynne tego dnia") - generator nikogo tu nie wymaga
            # (patrz add_duty_rotation_coverage_constraint), więc brak
            # obsady nie jest błędem.
            continue

        # Sprawdzenie po osi czasu obejmuje też przypadek zgłoszony
        # 2026-09-26 (zmiana 24h w zwykły dzień roboczy pokazywała się jako
        # niepokryta) bez osobnego warunku - 24h to po prostu 24-godzinny
        # interwał, tak samo jak każdy inny, w _intervals_around/_doba niżej.
        start, end = _doba(shop, rotation, day)
        if not _exactly_one_person(_intervals_around(schedule, employees, indices, day), start, end):
            return False

    return True
