"""Model godzin otwarcia placówek Ochrony BEZ rotacji 24/7 - placówki z
godzinami z edytora tygodnia (np. GZUK: pn-pt 15:00-07:00, sob-nd 24h).

Przed tym modelem taka placówka nie miała żadnej reguły obsady (generator
dokładał zmiany tylko pod godziny etatu), dostawała sztywną nockę 22:00-06:00
i zmiany zakotwiczone przy otwarciu/zamknięciu - efekt dla GZUK: ok. 60%
godzin otwarcia bez nikogo, a na nocce 4-6 osób naraz, przy wyniku OPTIMAL.

Decyzje użytkownika (2026-09-28):

1. Zakres: każdy profil Ochrony - profil „custom_ochrona” albo każdy profil
   custom z rolą „Nie chce 24h” (np. ochrona_enyo, ochrona_dane_klienta_test).
   Dino i pozostałe profile custom - bez zmian.
2. Jedna osoba na całe okno dnia: 15:00-07:00 = jedna zmiana 16 h. Doba
   (00:00-23:45, przycisk „24h”) = jedna zmiana 24 h albo dwie połówki po
   12 h (np. „Nie chce 24h” w weekend, urlopy) - jak rotacja 24/7.
3. Doba zaczyna się tam, gdzie kończy się okno dnia poprzedniego: pt
   15:00-07:00 + sob/nd 24h = ciągle od pt 15:00 do pn 07:00 (sobota
   07:00-07:00, niedziela 07:00-07:00). Ogólniej: okno dnia zaczyna się nie
   wcześniej niż skończyło się okno poprzednie (okna się nie nakładają).
4. Nakładki są dozwolone, ale sterowane zasadą „Maks. obsada naraz”
   (MAX_STAFF_POLICY): liczba osób (Konfiguracja, domyślnie 1) i tryb
   Wymagana/Preferowana/Wyłączona (domyślnie Preferowana, waga wyższa niż
   „Umowa”, więc drugiej osoby nie dokłada się tylko po to, żeby dobić
   godziny etatu).

Zasady modelu dla pracowników takiej placówki:

- jedyne dozwolone zmiany to kształty okien (cała zmiana / połówki doby) i
  zmiany resztkowe wokół ręcznych wpisów; brak sztywnej nocki i zmian
  OPEN/CLOSE/START/END;
- zmiana należy do dnia (komórki grafiku), w którym się zaczyna;
- ręczny wpis pasujący dokładnie do kształtu = ta zmiana; każdy inny =
  stały przedział: liczy się do obłożenia, obsady naraz, godzin, odpoczynku
  i dni pod rząd, a pozostała część okna dostaje zmianę resztkową;
- odpoczynek: 11 h po każdej zmianie, po zmianie 24 h - (N-1)x24 h, nie
  mniej niż 24 h (N = osoby placówki bez „Nie chce 24h”, jak rotacja 24/7);
- „Obłożenie godzin otwarcia” (OPENING_HOURS_COVERAGE_POLICY, domyślnie
  Wymagana): w każdym kwadransie okna co najmniej 1 osoba z placówki;
- „Nie chce 24h”: bez zmiany 24 h w sobotę/niedzielę (zasada
  duty_rotation_no24h, jak w rotacji 24/7).
"""

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta

DAY = 24 * 60
HALF_DAY = DAY // 2
SLOT = 15
MIN_REST_MINUTES = 11 * 60
# Okno trwające co najmniej 23:45 to doba - konwencja „24h” z edytora
# tygodnia (00:00-23:45); plik projektu może też mieć 07:00-07:00.
FULL_DAY_MIN_LENGTH = DAY - SLOT
# Ile dni poprzedniego miesiąca (wg wzorca tygodnia) liczyć, żeby ustalić,
# gdzie kończy się okno sprzed dnia 1 (kotwica doby w dniu 1).
WARMUP_DAYS = 7
NIGHT_START = 22 * 60
NIGHT_END = 6 * 60
AFTERNOON_START = 12 * 60

