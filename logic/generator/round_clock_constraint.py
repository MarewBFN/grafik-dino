"""Rotacja całodobowa "ogólna" dla lokalizacji 24/7 z ustawioną godziną
rozpoczęcia (LocationConfig.round_clock_start_hour, patrz jej docstring w
model/location.py) - w odróżnieniu od duty_rotation_constraint.py (pięć
nazwanych typów zmian, jedna osoba na zmianę, wyłącznie dla profilu
Ochrona), to N RÓWNYCH "kafelków" rozstawionych co 24h/N od godziny startu,
obsadzanych DOKŁADNIE tą samą regułą co dzisiejsze OPEN/CLOSE
(add_fixed_staff_shift_constraints - min_open_staff + wymóg
"otwiera"/"mięso", patrz dino_retail_profile.py).

Zgłoszenie klienta (2026-09-21, patrz ENYO_ONLY_CHANGES.md): mechanizm
OPEN/CLOSE nie jest fizycznie w stanie obsadzić środka doby dla lokalizacji
24/7 - maks. przesunięcie od otwarcia/zamknięcia to 90/75 minut
(logic/auto_generator.py::START_SHIFT_MAP/END_SHIFT_MAP), więc przy 24h
otwarcia zawsze zostaje kilkugodzinna luka bez nikogo w pracy. Zweryfikowane
empirycznie przed napisaniem tego modułu.

Dwa elementy, ten sam wzorzec co duty_rotation_constraint.py:
- add_round_clock_gate_constraint: strukturalny fakt (jak duty_rotation_gate)
  - lokalizacja bez round_clock_start_hour nigdy nie dostaje tych zmian;
    kafelki nieużywane w tym projekcie (>= N, patrz round_clock_tile_count)
    są zawsze zablokowane, dla każdego pracownika. Zawsze twardy, poza
    systemem polityk.
- add_round_clock_coverage_constraint: obsada każdego kafelka - wołana
  WYŁĄCZNIE przez profil Dino (patrz dino_retail_profile.py), tym samym
  wzorcem co "open"/"close": domyślnie MANDATORY, add_fixed_staff_shift_constraints
  na każdy kafelek osobno. Świadomie NIE jest ogólnodostępna dla dowolnego
  profilu custom - is_opener/is_meat to role specyficzne dla Dino, więc
  narzucanie ich profilowi bez tych ról (np. Ochrona, która i tak ma własny
  duty_rotation na 24/7) nie miałoby sensu.

Odpoczynek 11h między kafelkami: round_clock_rest_constraint.py (żaden
kafelek nie jest tak długi jak doba, więc - w odróżnieniu od duty_rotation's
weekend_full - standardowe 11h zawsze wystarcza, sprawdzenie dnia d wobec
d+1 jak add_rest_11h_constraint). Ręczna blokada dnia w gridzie:
round_clock_manual_constraint.py.

Świadome ograniczenie zakresu: budżet "mięsa tymczasowego" (is_meat_light,
build_meat_light_duty) nie zna kafelków round-clock (liczony tylko dla
OPEN/CLOSE/START/END) - pracownik is_meat_light nie policzy się do wymogu
"co najmniej 1 mięso" na kafelku. Akceptowalne uproszczenie v1: budżet
mięsa tymczasowego to osobna, opcjonalna funkcja, nie blokuje podstawowej
obsady."""

import math
from datetime import datetime, timedelta

MAX_ROUND_CLOCK_TILES = 6
_FMT = "%H:%M"


def round_clock_tile_count(standard_daily_hours: float) -> int:
    """Ile kafelków potrzeba, żeby pokryć całą dobę zmianami zbliżonej
    długości do standard_daily_hours (ShopConfig - "standardowe godziny
    dzienne" w Konfiguracji), zaczynając od godziny startu -
    ceil(24h / standard_daily_hours), z granicami [2, MAX_ROUND_CLOCK_TILES]
    (jeden "kafelek" 24h nie miałby sensu jako rotacja, a więcej niż
    MAX_ROUND_CLOCK_TILES to już nierealistyczna konfiguracja - wymagałoby
    standard_daily_hours < 4h)."""
    if not standard_daily_hours or standard_daily_hours <= 0:
        return MAX_ROUND_CLOCK_TILES
    return max(2, min(MAX_ROUND_CLOCK_TILES, math.ceil(24 / standard_daily_hours)))


