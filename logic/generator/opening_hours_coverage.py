"""Obłożenie godzin otwarcia placówek BEZ rotacji 24/7 dla profilu Ochrona
(decyzja użytkownika 2026-09-28, audyt generatora przed wydaniem).

Przed tą zmianą placówka Ochrony z godzinami z edytora tygodnia (nie 24/7)
nie miała ŻADNEJ reguły obsady - generator przydzielał tam zmiany tylko pod
godziny etatu - a do tego:

- sztywna zmiana nocna 22:00-06:00 (LocationConfig.get_night_shift_hours)
  włączała się dla każdej placówki, której godziny choć trochę nachodzą na
  22:00-06:00 (np. do 22:45), więc ludzie pracowali ok. 7 h po zamknięciu;
- zmiany przesunięte od otwarcia/zamknięcia (START/END) wychodziły poza
  godziny otwarcia przy krótkich dniach (np. 10:00-18:00: 10:45-19:15);
- doby 00:00-23:45 nie dało się pokryć (zmiany zakotwiczone przy otwarciu/
  zamknięciu zostawiają lukę w środku dnia);
- ręczny wpis niepasujący do żadnego wzorca zmiany był dla generatora
  niewidoczny (nie liczył się do obsady, odpoczynku, dni pod rząd, godzin).

"Model godzin otwarcia" dla tych pracowników:

1. Brak sztywnej nocki (SHIFT_NIGHT zawsze 0).
2. Zwykły dzień: OPEN i CLOSE jak dotąd; warianty START/END tylko gdy
   mieszczą się w godzinach otwarcia (decyzja użytkownika: "warianty
   przesunięte w godzinach").
3. Doba (otwarcie 00:00, zamknięcie 23:45 lub później): wyłącznie kolejne
   zmiany od 00:00 o długości zmiany standardowej (kafelki
   ROUND_CLOCK_SHIFTS, np. 00-08, 08-16, 16-24) - bez sztywnej nocki.
4. Ręczny wpis pasujący DOKŁADNIE (początek i koniec) do dozwolonego kształtu
   zmiany tego dnia = ta zmiana; każdy inny = stały przedział: liczy się do
   obłożenia, godzin, odpoczynku i dni pod rząd, a generator nie dokłada
   temu pracownikowi tego dnia żadnej zmiany.
5. Zasada "Obłożenie godzin otwarcia" (OPENING_HOURS_COVERAGE_POLICY,
   domyślnie Wymagana): w każdym kwadransie godzin otwarcia placówki co
   najmniej 1 osoba z tej placówki.

Profil Dino i pozostałe profile custom - bez zmian (decyzja użytkownika:
błędy Dino tylko raportowane, patrz raport audytu).
"""

from datetime import datetime

from logic.generator.round_clock_constraint import (
    round_clock_tile_count,
    round_clock_tile_spacing_minutes,
)
from logic.utils.time_utils import get_effective_daily_hours

DAY = 24 * 60
SLOT = 15
MIN_REST_MINUTES = 11 * 60
FULL_DAY_CLOSE_MINUTES = 23 * 60 + 45

OPENING_HOURS_COVERAGE_POLICY = "opening_hours_coverage"
OPENING_HOURS_COVERAGE_LABEL = "Obłożenie godzin otwarcia"
OPENING_HOURS_COVERAGE_WEIGHT = 5000


def _profiles():
    from model.business_profile import DEFAULT_OCHRONA_PROFILE_KEY
    return frozenset({DEFAULT_OCHRONA_PROFILE_KEY})


def profile_uses_opening_hours_model(business_type) -> bool:
    return business_type in _profiles()


def uses_opening_hours_model(shop) -> bool:
    return profile_uses_opening_hours_model(getattr(shop, "business_type", None))


def is_regular_location(location_view) -> bool:
    """Placówka z godzinami otwarcia (bez rotacji służby i rotacji całodobowej)."""
    return not location_view.get_duty_rotation() and not location_view.get_round_clock_start_hour()


