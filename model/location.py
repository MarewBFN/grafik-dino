"""One location/obiekt within a multi-location project.

This is the data model only (Etap 3a of the location roadmap). It mirrors
the single-location fields ShopConfig already has (open_hours, trade_sundays,
public_holidays, day_overrides, min/max staffing) so a future generator/UI
pass can reuse the same shape - but nothing in logic/generator or ui reads
ShopConfig.locations yet. A project with no locations defined behaves
exactly as before this module existed.
"""

import calendar
from dataclasses import dataclass, field

DEFAULT_OPEN_HOURS = {
    0: ("05:30", "23:00"),
    1: ("05:30", "22:45"),
    2: ("05:30", "22:45"),
    3: ("05:30", "22:45"),
    4: ("05:30", "22:45"),
    5: ("05:30", "22:45"),
    6: ("05:30", "22:45"),
}

DEFAULT_LOCATION_CONSTRAINTS = {
    "min_open_staff": 3,
    "min_close_staff": 3,
    "max_consecutive_days": 4,
}


def normalize_night_shift(start: str | None, end: str | None) -> dict | None:
    """Shared validation for the (optional) night-shift window used by both
    LocationConfig and ShopConfig (Etap B of the night-shift plan). A None/
    empty pair clears the window; a single missing side or start == end is
    rejected the same way DaySchedule.set_hours() rejects an ambiguous
    zero-length shift. end < start is allowed on purpose - that's exactly
    what marks the window as crossing midnight.
    """
    if not start and not end:
        return None
    if not start or not end:
        raise ValueError("Zmiana nocna wymaga podania obu godzin (początku i końca)")
    if start == end:
        raise ValueError("Godzina początku i końca zmiany nocnej nie mogą być takie same")
    return {"start": start, "end": end}


_WEEKDAY_DUTY_PAIR_KEYS = {
    "weekday_long": "długiej zmiany w tygodniu",
    "weekday_short": "krótkiej zmiany w tygodniu",
}
_WEEKEND_DUTY_PAIR_KEYS = {
    "weekend_half_a": "pierwszej połowy doby weekendowej",
    "weekend_half_b": "drugiej połowy doby weekendowej",
}
_DUTY_ROTATION_PAIR_KEYS = {**_WEEKDAY_DUTY_PAIR_KEYS, **_WEEKEND_DUTY_PAIR_KEYS}


def _normalize_duty_window(raw: dict, label: str) -> dict:
    start = raw.get("start") if raw else None
    end = raw.get("end") if raw else None
    if not start or not end:
        raise ValueError(f"Okno \"{label}\" wymaga podania obu godzin (początku i końca)")
    if start == end:
        raise ValueError(f"Godzina początku i końca okna \"{label}\" nie mogą być takie same")
    return {"start": start, "end": end}


def normalize_duty_rotation(raw: dict | None) -> dict | None:
    """Walidacja opcjonalnej konfiguracji rotacji służby 24/7 tej lokalizacji
    ("plan profil ochrona (analiza specyfikacji klienta).md", sekcja 12,
    Etap A) - okna czasowe:

    - `weekday_long` + `weekday_short`: dwie zmiany pokrywające razem całą
      dobę w tygodniu (pon-pt), np. SHIFT_16H 06:00-22:00 + SHIFT_8H_NIGHT
      22:00-06:00. Wymagane, chyba że `only_12_24h` jest włączone (patrz
      niżej) - wtedy te dwa typy zmian w ogóle nie są używane.
    - `weekend_full`: sztywna zmiana 24h - tylko godzina startu, koniec z
      definicji 24h później (patrz DaySchedule.set_full_day_shift) - "end"
      w tym oknie jest niejednoznaczny (patrz normalize_night_shift), więc
      się go tu w ogóle nie przyjmuje. Zawsze wymagane.
    - `weekend_half_a` + `weekend_half_b`: dwuosobowa alternatywa dla
      `weekend_full`, gdy przypisana osoba (albo obie) mają flagę "nie chce
      24h" - też razem cała doba. Zawsze wymagane.
    - `only_12_24h` (bool, domyślnie False): gdy True, generator używa tego
      samego przełącznika 24h-albo-12h+12h co w weekend dla KAŻDEGO dnia
      tygodnia - `weekday_long`/`weekday_short` nigdy się wtedy nie
      przydzielają (i nie trzeba ich tu w ogóle konfigurować). Odpowiada
      toggle'owi "Używaj tylko zmian 12/24h" w Konfiguracji.

    None/pusty słownik = lokalizacja nie używa tego mechanizmu (domyślne -
    zero zmiany zachowania dla każdego istniejącego projektu/lokalizacji).
    Skonfigurowanie choć jednego wymaganego okna wymaga skonfigurowania
    wszystkich pozostałych wymaganych - to jeden, spójny schemat rotacji,
    nie da się użyć częściowo.
    """
    if not raw:
        return None

    only_12_24h = bool(raw.get("only_12_24h", False))
    required_pair_keys = dict(_WEEKEND_DUTY_PAIR_KEYS)
    if not only_12_24h:
        required_pair_keys.update(_WEEKDAY_DUTY_PAIR_KEYS)

    missing = [key for key in (*required_pair_keys, "weekend_full") if not raw.get(key)]
    if missing:
        raise ValueError(f"Rotacja służby wymaga skonfigurowania wszystkich okien - brakuje: {', '.join(missing)}")

    weekend_full_start = raw["weekend_full"].get("start")
    if not weekend_full_start:
        raise ValueError("Zmiana 24h w weekend wymaga podania godziny startu")

    # Waliduje/kopiuje KAŻDE podane okno parowe, nawet spoza required_pair_keys
    # (np. weekday_long/short podane razem z only_12_24h=True) - nieużywane w
    # tym trybie, ale zachowane, żeby toggle "Używaj tylko zmian 12/24h" dało
    # się bezpiecznie przełączyć z powrotem bez utraty wcześniej wpisanych
    # godzin (dziś nie ma osobnego UI do ich ponownego wpisania).
    normalized = {
        key: _normalize_duty_window(raw[key], label)
        for key, label in _DUTY_ROTATION_PAIR_KEYS.items()
        if raw.get(key)
    }
    normalized["weekend_full"] = {"start": weekend_full_start}
    normalized["only_12_24h"] = only_12_24h
    return normalized


