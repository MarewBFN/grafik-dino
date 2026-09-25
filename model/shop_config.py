import calendar
from model.constraint_policy import ConstraintPolicy
from model.business_profile import DEFAULT_BUSINESS_TYPE, get_profile
from model.location import LocationConfig, normalize_night_shift, normalize_duty_rotation

# Klucz/nazwa auto-tworzonej domyślnej lokalizacji: każdy projekt ma zawsze
# co najmniej jedną lokalizację (patrz ShopConfig.__init__/from_dict), żeby
# UI/generator mogły zawsze liczyć na shop_config.locations będące niepuste.
DEFAULT_LOCATION_KEY = "glowna"
DEFAULT_LOCATION_NAME = "Placówka główna"


def _default_location_from_shop(shop, key: str, name: str) -> LocationConfig:
    """Buduje nową LocationConfig zasiedloną z pól poziomu projektu (open_hours,
    trade_sundays, itd.) - używane zarówno przy tworzeniu nowego projektu, jak
    i przy migracji starego pliku bez zdefiniowanych lokalizacji, tak że
    zachowanie generatora się nie zmienia (patrz ShopConfig.__init__/from_dict)."""
    loc = LocationConfig(key=key, name=name)
    loc.open_hours = dict(shop.open_hours)
    loc.trade_sundays = set(shop.trade_sundays)
    loc.public_holidays = set(shop.public_holidays)
    loc.day_overrides = dict(shop.day_overrides)
    loc.duty_rotation = dict(shop.duty_rotation) if shop.duty_rotation else None
    return loc


class _LocationView:
    """Duck-types the day-hours subset of ShopConfig's API (weekday /
    get_open_hours_for_day) against one LocationConfig, bound to the parent
    project's year/month - so constraint code can call
    shop.get_location(emp).get_open_hours_for_day(d) the same way it calls
    shop.get_open_hours_for_day(d) today, regardless of which one it got."""

    def __init__(
        self, location: LocationConfig, year: int, month: int, fallback_constraints: dict,
        uses_trade_calendar: bool = True,
    ):
        self._location = location
        self._year = year
        self._month = month
        self._fallback_constraints = fallback_constraints
        self._uses_trade_calendar = uses_trade_calendar

    def weekday(self, day: int) -> int:
        return self._location.weekday(self._year, self._month, day)

    def is_trade_day(self, day: int) -> bool:
        return self._location.is_trade_day(self._year, self._month, day, self._uses_trade_calendar)

    def get_open_hours_for_day(self, day: int):
        return self._location.get_open_hours_for_day(self._year, self._month, day, self._uses_trade_calendar)

    def get_night_shift_hours(self):
        return self._location.get_night_shift_hours()

    def get_duty_rotation(self):
        return self._location.get_duty_rotation()

    def get_round_clock_start_hour(self) -> str | None:
        return self._location.round_clock_start_hour if self._location.is_24_7 else None

    def is_closed_for_public_holiday(self, day: int) -> bool:
        return self._location.is_closed_for_public_holiday(self._year, self._month, day)

    @property
    def constraints(self) -> dict:
        # LocationConfig always carries all of DEFAULT_LOCATION_CONSTRAINTS
        # today, so this merge only matters for a location saved before a
        # future key gets added there.
        merged = dict(self._fallback_constraints)
        merged.update(self._location.constraints)
        return merged


