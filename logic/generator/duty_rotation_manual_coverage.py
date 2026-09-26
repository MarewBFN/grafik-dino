"""Ręczne wpisy pracowników rotacji służby 24/7 liczone jako pokrycie doby
(decyzja użytkownika 2026-09-25, "Licz jako pokrycie" - patrz
ENYO_ONLY_CHANGES.md).

Wcześniej zablokowana ręcznie zmiana, której godziny nie pasowały do żadnej
zmiany rotacji placówki (np. preset trybu szybkiego 07:00-19:00 w PGE, gdzie
zmiany to 08-20 / 20-08), była dla generatora niewidoczna: nie liczyła się
do pokrycia ani do odpoczynku, więc generator dokładał drugą osobę na
standardową zmianę (podwójna obsada 07-19).

Teraz każda doba placówki, w którą wchodzi taki ręczny wpis, jest
"planowana": standardowe zmiany tej doby (połówki, albo w starszym
schemacie tygodnia - zmiana długa/krótka) są przycinane o wszystkie ręczne
wpisy (także te pasujące do rotacji, zablokowane tego dnia), a kawałki
krótsze niż MIN_PIECE_MINUTES są scalane z sąsiednim kawałkiem, z którym
się stykają (przykład użytkownika: 10.10 zostaje 19:00-20:00 + 20:00-08:00
-> jedna zmiana 19:00-08:00; noc 9.10 przycięta do 20:00-07:00). Każdy
kawałek to osobna "zmiana resztkowa" (custom_0..N) z dokładnie jedną osobą.
Ręczne wpisy są przy tym stałymi przedziałami: liczą się do godzin
pracownika i do jego odpoczynku względem zmian przydzielanych przez
generator.

Plan liczony raz na generowanie (AutoScheduleGenerator.generate(), po
wyczyszczeniu niezablokowanych dni) i przekazywany dalej jako atrybut
`plan` mapy zmian rotacji (DutyShiftMap) - dzięki temu wszystkie istniejące
constrainty, które już dostają `duty_shifts`, widzą go bez zmiany sygnatur.
Zwykły dict (np. w testach budujących model ręcznie) = brak planu =
dotychczasowe zachowanie.
"""

from dataclasses import dataclass, field

DAY_MINUTES = 24 * 60
MIN_PIECE_MINUTES = 4 * 60
MAX_CUSTOM_PIECES = 8
CUSTOM_KEYS = tuple(f"custom_{i}" for i in range(MAX_CUSTOM_PIECES))

_HALF_KEYS = ("weekend_half_a", "weekend_half_b")
_WEEKDAY_KEYS = ("weekday_long", "weekday_short")


class DutyShiftMap(dict):
    """{klucz zmiany rotacji: id zmiany} + plan pokrycia z ręcznymi wpisami
    bieżącego generowania (None = brak ręcznych wpisów do uwzględnienia)."""

    plan = None


def _minutes(time_str: str) -> int:
    hours, minutes = time_str.split(":")
    return int(hours) * 60 + int(minutes)


def format_minutes(offset: int) -> str:
    offset %= DAY_MINUTES
    return f"{offset // 60:02d}:{offset % 60:02d}"


def pattern_keys(rotation: dict, weekday: int) -> tuple:
    """Standardowy podział doby tego dnia (bez wariantu 24h)."""
    if rotation.get("only_12_24h") or weekday >= 5:
        return _HALF_KEYS
    return _WEEKDAY_KEYS


def window_offsets(rotation: dict, key: str) -> tuple[int, int]:
    """(start, koniec) zmiany rotacji w minutach od północy dnia, w którym
    się zaczyna - koniec > start (także przez północ i dla zmiany 24h)."""
    window = rotation[key]
    start = _minutes(window["start"])
    if key == "weekend_full":
        return start, start + DAY_MINUTES
    end = _minutes(window["end"])
    if end <= start:
        end += DAY_MINUTES
    return start, end


def day_anchor(rotation: dict, weekday: int) -> int:
    """Początek doby rotacji tego dnia (minuty od północy) - najwcześniej
    zaczynająca się zmiana standardowego podziału."""
    return min(window_offsets(rotation, key)[0] for key in pattern_keys(rotation, weekday) if rotation.get(key))


def manual_offsets(day_state) -> tuple[int, int] | None:
    """(start, koniec) ręcznego wpisu w minutach od północy jego dnia."""
    if not day_state.start:
        return None
    start = _minutes(day_state.start)
    if getattr(day_state, "is_full_day", False):
        return start, start + DAY_MINUTES
    if not day_state.end:
        return None
    end = _minutes(day_state.end)
    if end <= start:
        end += DAY_MINUTES
    return start, end


