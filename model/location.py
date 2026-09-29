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
from datetime import datetime

from model.constraint_policy import ConstraintPolicy

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

# Ustawienia z „Zasad generatora” (ustawienia zaawansowane) zapisywane per
# placówka w LocationConfig.constraints, a czytane przez generator z
# ShopConfig.constraints - patrz ShopConfig.with_location_settings. (Limit
# dni pod rząd i maks. obsada naraz generator i tak czyta per placówka przez
# ShopConfig.get_location().)
LOCATION_RUN_SETTING_KEYS = ("rest_11h_mode",)

# Stała, powtarzalna codziennie "pora nocna" (Kodeks pracy, art. 151(7) §1:
# 8 godzin między 21:00 a 7:00, w praktyce ustalane przez pracodawcę - tu
# 22:00-6:00) używana do automatycznego wykrywania zmiany nocnej z godzin
# otwarcia lokalizacji (patrz LocationConfig.get_night_shift_hours()).
NIGHT_WINDOW = ("22:00", "06:00")


def daily_subintervals(start_minutes, end_minutes):
    """Splits a possibly midnight-crossing, recurring-daily [start, end)
    window (minutes-of-day) into 1 or 2 non-wrapping sub-intervals within
    [0, 1440) - the building block for comparing two such recurring windows
    (e.g. a no_night/role_time_restriction window and a location's night
    window) for overlap without anchoring either to a specific calendar
    date."""
    start_minutes %= 1440
    length = (end_minutes - start_minutes) % 1440 or 1440
    end = start_minutes + length
    if end <= 1440:
        return [(start_minutes, end)]
    return [(start_minutes, 1440), (0, end - 1440)]


def daily_windows_overlap(a_start_minutes, a_end_minutes, b_start_minutes, b_end_minutes):
    """True gdy dwa powtarzające się codziennie okna [start, end) (w
    minutach dnia) pokrywają się choć częściowo - poprawne niezależnie od
    tego, które z nich (lub oba) przechodzi przez północ."""
    a_parts = daily_subintervals(a_start_minutes, a_end_minutes)
    b_parts = daily_subintervals(b_start_minutes, b_end_minutes)
    return any(a[0] < b[1] and b[0] < a[1] for a in a_parts for b in b_parts)


def hour_window_overlaps_time_range(window_start_hour, window_end_hour, hhmm_range):
    """True gdy godzinowe okno [window_start_hour, window_end_hour) pokrywa
    się choć częściowo z zakresem podanym jako para "HH:MM" (np. godziny
    otwarcia lokalizacji) - np. dla no_night (domyślnie 22-6) i lokalizacji
    otwartej tylko w środku dnia, to False."""
    start_str, end_str = hhmm_range
    fmt = "%H:%M"
    start_dt = datetime.strptime(start_str, fmt)
    end_dt = datetime.strptime(end_str, fmt)
    return daily_windows_overlap(
        window_start_hour * 60, window_end_hour * 60,
        start_dt.hour * 60 + start_dt.minute, end_dt.hour * 60 + end_dt.minute,
    )