def normalize_quick_mode_presets(raw: list[dict] | None) -> list[dict]:
    """Waliduje i porządkuje presety trybu szybkiego (patrz
    ShopConfig.quick_mode_presets). Rzuca ValueError przy nazwie pustej/
    zdublowanej albo niepoprawnym zakresie godzin - to samo miejsce, z
    którego korzysta zarówno UI (ui/quick_mode_settings_dialog.py), jak i
    deserializacja projektu, żeby raz zapisany plik nie mógł zawierać
    nieprawidłowych presetów.

    "visible" (domyślnie True dla presetów bez tego pola - stare projekty
    sprzed tej flagi) mówi ui/main_window.py::_rebuild_quick_preset_buttons,
    czy dany przedział ma dostać przycisk w trybie szybkim - pozwala trzymać
    przygotowane, ale niepotrzebne akurat teraz przedziały bez zaśmiecania
    panelu, bez usuwania i odtwarzania ich za każdym razem."""
    if not raw:
        return []

    presets = []
    seen_names = set()
    for entry in raw:
        name = (entry.get("name") or "").strip()
        if not name:
            raise ValueError("Nazwa przedziału nie może być pusta.")
        if name in seen_names:
            raise ValueError(f'Nazwa przedziału musi być unikalna: "{name}".')
        seen_names.add(name)

        start = entry.get("start")
        if not start:
            raise ValueError(f'Brak godziny startu dla "{name}".')

        visible = bool(entry.get("visible", True))

        full_day = bool(entry.get("full_day"))
        if full_day:
            presets.append({"name": name, "start": start, "end": None, "full_day": True, "visible": visible})
            continue

        end = entry.get("end")
        if not end:
            raise ValueError(f'Brak godziny końca dla "{name}".')
        if end == start:
            raise ValueError(
                f'Koniec nie może być równy początkowi dla "{name}" - '
                'zaznacz "Cała doba (24h)", jeśli o to chodzi.'
            )
        presets.append({"name": name, "start": start, "end": end, "full_day": False, "visible": visible})

    return presets


