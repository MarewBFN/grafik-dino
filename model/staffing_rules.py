"""Reguła profilu custom "min. N osób z kwalifikacją X na poziomie >= L
[na otwarciu / na zamknięciu / w ciągu dnia / na zmianie nocnej / w każdej
chwili okna godzin]" (RULE_TYPE_MIN_STAFF_WITH_ROLE) - jedna definicja
reguły dla obu miejsc, które ją sprawdzają:

- generator (logic/generator/generic_rules.py::build_min_staff_with_role)
  buduje z niej ograniczenia CP-SAT na zmiennych x[e, d, s],
- walidacja siatki (model/constraints.py::CustomStaffRule) sprawdza nią
  gotowy grafik i koloruje wiersz kwalifikacji nad tabelą.

Wspólne są: kto się liczy danego dnia (kwalifikacja ważna tego dnia, w
placówce pracownika, na poziomie >= L), progi per placówka (nadpisanie
LocationConfig.constraints["rule:<id>"]), dni, w których reguła obowiązuje,
podział okna godzin na odcinki i przedział zmiany w minutach. Różni się
tylko to, co jest nieznane: generator liczy zmienne kandydujących zmian,
siatka - wpisane godziny (patrz scope_shift_ids / cell_in_scope - dwie
strony tej samej definicji zakresu, trzymane obok siebie).

Moduł nie zależy od OR-Tools - model nie importuje generatora."""

from model.qualification import has_on, held_in_month

DAY = 24 * 60
SLOT_MINUTES = 15

SCOPE_OPEN = "open"
SCOPE_CLOSE = "close"
SCOPE_ANY_SHIFT = "any_shift"
SCOPE_NIGHT = "night"
SCOPE_WINDOW = "window"

# Domyślne parametry reguły (RuleInstance.params) - te same dla generatora
# i siatki.
DEFAULT_PARAMS = {
    "min_count": 1,
    "scope": SCOPE_OPEN,
    "min_level": 1,
    "window_start": "10:00",
    "window_end": "14:00",
}


def rule_params(params: dict) -> dict:
    return {**DEFAULT_PARAMS, **{key: params[key] for key in DEFAULT_PARAMS if key in params}}


def minutes(value: str) -> int:
    """"HH:MM" (także "H:MM") -> minuty od północy."""
    hours, mins = value.split(":")
    return int(hours) * 60 + int(mins)


def span(start: str, end: str) -> tuple[int, int]:
    """(start, koniec) w minutach od północy; koniec <= początek = przez
    północ (koniec + 24 h)."""
    s, e = minutes(start), minutes(end)
    if e <= s:
        e += DAY
    return s, e


# ---------------------------------------------------------------------------
# Kto i kiedy
# ---------------------------------------------------------------------------

def qualified_on(employee, shop, qualification_key, min_level, day) -> bool:
    """Czy pracownik liczy się do reguły w dniu `day` (kwalifikacja ważna
    tego dnia, w jego placówce, na poziomie >= min_level)."""
    return has_on(employee, qualification_key, shop.year, shop.month, day, min_level)


def threshold_groups(employees, shop, rule_key, qualification_key, min_count, min_level) -> dict:
    """{próg: [indeksy pracowników]} - pracownicy z kwalifikacją choć jeden
    dzień miesiąca, pogrupowani wg progu ich placówki (nadpisanie
    LocationConfig.constraints[rule_key], tak jak max_consecutive_days).
    Nikt nie ma kwalifikacji - {min_count: []}: wymóg dalej obowiązuje
    (i sygnalizuje brak)."""
    groups: dict[int, list[int]] = {}
    for e, employee in enumerate(employees):
        if not held_in_month(employee, qualification_key, shop.year, shop.month, min_level):
            continue
        threshold = shop.get_location(employee).constraints.get(rule_key, min_count)
        groups.setdefault(threshold, []).append(e)
    return groups or {min_count: []}


def location_open_for(shop, employee, day) -> bool:
    """False gdy placówka pracownika nie ma tego dnia godzin otwarcia
    ("Nieczynne", święto, ręczne zamknięcie). Placówka z rotacją 24/7 -
    zawsze True. To samo co logic.generator.constraints_basic.
    is_location_open_for_employee."""
    location = shop.get_location(employee)
    if location.get_duty_rotation():
        return True
    return bool(location.get_open_hours_for_day(day))


def staffing_days(employees, shop, days) -> list:
    """Dni, w których obowiązują wymogi obsady: dni handlowe, w których
    czynna jest choć jedna placówka pracowników (bez pracowników - każdy
    dzień handlowy)."""
    return [
        d for d in days
        if shop.is_trade_day(d)
        and (not employees or any(location_open_for(shop, employee, d) for employee in employees))
    ]


def group_active_on(shop, employees, indices, day) -> bool:
    """Reguła nie obowiązuje grupy w dniu, w którym placówki wszystkich jej
    osób są zamknięte (nie mogą wtedy pracować). Pusta grupa (nikt nie ma
    kwalifikacji) - obowiązuje i sygnalizuje brak."""
    return not indices or any(location_open_for(shop, employees[e], day) for e in indices)


# ---------------------------------------------------------------------------
# Przedziały i okno godzin
# ---------------------------------------------------------------------------

def cell_interval(day_state) -> tuple[int, int] | None:
    """Przedział wpisanej zmiany (minuty od północy jej dnia) albo None dla
    pustego dnia, urlopu i L4. Zmiana 24 h (is_full_day) trwa dobę od
    startu."""
    if day_state.is_leave or getattr(day_state, "is_sick", False):
        return None
    if not day_state.start or not day_state.end:
        return None
    if getattr(day_state, "is_full_day", False):
        start = minutes(day_state.start)
        return start, start + DAY
    return span(day_state.start, day_state.end)