OPENING_HOURS_COVERAGE_POLICY = "opening_hours_coverage"
OPENING_HOURS_COVERAGE_LABEL = "Obłożenie godzin otwarcia"
OPENING_HOURS_COVERAGE_WEIGHT = 5000  # za kwadrans bez obsady

MAX_STAFF_POLICY = "max_staff_at_once"
MAX_STAFF_LABEL = "Maks. obsada naraz"
MAX_STAFF_CONSTRAINT_KEY = "max_staff_at_once"
DEFAULT_MAX_STAFF = 1
# Za każdą nadmiarową osobo-minutę - więcej niż „Umowa” (10000 za minutę
# niedoboru, priority_hours_constraint.PRIORITY_WEIGHT): przy Preferowanej
# generator nie dokłada drugiej osoby tylko po to, żeby dobić godziny.
MAX_STAFF_WEIGHT = 20000
# Lekka zachęta do całej doby zamiast dwóch połówek (połówki dla „Nie chce
# 24h” i urlopów) - tylko rozstrzyga remisy, nie przebija żadnej zasady.
PREFER_FULL_DAY_WEIGHT = 5

KIND_FULL = "full"
KIND_HALF_A = "half_a"
KIND_HALF_B = "half_b"
KIND_RESIDUAL = "residual"


# ---------------------------------------------------------------------------
# Profil
# ---------------------------------------------------------------------------

def custom_profile_uses_opening_hours_model(custom) -> bool:
    """Profil Ochrony: „custom_ochrona” albo profil custom z rolą „Nie chce 24h”."""
    if custom is None:
        return False
    from logic.generator.duty_rotation_constraint import NIE_CHCE_24H_ROLE_KEY
    from model.business_profile import DEFAULT_OCHRONA_PROFILE_KEY

    if getattr(custom, "key", None) == DEFAULT_OCHRONA_PROFILE_KEY:
        return True
    return any(getattr(role, "key", None) == NIE_CHCE_24H_ROLE_KEY for role in getattr(custom, "roles", ()))


def profile_uses_opening_hours_model(business_type) -> bool:
    from model.business_profile import get_custom_profile

    return custom_profile_uses_opening_hours_model(get_custom_profile(business_type))


def uses_opening_hours_model(shop) -> bool:
    return profile_uses_opening_hours_model(getattr(shop, "business_type", None))


def is_regular_location(location_view) -> bool:
    """Placówka z godzinami otwarcia (bez rotacji służby i rotacji całodobowej)."""
    return not location_view.get_duty_rotation() and not location_view.get_round_clock_start_hour()


def _has_no24h_role(emp) -> bool:
    from logic.generator.duty_rotation_constraint import NIE_CHCE_24H_ROLE_KEY

    return bool(getattr(emp, "custom_roles", {}).get(NIE_CHCE_24H_ROLE_KEY, False))


# ---------------------------------------------------------------------------
# Okna dni
# ---------------------------------------------------------------------------

def _minutes(value: str) -> int:
    t = datetime.strptime(value, "%H:%M")
    return t.hour * 60 + t.minute


def fmt_minutes(minute_of_day: int) -> str:
    minute_of_day %= DAY
    return f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"


@dataclass(frozen=True)
class Window:
    """Okno obsady dnia `day`: [start, end) w minutach od początku miesiąca
    (dzień 1, 00:00 = 0)."""
    day: int
    start: int
    end: int
    is_full_day: bool


@dataclass(frozen=True)
class Shape:
    """Dozwolona zmiana: [start, end) w minutach od początku miesiąca, rodzaj
    i dzień okna, do którego należy."""
    start: int
    end: int
    kind: str
    window_day: int

    @property
    def length(self) -> int:
        return self.end - self.start