def _minutes(value: str) -> int:
    t = datetime.strptime(value, "%H:%M")
    return t.hour * 60 + t.minute


def _fmt(minute_of_day: int) -> str:
    minute_of_day %= DAY
    return f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"


def day_window(location_view, day):
    """(start, end) godzin otwarcia w minutach od północy dnia `day` (end >
    start; doba 00:00-23:45 => end = 24:00) albo None, gdy zamknięte."""
    hours = location_view.get_open_hours_for_day(day)
    if not hours:
        return None
    start, end = _minutes(hours[0]), _minutes(hours[1])
    if start == 0 and end >= FULL_DAY_CLOSE_MINUTES:
        return 0, DAY
    if end <= start:
        end += DAY
    return start, end


def is_full_day(window) -> bool:
    return window is not None and window == (0, DAY)


def tile_length_minutes(emp, shop) -> int:
    """Długość kafelka doby dla pracownika - efektywne godziny, ale nie
    dłużej niż odstęp między kafelkami (żeby doba dzieliła się bez nakładek
    i bez wychodzenia poza północ, także przy "8h 30 min")."""
    eff = int(get_effective_daily_hours(emp, shop) * 60)
    return min(eff, round_clock_tile_spacing_minutes(shop.standard_daily_hours))


class OpeningHoursModel:
    """Dozwolone kształty zmian (na osi miesiąca), ręczne stałe przedziały i
    dopasowania ręcznych wpisów - liczone raz na generowanie."""

    def __init__(self, ctx):
        self.shop = ctx.shop
        self.days = list(ctx.days)
        self.employees = ctx.employees
        self.indices = [
            e for e, emp in enumerate(ctx.employees)
            if is_regular_location(ctx.shop.get_location(emp))
        ]
        self.index_set = set(self.indices)
        self.n_tiles = round_clock_tile_count(ctx.shop.standard_daily_hours)
        self.spacing = round_clock_tile_spacing_minutes(ctx.shop.standard_daily_hours)
        self.tile_ids = list(ctx.round_clock_shifts[: self.n_tiles]) if ctx.round_clock_shifts else []

        self.windows = {}      # (e, d) -> {shift_id: (abs_start, abs_end)}
        self.fixed = {}        # e -> [(d, abs_start, abs_end)]
        self.manual_shift = {}  # (e, d) -> shift_id (dokładnie dopasowany ręczny wpis)
        self.manual_blocked = set()  # (e, d) - dzień zablokowany bez zmiany z generatora

        for e in self.indices:
            emp = ctx.employees[e]
            location = ctx.shop.get_location(emp)
            eff = int(get_effective_daily_hours(emp, ctx.shop) * 60)
            tile_len = tile_length_minutes(emp, ctx.shop)
            for d in self.days:
                self.windows[(e, d)] = self._day_shapes(ctx, location, d, eff, tile_len)
            self._resolve_manual(ctx, e, emp)

    # ------------------------------------------------------------------

    def _day_shapes(self, ctx, location, d, eff, tile_len):
        window = day_window(location, d)
        if window is None:
            return {}
        base = (d - 1) * DAY
        if is_full_day(window):
            return {
                sid: (base + i * self.spacing, base + i * self.spacing + tile_len)
                for i, sid in enumerate(self.tile_ids)
            }
        start, end = window
        shapes = {
            ctx.shift_open: (base + start, base + start + eff),
            ctx.shift_close: (base + end - eff, base + end),
        }
        for sid, offset in ctx.start_shift_map.items():
            if start + offset + eff <= end:
                shapes[sid] = (base + start + offset, base + start + offset + eff)
        for sid, offset in ctx.end_shift_map.items():
            if end - offset - eff >= start:
                shapes[sid] = (base + end - offset - eff, base + end - offset)
        return shapes

    def _resolve_manual(self, ctx, e, emp):
        schedule = ctx.schedule
        for d in self.days:
            ds = schedule.get_day(emp, d)
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
            match = next((sid for sid, w in self.windows[(e, d)].items() if w == (start, end)), None)
            if match is not None:
                self.manual_shift[(e, d)] = match
            else:
                self.fixed.setdefault(e, []).append((d, start, end))
                self.manual_blocked.add((e, d))

    # ------------------------------------------------------------------

    def fixed_days(self, e):
        return {d for d, _s, _e in self.fixed.get(e, ())}

    def fixed_minutes(self, emp):
        e = self._index_of(emp)
        if e is None:
            return 0
        return sum(end - start for _d, start, end in self.fixed.get(e, ()))

    def duration_overrides(self, emp):
        """Minuty kafelków doby tego pracownika (zamiast efektywnych godzin)."""
        if self._index_of(emp) is None:
            return {}
        tile_len = tile_length_minutes(emp, self.shop)
        return {sid: tile_len for sid in self.tile_ids}

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