def normalize_night_shift(start: str | None, end: str | None) -> dict | None:
    """Walidacja opcjonalnego, ręcznie ustawianego okna zmiany nocnej na
    poziomie CAŁEGO PROJEKTU (ShopConfig.night_shift - legacy fallback dla
    projektów bez zdefiniowanych lokalizacji, patrz komentarz przy tym polu
    w model/shop_config.py). LocationConfig NIE ma już własnego ręcznego pola
    - zamiast tego wykrywa zmianę nocną automatycznie z godzin otwarcia, patrz
    LocationConfig.get_night_shift_hours(). A None/empty pair clears the
    window; a single missing side or start == end is rejected the same way
    DaySchedule.set_hours() rejects an ambiguous zero-length shift. end < start
    is allowed on purpose - that's exactly what marks the window as crossing
    midnight.
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

    - `weekday_long` + `weekday_short`: dwie zmiany w tygodniu (pon-pt),
      zwykle razem pokrywające całą dobę, np. SHIFT_16H 06:00-22:00 +
      SHIFT_8H_NIGHT 22:00-06:00. Każda z osobna OPCJONALNA - lokalizacja
      może skonfigurować tylko jedną z nich (klient GZUK, 2026-09-28: sama
      `weekday_long` 15:00-07:00, bez drugiej osoby na resztę doby - patrz
      add_duty_rotation_coverage_constraint, która wymaga obsady TYLKO tej
      skonfigurowanej) - wymagana jest co najmniej jedna z dwóch, chyba że
      `only_12_24h` jest włączone (patrz niżej) - wtedy żadna nie jest w
      ogóle używana.
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
    Weekend to jeden, spójny schemat (nie da się go skonfigurować częściowo);
    tydzień jest elastyczny - patrz `weekday_long`/`weekday_short` wyżej.
    """
    if not raw:
        return None

    only_12_24h = bool(raw.get("only_12_24h", False))
    # Weekend zawsze wymaga kompletu (weekend_full + obie połówki - wybór
    # między nimi robi solver, patrz add_duty_rotation_coverage_constraint).
    # Tydzień: weekday_long/weekday_short są OPCJONALNE każda z osobna (patrz
    # docstring wyżej) - ale gdy duty_rotation w ogóle obejmuje tydzień
    # (not only_12_24h), potrzeba co najmniej jednej z nich, inaczej tydzień
    # nie miałby żadnej obsady w ogóle.
    missing = [key for key in (*_WEEKEND_DUTY_PAIR_KEYS, "weekend_full") if not raw.get(key)]
    if missing:
        raise ValueError(f"Rotacja służby wymaga skonfigurowania wszystkich okien - brakuje: {', '.join(missing)}")
    if not only_12_24h and not raw.get("weekday_long") and not raw.get("weekday_short"):
        raise ValueError(
            "Rotacja służby w tygodniu wymaga skonfigurowania co najmniej jednego okna "
            "(długiej albo krótkiej zmiany)"
        )

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
    # "Preferuj zmiany 24h" (ui/duty_rotation_editor.py) - odwraca miękką
    # preferencję generatora (logic/generator/duty_rotation_preference.py).
    # Zapisywane tylko gdy włączone, żeby projekty bez tej opcji miały
    # dokładnie ten sam słownik co wcześniej.
    if raw.get("prefer_24h"):
        normalized["prefer_24h"] = True
    return normalized


MAX_PREFERRED_SHIFTS = 3


def _minutes_of_day(value: str) -> int:
    h, m = value.split(":")
    return int(h) * 60 + int(m)


def _window_length(start_minutes: int, end_minutes: int) -> int:
    return (end_minutes - start_minutes) % 1440 or 1440


def _shift_fits_day_window(pref_start: str, pref_end: str, day_start: str, day_end: str) -> bool:
    """True gdy przedział [pref_start, pref_end) mieści się w całości w
    [day_start, day_end) - wszystkie cztery podane jako "HH:MM", oba
    przedziały mogą przechodzić przez północ (koniec wcześniejszy niż
    początek = kończy się w dniu następnym), liczone modulo 24h - ta sama
    konwencja co logic/generator/opening_hours_coverage.py::parse_open_hours."""
    day_len = _window_length(_minutes_of_day(day_start), _minutes_of_day(day_end))
    pref_len = _window_length(_minutes_of_day(pref_start), _minutes_of_day(pref_end))
    offset = (_minutes_of_day(pref_start) - _minutes_of_day(day_start)) % 1440
    return offset + pref_len <= day_len


