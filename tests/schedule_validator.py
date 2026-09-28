"""Niezależny walidator wygenerowanego grafiku (audyt przed wydaniem).

CONFIGURATION -> GENERATOR -> GENERATED SCHEDULE -> VALIDATOR -> PASS / VIOLATIONS

Walidator celowo NIE importuje niczego z logic/generator/ - wszystkie
oczekiwania liczy od zera z surowej konfiguracji (ShopConfig/LocationConfig/
Employee/DaySchedule) i z rzeczywistego wyniku (godziny zapisane w komórkach
grafiku), na jednej osi czasu całego miesiąca (minuty od północy dnia 1).
Dzięki temu błąd w generatorze (np. zgubione ustawienie, zła interpretacja
godzin przez północ) nie może się tu "zamaskować" tym samym błędem.

Każde naruszenie ma `rule` - nazwę polityki z ShopConfig.constraint_policies
(albo stałą regułę strukturalną, np. "closed_day"/"opening_hours"/
"preserve_input"), którą ocenia `evaluate()` względem trybu MANDATORY/
PREFERRED/DISABLED tej polityki.
"""

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

import holidays as _holidays

DAY = 24 * 60
SLOT = 15

DINO = "dino_retail"
# Profil Ochrony (model godzin otwarcia placówek bez rotacji 24/7, decyzja
# użytkownika 2026-09-28): "custom_ochrona" albo każdy profil custom z rolą
# "Nie chce 24h".
OCHRONA_PROFILE_KEY = "custom_ochrona"
NIE_CHCE_24H = "nie_chce_24h"
MAX_STAFF_KEY = "max_staff_at_once"


@dataclass
class Violation:
    rule: str
    message: str
    employee: str | None = None
    day: int | None = None
    # "generator" = błąd wyniku generatora; "input" = sprzeczność wyłącznie
    # między ręcznymi wpisami użytkownika (generator nie mógł tego zmienić).
    source: str = "generator"

    def as_dict(self):
        return {
            "rule": self.rule,
            "message": self.message,
            "employee": self.employee,
            "day": self.day,
            "source": self.source,
        }


@dataclass
class ValidationReport:
    violations: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def by_rule(self, rule):
        return [v for v in self.violations if v.rule == rule]

    def rules(self):
        return sorted({v.rule for v in self.violations})


# ---------------------------------------------------------------------------
# Pomocnicze: czas
# ---------------------------------------------------------------------------

def hm(value: str) -> int:
    h, m = value.split(":")
    return int(h) * 60 + int(m)


def fmt_abs(minute: int) -> str:
    day = minute // DAY + 1
    rest = minute % DAY
    return f"d{day} {rest // 60:02d}:{rest % 60:02d}"


def cell_interval(ds, day: int):
    """(abs_start, abs_end) zmiany z komórki dnia `day` albo None."""
    if ds.start is None or ds.end is None or ds.is_leave or ds.is_sick:
        return None
    start = (day - 1) * DAY + hm(ds.start)
    if ds.is_full_day:
        return start, start + DAY
    end = (day - 1) * DAY + hm(ds.end)
    if end <= start:
        end += DAY
    return start, end


def overlaps_daily_window(abs_start, abs_end, win_start, win_end):
    """Czy [abs_start, abs_end) dotyka codziennego okna [win_start, win_end)
    (minuty doby; okno może przechodzić przez północ)."""
    length = (win_end - win_start) % DAY or DAY
    first_day = abs_start // DAY - 1
    last_day = abs_end // DAY + 1
    for d in range(first_day, last_day + 1):
        ws = d * DAY + win_start
        we = ws + length
        if ws < abs_end and abs_start < we:
            return True
    return False


# ---------------------------------------------------------------------------
# Konfiguracja -> oczekiwania (liczone niezależnie od generatora)
# ---------------------------------------------------------------------------