def round_clock_tile_spacing_minutes(standard_daily_hours: float) -> int:
    """Odstęp (w minutach) między kolejnymi kafelkami - 24h równo podzielone
    na round_clock_tile_count() kafelków (NIE dokładnie standard_daily_hours
    - inaczej kafelki nie okrążałyby dokładnie doby, patrz moduł docstring
    o standard_daily_hours=7h dającym 4 kafelki po 7h=28h > 24h)."""
    return round(24 * 60 / round_clock_tile_count(standard_daily_hours))


def round_clock_tile_start_hour(start_hour: str, tile_index: int, standard_daily_hours: float) -> str:
    """Godzina (HH:MM) startu kafelka `tile_index` (0-based) - kafelek 0
    zaczyna się dokładnie o `start_hour`, każdy kolejny o
    round_clock_tile_spacing_minutes() dalej, zawinięte w granicach doby."""
    base = datetime.strptime(start_hour, _FMT)
    spacing = round_clock_tile_spacing_minutes(standard_daily_hours)
    minutes = (base.hour * 60 + base.minute + tile_index * spacing) % 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def group_employees_with_round_clock(employees, shop) -> dict:
    """{location_key: (start_hour, [employee_indices])} - tylko dla
    pracowników, których lokalizacja faktycznie ma ustawioną
    round_clock_start_hour (patrz ShopConfig._LocationView::
    get_round_clock_start_hour). Ten sam wzorzec co
    duty_rotation_constraint.py::group_employees_with_duty_rotation."""
    groups: dict[str, tuple[str, list[int]]] = {}
    for e, emp in enumerate(employees):
        start_hour = shop.get_location(emp).get_round_clock_start_hour()
        if not start_hour:
            continue
        key = emp.location_key or ""
        if key not in groups:
            groups[key] = (start_hour, [])
        groups[key][1].append(e)
    return groups


def add_round_clock_gate_constraint(
    model, x, employees, days, shop, round_clock_shifts, all_shifts, standard_daily_hours, trace=None,
):
    if trace is not None:
        trace.log_constraint(
            "round_clock_gate",
            "round-clock tile shifts and the old OPEN/CLOSE/START/END/NIGHT model are mutually exclusive per employee",
        )

    all_round_clock_ids = set(round_clock_shifts)

    # Nikt w projekcie nie ma skonfigurowanej rotacji całodobowej - prosta
    # blokada bez dotykania standard_daily_hours w ogóle (istotne dla
    # testów z mockowanym ShopConfig, patrz round_clock_rest_constraint.py).
    if not any(shop.get_location(emp).get_round_clock_start_hour() for emp in employees):
        for e in range(len(employees)):
            for d in days:
                for s in all_round_clock_ids:
                    model.Add(x[e, d, s] == 0)
        return

    n_tiles = round_clock_tile_count(standard_daily_hours)
    active_ids = set(round_clock_shifts[:n_tiles])
    other_shift_ids = [s for s in all_shifts if s not in all_round_clock_ids]

    for e, emp in enumerate(employees):
        start_hour = shop.get_location(emp).get_round_clock_start_hour()

        for d in days:
            if not start_hour:
                for s in all_round_clock_ids:
                    model.Add(x[e, d, s] == 0)
                continue

            for s in other_shift_ids:
                model.Add(x[e, d, s] == 0)

            for s in all_round_clock_ids - active_ids:
                model.Add(x[e, d, s] == 0)


def add_round_clock_coverage_constraint(
    model, x, employees, days, shop, round_clock_shifts, standard_daily_hours,
    soft=False, trace=None, meat_light_penalties=None, shift_duty_sum=None,
):
    from logic.generator.constraints_staff import add_fixed_staff_shift_constraints

    if trace is not None:
        trace.log_constraint("round_clock_coverage", f"soft={soft}")

    if not any(shop.get_location(emp).get_round_clock_start_hour() for emp in employees):
        return []

    min_staff = shop.constraints.get("min_open_staff", 3)
    n_tiles = round_clock_tile_count(standard_daily_hours)

    violations = []
    for tile_index in range(n_tiles):
        violations.extend(
            add_fixed_staff_shift_constraints(
                model, x, employees, days, round_clock_shifts[tile_index], min_staff,
                soft=soft, trace=trace,
                meat_light_penalties=meat_light_penalties,
                shift_duty_sum=shift_duty_sum,
            )
        )
    return violations