def match_duty_key(day_state, rotation: dict, weekday: int) -> str | None:
    """Który typ zmiany rotacji WAŻNY TEGO DNIA odpowiada dokładnie
    ręcznemu wpisowi (None gdy żaden). Zmiana 24h tylko przy is_full_day i
    starcie równym startowi zmiany 24h."""
    start = getattr(day_state, "start", None)
    if not start:
        return None
    keys = pattern_keys(rotation, weekday)
    if getattr(day_state, "is_full_day", False):
        full = rotation.get("weekend_full")
        if keys == _HALF_KEYS and full and full.get("start") == start:
            return "weekend_full"
        return None
    for key in keys:
        window = rotation.get(key)
        if window and window.get("start") == start and window.get("end") == day_state.end:
            return key
    return None


def _subtract(intervals, cuts):
    result = []
    for start, end in intervals:
        segments = [(start, end)]
        for cut_start, cut_end in cuts:
            remaining = []
            for a, b in segments:
                if cut_end <= a or cut_start >= b:
                    remaining.append((a, b))
                    continue
                if a < cut_start:
                    remaining.append((a, cut_start))
                if cut_end < b:
                    remaining.append((cut_end, b))
            segments = remaining
        result.extend(segments)
    return sorted(result)


def _merge_short(pieces):
    pieces = list(pieces)
    changed = True
    while changed:
        changed = False
        for i, (start, end) in enumerate(pieces):
            if end - start >= MIN_PIECE_MINUTES:
                continue
            if i > 0 and pieces[i - 1][1] == start:
                pieces[i - 1] = (pieces[i - 1][0], end)
                del pieces[i]
                changed = True
                break
            if i + 1 < len(pieces) and pieces[i + 1][0] == end:
                pieces[i + 1] = (start, pieces[i + 1][1])
                del pieces[i]
                changed = True
                break
    return pieces


@dataclass
class DutyCoveragePlan:
    # (location_key, dzień) -> [(start, koniec)] zmian resztkowych, które
    # ZACZYNAJĄ SIĘ tego dnia kalendarzowego (start w [0, 1440) minut od
    # północy tego dnia, koniec > start) - kawałek doby d zaczynający się po
    # północy należy do komórki dnia d+1.
    pieces: dict = field(default_factory=dict)
    # {(location_key, dzień)} - doby, w których standardowy podział rotacji
    # zastępują zmiany resztkowe
    planned_days: set = field(default_factory=set)
    # employee.id -> [(dzień, start, koniec)] - ręczne wpisy liczone jako
    # stałe przedziały (generator nie przydziela temu pracownikowi tego
    # dnia żadnej zmiany rotacji)
    fixed: dict = field(default_factory=dict)

    def is_planned(self, location_key: str, day: int) -> bool:
        return (location_key, day) in self.planned_days

    def day_pieces(self, location_key: str, day: int) -> list:
        return self.pieces.get((location_key, day), [])

    def is_fixed(self, employee, day: int) -> bool:
        return any(d == day for d, _, _ in self.fixed.get(employee.id, ()))

    def fixed_intervals(self, employee) -> list:
        return self.fixed.get(employee.id, [])


def _doba_bounds(shop, rotation, day: int) -> tuple[int, int]:
    start = day * DAY_MINUTES + day_anchor(rotation, shop.weekday(day))
    end = (day + 1) * DAY_MINUTES + day_anchor(rotation, (shop.weekday(day) + 1) % 7)
    return start, end


def _pattern_intervals(shop, rotation, day: int) -> list:
    return [
        tuple(day * DAY_MINUTES + v for v in window_offsets(rotation, key))
        for key in pattern_keys(rotation, shop.weekday(day))
    ]


def _plan_location(shop, rotation, location, days, unmatched, matched):
    """Zmiany resztkowe jednej placówki na osi czasu całego miesiąca:
    (lista kawałków (abs_start, abs_end), zbiór zaplanowanych dób)."""

    def is_open(d):
        return 1 <= d <= days[-1] and not (
            location is not None and location.is_duty_day_closed(shop.year, shop.month, d)
        )

    planned = {
        d for d in days
        if is_open(d) and any(
            s < _doba_bounds(shop, rotation, d)[1] and e > _doba_bounds(shop, rotation, d)[0]
            for _, _, s, e in unmatched
        )
    }
    cuts = [(s, e) for _, _, s, e in unmatched]

    for _ in range(len(days) + 1):
        day_cuts = cuts + [(s, e) for d in planned for _, s, e in matched.get(d, [])]
        pattern = [interval for d in sorted(planned) for interval in _pattern_intervals(shop, rotation, d)]
        pieces = _merge_short(_subtract(pattern, day_cuts))

        # Krótki kawałek na granicy doby bez sąsiada do scalenia - dołączamy
        # sąsiednią dobę do planu, żeby dało się go scalić z jej zmianą
        # (np. 06:00-08:00 + 08:00-20:00 = 06:00-20:00 zamiast zmiany 2h).
        extra = set()
        for start, end in pieces:
            if end - start >= MIN_PIECE_MINUTES:
                continue
            for d in sorted(planned):
                doba_start, doba_end = _doba_bounds(shop, rotation, d)
                if end == doba_end and is_open(d + 1) and d + 1 not in planned:
                    extra.add(d + 1)
                if start == doba_start and is_open(d - 1) and d - 1 not in planned:
                    extra.add(d - 1)
        if not extra:
            return pieces, planned
        planned |= extra

    return pieces, planned