def normalize_preferred_shifts(raw: list | None, open_hours: dict) -> list[dict]:
    """Walidacja opcjonalnej listy "Preferowanych godzin pracy" tej
    lokalizacji (model godzin otwarcia, profil Ochrony bez rotacji 24/7,
    opcje zaawansowane - patrz ui/preferred_shifts_editor.py) - lista par
    {"start", "end"}, patrz LocationConfig.preferred_shifts. Generator
    (logic/generator/opening_hours_coverage.py::window_shapes) oferuje te
    godziny jako dodatkowe, miękko preferowane kształty zmiany obok
    domyślnej "cała zmiana na okno dnia" - tylko w dniach, w których dany
    przedział mieści się w całości w skonfigurowanym oknie otwarcia tego
    dnia. Odrzucane tu z góry, jeśli nie mieści się w ŻADNYM dniu tygodnia
    z `open_hours` - to niemal zawsze literówka (taki przedział nigdy nie
    zmieściłby się w żadnym oknie, więc generator nigdy by go nie użył), a
    złapanie tego od razu przy zapisie jest czytelniejsze niż ciche
    pomijanie w generatorze.
    """
    if not raw:
        return []
    if len(raw) > MAX_PREFERRED_SHIFTS:
        raise ValueError(f"Można podać najwyżej {MAX_PREFERRED_SHIFTS} przedziałów godzin.")

    valid_days = [
        hours for hours in open_hours.values()
        if hours and hours[0] and hours[1]
    ]
    normalized = []
    for entry in raw:
        start = entry.get("start") if entry else None
        end = entry.get("end") if entry else None
        if not start or not end:
            raise ValueError("Preferowana zmiana wymaga podania obu godzin (początku i końca)")
        if start == end:
            raise ValueError("Godzina początku i końca preferowanej zmiany nie mogą być takie same")
        if not any(_shift_fits_day_window(start, end, day_start, day_end) for day_start, day_end in valid_days):
            raise ValueError(
                f"Godziny {start}-{end} wykraczają poza godziny otwarcia tej lokalizacji - "
                "podaj przedział mieszczący się w co najmniej jednym dniu otwarcia."
            )
        normalized.append({"start": start, "end": end})
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

    # Placówka czynna całodobowo 7 dni w tygodniu. Sam w sobie to tylko skrót
    # do godzin otwarcia (patrz set_24_7()) - niezależny od `duty_rotation`
    # poniżej (osobny, dalej opcjonalny mechanizm rotacji służby).
    is_24_7: bool = False

    # "Godzina rozpoczęcia" rotacji całodobowej (tylko dla is_24_7=True,
    # niezależna od duty_rotation - patrz logic/generator/round_clock_constraint.py).
    # None = wyłączone: generator używa dotychczasowego mechanizmu OPEN/CLOSE
    # (zakotwiczonego na 00:00/23:45 dla lokalizacji 24/7), który - jak się
    # okazało (2026-09-21, zgłoszenie klienta) - fizycznie nie jest w stanie
    # obsadzić środka doby (maks. przesunięcie od otwarcia/zamknięcia to
    # 90/75 minut, więc przy 24h otwarcia zawsze zostaje kilkugodzinna luka
    # bez nikogo w pracy). Ustawione (np. "08:00") - generator dzieli dobę na
    # kolejne, następujące po sobie zmiany zaczynające się o tej godzinie, o
    # ShopConfig.standard_daily_hours długości każda (patrz
    # round_clock_constraint.py::round_clock_tile_count), aż wypełni całą
    # dobę - i tak każdego dnia miesiąca.
    round_clock_start_hour: str | None = None

    # Opcjonalna konfiguracja rotacji służby 24/7 (np. ochrona) - patrz
    # normalize_duty_rotation() wyżej. None = lokalizacja jej nie używa
    # (domyślne - zero zmiany zachowania). Niezależna od `is_24_7`/godzin
    # nocnych (ten mechanizm ma własny, oddzielny zestaw typów zmian - patrz
    # "plan profil ochrona (analiza specyfikacji klienta).md", sekcja 12,
    # Etap A).
    duty_rotation: dict | None = field(default=None)

    # "Preferowane godziny pracy" (opcje zaawansowane, model godzin otwarcia
    # - profil Ochrony bez rotacji 24/7): lista par {"start", "end"}, którymi
    # generator w miarę możliwości dzieli okno dnia zamiast domyślnej jednej
    # zmiany na całe okno (np. 7:00-15:00 + 15:00-22:00 zamiast jednej osoby
    # 7:00-22:00) - patrz normalize_preferred_shifts() wyżej i
    # logic/generator/opening_hours_coverage.py::window_shapes/
    # prefer_preferred_shifts_terms. Miękka preferencja - generator wraca do
    # jednej zmiany, gdy trzeba (za mało ludzi, urlopy). `preferred_shifts`
    # zostaje zapisane nawet gdy enabled=False, żeby wyłączenie przełącznika
    # nie gubiło wpisanych godzin (ten sam wzorzec co duty_rotation wyżej).
    preferred_shifts_enabled: bool = False
    preferred_shifts: list = field(default_factory=list)

    # Czy automatycznie zamykać tę lokalizację w polskie święta ustawowo
    # wolne od pracy (patrz logic/utils/holidays_pl.py - biblioteka
    # `holidays`, nie ręczne `public_holidays` wyżej). Domyślnie WŁĄCZONE -
    # większość placówek nie jest chroniona w święta; część (np. obiekty
    # krytyczne) zostaje mimo to 24/7, stąd przełącznik per lokalizacja, nie
    # globalny. Niezależne od `uses_trade_calendar` profilu (patrz
    # is_trade_day) - to osobny mechanizm, żeby działał też dla profili bez
    # kalendarza handlowego (np. Enyo/ochrona). Jawnie nadpisany dzień
    # (`day_overrides`) zawsze wygrywa - patrz is_closed_for_public_holiday().
    closed_on_public_holidays: bool = True

    # Tryby zasad generatora tej placówki (Konfiguracja -> Zasady generatora
    # -> ustawienia zaawansowane): nazwa zasady -> ConstraintPolicy. Brak
    # wpisu = tryb projektu (ShopConfig.constraint_policies) - patrz
    # ShopConfig.effective_constraint_policies/with_location_settings.
    constraint_policies: dict = field(default_factory=dict)

    def is_closed_for_public_holiday(self, year: int, month: int, day: int) -> bool:
        """True gdy `closed_on_public_holidays` obejmuje ten dzień (polskie
        święto ustawowe, patrz logic/utils/holidays_pl.py) - używane zarówno
        przez get_open_hours_for_day() (godziny otwarcia/grid) niżej, jak i
        bezpośrednio przez generator dla lokalizacji z duty_rotation (te w
        ogóle nie korzystają z open_hours - patrz
        logic/generator/duty_rotation_public_holiday_constraint.py)."""
        if not self.closed_on_public_holidays:
            return False
        if day in self.day_overrides:
            return False
        from logic.utils.holidays_pl import polish_public_holiday_days
        return day in polish_public_holiday_days(year, month)

    def is_duty_day_closed(self, year: int, month: int, day: int) -> bool:
        """True gdy doba rotacji służby zaczynająca się tego dnia ma zostać
        bez obsady: zamknięte święto (is_closed_for_public_holiday) ALBO dzień
        ręcznie oznaczony "Nieczynne tego dnia" (dwuklik na nagłówku w
        grafiku - day_overrides[day] bez godzin). Rotacja nie korzysta z
        godzin otwarcia, więc samo get_open_hours_for_day() jej nie dotyczy -
        wcześniej dzień "Nieczynne" był w siatce szary i pusty, a generator
        i tak go obsadzał (niewidoczne zmiany liczone do godzin i eksportu).
        Ręczne nadpisanie Z godzinami otwiera dzień, także w święto."""
        override = self.day_overrides.get(day)
        if override is not None:
            start, end = override
            return not (start and end)
        return self.is_closed_for_public_holiday(year, month, day)

    # Same logic as ShopConfig.weekday/is_trade_day/get_open_hours_for_day
    # (model/shop_config.py) - a location has no year/month of its own, so
    # these take them as arguments instead of reading self.year/self.month.

    def weekday(self, year: int, month: int, day: int) -> int:
        return calendar.weekday(year, month, day)

    def is_sunday(self, year: int, month: int, day: int) -> bool:
        return self.weekday(year, month, day) == 6

    def is_trade_day(self, year: int, month: int, day: int, uses_trade_calendar: bool = True) -> bool:
        # "Dni handlowe" (święta/niedziele handlowe) to koncept specyficzny
        # dla profili z kalendarzem handlowym (patrz BusinessProfile.
        # uses_trade_calendar, ShopConfig.is_trade_day - ta metoda ma tu ten
        # sam parametr z tego samego powodu). Profile bez tego konceptu (np.
        # ochrona) mają wszystkie dni, w tym niedziele, normalnie pracujące -
        # inaczej KAŻDA niedziela wychodziłaby "zamknięta" (trade_sundays
        # puste domyślnie), mimo że użytkownik nigdy jej tak nie oznaczył.
        if not uses_trade_calendar:
            return True
        if day in self.public_holidays:
            return False
        if self.is_sunday(year, month, day):
            return day in self.trade_sundays
        return True

    def get_open_hours_for_day(self, year: int, month: int, day: int, uses_trade_calendar: bool = True):
        if not self.is_trade_day(year, month, day, uses_trade_calendar):
            return None

        if day in self.day_overrides:
            start, end = self.day_overrides[day]
            if start and end:
                return start, end
            return None

        if self.is_closed_for_public_holiday(year, month, day):
            return None

        wd = self.weekday(year, month, day)
        hours = self.open_hours.get(wd)
        if not hours:
            return None

        start, end = hours
        if not start or not end:
            return None
        return start, end

    def get_weekly_open_hours_on(self, dt):
        """Godziny otwarcia w dowolnym dniu kalendarza (np. ostatnim dniu
        poprzedniego miesiąca) wg tygodniowego wzorca `open_hours` i
        zamknięcia w polskie święta - bez `day_overrides` (te dotyczą dni
        bieżącego miesiąca). Używane przez model godzin otwarcia Ochrony do
        ustalenia, gdzie kończy się okno sprzed dnia 1 (kotwica doby)."""
        if self.closed_on_public_holidays:
            from logic.utils.holidays_pl import polish_public_holiday_days
            if dt.day in polish_public_holiday_days(dt.year, dt.month):
                return None
        hours = self.open_hours.get(dt.weekday())
        if not hours or not hours[0] or not hours[1]:
            return None
        return hours[0], hours[1]

    def get_night_shift_hours(self) -> tuple[str, str] | None:
        """(start, end) zmiany nocnej tej lokalizacji, wykrywana automatycznie
        z jej godzin otwarcia - nie ma już osobnego, ręcznie ustawianego pola
        (patrz normalize_night_shift() wyżej - to teraz wyłącznie legacy
        fallback na poziomie ShopConfig). Zwraca stałe NIGHT_WINDOW
        (22:00-06:00, zgodnie z Kodeksem pracy) gdy `is_24_7` jest ustawione
        albo gdy którykolwiek dzień tygodnia w `open_hours` faktycznie
        przechodzi przez północ (koniec <= początek, np. GZUK 15:00-07:00);
        w przeciwnym razie None. Zwykłe, tego samego dnia godziny kończące
        się po 22:00 (np. domyślne Dino 05:30-22:45/23:00) NIE liczą się -
        to zwykłe późne zamknięcie, nie osobna zmiana nocna (naprawiona
        regresja, patrz DINO_REGRESSION_AUDIT.md punkt 1: przed tą poprawką
        każda taka placówka dostawała dostępną zmianę SHIFT_NIGHT, której
        v1.2.0 nigdy nie miał, i której no_night/dostępność pracownika w
        ogóle nie blokowały)."""
        if self.is_24_7:
            return NIGHT_WINDOW
        fmt = "%H:%M"
        for hours in self.open_hours.values():
            if not hours or not hours[0] or not hours[1]:
                continue
            start_dt = datetime.strptime(hours[0], fmt)
            end_dt = datetime.strptime(hours[1], fmt)
            if end_dt <= start_dt:
                return NIGHT_WINDOW
        return None

    def set_24_7(self, enabled: bool) -> None:
        """Włącza/wyłącza skrót "Działalność całodobowa (24/7)": ustawia
        (albo nie) `open_hours` na całą dobę każdego dnia tygodnia, tą samą
        konwencją "00:00-23:45" co reszta kodu używa dla "cały dzień"
        (godziny otwarcia zakładają parę z tego samego dnia, bez zawijania
        przez północ - w przeciwieństwie do zawsze-zawijającego NIGHT_WINDOW
        powyżej)."""
        self.is_24_7 = enabled
        if enabled:
            self.open_hours = {wd: ("00:00", "23:45") for wd in range(7)}
        else:
            self.round_clock_start_hour = None

    def get_duty_rotation(self) -> dict | None:
        """Konfiguracja rotacji służby 24/7 tej lokalizacji, albo None gdy
        jej nie ma - patrz normalize_duty_rotation(). Celowo NIEZALEŻNE od
        `is_24_7` (patrz komentarz przy tym polu) - `duty_rotation` samo w
        sobie w pełni definiuje obsadę (godziny otwarcia nie mają tu
        znaczenia), a generator/testy legalnie konstruują lokalizacje z
        duty_rotation bez dotykania is_24_7 w ogóle. Spójność z is_24_7 jest
        egzekwowana WYŁĄCZNIE przy wczytywaniu zapisanego projektu - patrz
        from_dict() niżej - nie tutaj."""
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
            "is_24_7": self.is_24_7,
            "round_clock_start_hour": self.round_clock_start_hour,
            "duty_rotation": self.duty_rotation,
            "closed_on_public_holidays": self.closed_on_public_holidays,
            "preferred_shifts_enabled": self.preferred_shifts_enabled,
            "preferred_shifts": self.preferred_shifts,
            "constraint_policies": {
                name: getattr(policy, "value", policy) for name, policy in self.constraint_policies.items()
            },
        }

    @classmethod
    def from_dict(cls, data):
        # "night_shift" z plików zapisanych przed auto-wykrywaniem jest
        # celowo ignorowany - godziny nocne liczą się teraz zawsze z
        # open_hours/is_24_7 (patrz get_night_shift_hours()).
        loc = cls(key=data["key"], name=data.get("name", data["key"]))
        loc.open_hours = {
            int(k): tuple(v) for k, v in data.get("open_hours", {}).items()
        } or dict(DEFAULT_OPEN_HOURS)
        loc.trade_sundays = set(data.get("trade_sundays", []))
        loc.public_holidays = set(data.get("public_holidays", []))
        loc.day_overrides = {
            int(day): tuple(hours) for day, hours in data.get("day_overrides", {}).items()
        }
        loc.is_24_7 = bool(data.get("is_24_7", False))
        loc.closed_on_public_holidays = bool(data.get("closed_on_public_holidays", True))
        loc.round_clock_start_hour = data.get("round_clock_start_hour")
        loc.constraints = dict(DEFAULT_LOCATION_CONSTRAINTS)
        loc.constraints.update(data.get("constraints", {}))
        loc.constraint_policies = {}
        for name, value in data.get("constraint_policies", {}).items():
            try:
                loc.constraint_policies[name] = ConstraintPolicy(value)
            except ValueError:
                continue
        # Tryb „Dni pod rząd” zapisywany chwilę (2026-09-29) osobno w
        # constraints - teraz zwykły wpis constraint_policies.
        legacy_max_consecutive = loc.constraints.pop("max_consecutive_policy", None)
        if legacy_max_consecutive in {p.value for p in ConstraintPolicy}:
            loc.constraint_policies.setdefault("max_consecutive", ConstraintPolicy(legacy_max_consecutive))
        loc.preferred_shifts_enabled = bool(data.get("preferred_shifts_enabled", False))
        loc.preferred_shifts = [dict(entry) for entry in data.get("preferred_shifts", [])]
        duty_rotation = data.get("duty_rotation")
        # duty_rotation samo w sobie w pełni definiuje obsadę tej lokalizacji
        # dla generatora (get_duty_rotation() jest CELOWO niezależne od
        # is_24_7 - patrz jej docstring), więc jest tu źródłem prawdy - NIE
        # kasujemy go, gdy plik ma is_24_7=False obok skonfigurowanego
        # duty_rotation (dokładnie taki stan miały wszystkie lokalizacje w
        # test_data/dane_klienta_ochrona.json przed regeneracją). Wcześniejsza
        # wersja tego kodu (2026-09-25) w tej sytuacji cicho zerowała
        # duty_rotation, żeby "zgadzało się" z is_24_7 w UI - to niszczyło
        # prawdziwą konfigurację rotacji przy każdym wczytaniu pliku (grafik
        # przestawał generować zmiany rotacji, wiersz "Obłożenie" przestawał
        # widzieć tę lokalizację) zamiast naprawić niespójność we właściwą
        # stronę. Zamiast tego: is_24_7 dociąga się DO duty_rotation, żeby
        # checkbox w UI od razu pokazywał to, co grafik i tak już robi
        # (zgłoszenie użytkownika 2026-09-26).
        loc.duty_rotation = dict(duty_rotation) if duty_rotation else None
        if loc.duty_rotation:
            loc.is_24_7 = True
            # Rotacja służby i rotacja całodobowa (round_clock_start_hour) mają
            # wzajemnie wykluczające się bramy w generatorze - razem blokują
            # pracownikom tej lokalizacji KAŻDĄ zmianę (generator bez
            # rozwiązania). Rotacja służby to mechanizm ze specyfikacji klienta
            # Enyo, a pole rotacji całodobowej jest ukryte w UI (patrz
            # ui/locations_dialog.py::ROUND_CLOCK_UI_ENABLED) - wartość zapisana
            # wcześniej obok rotacji służby jest więc ignorowana przy wczytaniu.
            loc.round_clock_start_hour = None
        return loc