class ExpectedConfig:
    def __init__(self, shop, *, gui_trade_sundays=True):
        from model.business_profile import get_custom_profile, get_profile

        self.shop = shop
        self.year = shop.year
        self.month = shop.month
        self.days_in_month = calendar.monthrange(shop.year, shop.month)[1]
        self.custom = get_custom_profile(shop.business_type)
        self.profile = get_profile(shop.business_type)
        self.is_dino = self.custom is None
        self.uses_trade_calendar = self.profile.uses_trade_calendar
        # Niedziele handlowe zaznaczone w Konfiguracji (ui/config_dialog.py
        # zapisuje je do ShopConfig.trade_sundays) - z punktu widzenia
        # użytkownika dotyczą każdej placówki projektu.
        self.gui_trade_sundays = gui_trade_sundays
        self.pl_holidays = {
            d.day for d in _holidays.country_holidays("PL", years=shop.year)
            if d.year == shop.year and d.month == shop.month
        }
        self._pl_all = set(_holidays.country_holidays("PL", years=[shop.year - 1, shop.year]))
        self.opening_model = self.custom is not None and (
            self.custom.key == OCHRONA_PROFILE_KEY
            or any(role.key == NIE_CHCE_24H for role in self.custom.roles)
        )
        self._opening_windows = {}

    def policy(self, name, default="DISABLED"):
        value = self.shop.constraint_policies.get(name)
        if value is None:
            return default
        return getattr(value, "value", value)

    def location(self, emp):
        return self.shop.locations.get(emp.location_key)

    def weekday(self, day):
        return calendar.weekday(self.year, self.month, day)

    def is_trade_day(self, day, loc):
        if not self.uses_trade_calendar:
            return True
        holidays_ = set(self.shop.public_holidays) | (set(loc.public_holidays) if loc else set())
        if day in holidays_:
            return False
        if self.weekday(day) == 6:
            sundays = set(loc.trade_sundays) if loc else set()
            if self.gui_trade_sundays:
                sundays |= set(self.shop.trade_sundays)
            return day in sundays
        return True

    def open_window(self, emp, day):
        """(abs_open, abs_close) albo None, gdy placówka pracownika jest tego
        dnia zamknięta. Tylko dla lokalizacji BEZ rotacji służby."""
        loc = self.location(emp)
        if loc is None:
            hours_map, overrides = self.shop.open_hours, self.shop.day_overrides
            closed_on_holidays = False
        else:
            hours_map, overrides = loc.open_hours, loc.day_overrides
            closed_on_holidays = loc.closed_on_public_holidays
        if not self.is_trade_day(day, loc):
            return None
        if day in overrides:
            start, end = overrides[day]
            if not (start and end):
                return None
            hours = (start, end)
        else:
            if closed_on_holidays and day in self.pl_holidays:
                return None
            hours = hours_map.get(self.weekday(day))
            if not hours or not hours[0] or not hours[1]:
                return None
        s = (day - 1) * DAY + hm(hours[0])
        e = (day - 1) * DAY + hm(hours[1])
        if hm(hours[0]) == 0 and hm(hours[1]) >= 23 * 60 + 45:
            e = day * DAY  # doba: 00:00-23:45 w GUI oznacza całą dobę
        if e <= s:
            e += DAY
        return s, e

    # ---- model godzin otwarcia (Ochrona, placówki bez rotacji) ----

    def is_regular(self, emp):
        loc = self.location(emp)
        if loc is None:
            return not self.shop.duty_rotation
        return not loc.duty_rotation and not (loc.is_24_7 and loc.round_clock_start_hour)

    def uses_opening_model(self, emp):
        return self.opening_model and self.is_regular(emp)

    def _day_hours(self, loc, day):
        """Godziny dnia bieżącego miesiąca (nadpisania, święta) albo None."""
        if loc is None:
            hours_map, overrides, closed_on_holidays = self.shop.open_hours, self.shop.day_overrides, False
        else:
            hours_map, overrides, closed_on_holidays = loc.open_hours, loc.day_overrides, loc.closed_on_public_holidays
        if not self.is_trade_day(day, loc):
            return None
        if day in overrides:
            start, end = overrides[day]
            return (start, end) if start and end else None
        if closed_on_holidays and day in self.pl_holidays:
            return None
        hours = hours_map.get(self.weekday(day))
        return hours if hours and hours[0] and hours[1] else None

    def _pattern_hours(self, loc, dt):
        """Godziny dnia poprzedniego miesiąca wg wzorca tygodnia."""
        hours_map = loc.open_hours if loc is not None else self.shop.open_hours
        if loc is not None and loc.closed_on_public_holidays and dt in self._pl_all:
            return None
        hours = hours_map.get(dt.weekday())
        return hours if hours and hours[0] and hours[1] else None

    @staticmethod
    def _span(hours):
        """(start, end, doba) w minutach dnia - okno >= 23:45 to doba 24 h."""
        start, end = hm(hours[0]), hm(hours[1])
        length = (end - start) % DAY or DAY
        if length >= DAY - SLOT:
            return start, start + DAY, True
        return start, start + length, False

    def opening_windows(self, location_key):
        """{dzień: (abs_start, abs_end, doba)} - okno dnia zaczyna się nie
        wcześniej niż skończyło się poprzednie (doba trwa wtedy 24 h od
        końca poprzedniego okna, np. pt 15-07 + sob 24h = sob 07-nd 07)."""
        if location_key in self._opening_windows:
            return self._opening_windows[location_key]
        loc = self.shop.locations.get(location_key)
        first = date(self.year, self.month, 1)
        last_end = None
        entries = [(-back, self._pattern_hours(loc, first - timedelta(days=back))) for back in range(7, 0, -1)]
        entries += [(day - 1, self._day_hours(loc, day)) for day in range(1, self.days_in_month + 1)]
        result = {}
        for offset, hours in entries:
            if not hours:
                continue
            s, e, doba = self._span(hours)
            s, e = offset * DAY + s, offset * DAY + e
            if last_end is not None and last_end > s:
                if doba:
                    e = last_end + DAY
                s = last_end
                if s >= e:
                    continue
            last_end = e if last_end is None else max(last_end, e)
            if offset >= 0:
                result[offset + 1] = (s, e, doba)
        self._opening_windows[location_key] = result
        return result

    def max_staff(self, emp):
        loc = self.location(emp)
        value = (loc.constraints if loc is not None else {}).get(MAX_STAFF_KEY)
        if value is None:
            value = self.shop.constraints.get(MAX_STAFF_KEY, 1)
        return max(1, int(value))

    # ---- rotacja służby 24/7 ----

    def rotation(self, emp):
        loc = self.location(emp)
        return loc.duty_rotation if loc is not None and loc.duty_rotation else None

    def duty_day_closed(self, loc, day):
        override = loc.day_overrides.get(day)
        if override is not None:
            return not (override[0] and override[1])
        return loc.closed_on_public_holidays and day in self.pl_holidays

    @staticmethod
    def pattern_keys(rotation, weekday):
        if rotation.get("only_12_24h") or weekday >= 5:
            return ("weekend_half_a", "weekend_half_b")
        return ("weekday_long", "weekday_short")

    @staticmethod
    def window(rotation, key):
        start = hm(rotation[key]["start"])
        if key == "weekend_full":
            return start, start + DAY
        end = hm(rotation[key]["end"])
        if end <= start:
            end += DAY
        return start, end

    def doba(self, rotation, day):
        """Doba rotacji zaczynająca się w dniu `day` - (abs_start, abs_end)."""
        def anchor(d):
            wd = calendar.weekday(self.year, self.month, d) if 1 <= d <= self.days_in_month else (
                (self.weekday(self.days_in_month) + (d - self.days_in_month)) % 7
            )
            return min(self.window(rotation, k)[0] for k in self.pattern_keys(rotation, wd))
        start = (day - 1) * DAY + anchor(day)
        end = day * DAY + anchor(day + 1)
        return start, end

    def standard_duty_windows(self, rotation, day):
        """Dozwolone kształty zmian rotacji zaczynających się w dniu `day`."""
        wd = self.weekday(day)
        keys = list(self.pattern_keys(rotation, wd))
        if rotation.get("only_12_24h") or wd >= 5:
            keys.append("weekend_full")
        base = (day - 1) * DAY
        return {key: tuple(base + v for v in self.window(rotation, key)) for key in keys}