@dataclass
class LocationConfig:
    key: str
    name: str
    open_hours: dict = field(default_factory=lambda: dict(DEFAULT_OPEN_HOURS))
    trade_sundays: set = field(default_factory=set)
    public_holidays: set = field(default_factory=set)
    day_overrides: dict = field(default_factory=dict)
    constraints: dict = field(default_factory=lambda: dict(DEFAULT_LOCATION_CONSTRAINTS))
    # Opcjonalny, sztywny blok zmiany nocnej dla tej lokalizacji, np.
    # {"start": "22:00", "end": "06:00"}. None = lokalizacja nie ma zmiany
    # nocnej (domyślne - zero zmiany zachowania dla Dino i profili bez tej
    # potrzeby). Zob. "plan zmiany nocne (24-7).md", Etap B.
    night_shift: dict | None = field(default=None)

    # Opcjonalna konfiguracja rotacji służby 24/7 (np. ochrona) - patrz
    # normalize_duty_rotation() wyżej. None = lokalizacja jej nie używa
    # (domyślne - zero zmiany zachowania). Niezależna od `night_shift`
    # (ten mechanizm ma własny, oddzielny zestaw typów zmian - patrz "plan
    # profil ochrona (analiza specyfikacji klienta).md", sekcja 12, Etap A).
    duty_rotation: dict | None = field(default=None)

    # Same logic as ShopConfig.weekday/is_trade_day/get_open_hours_for_day
    # (model/shop_config.py) - a location has no year/month of its own, so
    # these take them as arguments instead of reading self.year/self.month.

    def weekday(self, year: int, month: int, day: int) -> int:
        return calendar.weekday(year, month, day)

    def is_sunday(self, year: int, month: int, day: int) -> bool:
        return self.weekday(year, month, day) == 6

    def is_trade_day(self, year: int, month: int, day: int) -> bool:
        if day in self.public_holidays:
            return False
        if self.is_sunday(year, month, day):
            return day in self.trade_sundays
        return True

    def get_open_hours_for_day(self, year: int, month: int, day: int):
        if not self.is_trade_day(year, month, day):
            return None

        if day in self.day_overrides:
            start, end = self.day_overrides[day]
            if start and end:
                return start, end
            return None

        wd = self.weekday(year, month, day)
        hours = self.open_hours.get(wd)
        if not hours:
            return None

        start, end = hours
        if not start or not end:
            return None
        return start, end

    def get_night_shift_hours(self) -> tuple[str, str] | None:
        """(start, end) zmiany nocnej tej lokalizacji, albo None gdy jej nie ma."""
        if not self.night_shift:
            return None
        start = self.night_shift.get("start")
        end = self.night_shift.get("end")
        if not start or not end:
            return None
        return start, end

    def set_night_shift(self, start: str | None, end: str | None) -> None:
        self.night_shift = normalize_night_shift(start, end)

    def get_duty_rotation(self) -> dict | None:
        """Konfiguracja rotacji służby 24/7 tej lokalizacji, albo None gdy
        jej nie ma - patrz normalize_duty_rotation()."""
        return self.duty_rotation

    def set_duty_rotation(self, raw: dict | None) -> None:
        self.duty_rotation = normalize_duty_rotation(raw)

    def to_dict(self):
        return {
            "key": self.key,
            "name": self.name,
            "open_hours": self.open_hours,
            "trade_sundays": list(self.trade_sundays),
            "public_holidays": list(self.public_holidays),
            "day_overrides": self.day_overrides,
            "constraints": self.constraints,
            "night_shift": self.night_shift,
            "duty_rotation": self.duty_rotation,
        }

    @classmethod
    def from_dict(cls, data):
        loc = cls(key=data["key"], name=data.get("name", data["key"]))
        loc.open_hours = {
            int(k): tuple(v) for k, v in data.get("open_hours", {}).items()
        } or dict(DEFAULT_OPEN_HOURS)
        loc.trade_sundays = set(data.get("trade_sundays", []))
        loc.public_holidays = set(data.get("public_holidays", []))
        loc.day_overrides = {
            int(day): tuple(hours) for day, hours in data.get("day_overrides", {}).items()
        }
        loc.constraints = dict(DEFAULT_LOCATION_CONSTRAINTS)
        loc.constraints.update(data.get("constraints", {}))
        night_shift = data.get("night_shift")
        loc.night_shift = dict(night_shift) if night_shift else None
        duty_rotation = data.get("duty_rotation")
        loc.duty_rotation = dict(duty_rotation) if duty_rotation else None
        return loc