_DAY_ABBR = ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Nd"]


def format_open_hours_summary(location: "LocationConfig") -> str:
    """Krótki opis godzin pracy lokalizacji do paska nad tabelą grafiku
    (ui/main_window.py) - liczony wyłącznie z konfiguracji godzin otwarcia
    (open_hours/is_24_7), ignoruje ręczne nadpisania dni w tabeli."""
    if location.is_24_7:
        return "24/7"

    hours = [location.open_hours.get(wd) for wd in range(7)]
    if any(not h or not h[0] or not h[1] for h in hours):
        return "Niestandardowe godziny pracy"

    if len(set(hours)) == 1:
        start, end = hours[0]
        return f"Godziny pracy: {start} - {end}"

    weekdays, sat, sun = hours[0:5], hours[5], hours[6]
    if len(set(weekdays)) == 1:
        wd_start, wd_end = weekdays[0]
        parts = [f"Pon-Pt {wd_start}-{wd_end}"]
        if sat == sun:
            parts.append(f"Sob-Nd {sat[0]}-{sat[1]}")
        else:
            parts.append(f"Sob {sat[0]}-{sat[1]}")
            parts.append(f"Nd {sun[0]}-{sun[1]}")
        return ", ".join(parts)

    return "Niestandardowe godziny pracy"