# ---------------------------------------------------------------------------
# Walidacja
# ---------------------------------------------------------------------------

def _employees_by_location(schedule):
    groups = {}
    for emp in schedule.employees:
        groups.setdefault(emp.location_key, []).append(emp)
    return groups


def _cell_state(ds):
    return (ds.start, ds.end, ds.is_leave, ds.is_sick, ds.is_full_day)


def validate(schedule_before, schedule_after, shop, *, generation_succeeded=True, gui_trade_sundays=True):
    """Pełna walidacja wyniku. `schedule_before` = stan grafiku tuż przed
    kliknięciem "Generuj" (ręczne wpisy, urlopy, L4, blokady)."""
    cfg = ExpectedConfig(shop, gui_trade_sundays=gui_trade_sundays)
    report = ValidationReport()
    add = report.violations.append

    before_emps = {emp.id: emp for emp in schedule_before.employees}

    def before_cell(emp, day):
        emp_before = before_emps.get(emp.id)
        if emp_before is None:
            return None
        return schedule_before.get_day(emp_before, day)

    # ------------------------------------------------------------------
    # 0. Nieudane generowanie = grafik bez zmian
    # ------------------------------------------------------------------
    if not generation_succeeded:
        for emp in schedule_after.employees:
            for day in range(1, cfg.days_in_month + 1):
                b = before_cell(emp, day)
                a = schedule_after.get_day(emp, day)
                if b is not None and _cell_state(a) != _cell_state(b):
                    add(Violation(
                        "preserve_input", "grafik zmieniony mimo braku rozwiązania",
                        emp.display_name(), day,
                    ))
        return report

    # ------------------------------------------------------------------
    # 1. Zachowanie danych wejściowych (ręczne wpisy / urlop / L4)
    # ------------------------------------------------------------------
    manual = {}  # (emp.id, day) -> True dla komórek niezmienialnych przez generator
    for emp in schedule_after.employees:
        for day in range(1, cfg.days_in_month + 1):
            b = before_cell(emp, day)
            a = schedule_after.get_day(emp, day)
            if b is None:
                continue
            fixed = b.is_locked or b.is_leave or b.is_sick
            if emp.is_manager and cfg.is_dino:
                # Kierowniczka: sztywny wzorzec nakładany przez generator
                # (logic/manager_schedule.py) - traktujemy jak ręczny wpis.
                fixed = fixed or a.is_locked
            if fixed:
                manual[(emp.id, day)] = True
                if (b.is_locked or b.is_leave or b.is_sick) and _cell_state(a) != _cell_state(b):
                    add(Violation(
                        "preserve_input",
                        f"komórka ręczna/urlop/L4 zmieniona: przed={_cell_state(b)} po={_cell_state(a)}",
                        emp.display_name(), day,
                    ))
            if b.is_day_off and not a.is_empty():
                add(Violation("preserve_input", "zmiana w dniu oznaczonym jako wolne", emp.display_name(), day))

    # ------------------------------------------------------------------
    # 2. Interwały pracy (na osi miesiąca)
    # ------------------------------------------------------------------
    intervals = {}  # emp.id -> [(start, end, day, is_manual, is_full_day)]
    for emp in schedule_after.employees:
        rows = []
        for day in range(1, cfg.days_in_month + 1):
            ds = schedule_after.get_day(emp, day)
            iv = cell_interval(ds, day)
            if iv is None:
                continue
            rows.append((iv[0], iv[1], day, bool(manual.get((emp.id, day))), ds.is_full_day))
        intervals[emp.id] = rows

    # ------------------------------------------------------------------
    # 3. Dni zamknięte i godziny otwarcia (lokalizacje bez rotacji 24/7)
    # ------------------------------------------------------------------
    loc_manual_bounds = {}
    for emp in schedule_after.employees:
        for start, end, _day, is_manual, _full in intervals[emp.id]:
            if is_manual:
                loc_manual_bounds.setdefault(emp.location_key, set()).update((start, end))
    for emp in schedule_after.employees:
        rotation = cfg.rotation(emp)
        for start, end, day, is_manual, full in intervals[emp.id]:
            if is_manual:
                continue
            if cfg.uses_opening_model(emp):
                windows = cfg.opening_windows(emp.location_key)
                container = next(
                    ((wd, w) for wd, w in windows.items() if w[0] <= start and end <= w[1]), None
                )
                if container is None:
                    touching = any(w[0] < end and start < w[1] for w in windows.values())
                    add(Violation(
                        "opening_hours" if touching else "closed_day",
                        f"zmiana {fmt_abs(start)}-{fmt_abs(end)} poza oknami placówki",
                        emp.display_name(), day,
                    ))
                    continue
                window_day, (ws, we, doba) = container
                bounds = {ws, we} | ({ws + DAY // 2} if doba else set()) | loc_manual_bounds.get(emp.location_key, set())
                if start not in bounds or end not in bounds:
                    add(Violation(
                        "opening_shape",
                        f"zmiana {fmt_abs(start)}-{fmt_abs(end)} nie jest całym oknem {fmt_abs(ws)}-{fmt_abs(we)}"
                        + (" ani połówką doby" if doba else ""),
                        emp.display_name(), day,
                    ))
                if full and emp.custom_roles.get(NIE_CHCE_24H) and cfg.weekday(window_day) >= 5:
                    add(Violation(
                        "duty_rotation_no24h", f"zmiana 24h w weekend dla osoby \"nie chce 24h\" ({fmt_abs(start)})",
                        emp.display_name(), day,
                    ))
                if emp.no_night and overlaps_daily_window(start, end, 22 * 60, 6 * 60):
                    add(Violation("no_night", f"zmiana {fmt_abs(start)}-{fmt_abs(end)} w porze nocnej", emp.display_name(), day))
                if emp.no_afternoon and start - (day - 1) * DAY >= 12 * 60:
                    add(Violation("no_afternoon", f"zmiana {fmt_abs(start)}-{fmt_abs(end)} zaczyna się po południu", emp.display_name(), day))
                continue
            if rotation:
                loc = cfg.location(emp)
                # Zmiana należy do doby, w której się zaczyna (kawałek doby
                # dnia poprzedniego po północy trafia do komórki następnego
                # dnia - także gdy ten jest zamknięty).
                doba_day = day
                if day > 1 and start < cfg.doba(rotation, day)[0]:
                    doba_day = day - 1
                if cfg.duty_day_closed(loc, doba_day):
                    add(Violation("closed_day", f"zmiana rotacji w dzień zamknięty ({fmt_abs(start)})", emp.display_name(), day))
                continue
            window = cfg.open_window(emp, day)
            if window is None:
                add(Violation("closed_day", f"zmiana {fmt_abs(start)}-{fmt_abs(end)} w dzień zamknięty placówki", emp.display_name(), day))
                continue
            anchored_long = (start == window[0] or end == window[1]) and (end - start) > (window[1] - window[0])
            if (start < window[0] or end > window[1]) and not anchored_long:
                is_auto_night = (start % DAY, end - start) == (22 * 60, 8 * 60)
                add(Violation(
                    "night_outside_hours" if is_auto_night else "opening_hours",
                    f"zmiana {fmt_abs(start)}-{fmt_abs(end)} poza godzinami otwarcia {fmt_abs(window[0])}-{fmt_abs(window[1])}",
                    emp.display_name(), day,
                ))

    # ------------------------------------------------------------------
    # 4. Odpoczynek (11h; po zmianie 24h rotacji: (N-1)x24h, min. 24h)
    # ------------------------------------------------------------------
    loc_groups = _employees_by_location(schedule_after)
    for emp in schedule_after.employees:
        rows = sorted(intervals[emp.id])
        carry = schedule_after.get_previous_month_end_shift(emp)
        if carry is not None:
            end_prev = hm(carry.end) - (0 if carry.crosses_midnight else DAY)
            rows = [(end_prev - 1, end_prev, 0, True, False)] + rows
        rotation = cfg.rotation(emp)
        capable = None
        long_rest = bool(rotation) or cfg.uses_opening_model(emp)
        if long_rest:
            capable = sum(1 for other in loc_groups.get(emp.location_key, []) if not other.custom_roles.get(NIE_CHCE_24H))
        for (s1, e1, d1, m1, full1), (s2, e2, d2, m2, _f2) in zip(rows, rows[1:]):
            required = 11 * 60
            if long_rest and full1:
                required = 24 * 60 * max((capable or 0) - 1, 1)
            gap = s2 - e1
            if gap < required:
                add(Violation(
                    "rest_11h",
                    f"odpoczynek {gap / 60:.2f}h < {required / 60:.0f}h ({fmt_abs(e1)} -> {fmt_abs(s2)})",
                    emp.display_name(), d2,
                    source="input" if (m1 and m2) else "generator",
                ))

    # ------------------------------------------------------------------
    # 5. Dni pod rząd
    # ------------------------------------------------------------------
    for emp in schedule_after.employees:
        loc = cfg.location(emp)
        limit = (loc.constraints if loc else shop.constraints).get("max_consecutive_days", shop.constraints.get("max_consecutive_days", 4))
        worked = {d for _s, _e, d, _m, _f in intervals[emp.id]}
        manual_days = {d for _s, _e, d, m, _f in intervals[emp.id] if m}
        streak = []
        for day in range(1, cfg.days_in_month + 2):
            if day in worked:
                streak.append(day)
                continue
            if len(streak) > limit:
                add(Violation(
                    "max_consecutive",
                    f"{len(streak)} dni pod rząd (limit {limit}): dni {streak[0]}-{streak[-1]}",
                    emp.display_name(), streak[0],
                    source="input" if all(d in manual_days for d in streak[: limit + 1]) else "generator",
                ))
            streak = []

    # ------------------------------------------------------------------
    # 6. Godziny miesięczne (cel = nominał*etat - urlop/L4 w dziennym wymiarze)
    # ------------------------------------------------------------------
    nominal = _nominal_minutes(shop, cfg)
    for emp in schedule_after.employees:
        total = sum(e - s for s, e, _d, _m, _f in intervals[emp.id])
        absent = sum(
            1 for day in range(1, cfg.days_in_month + 1)
            if schedule_after.get_day(emp, day).is_leave or schedule_after.get_day(emp, day).is_sick
        )
        daily = _effective_daily_minutes(emp, shop)
        target = max(0, int(nominal * emp.employment_fraction - absent * daily))
        report.metrics.setdefault("hours", {})[emp.display_name()] = {"total": total, "target": target}
        upper = target + emp.daily_hours * 60
        if total < target or total > upper:
            add(Violation(
                "monthly_hours",
                f"suma {total / 60:.2f}h poza [{target / 60:.2f}h, {upper / 60:.2f}h]",
                emp.display_name(),
            ))

    # ------------------------------------------------------------------
    # 7. Reguły Dino (obsada otwarcia/zamknięcia, mięso, no_night/no_afternoon)
    # ------------------------------------------------------------------
    if cfg.is_dino:
        _validate_dino(cfg, schedule_after, intervals, report)

    # ------------------------------------------------------------------
    # 8. Rotacja służby 24/7 (obłożenie minuta po minucie)
    # ------------------------------------------------------------------
    _validate_duty(cfg, schedule_after, intervals, manual, report)

    # ------------------------------------------------------------------
    # 8b. Obłożenie godzin otwarcia placówek bez rotacji (profil Ochrona)
    # ------------------------------------------------------------------
    if cfg.opening_model:
        _validate_opening_coverage(cfg, schedule_after, intervals, report)

    # ------------------------------------------------------------------
    # 9. Reguły profili custom (min. N osób z rolą, zakaz godzin dla roli)
    # ------------------------------------------------------------------
    if cfg.custom is not None:
        _validate_custom_rules(cfg, schedule_after, intervals, report)

    return report


def _effective_daily_minutes(emp, shop):
    if emp.employment_fraction == 1.01:
        hours = 8.0
    elif shop.constraints.get("force_fulltime_845", False) and emp.employment_fraction == 1.0:
        hours = 8.5
    else:
        hours = shop.standard_daily_hours * emp.employment_fraction
    minutes = int(hours * 60)
    return (minutes // 15) * 15


def _nominal_minutes(shop, cfg):
    workdays = 0
    saturday_holidays = 0
    for d in range(1, cfg.days_in_month + 1):
        wd = cfg.weekday(d)
        holiday = d in cfg.pl_holidays or d in shop.public_holidays
        if wd < 5:
            if not holiday:
                workdays += 1
        elif wd == 5 and d in cfg.pl_holidays:
            saturday_holidays += 1
    return (workdays - saturday_holidays) * shop.standard_daily_hours * 60


def _validate_dino(cfg, schedule, intervals, report):
    add = report.violations.append
    shop = cfg.shop
    min_open = shop.constraints.get("min_open_staff", 3)
    min_close = shop.constraints.get("min_close_staff", 3)
    by_loc = _employees_by_location(schedule)
    per_day = {}

    for loc_key, emps in by_loc.items():
        if cfg.rotation(emps[0]):
            continue
        if cfg.shop.locations.get(loc_key) and cfg.shop.locations[loc_key].round_clock_start_hour and cfg.shop.locations[loc_key].is_24_7:
            continue
        for day in range(1, cfg.days_in_month + 1):
            window = cfg.open_window(emps[0], day)
            if window is None:
                continue
            open_t, close_t = window
            openers = [e for e in emps if any(s == open_t for s, _e, _d, _m, _f in intervals[e.id])]
            closers = [e for e in emps if any(en == close_t for _s, en, _d, _m, _f in intervals[e.id])]
            per_day.setdefault(day, {})[loc_key] = (len(openers), len(closers))

            if len(openers) < min_open:
                add(Violation("open", f"[{loc_key}] na otwarciu {len(openers)} os. < min {min_open}", day=day))
            if not any(e.is_opener for e in openers):
                add(Violation("open", f"[{loc_key}] brak pracownika otwarcia (is_opener) na otwarciu", day=day))
            if not any(e.is_meat or e.is_meat_light for e in openers):
                add(Violation("open", f"[{loc_key}] brak mięsa na otwarciu", day=day))
            if len(closers) < min_close:
                add(Violation("close", f"[{loc_key}] na zamknięciu {len(closers)} os. < min {min_close}", day=day))
            if not any(e.is_meat or e.is_meat_light for e in closers):
                add(Violation("close", f"[{loc_key}] brak mięsa na zamknięciu", day=day))
            # Generator (constraints_staff.add_fixed_staff_shift_constraints)
            # wymaga osoby z "otwarciem" także na zamknięciu.
            if not any(e.is_opener for e in closers):
                add(Violation("close", f"[{loc_key}] brak pracownika otwarcia (is_opener) na zamknięciu", day=day))

            # "Mięso na zmianach" (policy "meat", semantyka trybu MANDATORY w
            # generatorze): jeśli tego dnia jest choć jedna zmiana spoza
            # otwarcia/zamknięcia, co najmniej jedna z nich ma mięso.
            middle = [
                e for e in emps
                for s, en, d, _m, _f in intervals[e.id]
                if d == day and s != open_t and en != close_t
            ]
            if middle and not any(e.is_meat or e.is_meat_light for e in middle):
                add(Violation("meat", f"[{loc_key}] brak mięsa na zmianach środkowych", day=day))

            # Mięso przez cały dzień (kwadrans po kwadransie): is_meat, a
            # is_meat_light maks. 60 min/dzień/osobę.
            gaps = []
            light_budget = {e.id: 60 for e in emps if e.is_meat_light}
            t = open_t
            while t < close_t:
                covered = any(
                    s <= t < en for e in emps if e.is_meat for s, en, _d, _m, _f in intervals[e.id]
                )
                if not covered:
                    for e in emps:
                        if e.id in light_budget and light_budget[e.id] >= SLOT and any(
                            s <= t < en for s, en, _d, _m, _f in intervals[e.id]
                        ):
                            light_budget[e.id] -= SLOT
                            covered = True
                            break
                if not covered:
                    gaps.append(t)
                t += SLOT
            if gaps:
                add(Violation(
                    "meat_coverage",
                    f"[{loc_key}] brak mięsa w {len(gaps)} kwadransach (pierwszy {fmt_abs(gaps[0])})",
                    day=day,
                ))

    report.metrics["open_close_per_day"] = per_day

    for emp in schedule.employees:
        for s, e, day, is_manual, _f in intervals[emp.id]:
            if is_manual:
                continue
            if emp.no_night and overlaps_daily_window(s, e, 22 * 60, 6 * 60):
                add(Violation("no_night", f"zmiana {fmt_abs(s)}-{fmt_abs(e)} w porze nocnej", emp.display_name(), day))
            if emp.no_afternoon:
                window = cfg.open_window(emp, day)
                if window is not None and s != window[0] and not (0 < s - window[0] <= 90 and (s - window[0]) % 15 == 0):
                    add(Violation("no_afternoon", f"zmiana {fmt_abs(s)}-{fmt_abs(e)} nie jest poranna", emp.display_name(), day))


def _validate_duty(cfg, schedule, intervals, manual, report):
    add = report.violations.append
    by_loc = _employees_by_location(schedule)
    coverage_metrics = {}
    for loc_key, emps in by_loc.items():
        loc = cfg.shop.locations.get(loc_key)
        rotation = loc.duty_rotation if loc is not None else None
        if not rotation:
            continue

        has_manual_work = any(m for e in emps for _s, _e, _d, m, _f in intervals[e.id])

        # Kształty zmian i zakaz 24h
        for emp in emps:
            for s, e, day, is_manual, is_full in intervals[emp.id]:
                if is_manual:
                    continue
                allowed = cfg.standard_duty_windows(rotation, day)
                if (s, e) not in allowed.values() and not has_manual_work:
                    add(Violation("duty_shape", f"zmiana {fmt_abs(s)}-{fmt_abs(e)} nie pasuje do rotacji", emp.display_name(), day))
                if is_full and emp.custom_roles.get(NIE_CHCE_24H) and (
                    cfg.weekday(day) >= 5 if 1 <= day <= cfg.days_in_month else True
                ):
                    add(Violation("duty_rotation_no24h", f"zmiana 24h dla osoby \"nie chce 24h\" ({fmt_abs(s)})", emp.display_name(), day))

        # Obłożenie minuta po minucie (w kwadransach - wszystkie godziny
        # rotacji i ręcznych wpisów są w pełnych kwadransach w UI)
        events = []
        for emp in emps:
            for s, e, _d, m, _f in intervals[emp.id]:
                events.append((s, e, m))
        gaps = 0
        doubles = 0
        manual_doubles = 0
        first_problem = None
        for day in range(1, cfg.days_in_month + 1):
            closed = cfg.duty_day_closed(loc, day)
            start, end = cfg.doba(rotation, day)
            t = start
            while t < end:
                covering = [m for s, e, m in events if s <= t < e]
                count = len(covering)
                if not closed and count == 0:
                    gaps += 1
                    first_problem = first_problem or (day, t, count)
                elif count >= 2:
                    # dwa nakładające się RĘCZNE wpisy - sprzeczność danych
                    # wejściowych, generator nie może jej usunąć
                    if sum(covering) >= 2:
                        manual_doubles += 1
                    else:
                        doubles += 1
                        first_problem = first_problem or (day, t, count)
                t += SLOT
        coverage_metrics[loc_key] = {"gap_slots": gaps, "double_slots": doubles, "manual_double_slots": manual_doubles}
        if manual_doubles:
            add(Violation(
                "duty_rotation_coverage",
                f"[{loc_key}] nakładające się ręczne wpisy: {manual_doubles} kwadransów",
                source="input",
            ))
        if gaps:
            day, t, _c = first_problem if first_problem and first_problem[2] == 0 else (None, None, None)
            add(Violation(
                "duty_rotation_coverage",
                f"[{loc_key}] luka w obsadzie: {gaps} kwadransów bez nikogo" + (f" (np. {fmt_abs(t)})" if t is not None else ""),
                day=day,
            ))
        if doubles:
            add(Violation(
                "duty_rotation_coverage",
                f"[{loc_key}] podwójna obsada: {doubles} kwadransów z >=2 osobami",
            ))
    report.metrics["duty_coverage"] = coverage_metrics


def _validate_opening_coverage(cfg, schedule, intervals, report):
    """Placówki Ochrony bez rotacji: każdy kwadrans okien (do końca
    miesiąca) ma co najmniej 1 osobę; obsada naraz nie większa niż „Maks.
    obsada naraz” (ręczne wpisy zajmują miejsca, ale same nie łamią
    limitu)."""
    add = report.violations.append
    metrics = {}
    month_end = cfg.days_in_month * DAY
    for loc_key, emps in _employees_by_location(schedule).items():
        if not cfg.uses_opening_model(emps[0]):
            continue
        cap = cfg.max_staff(emps[0])
        events = [(s, e, m) for emp in emps for s, e, _d, m, _f in intervals[emp.id]]
        open_slots = set()
        for ws, we, _doba in cfg.opening_windows(loc_key).values():
            t = ws
            while t < min(we, month_end):
                open_slots.add(t)
                t += SLOT
        gaps, doubles, manual_doubles, over_cap = [], [], 0, []
        for t in sorted(open_slots):
            covering = [m for s, e, m in events if s <= t < e]
            if not covering:
                gaps.append(t)
            elif len(covering) >= 2:
                if sum(covering) >= 2:
                    manual_doubles += 1
                else:
                    doubles.append(t)
            generated = sum(1 for m in covering if not m)
            if generated > max(cap - (len(covering) - generated), 0):
                over_cap.append(t)
        metrics[loc_key] = {
            "open_slots": len(open_slots), "gap_slots": len(gaps),
            "double_slots": len(doubles), "manual_double_slots": manual_doubles,
            "first_double": fmt_abs(doubles[0]) if doubles else None,
            "max_staff": cap, "over_cap_slots": len(over_cap),
        }
        if gaps:
            add(Violation(
                "opening_hours_coverage",
                f"[{loc_key}] {len(gaps)} kwadransów godzin otwarcia bez nikogo (np. {fmt_abs(gaps[0])})",
                day=gaps[0] // DAY + 1,
            ))
        if over_cap:
            add(Violation(
                MAX_STAFF_KEY,
                f"[{loc_key}] {len(over_cap)} kwadransów z obsadą ponad limit {cap} (np. {fmt_abs(over_cap[0])})",
                day=over_cap[0] // DAY + 1,
            ))
    report.metrics["opening_coverage"] = metrics


def _validate_custom_rules(cfg, schedule, intervals, report):
    add = report.violations.append
    custom = cfg.custom
    for rule in custom.rules:
        key = custom.rule_policy_key(rule)
        role_emps = [e for e in schedule.employees if e.has_role(rule.role_key)]
        if rule.type == "min_staff_with_role":
            scope = rule.params.get("scope", "open")
            base_threshold = rule.params.get("min_count", 1)
            # Próg może być nadpisany per lokalizacja (LocationConfig.constraints[klucz reguły]).
            groups = {}
            for e in role_emps:
                loc = cfg.location(e)
                groups.setdefault((loc.constraints if loc else {}).get(key, base_threshold), []).append(e)
            for day in range(1, cfg.days_in_month + 1):
                if not role_emps:
                    if any(cfg.open_window(e, day) for e in schedule.employees):
                        add(Violation(key, f"brak osób z rolą {rule.role_key} (wymagane {base_threshold})", day=day))
                    continue
                for threshold, members in groups.items():
                    # dzień pomijany, gdy placówki wszystkich osób z grupy są zamknięte
                    open_emps = [(e, cfg.open_window(e, day)) for e in members]
                    open_emps = [(e, w) for e, w in open_emps if w is not None]
                    if not open_emps:
                        continue
                    count = 0
                    for e, w in open_emps:
                        for s, en, d, _m, _f in intervals[e.id]:
                            if d != day:
                                continue
                            if scope == "open" and s == w[0]:
                                count += 1
                            elif scope == "close" and en == w[1]:
                                count += 1
                            elif scope == "any_shift":
                                count += 1
                    if count < threshold:
                        add(Violation(key, f"rola {rule.role_key} [{scope}]: {count} < {threshold}", day=day))
        elif rule.type == "role_time_restriction":
            ws = rule.params.get("window_start_hour", 22) * 60
            we = rule.params.get("window_end_hour", 6) * 60
            for e in role_emps:
                for s, en, day, is_manual, _f in intervals[e.id]:
                    if not is_manual and overlaps_daily_window(s, en, ws, we):
                        add(Violation(key, f"rola {rule.role_key}: zmiana {fmt_abs(s)}-{fmt_abs(en)} w zakazanym oknie", e.display_name(), day))


# ---------------------------------------------------------------------------
# Ocena względem polityk
# ---------------------------------------------------------------------------

STRUCTURAL_RULES = ("preserve_input", "closed_day", "opening_hours", "opening_shape", "night_outside_hours", "duty_shape")


def evaluate(report, shop):
    """Dzieli naruszenia na: twarde (MANDATORY albo strukturalne - błąd
    krytyczny), miękkie (PREFERRED - dozwolone, ale raportowane),
    zignorowane (DISABLED) i sprzeczności samych danych wejściowych."""
    hard, soft, ignored, input_conflicts = [], [], [], []
    for v in report.violations:
        if v.source == "input":
            input_conflicts.append(v)
            continue
        if v.rule in STRUCTURAL_RULES:
            hard.append(v)
            continue
        policy = shop.constraint_policies.get(v.rule)
        policy = getattr(policy, "value", policy)
        if policy == "MANDATORY":
            hard.append(v)
        elif policy == "PREFERRED":
            soft.append(v)
        else:
            ignored.append(v)
    return {"hard": hard, "soft": soft, "ignored": ignored, "input": input_conflicts}