def parse_open_hours(hours):
    """(czy doba, początek, koniec) w minutach od północy dnia albo None.
    Koniec wcześniej niż początek = przejście przez północ; okno co
    najmniej 23:45 (00:00-23:45, 07:00-07:00) = doba 24 h od początku."""
    if not hours or not hours[0] or not hours[1]:
        return None
    start, end = _minutes(hours[0]), _minutes(hours[1])
    length = (end - start) % DAY or DAY
    if length >= FULL_DAY_MIN_LENGTH:
        return True, start, start + DAY
    return False, start, start + length


def _place(parsed, day, base, last_end):
    """Okno na osi miesiąca, przesunięte tak, żeby zaczynało się nie
    wcześniej niż koniec poprzedniego (doba zachowuje 24 h)."""
    if parsed is None:
        return None
    is_full_day, start, end = parsed
    start, end = base + start, base + end
    if last_end is not None and last_end > start:
        if is_full_day:
            end += last_end - start
        start = last_end
        if start >= end:
            return None
    return Window(day, start, end, is_full_day)


def location_windows(view, year, month, days_in_month):
    """{dzień: Window} placówki na cały miesiąc. Dni poprzedniego miesiąca
    liczone z tygodniowego wzorca godzin (bez ręcznych nadpisań) - tylko po
    to, żeby wiedzieć, gdzie kończy się okno sprzed dnia 1."""
    first = date(year, month, 1)
    pattern = getattr(view, "get_weekly_open_hours_on", None)
    last_end = None
    if pattern is not None:
        for back in range(WARMUP_DAYS, 0, -1):
            window = _place(parse_open_hours(pattern(first - timedelta(days=back))), None, -back * DAY, last_end)
            if window is not None:
                last_end = window.end if last_end is None else max(last_end, window.end)
    windows = {}
    for day in range(1, days_in_month + 1):
        window = _place(parse_open_hours(view.get_open_hours_for_day(day)), day, (day - 1) * DAY, last_end)
        if window is not None:
            windows[day] = window
            last_end = window.end if last_end is None else max(last_end, window.end)
    return windows


def window_shapes(window):
    if not window.is_full_day:
        return [Shape(window.start, window.end, KIND_FULL, window.day)]
    middle = window.start + HALF_DAY
    return [
        Shape(window.start, window.end, KIND_FULL, window.day),
        Shape(window.start, middle, KIND_HALF_A, window.day),
        Shape(middle, window.end, KIND_HALF_B, window.day),
    ]


def _subtract(start, end, intervals):
    """Części [start, end) nieprzykryte żadnym z `intervals`."""
    pieces = []
    t = start
    for a, b in sorted(intervals):
        if b <= t or a >= end:
            continue
        if a > t:
            pieces.append((t, a))
        t = max(t, b)
        if t >= end:
            break
    if t < end:
        pieces.append((t, end))
    return pieces