def build_duty_coverage_plan(schedule, shop, employees) -> DutyCoveragePlan | None:
    from logic.generator.duty_rotation_constraint import group_employees_with_duty_rotation

    plan = DutyCoveragePlan()
    days = list(range(1, schedule.days_in_month + 1))

    for location_key, (rotation, indices) in group_employees_with_duty_rotation(employees, shop).items():
        location = shop.locations.get(location_key)
        unmatched = []  # (employee, dzień, abs_start, abs_end)
        matched = {}  # dzień -> [(employee, abs_start, abs_end)]

        for e in indices:
            emp = employees[e]
            for d in days:
                ds = schedule.get_day(emp, d)
                if ds.is_leave or getattr(ds, "is_sick", False) or not ds.is_locked:
                    continue
                offsets = manual_offsets(ds)
                if offsets is None:
                    continue
                absolute = (d * DAY_MINUTES + offsets[0], d * DAY_MINUTES + offsets[1])
                if match_duty_key(ds, rotation, shop.weekday(d)) is None:
                    unmatched.append((emp, d, *absolute))
                else:
                    matched.setdefault(d, []).append((emp, *absolute))

        for emp, d, abs_start, abs_end in unmatched:
            plan.fixed.setdefault(emp.id, []).append((d, abs_start - d * DAY_MINUTES, abs_end - d * DAY_MINUTES))

        if not unmatched:
            continue

        pieces, planned = _plan_location(shop, rotation, location, days, unmatched, matched)

        by_day = {}
        for start, end in pieces:
            day = start // DAY_MINUTES
            if day not in days:
                # Kawałek ostatniej doby miesiąca zaczynający się już w
                # następnym miesiącu - poza zakresem tego grafiku.
                print(f"[DUTY PLAN] {location_key}: kawałek poza miesiącem pominięty")
                continue
            by_day.setdefault(day, []).append((start - day * DAY_MINUTES, end - day * DAY_MINUTES))

        if any(len(p) > MAX_CUSTOM_PIECES for p in by_day.values()):
            # Praktycznie niespotykane (8+ osobnych ręcznych wpisów w
            # jednej dobie) - zostaje dotychczasowe zachowanie.
            print(f"[DUTY PLAN] {location_key}: za dużo kawałków w jednym dniu, pomijam plan")
            continue

        for day, day_pieces in by_day.items():
            plan.pieces[(location_key, day)] = day_pieces
        for d in planned:
            plan.planned_days.add((location_key, d))
            for emp, s, e in matched.get(d, []):
                plan.fixed.setdefault(emp.id, []).append((d, s - d * DAY_MINUTES, e - d * DAY_MINUTES))

    if not plan.pieces and not plan.fixed:
        return None
    return plan


def get_plan(duty_shifts):
    return getattr(duty_shifts, "plan", None)


def custom_shift_ids(duty_shifts) -> list:
    return [duty_shifts[key] for key in CUSTOM_KEYS if key in duty_shifts]


def planned_minutes_expr(x, e, employee, days, duty_shifts):
    """Minuty zmian resztkowych (per dzień - każda doba ma inne kawałki) i
    stałych ręcznych wpisów pracownika rotacji - do dodania do sumy godzin
    liczonej z minutes_by_shift (gdzie zmiany resztkowe mają 0)."""
    plan = get_plan(duty_shifts)
    if plan is None:
        return 0
    location_key = employee.location_key or ""
    day_set = set(days)
    terms = [
        x[e, d, duty_shifts[CUSTOM_KEYS[i]]] * (end - start)
        for d in days
        for i, (start, end) in enumerate(plan.day_pieces(location_key, d))
    ]
    fixed = sum(end - start for d, start, end in plan.fixed_intervals(employee) if d in day_set)
    return sum(terms) + fixed