class ShopConfig:
    """
    Konfiguracja sklepu:
    - niedziele handlowe
    - godziny otwarcia per dzień tygodnia
    - constrainty
    - opcje UI
    """

    def __init__(self, year: int, month: int):
        self.year = year
        self.month = month

        # Nazwa placówki/firmy nadawana w szybkiej konfiguracji (ui/first_run_wizard.py)
        # albo w zakładce "Godziny otwarcia". Czysto opisowa - nie wpływa na
        # generator. Puste domyślnie: stare projekty i te utworzone poza
        # kreatorem po prostu nie mają nazwy.
        self.name: str = ""

        # Jaki profil działalności (role, constrainty, etykiety UI) obowiązuje
        # dla tego projektu. Domyślnie Dino - stare projekty bez tego pola
        # zachowują się dokładnie jak dziś.
        self.business_type: str = DEFAULT_BUSINESS_TYPE

        # Lokalizacje/obiekty w ramach tego projektu. Każdy projekt ma zawsze
        # co najmniej jedną (patrz koniec tej metody i from_dict()) - pola
        # bezpośrednio na tym ShopConfig (open_hours, trade_sundays, itd.
        # poniżej) zostają tylko jako legacy fallback dla starych plików w
        # trakcie wczytywania (patrz get_location()), UI już ich nie edytuje.
        self.locations: dict[str, LocationConfig] = {}

        # Toggle dla constraintów z model.constraint_policy
        self.constraint_policies = {
            "rest_11h": ConstraintPolicy.MANDATORY,
            "meat": ConstraintPolicy.PREFERRED,
            "balance": ConstraintPolicy.PREFERRED,
            "max_consecutive": ConstraintPolicy.PREFERRED,
            # Minimalna obsada na otwarciu i zamknięciu jest zasadą twardą.
            "open": ConstraintPolicy.MANDATORY,
            "close": ConstraintPolicy.MANDATORY,
            "monthly_hours": ConstraintPolicy.PREFERRED,
            "meat_coverage": ConstraintPolicy.PREFERRED,
            "availability": ConstraintPolicy.PREFERRED,
            "no_night": ConstraintPolicy.PREFERRED,
            "no_afternoon": ConstraintPolicy.PREFERRED,
            # Rotacja służby 24/7 (patrz LocationConfig.duty_rotation) - te
            # dwa constrainty są no-opami dopóki żadna lokalizacja projektu
            # nie ma skonfigurowanej duty_rotation (patrz
            # logic/generator/duty_rotation_constraint.py), więc MANDATORY
            # domyślnie dla KAŻDEGO profilu (w tym Dino) nie zmienia
            # zachowania żadnego istniejącego projektu - liczy się dopiero,
            # gdy klient faktycznie skonfiguruje ten mechanizm.
            "duty_rotation_coverage": ConstraintPolicy.MANDATORY,
            "duty_rotation_no24h": ConstraintPolicy.MANDATORY,
            # Rotacja całodobowa "ogólna" (patrz LocationConfig.round_clock_start_hour,
            # logic/generator/round_clock_constraint.py) - no-op dopóki żadna
            # lokalizacja nie ma jej ustawionej, ten sam wzorzec co
            # duty_rotation_coverage wyżej: MANDATORY domyślnie (jak "open"/
            # "close") nie zmienia zachowania żadnego istniejącego projektu.
            "round_clock_coverage": ConstraintPolicy.MANDATORY,
        }
        # -----------------------------
        # Override godzin dla konkretnego dnia
        # -----------------------------
        self.day_overrides: dict[int, tuple[str, str]] = {}

        # -----------------------------
        # CONSTRAINTS CONFIG
        # -----------------------------
        self.constraints = {
            "max_consecutive_days": 4,
            "min_open_staff": 3,
            "min_close_staff": 3,
            "force_fulltime_845": True,
            # "standard" (dokładny) albo "simplified" (tylko klasa zmiany rano/popo)
            "rest_11h_mode": "standard",
            "solver_time_limit_seconds": 60,
        }

        # -----------------------------
        # UI OPTIONS
        # -----------------------------
        # "compact" | "detailed"
        self.cell_display_mode = "compact"

        # Menu Wygląd -> "Widok trybu szybkiego" - jak siatka grafiku
        # (ui/grid_view.py, przez logic/schedule_presenter.py) wyświetla
        # godziny zmiany w komórce. "standard" = dzisiejszy wygląd
        # (HH:MM/HH:MM w osobnych liniach). "fractions" = zwarty zapis
        # ułamkowy jednej linii, np. "8:00-20:00" -> "8/20" (godzina bez
        # zera wiodącego, minuty na razie po prostu zaokrąglane do
        # najbliższej pełnej godziny - patrz schedule_presenter.py).
        self.hours_display_mode = "standard"

        # Menu Wygląd -> "Legenda kolorów" (ui/grid_legend.py) - domyślnie
        # ukryta (świadoma decyzja: siatka ma jak najwięcej miejsca od
        # razu po otwarciu projektu), użytkownik włącza ją ręcznie, gdy
        # potrzebuje przypomnienia znaczenia kolorów/zakreśleń komórek.
        self.show_grid_legend = False

        # -----------------------------
        # Niedziele handlowe
        # -----------------------------
        self.trade_sundays: set[int] = set()

        # dni ustawowo wolne
        self.public_holidays: set[int] = set()
        self.standard_daily_hours = 8.0

        # -----------------------------
        # Godziny otwarcia per weekday
        # (0=Pn ... 6=Nd)
        # -----------------------------
        self.open_hours: dict[int, tuple[str, str]] = {
            0: ("05:30", "23:00"),
            1: ("05:30", "22:45"),
            2: ("05:30", "22:45"),
            3: ("05:30", "22:45"),
            4: ("05:30", "22:45"),
            5: ("05:30", "22:45"),
            6: ("05:30", "22:45"),  # Nd (jeśli handlowa)
        }

        # Opcjonalny, sztywny blok zmiany nocnej dla projektów bez
        # zdefiniowanych lokalizacji (patrz LocationConfig.night_shift w
        # model/location.py - to jest dokładnie ten sam mechanizm, tylko na
        # poziomie całego projektu). None = brak zmiany nocnej (domyślne).
        self.night_shift: dict | None = None

        # Opcjonalna konfiguracja rotacji służby 24/7 dla projektów bez
        # zdefiniowanych lokalizacji - patrz LocationConfig.duty_rotation /
        # normalize_duty_rotation() w model/location.py. None = domyślne.
        self.duty_rotation: dict | None = None

        # Ręcznie zdefiniowane, nazwane przedziały czasowe do trybu szybkiego
        # (ui/main_window.py::_build_quick_panel) - zastępują ręczne wpisywanie
        # godzin przyciskiem "Praca" (patrz "plan profil ochrona...", prośba
        # klienta 2026-09-17). Każdy wpis: {"name": str, "start": "HH:MM",
        # "end": "HH:MM" | None, "full_day": bool}. `end` jest None wyłącznie
        # gdy full_day=True (zmiana trwająca dokładnie 24h, patrz
        # DaySchedule.set_full_day_shift) - w przeciwnym razie zawsze ustawione,
        # ewentualnie <= start, co oznacza przejście przez północ. Pusta lista
        # domyślnie: stare projekty i te bez tej konfiguracji zachowują się
        # dokładnie jak dziś (przycisk "Praca" widoczny, ręczne wpisywanie).
        self.quick_mode_presets: list[dict] = []

        # Nowy projekt startuje zawsze z jedną, domyślną lokalizacją zasiedloną
        # z powyższych pól (patrz DEFAULT_LOCATION_KEY/_default_location_from_shop
        # wyżej) - "projekt zawsze ma co najmniej jedną lokalizację" jest
        # niezmiennikiem, na którym opiera się przełącznik placówek w UI.
        self.locations[DEFAULT_LOCATION_KEY] = _default_location_from_shop(
            self, DEFAULT_LOCATION_KEY, DEFAULT_LOCATION_NAME
        )

    # ==========================================================
    # PODSTAWOWE METODY
    # ==========================================================

    def reset_for_new_month(self, year: int, month: int) -> None:
        """Zmiana miesiąca dla TEGO SAMEGO projektu ("Zmień datę" w
        ui/main_window.py::_save_date_clicked) - zeruje tylko to, co jest
        specyficzne dla poprzedniego miesiąca (niedziele handlowe, święta,
        ręczne nadpisania dni - na poziomie projektu i każdej lokalizacji),
        zachowując WSZYSTKO inne bez zmian: profil działalności, lokalizacje
        (wraz z ich godzinami otwarcia/24-7/rotacją służby/progami obsady),
        presety trybu szybkiego, zasady generatora, nazwę placówki itd.
        Odwrotnie niż _init_state() w main_window.py, która przy "Nowym
        projekcie" świadomie tworzy zupełnie nowy, pusty ShopConfig."""
        self.year = year
        self.month = month
        self.trade_sundays = set()
        self.public_holidays = set()
        self.day_overrides = {}
        for location in self.locations.values():
            location.trade_sundays = set()
            location.public_holidays = set()
            location.day_overrides = {}

    def weekday(self, day: int) -> int:
        return calendar.weekday(self.year, self.month, day)

    def is_sunday(self, day: int) -> bool:
        return self.weekday(day) == 6

    def is_trade_day(self, day: int) -> bool:
        # "Dni handlowe" is a Dino/retail-specific concept - businesses
        # whose profile doesn't use it (see BusinessProfile.uses_trade_calendar)
        # treat every day as a normal potential working day.
        if not get_profile(self.business_type).uses_trade_calendar:
            return True

        if day in self.public_holidays:
            return False

        if self.is_sunday(day):
            return day in self.trade_sundays

        return True

    # ==========================================================
    # GODZINY OTWARCIA
    # ==========================================================

    def get_open_hours_for_day(self, day: int) -> tuple[str, str] | None:
        """
        Zwraca (open, close) albo None jeśli sklep zamknięty
        lub brak poprawnych godzin.
        """
        if not self.is_trade_day(day):
            return None

        # override ma najwyższy priorytet
        if day in self.day_overrides:
            start, end = self.day_overrides[day]
            if start and end:
                return start, end
            return None

        wd = self.weekday(day)
        hours = self.open_hours.get(wd)

        if not hours:
            return None

        start, end = hours
        if not start or not end:
            return None

        return start, end

    def get_open_hours_for_weekday(self, weekday: int) -> tuple[str, str]:
        return self.open_hours[weekday]

    def set_open_hours_for_weekday(self, weekday: int, start: str, end: str):
        self.open_hours[weekday] = (start, end)

    def get_night_shift_hours(self) -> tuple[str, str] | None:
        """(start, end) zmiany nocnej projektu, albo None gdy jej nie ma."""
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
        return self.duty_rotation

    def set_duty_rotation(self, raw: dict | None) -> None:
        self.duty_rotation = normalize_duty_rotation(raw)

    def get_round_clock_start_hour(self) -> str | None:
        # "Godzina rozpoczęcia" rotacji całodobowej (round_clock_constraint.py)
        # jest, tak jak `is_24_7`, wyłącznie polem LocationConfig - nie ma
        # (i nigdy nie miała) odpowiednika na poziomie projektu, więc ten
        # sam wzorzec co get_duty_rotation() wyżej, ale zawsze None: dotyczy
        # tylko pracownika bez rozwiązywalnej lokalizacji (patrz get_location()
        # niżej), dla którego ten mechanizm i tak nigdy nie ma zastosowania.
        return None

    def is_closed_for_public_holiday(self, day: int) -> bool:
        # Ten sam wzorzec co get_round_clock_start_hour() wyżej - wyłącznie
        # pole LocationConfig, ten fallback dotyczy tylko pracownika bez
        # rozwiązywalnej lokalizacji.
        return False

    # ==========================================================
    # PRESETY TRYBU SZYBKIEGO
    # ==========================================================

    def set_quick_mode_presets(self, raw: list[dict] | None) -> None:
        self.quick_mode_presets = normalize_quick_mode_presets(raw)

    # ==========================================================
    # LOKALIZACJE (Etap 3b)
    # ==========================================================

    def get_location(self, employee):
        """Godzinowy "widok" dla tego pracownika: jeśli ma przypisaną
        lokalizację (employee.location_key) i projekt ją definiuje, zwraca
        obiekt z tym samym API co ShopConfig (`weekday`/`get_open_hours_for_day`/
        `constraints`) wspierający się o tę lokalizację; w przeciwnym razie
        zwraca `self` - dokładnie dzisiejsza, jednolokalizacyjna ścieżka.
        """
        if self.locations and employee.location_key in self.locations:
            return _LocationView(
                self.locations[employee.location_key], self.year, self.month, self.constraints,
                uses_trade_calendar=get_profile(self.business_type).uses_trade_calendar,
            )
        return self

    # ==========================================================
    # SERIALIZACJA
    # ==========================================================

    def to_dict(self):
        return {
            "year": self.year,
            "month": self.month,
            "name": self.name,
            "business_type": self.business_type,
            "locations": {key: loc.to_dict() for key, loc in self.locations.items()},
            "open_hours": self.open_hours,
            "night_shift": self.night_shift,
            "duty_rotation": self.duty_rotation,
            "quick_mode_presets": self.quick_mode_presets,
            "trade_sundays": list(self.trade_sundays),
            "day_overrides": self.day_overrides,
            "constraints": self.constraints,
            "cell_display_mode": self.cell_display_mode,
            "hours_display_mode": self.hours_display_mode,
            "show_grid_legend": self.show_grid_legend,
            "public_holidays": list(self.public_holidays),
            "standard_daily_hours": self.standard_daily_hours,
            "constraint_policies": {
                name: policy.value if isinstance(policy, ConstraintPolicy) else policy
                for name, policy in self.constraint_policies.items()
            },
        }

    @classmethod
    def from_dict(cls, data):
        cfg = cls(data["year"], data["month"])
        cfg.name = data.get("name", "")
        cfg.business_type = data.get("business_type", DEFAULT_BUSINESS_TYPE)
        cfg.locations = {
            key: LocationConfig.from_dict(loc_data)
            for key, loc_data in data.get("locations", {}).items()
        }
        night_shift = data.get("night_shift")
        cfg.night_shift = dict(night_shift) if night_shift else None
        duty_rotation = data.get("duty_rotation")
        cfg.duty_rotation = dict(duty_rotation) if duty_rotation else None

        try:
            cfg.quick_mode_presets = normalize_quick_mode_presets(data.get("quick_mode_presets"))
        except ValueError:
            # Plik z ręcznie popsutą/starszą, niepoprawną konfiguracją -
            # traktujemy jak brak presetów zamiast blokować wczytanie projektu.
            cfg.quick_mode_presets = []

        # open_hours
        cfg.open_hours = {
            int(k): tuple(v)
            for k, v in data.get("open_hours", {}).items()
        }

        # niedziele handlowe
        cfg.trade_sundays = set(data.get("trade_sundays", []))

        #święta ustawowo wolne
        cfg.public_holidays = set(data.get("public_holidays", []))


        # override dni
        cfg.day_overrides = {
            int(day): tuple(hours)
            for day, hours in data.get("day_overrides", {}).items()
        }

        # constraints
        saved_constraints = data.get("constraints", {})
        cfg.constraints.update(saved_constraints)

        # UI
        cfg.cell_display_mode = data.get("cell_display_mode", "compact")
        cfg.hours_display_mode = data.get("hours_display_mode", "standard")
        cfg.show_grid_legend = data.get("show_grid_legend", False)
        cfg.standard_daily_hours = data.get("standard_daily_hours", 8.0)

        # Project files created before this field was added retain the defaults.
        for name, value in data.get("constraint_policies", {}).items():
            try:
                cfg.constraint_policies[name] = ConstraintPolicy(value)
            except ValueError:
                continue

        # "balance" jest celem optymalizacji, nie twardym wymogiem - MANDATORY
        # zrobiłby grafik niewykonalnym za każdym razem, gdy nie da się trafić
        # w bilans dokładnie, więc nigdy nie wczytujemy tej wartości z pliku.
        # DISABLED (np. profil ochrony, gdzie klient świadomie nie chce
        # bilansu wcale - "plan profil ochrona...", sekcja 10) zostaje.
        if cfg.constraint_policies.get("balance") == ConstraintPolicy.MANDATORY:
            cfg.constraint_policies["balance"] = ConstraintPolicy.PREFERRED

        if not cfg.locations:
            # Stary plik sprzed lokalizacji (Etap 3b) - migrujemy na jedną
            # domyślną lokalizację zasiedloną z pól projektu wczytanych
            # powyżej. `_migrated_default_location` (nieserializowane) mówi
            # persistence/project_io.py::load_project(), że trzeba jeszcze
            # dopiąć location_key każdemu pracownikowi.
            cfg.locations[DEFAULT_LOCATION_KEY] = _default_location_from_shop(
                cfg, DEFAULT_LOCATION_KEY, DEFAULT_LOCATION_NAME
            )
            cfg._migrated_default_location = True

        return cfg

    def get_full_time_nominal_hours(self) -> float:
        """
        Nominalny wymiar czasu pracy (pełny etat) dla danego miesiąca,
        zgodnie z Kodeksem pracy (art. 130 §1 i §2¹): liczba dni roboczych
        (pon-pt) w miesiącu, pomniejszona o:

        - święta ustawowo wolne od pracy przypadające w dzień powszedni
          (pon-pt) - każde obniża normę o jedną dniówkę, niezależnie od
          tego, czy akurat ten projekt normalnie w ten dzień pracuje (np.
          ochrona 24/7);
        - święto ustawowe przypadające w SOBOTĘ - art. 130 §2¹ każe wtedy
          oddać dodatkowy dzień wolny (obniża normę o dniówkę tak samo jak
          święto w tygodniu, mimo że sobota i tak nie była liczona jako dzień
          roboczy) - dotyczy WYŁĄCZNIE świąt ustawowych (auto-wykrytych),
          nie ręcznie zaznaczonych dni (te nie muszą być świętem w sensie
          ustawy o dniach wolnych od pracy, np. dzień wolny firmowy).

        Święta liczone automatycznie z biblioteki `holidays` (kalendarz
        polski - patrz logic/utils/holidays_pl.py), żeby nie trzeba było
        pamiętać o ręcznym zaznaczaniu ich co roku w każdym projekcie -
        zgłoszenie użytkownika (2026-09-25): program dotąd "prosto" liczył
        wyłącznie ręcznie zaznaczone self.public_holidays (unia z
        automatycznymi, na wypadek dnia wolnego spoza kalendarza krajowego,
        np. lokalnego/firmowego), bez obniżenia za sobotnie święta
        - zweryfikowane liczbowo (2026-09-25) na zestawieniu użytkownika
        wrzesień 2026 - wrzesień 2028 (24 miesiące): identyczne wartości po
        tej poprawce.
        """
        import calendar

        from logic.utils.holidays_pl import polish_public_holiday_days

        workdays = 0
        saturday_holidays = 0

        days_in_month = calendar.monthrange(self.year, self.month)[1]
        auto_holidays = polish_public_holiday_days(self.year, self.month)

        for d in range(1, days_in_month + 1):
            wd = calendar.weekday(self.year, self.month, d)
            is_holiday = d in auto_holidays or d in self.public_holidays

            if wd < 5:  # pon-pt
                if is_holiday:
                    continue
                workdays += 1
            elif wd == 5 and d in auto_holidays:  # sobota, święto ustawowe
                saturday_holidays += 1

        return (workdays - saturday_holidays) * self.standard_daily_hours