def _overlaps_night(start, end) -> bool:
    first = start // DAY - 1
    for k in range(first, end // DAY + 1):
        night_start = k * DAY + NIGHT_START
        night_end = (k + 1) * DAY + NIGHT_END
        if start < night_end and night_start < end:
            return True
    return False


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class OpeningHoursModel:
    """Okna placówek, dozwolone kształty zmian (per komórka dnia), ręczne
    stałe przedziały i dopasowania ręcznych wpisów - liczone raz na
    generowanie."""

    def __init__(self, ctx):
        shop = ctx.shop
        self.shop = shop
        self.days = list(ctx.days)
        self.employees = ctx.employees
        self.days_in_month = calendar.monthrange(shop.year, shop.month)[1]
        self.month_end = self.days_in_month * DAY
        self.shape_ids = list(ctx.round_clock_shifts or [])

        self.indices = [
            e for e, emp in enumerate(ctx.employees)
            if is_regular_location(shop.get_location(emp))
        ]
        self.index_set = set(self.indices)
        self.location_of = {}   # e -> klucz placówki
        self.members = {}       # klucz placówki -> [e]
        self.views = {}
        for e in self.indices:
            emp = ctx.employees[e]
            key = emp.location_key or ""
            self.location_of[e] = key
            self.members.setdefault(key, []).append(e)
            self.views.setdefault(key, shop.get_location(emp))

        self.windows_by_location = {
            key: location_windows(view, shop.year, shop.month, self.days_in_month)
            for key, view in self.views.items()
        }
        self.capable_24h = {
            key: sum(1 for e in members if not _has_no24h_role(ctx.employees[e]))
            for key, members in self.members.items()
        }

        base = {}  # (klucz, dzień komórki) -> [Shape]
        for key, windows in self.windows_by_location.items():
            for window in windows.values():
                for shape in window_shapes(window):
                    cell = self._cell_of(shape.start)
                    if cell is not None:
                        base.setdefault((key, cell), []).append(shape)

        self.fixed = {}           # e -> [(dzień, start, end)]
        self.manual_blocked = set()
        manual_match = {}         # (e, d) -> Shape
        for e in self.indices:
            self._resolve_manual(ctx, e, base, manual_match)

        # Zmiany resztkowe: część okna, której nie przykrywają ręczne stałe
        # przedziały - inaczej do pokrycia zostawałaby tylko cała zmiana,
        # nachodząca na ręczny wpis (dwie osoby naraz).
        cells = {k: list(v) for k, v in base.items()}
        for key, windows in self.windows_by_location.items():
            fixed = [(s, en) for e in self.members[key] for _d, s, en in self.fixed.get(e, ())]
            if not fixed:
                continue
            for window in windows.values():
                pieces = _subtract(window.start, window.end, fixed)
                if pieces == [(window.start, window.end)]:
                    continue
                for a, b in pieces:
                    cell = self._cell_of(a)
                    if cell is not None:
                        cells.setdefault((key, cell), []).append(Shape(a, b, KIND_RESIDUAL, window.day))

        self.shapes = {}  # (klucz, dzień) -> {id zmiany: Shape}
        self.dropped_shapes = []
        for (key, cell), shapes in cells.items():
            assigned = {}
            for sid, shape in zip(self.shape_ids, shapes):
                assigned[sid] = shape
            self.dropped_shapes.extend(shapes[len(self.shape_ids):])
            self.shapes[(key, cell)] = assigned

        self.windows = {}       # (e, d) -> {id zmiany: (start, end)}
        self.manual_shift = {}  # (e, d) -> id zmiany (dokładnie dopasowany ręczny wpis)
        for e in self.indices:
            key = self.location_of[e]
            for d in self.days:
                shapes = self.shapes.get((key, d), {})
                self.windows[(e, d)] = {sid: (sh.start, sh.end) for sid, sh in shapes.items()}
                target = manual_match.get((e, d))
                if target is not None:
                    self.manual_shift[(e, d)] = next(sid for sid, sh in shapes.items() if sh == target)

    # ------------------------------------------------------------------

    def _cell_of(self, minute):
        cell = minute // DAY + 1
        return cell if 1 <= cell <= self.days_in_month else None

    def _resolve_manual(self, ctx, e, base, manual_match):
        emp = ctx.employees[e]
        key = self.location_of[e]
        for d in self.days:
            ds = ctx.schedule.get_day(emp, d)
            if ds.is_leave or getattr(ds, "is_sick", False) or not ds.is_locked:
                continue
            if not ds.start or not ds.end:
                self.manual_blocked.add((e, d))
                continue
            start = (d - 1) * DAY + _minutes(ds.start)
            if getattr(ds, "is_full_day", False):
                end = start + DAY
            else:
                end = (d - 1) * DAY + _minutes(ds.end)
                if end <= start:
                    end += DAY
            match = next((sh for sh in base.get((key, d), ()) if (sh.start, sh.end) == (start, end)), None)
            if match is not None:
                manual_match[(e, d)] = match
            else:
                self.fixed.setdefault(e, []).append((d, start, end))
                self.manual_blocked.add((e, d))

    # ------------------------------------------------------------------

    def shape(self, e, d, sid):
        return self.shapes.get((self.location_of[e], d), {}).get(sid)

    def allowed(self, e, d):
        """{id: Shape} zmian, które generator może przydzielić e w dniu d."""
        if (e, d) in self.manual_blocked:
            return {}
        shapes = self.shapes.get((self.location_of[e], d), {})
        forced = self.manual_shift.get((e, d))
        if forced is not None:
            return {forced: shapes[forced]}
        return dict(shapes)

    def items(self, e):
        """[(start, end, dzień, id)] wszystkich dozwolonych zmian e."""
        return sorted(
            (sh.start, sh.end, d, sid)
            for d in self.days
            for sid, sh in self.allowed(e, d).items()
        )

    def required_rest_after(self, location_key, length) -> int:
        """11 h; po zmianie 24 h - (N-1)x24 h, nie mniej niż 24 h (jak
        rotacja 24/7, duty_rotation_rest_constraint._required_rest)."""
        if length >= DAY:
            return DAY * max(self.capable_24h.get(location_key, 0) - 1, 1)
        return MIN_REST_MINUTES

    def max_staff(self, location_key) -> int:
        value = self.views[location_key].constraints.get(MAX_STAFF_CONSTRAINT_KEY, DEFAULT_MAX_STAFF)
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return DEFAULT_MAX_STAFF

    def fixed_days(self, e):
        return {d for d, _s, _e in self.fixed.get(e, ())}

    def fixed_minutes(self, emp):
        e = self._index_of(emp)
        if e is None:
            return 0
        return sum(end - start for _d, start, end in self.fixed.get(e, ()))

    def duration_overrides(self, emp):
        """Kształty tego modelu liczone są przez minutes_expr (różna długość
        per dzień) - w ogólnej sumie „minuty x zmiana” mają 0."""
        if self._index_of(emp) is None:
            return {}
        return {sid: 0 for sid in self.shape_ids}

    def minutes_expr(self, x, emp):
        """Minuty pracy e z kształtów tego modelu + ręczne stałe przedziały
        (0 dla pracownika spoza modelu)."""
        e = self._index_of(emp)
        if e is None:
            return 0
        return sum(
            x[e, d, sid] * (end - start)
            for d in self.days
            for sid, (start, end) in self.windows[(e, d)].items()
        ) + self.fixed_minutes(emp)

    def assignment_hours(self, e, d, sid):
        """("HH:MM", "HH:MM", czy 24h) zmiany do zapisu w komórce dnia d."""
        shape = self.shape(e, d, sid)
        if shape is None:
            return None
        base = (d - 1) * DAY
        return fmt_minutes(shape.start - base), fmt_minutes(shape.end - base), shape.length >= DAY

    def _index_of(self, emp):
        for e in self.indices:
            if self.employees[e] is emp or self.employees[e].id == emp.id:
                return e
        return None


def get_model(ctx):
    extra = getattr(ctx, "extra", None) if ctx is not None else None
    return extra.get("opening_hours_model") if extra else None


def setup_opening_hours_model(ctx) -> None:
    if uses_opening_hours_model(ctx.shop):
        ctx.extra["opening_hours_model"] = OpeningHoursModel(ctx)


def _segments(start, end, intervals):
    """Kolejne odcinki [a, b) w [start, end), na których żaden z
    `intervals` nie zaczyna się ani nie kończy."""
    points = {start, end}
    for a, b in intervals:
        if start < a < end:
            points.add(a)
        if start < b < end:
            points.add(b)
    points = sorted(points)
    return list(zip(points, points[1:]))


def _slots(length) -> int:
    return max(1, -(-length // SLOT))


# ---------------------------------------------------------------------------
# Constrainty
# ---------------------------------------------------------------------------

def add_opening_hours_shape_constraint(ctx) -> None:
    """Zawsze twarde (fakt strukturalny, jak bramy rotacji): tylko dozwolone
    kształty zmian tego dnia + ręczne wpisy (dopasowane/stałe) + typ zmiany
    z grafiku („W” = musi dostać zmianę, „1”/„2” = zaczynającą się przed/od
    12:00)."""
    model = get_model(ctx)
    if model is None:
        return
    if ctx.trace is not None:
        ctx.trace.log_constraint("opening_hours_shape", "allowed shift shapes for regular locations (Ochrona)")

    for e in model.indices:
        emp = ctx.employees[e]
        for d in model.days:
            allowed = model.allowed(e, d)
            forced = model.manual_shift.get((e, d))
            if forced is not None and (e, d) not in model.manual_blocked:
                ctx.model.Add(ctx.x[e, d, forced] == 1)
            elif allowed:
                shift_class = getattr(ctx.schedule.get_day(emp, d), "shift_class", None)
                if shift_class in ("1", "2", "W"):
                    wanted = allowed
                    if shift_class in ("1", "2"):
                        base = (d - 1) * DAY
                        morning = {
                            sid for sid, sh in allowed.items()
                            if sh.start - base < AFTERNOON_START
                        }
                        chosen = morning if shift_class == "1" else set(allowed) - morning
                        # Brak zmiany tego typu w tym dniu - zostaje „musi
                        # pracować” (jak „W”), zamiast cichego pominięcia.
                        wanted = {sid: allowed[sid] for sid in chosen} or allowed
                    allowed = wanted
                    ctx.model.Add(sum(ctx.x[e, d, s] for s in allowed) == 1)
            for s in ctx.all_shifts:
                if s not in allowed:
                    ctx.model.Add(ctx.x[e, d, s] == 0)


def add_opening_hours_rest_constraint(ctx, soft, schedule=None):
    """Odpoczynek między zmianami modelu (i ręcznymi stałymi przedziałami)
    tego samego pracownika, dokładnie na osi miesiąca, oraz względem zmiany
    z końca poprzedniego miesiąca (gdy `schedule` - pamięć poprzedniego
    miesiąca włączona)."""
    model = get_model(ctx)
    if model is None:
        return []
    if ctx.trace is not None:
        ctx.trace.log_constraint("opening_hours_rest", f"soft={soft}")
    violations = []

    def forbid_pair(e, d1, s1, d2, s2):
        if not soft:
            ctx.model.Add(ctx.x[e, d1, s1] + ctx.x[e, d2, s2] <= 1)
        else:
            v = ctx.model.NewBoolVar(f"opening_rest_e{e}_d{d1}_{s1}_d{d2}_{s2}")
            ctx.model.Add(ctx.x[e, d1, s1] + ctx.x[e, d2, s2] <= 1 + v)
            violations.append(v)

    def forbid_one(e, d, s, label):
        if not soft:
            ctx.model.Add(ctx.x[e, d, s] == 0)
        else:
            v = ctx.model.NewBoolVar(label)
            ctx.model.Add(ctx.x[e, d, s] <= v)
            violations.append(v)

    for e in model.indices:
        key = model.location_of[e]
        items = model.items(e)
        for i, (s1, e1, d1, sid1) in enumerate(items):
            limit = e1 + model.required_rest_after(key, e1 - s1)
            for s2, _e2, d2, sid2 in items[i + 1:]:
                if s2 >= limit:
                    break
                if d2 != d1:  # ten sam dzień: najwyżej jedna zmiana (one_shift_per_day)
                    forbid_pair(e, d1, sid1, d2, sid2)

        for fixed_day, f_start, f_end in model.fixed.get(e, ()):
            rest_after_fixed = model.required_rest_after(key, f_end - f_start)
            for start, end, d, sid in items:
                if d == fixed_day:
                    continue
                conflict = (
                    (start < f_end and f_start < end)
                    or (start >= f_end and start - f_end < rest_after_fixed)
                    or (end <= f_start and f_start - end < model.required_rest_after(key, end - start))
                )
                if conflict:
                    forbid_one(e, d, sid, f"opening_rest_fixed_e{e}_d{d}_{sid}")

        carry = schedule.get_previous_month_end_shift(ctx.employees[e]) if schedule is not None else None
        if carry is not None and carry.end:
            end_prev = _minutes(carry.end) - (0 if carry.crosses_midnight else DAY)
            for start, _end, d, sid in items:
                if start - end_prev >= MIN_REST_MINUTES:
                    break
                forbid_one(e, d, sid, f"opening_rest_prevmonth_e{e}_d{d}_{sid}")

    return violations


def add_opening_hours_coverage_constraint(ctx, soft):
    """Co najmniej 1 osoba z placówki w każdym kwadransie jej okien (ręczne
    stałe przedziały też się liczą). Część okna ostatniego dnia po końcu
    miesiąca należy już do następnego grafiku."""
    model = get_model(ctx)
    if model is None:
        return []
    if ctx.trace is not None:
        ctx.trace.log_constraint(OPENING_HOURS_COVERAGE_POLICY, f"soft={soft}")

    violations = []
    for key, members in model.members.items():
        fixed = [(s, en) for e in members for _d, s, en in model.fixed.get(e, ())]
        by_window = {}
        for e in members:
            for d in model.days:
                for sid, sh in model.allowed(e, d).items():
                    by_window.setdefault(sh.window_day, []).append((sh.start, sh.end, e, d, sid))
        for day, window in sorted(model.windows_by_location[key].items()):
            end = min(window.end, model.month_end)
            if end <= window.start:
                continue
            shapes = by_window.get(day, [])
            intervals = [(s, en) for s, en, *_ in shapes] + fixed
            for a, b in _segments(window.start, end, intervals):
                if any(fs <= a and b <= fe for fs, fe in fixed):
                    continue
                terms = [ctx.x[e, d, sid] for s, en, e, d, sid in shapes if s <= a and b <= en]
                if not soft:
                    if terms:
                        ctx.model.Add(sum(terms) >= 1)
                    else:
                        # Nikt z placówki nie może tu pracować (np. wszyscy na
                        # urlopie) - Wymagana zasada jest niespełnialna.
                        ctx.model.AddBoolOr([])
                else:
                    v = ctx.model.NewBoolVar(f"opening_cov_{key}_d{day}_{fmt_minutes(a)}")
                    ctx.model.Add(sum(terms) + v >= 1)
                    violations.append(v * _slots(b - a))
    return violations


def add_max_staff_constraint(ctx, soft):
    """„Maks. obsada naraz”: w każdej chwili okna najwyżej N osób z placówki
    (N = Konfiguracja, domyślnie 1). Ręczne stałe przedziały zajmują miejsca
    w limicie, ale nigdy same go nie łamią (ręczny wpis wygrywa)."""
    model = get_model(ctx)
    if model is None:
        return []
    if ctx.trace is not None:
        ctx.trace.log_constraint(MAX_STAFF_POLICY, f"soft={soft}")

    violations = []
    for key, members in model.members.items():
        cap = model.max_staff(key)
        fixed = [(s, en) for e in members for _d, s, en in model.fixed.get(e, ())]
        by_window = {}
        for e in members:
            for d in model.days:
                for sid, sh in model.allowed(e, d).items():
                    by_window.setdefault(sh.window_day, []).append((sh.start, sh.end, e, d, sid))
        for day, shapes in sorted(by_window.items()):
            window = model.windows_by_location[key][day]
            intervals = [(s, en) for s, en, *_ in shapes] + fixed
            for a, b in _segments(window.start, window.end, intervals):
                terms = [ctx.x[e, d, sid] for s, en, e, d, sid in shapes if s <= a and b <= en]
                limit = max(cap - sum(1 for fs, fe in fixed if fs <= a and b <= fe), 0)
                if len(terms) <= limit:
                    continue
                if not soft:
                    ctx.model.Add(sum(terms) <= limit)
                else:
                    excess = ctx.model.NewIntVar(0, len(terms) - limit, f"max_staff_{key}_d{day}_{fmt_minutes(a)}")
                    ctx.model.Add(sum(terms) - limit <= excess)
                    violations.append(excess * (b - a))
    return violations


def add_opening_hours_no24h_constraint(ctx, soft):
    """„Nie chce 24h”: bez zmiany 24 h w sobotę/niedzielę (dzień okna) -
    ta sama zasada co add_duty_rotation_no24h_gate_constraint. Ręczny wpis
    wygrywa."""
    model = get_model(ctx)
    if model is None:
        return []
    violations = []
    for e in model.indices:
        emp = ctx.employees[e]
        if not _has_no24h_role(emp):
            continue
        for d in model.days:
            if ctx.schedule.get_day(emp, d).is_locked:
                continue
            for sid, sh in model.allowed(e, d).items():
                if sh.length < DAY or ctx.shop.weekday(sh.window_day) < 5:
                    continue
                if soft:
                    v = ctx.model.NewBoolVar(f"opening_no24h_e{e}_d{d}_{sid}")
                    ctx.model.Add(ctx.x[e, d, sid] <= v)
                    violations.append(v)
                else:
                    ctx.model.Add(ctx.x[e, d, sid] == 0)
    return violations


def _forbid_shapes(ctx, soft, predicate, label):
    model = get_model(ctx)
    if model is None:
        return []
    violations = []
    for e in model.indices:
        emp = ctx.employees[e]
        for d in model.days:
            if not predicate(emp, d, None) or ctx.schedule.get_day(emp, d).is_locked:
                continue
            for sid, sh in model.allowed(e, d).items():
                if not predicate(emp, d, sh):
                    continue
                if soft:
                    v = ctx.model.NewBoolVar(f"{label}_e{e}_d{d}_{sid}")
                    ctx.model.Add(ctx.x[e, d, sid] <= v)
                    violations.append(v)
                else:
                    ctx.model.Add(ctx.x[e, d, sid] == 0)
    return violations


def add_opening_hours_no_night_constraint(ctx, soft):
    """„Nie pracuje w godzinach nocnych”: bez zmian nachodzących na
    22:00-06:00. Ręczny wpis wygrywa (jak night_constraint.py)."""
    return _forbid_shapes(
        ctx, soft,
        lambda emp, d, sh: getattr(emp, "no_night", False) and (sh is None or _overlaps_night(sh.start, sh.end)),
        "opening_no_night",
    )


def add_opening_hours_no_afternoon_constraint(ctx, soft):
    """„Nie pracuje na popołudniu”: tylko zmiany zaczynające się przed 12:00
    (ten sam podział rano/popołudnie co typ zmiany „1”/„2”)."""
    return _forbid_shapes(
        ctx, soft,
        lambda emp, d, sh: getattr(emp, "no_afternoon", False) and (
            sh is None or sh.start - (d - 1) * DAY >= AFTERNOON_START
        ),
        "opening_no_afternoon",
    )


def prefer_full_day_terms(ctx):
    """Człon celu: lekka kara za każdą połówkę doby (cała doba, gdy się da)."""
    model = get_model(ctx)
    if model is None:
        return []
    return [
        PREFER_FULL_DAY_WEIGHT * ctx.x[e, d, sid]
        for e in model.indices
        for d in model.days
        for sid, sh in model.allowed(e, d).items()
        if sh.kind in (KIND_HALF_A, KIND_HALF_B)
    ]