# ---------------------------------------------------------------------------
# Constrainty
# ---------------------------------------------------------------------------

def add_opening_hours_shape_constraint(ctx) -> None:
    """Zawsze twarde (fakt strukturalny, jak bramy rotacji): tylko dozwolone
    kształty zmian tego dnia + ręczne wpisy (dopasowane/stałe)."""
    model = get_model(ctx)
    if model is None:
        return
    if ctx.trace is not None:
        ctx.trace.log_constraint("opening_hours_shape", "allowed shift shapes for regular locations (Ochrona)")

    morning = {ctx.shift_open, *ctx.start_shift_map.keys()}
    afternoon = {ctx.shift_close, *ctx.end_shift_map.keys()}

    for e in model.indices:
        emp = ctx.employees[e]
        for d in model.days:
            allowed = model.windows[(e, d)]
            forced = model.manual_shift.get((e, d))
            if (e, d) in model.manual_blocked:
                allowed_ids = set()
            elif forced is not None:
                allowed_ids = {forced}
                ctx.model.Add(ctx.x[e, d, forced] == 1)
            else:
                allowed_ids = set(allowed)
                shift_class = getattr(ctx.schedule.get_day(emp, d), "shift_class", None)
                if shift_class in ("1", "2") and allowed_ids:
                    if set(model.tile_ids) & allowed_ids:
                        wanted = {
                            sid for sid in allowed_ids
                            if ((allowed[sid][0] % DAY) < 12 * 60) == (shift_class == "1")
                        }
                    else:
                        wanted = allowed_ids & (morning if shift_class == "1" else afternoon)
                    if wanted:
                        allowed_ids = wanted
                        ctx.model.Add(sum(ctx.x[e, d, s] for s in wanted) == 1)
            for s in ctx.all_shifts:
                if s not in allowed_ids:
                    ctx.model.Add(ctx.x[e, d, s] == 0)