def segments(start: int, end: int, intervals) -> list[tuple[int, int]]:
    """Podział [start, end) na odcinki w punktach, w których zaczyna się albo
    kończy którykolwiek z `intervals` - w każdym odcinku zbiór pokrywających
    go przedziałów jest stały."""
    points = {start, end}
    for a, b in intervals:
        if start < a < end:
            points.add(a)
        if start < b < end:
            points.add(b)
    points = sorted(points)
    return list(zip(points, points[1:]))


def covers(interval, a: int, b: int) -> bool:
    """Czy przedział pokrywa cały odcinek [a, b)."""
    return interval[0] <= a and b <= interval[1]


def slots(a: int, b: int) -> int:
    """Liczba rozpoczętych kwadransów odcinka - waga braku w wersji
    miękkiej reguły okna."""
    return -(-(b - a) // SLOT_MINUTES)


# ---------------------------------------------------------------------------
# Zakres reguły: generator (zmienne) i siatka (wpisane godziny)
# ---------------------------------------------------------------------------

def scope_shift_ids(scope, ctx) -> tuple:
    """Zmiany generatora, które liczą się do zakresu (poza "window" - tam
    liczą się przedziały, patrz generic_rules)."""
    if scope == SCOPE_OPEN:
        return (ctx.shift_open,)
    if scope == SCOPE_CLOSE:
        return (ctx.shift_close,)
    if scope == SCOPE_NIGHT:
        # Tylko SHIFT_NIGHT. Placówka bez zmiany nocnej ma ją zawsze
        # wyzerowaną - reguła słusznie sygnalizuje wtedy niespełnialność.
        return (ctx.shift_night,)
    return tuple(ctx.all_shifts)  # SCOPE_ANY_SHIFT


def cell_in_scope(scope, location, day, interval) -> bool:
    """Czy wpisana zmiana (`interval` dnia `day`) liczy się do zakresu -
    odpowiednik scope_shift_ids dla gotowego grafiku: otwarcie = zaczyna się
    o godzinie otwarcia placówki, zamknięcie = kończy o godzinie zamknięcia,
    noc = zaczyna się o początku jej zmiany nocnej, w ciągu dnia = każda."""
    if scope == SCOPE_ANY_SHIFT:
        return True
    if scope == SCOPE_NIGHT:
        night = location.get_night_shift_hours()
        return bool(night) and interval[0] == minutes(night[0])
    hours = location.get_open_hours_for_day(day)
    if not hours:
        return False
    open_m, close_m = span(*hours)
    if scope == SCOPE_OPEN:
        return interval[0] == open_m
    if scope == SCOPE_CLOSE:
        return interval[1] % DAY == close_m % DAY
    return False


# ---------------------------------------------------------------------------
# Sprawdzenie gotowego grafiku
# ---------------------------------------------------------------------------

def _fmt(minute: int) -> str:
    minute %= DAY
    return f"{minute // 60:02d}:{minute % 60:02d}"


def check_min_staff(schedule, shop, rule_key, qualification_key, params) -> list:
    """Braki obsady reguły w gotowym grafiku: [(dzień, opis)]. Te same
    grupy, dni i definicja zakresu co generator."""
    p = rule_params(params)
    employees = list(schedule.employees)
    groups = threshold_groups(employees, shop, rule_key, qualification_key, p["min_count"], p["min_level"])
    days = list(range(1, schedule.days_in_month + 1))
    result = []
    for day in staffing_days(employees, shop, days):
        for threshold, indices in groups.items():
            if not group_active_on(shop, employees, indices, day):
                continue
            if p["scope"] == SCOPE_WINDOW:
                gaps = _window_gaps(schedule, shop, employees, indices, qualification_key, p, threshold, day, days)
                if gaps:
                    text = ", ".join(f"{_fmt(a)}–{_fmt(b)} ({count} z {threshold})" for a, b, count in gaps)
                    result.append((day, f"za mało osób: {text}"))
                continue
            count = 0
            for e in indices:
                employee = employees[e]
                interval = cell_interval(schedule.get_day(employee, day))
                if (
                    interval is not None
                    and qualified_on(employee, shop, qualification_key, p["min_level"], day)
                    and cell_in_scope(p["scope"], shop.get_location(employee), day, interval)
                ):
                    count += 1
            if count < threshold:
                result.append((day, f"jest {count} z {threshold} os."))
    return result


def _window_gaps(schedule, shop, employees, indices, qualification_key, p, threshold, day, days):
    """Odcinki okna dnia `day` z obsadą poniżej progu: [(start, koniec,
    liczba osób)], sąsiednie odcinki o tej samej liczbie scalone. Liczą się
    zmiany z dnia poprzedniego i następnego (okna i zmiany przez północ)."""
    win_start, win_end = span(p["window_start"], p["window_end"])
    intervals = []
    for e in indices:
        employee = employees[e]
        for shift_day in (day - 1, day, day + 1):
            if shift_day not in days or not qualified_on(employee, shop, qualification_key, p["min_level"], shift_day):
                continue
            interval = cell_interval(schedule.get_day(employee, shift_day))
            if interval is not None:
                offset = (shift_day - day) * DAY
                intervals.append((interval[0] + offset, interval[1] + offset))
    gaps = []
    for a, b in segments(win_start, win_end, intervals):
        count = sum(1 for interval in intervals if covers(interval, a, b))
        if count >= threshold:
            continue
        if gaps and gaps[-1][1] == a and gaps[-1][2] == count:
            gaps[-1] = (gaps[-1][0], b, count)
        else:
            gaps.append((a, b, count))
    return gaps