def add_opening_hours_rest_constraint(ctx, soft):
    """Odpoczynek 11h dla par, których nie zna add_rest_11h_constraint:
    kafelki doby (z każdą zmianą sąsiedniego dnia), ręczne stałe przedziały
    (z każdą zmianą w ciągu 2 dni) i pamięć poprzedniego miesiąca wobec
    kafelków dnia 1."""
    model = get_model(ctx)
    if model is None:
        return []
    violations = []
    tile_set = set(model.tile_ids)

    def forbid_pair(e, d1, s1, d2, s2, label):
        if not soft:
            ctx.model.Add(ctx.x[e, d1, s1] + ctx.x[e, d2, s2] <= 1)
        else:
            v = ctx.model.NewBoolVar(label)
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
        for d in model.days:
            d_next = d + 1
            if (e, d_next) not in model.windows:
                continue
            for s1, (_a1, end1) in model.windows[(e, d)].items():
                for s2, (start2, _b2) in model.windows[(e, d_next)].items():
                    if s1 not in tile_set and s2 not in tile_set:
                        continue  # zwykłe pary pilnuje add_rest_11h_constraint
                    if start2 - end1 < MIN_REST_MINUTES:
                        forbid_pair(e, d, s1, d_next, s2, f"opening_rest_e{e}_d{d}_{s1}_{s2}")

        for fixed_day, f_start, f_end in model.fixed.get(e, ()):
            for d in model.days:
                if d == fixed_day or abs(d - fixed_day) > 2:
                    continue
                for s, (w_start, w_end) in model.windows[(e, d)].items():
                    overlaps = w_start < f_end and f_start < w_end
                    too_close = (
                        (w_start >= f_end and w_start - f_end < MIN_REST_MINUTES)
                        or (w_end <= f_start and f_start - w_end < MIN_REST_MINUTES)
                    )
                    if overlaps or too_close:
                        forbid_one(e, d, s, f"opening_rest_fixed_e{e}_d{d}_{s}")

        carry = ctx.schedule.get_previous_month_end_shift(ctx.employees[e]) if model.days else None
        if carry is not None:
            day1 = model.days[0]
            end_prev = _minutes(carry.end) - (0 if carry.crosses_midnight else DAY)
            for s, (w_start, _w_end) in model.windows[(e, day1)].items():
                if s in tile_set and w_start - end_prev < MIN_REST_MINUTES:
                    forbid_one(e, day1, s, f"opening_rest_prevmonth_e{e}_{s}")

    return violations


def add_opening_hours_coverage_constraint(ctx, soft):
    """Co najmniej 1 osoba z placówki w każdym kwadransie jej godzin
    otwarcia (ręczne stałe przedziały też się liczą)."""
    model = get_model(ctx)
    if model is None:
        return []
    if ctx.trace is not None:
        ctx.trace.log_constraint(OPENING_HOURS_COVERAGE_POLICY, f"soft={soft}")

    violations = []
    by_location = {}
    for e in model.indices:
        by_location.setdefault(ctx.employees[e].location_key or "", []).append(e)

    for location_key, indices in by_location.items():
        location = ctx.shop.get_location(ctx.employees[indices[0]])
        fixed = [(s, en) for e in indices for _d, s, en in model.fixed.get(e, ())]
        for d in model.days:
            window = day_window(location, d)
            if window is None:
                continue
            base = (d - 1) * DAY
            t = base + window[0]
            end = base + window[1]
            while t < end:
                if any(s <= t < en for s, en in fixed):
                    t += SLOT
                    continue
                terms = [
                    ctx.x[e, dd, sid]
                    for e in indices
                    for dd in (d - 1, d)
                    if (e, dd) in model.windows
                    for sid, (ws, we) in model.windows[(e, dd)].items()
                    if ws <= t < we
                ]
                label = f"opening_cov_{location_key}_d{d}_{_fmt(t - base)}"
                if not soft:
                    if terms:
                        ctx.model.Add(sum(terms) >= 1)
                    else:
                        # Nikt z placówki nie może tu pracować (np. wszyscy
                        # na urlopie) - Wymagana zasada jest niespełnialna.
                        ctx.model.AddBoolOr([])
                else:
                    v = ctx.model.NewBoolVar(label)
                    ctx.model.Add(sum(terms) + v >= 1)
                    violations.append(v)
                t += SLOT
    return violations


# ---------------------------------------------------------------------------
# Zapis wyniku
# ---------------------------------------------------------------------------

def tile_hours_for_assignment(shop, emp, day, tile_index):
    """(start, end) "HH:MM" kafelka doby do zapisu w grafiku albo None, gdy
    ten dzień pracownika nie jest dobą modelu godzin otwarcia."""
    if not uses_opening_hours_model(shop):
        return None
    location = shop.get_location(emp)
    if not is_regular_location(location) or not is_full_day(day_window(location, day)):
        return None
    spacing = round_clock_tile_spacing_minutes(shop.standard_daily_hours)
    start = tile_index * spacing
    return _fmt(start), _fmt(start + tile_length_minutes(emp, shop))

