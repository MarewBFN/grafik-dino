from dataclasses import dataclass, field
import re
import uuid
from datetime import date
from typing import Dict

from model.qualification import (
    MEAT_LEVEL_FULL,
    MEAT_LEVEL_LIGHT,
    QUAL_MANAGER,
    QUAL_MEAT,
    QUAL_OPENER,
)

# Pola danych osobowych - patrz Employee.phone itd. niżej.
PERSONAL_DATA_FIELDS = ("phone", "email", "street", "postal_code", "city")

# Ograniczenia pracownika, które (jeszcze) nie są kwalifikacjami - osobne
# pola Employee, czytane przez has_role() po nazwie pola.
_RESTRICTION_FIELDS = {"no_night", "no_afternoon"}

# PRZEJŚCIOWE (Krok 1.1 -> 1.5 migracji na Qualification): klucze dawnych pól
# roli profilu Dino, które UI wciąż podaje do has_role() (RoleDef.key w
# model/business_profile.py) - mapowane na kwalifikację i warunek poziomu.
_LEGACY_ROLE_KEYS = {
    "is_opener": (QUAL_OPENER, None),
    "is_meat": (QUAL_MEAT, MEAT_LEVEL_FULL),
    "is_meat_light": (QUAL_MEAT, MEAT_LEVEL_LIGHT),
    "is_manager": (QUAL_MANAGER, None),
}
_LEGACY_QUALIFICATION_KEYS = {QUAL_OPENER, QUAL_MEAT, QUAL_MANAGER}

@dataclass(order=True, frozen=True)
class Employee:
    """
    Reprezentuje jednego pracownika.

    frozen=True:
    - obiekt jest hashowalny
    - może być bezpiecznie używany jako klucz w dict
    """

    # pola do sortowania
    last_name: str
    first_name: str

    # pozostałe dane (nie wpływają na sortowanie)
    no_night: bool = field(default=False, compare=False)
    no_afternoon: bool = field(default=False, compare=False)
    monthly_target_hours: int = field(default=160, compare=False)
    daily_hours: int = field(default=8, compare=False)

    # 🔥 NOWE POLE
    employment_fraction: float = field(default=1.0, compare=False)

    id: str = field(default_factory=lambda: str(uuid.uuid4()), compare=False)
    availability: Dict[int, dict] = field(default_factory=dict, compare=False)

    # Kwalifikacje (role, umiejętności, uprawnienia) - krotka
    # model.qualification.EmployeeQualification. Zastępuje dawne pola
    # is_opener/is_meat/is_meat_light/is_manager i słownik custom_roles
    # (migracja starych plików: model/qualification.py::qualifications_from_legacy).
    qualifications: tuple = field(default=(), compare=False)

    # Klucz lokalizacji (model.location.LocationConfig) do której przypisany
    # jest pracownik. Puste = brak przypisania (dzisiejsze, jednolokalizacyjne
    # zachowanie) - patrz ShopConfig.locations.
    location_key: str = field(default="", compare=False)

    # Dane osobowe (EmployeeDialog -> "Zaawansowane" -> "Dane kontaktowe")
    # - pod przyszłe wnioski urlopowe; generator ich nie używa. Puste = nie
    # podano.
    phone: str = field(default="", compare=False)
    email: str = field(default="", compare=False)
    street: str = field(default="", compare=False)
    postal_code: str = field(default="", compare=False)
    city: str = field(default="", compare=False)

    # Dni urlopu pozostałe do wykorzystania (z dokładnością do 0,5 dnia) -
    # wpisywane ręcznie w EmployeeDialog ("Pozostało urlopu" + przycisk
    # "Zmień") i pomniejszane automatycznie o urlop zaznaczony w grafiku
    # (logic/leave_requests.py::sync_vacation_balances), pokazywane przy
    # nazwisku w grid_view (ui/grid_view.py::EmployeeNameDelegate). Może zejść
    # poniżej zera, gdy zaznaczono więcej urlopu niż zostało. Generator
    # grafiku go nie używa - czysto informacyjne, jak dane osobowe wyżej.
    vacation_days_left: float = field(default=0, compare=False)

    # Klucz firmy (model.company.Company, MonthlyProject.companies), do której
    # należy pracownik - EmployeeDialog -> "Zaawansowane". Używane tylko w
    # nagłówku wniosków urlopowych. Puste = nie wybrano.
    company_key: str = field(default="", compare=False)

    def display_name(self) -> str:
        # Imię jest opcjonalne (patrz validate()) - bez niego samo
        # nazwisko, bez końcowej spacji.
        return f"{self.last_name} {self.first_name}".strip()

    def personal_data(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in PERSONAL_DATA_FIELDS}

    def address(self) -> str:
        """Adres zamieszkania w jednej linii (pusty, gdy nie podano)."""
        town = " ".join(part for part in (self.postal_code, self.city) if part)
        return ", ".join(part for part in (self.street, town) if part)

    # ------------------------------------------------------------------
    # Kwalifikacje
    # ------------------------------------------------------------------

    def qualification_level(self, key: str, on: date | None = None, location_key: str | None = None) -> int:
        """Poziom kwalifikacji `key` (0 = brak). Z `on` (data) liczą się tylko
        kwalifikacje ważne w tym dniu; z `location_key` - tylko obowiązujące
        w tej placówce. Bez nich - bez sprawdzania dat i placówek."""
        level = 0
        for qualification in self.qualifications:
            if qualification.qualification_id != key:
                continue
            if not qualification.is_valid_on(on) or not qualification.applies_to_location(location_key):
                continue
            level = max(level, qualification.level)
        return level

    def has_qualification(
        self, key: str, min_level: int = 1, on: date | None = None, location_key: str | None = None,
    ) -> bool:
        return self.qualification_level(key, on=on, location_key=location_key) >= min_level

    # ------------------------------------------------------------------
    # PRZEJŚCIOWE (Krok 1.1 -> 1.5): dawne nazwy ról jako widoki tylko do
    # odczytu, liczone z kwalifikacji (bez dat i placówek - dokładnie tak,
    # jak działały dawne pola). Jedynym źródłem danych są `qualifications`;
    # kolejne kroki migracji zastępują te odczyty jawnym has_qualification()
    # i usuwają poniższe właściwości.
    # ------------------------------------------------------------------

    @property
    def is_opener(self) -> bool:
        return self.has_qualification(QUAL_OPENER)

    @property
    def is_meat(self) -> bool:
        return self.qualification_level(QUAL_MEAT) >= MEAT_LEVEL_FULL

    @property
    def is_meat_light(self) -> bool:
        return self.qualification_level(QUAL_MEAT) == MEAT_LEVEL_LIGHT

    @property
    def is_manager(self) -> bool:
        return self.has_qualification(QUAL_MANAGER)

    @property
    def custom_roles(self) -> Dict[str, bool]:
        return {
            q.qualification_id: True
            for q in self.qualifications
            if q.qualification_id not in _LEGACY_QUALIFICATION_KEYS
        }

    def has_role(self, key: str) -> bool:
        """True gdy pracownik ma rolę `key`: dawny klucz pola Dino
        (is_opener, is_meat, ...), ograniczenie (no_night/no_afternoon) albo
        klucz kwalifikacji (dawne custom_roles)."""
        if key in _RESTRICTION_FIELDS:
            return bool(getattr(self, key))
        if key in _LEGACY_ROLE_KEYS:
            qualification_key, exact_level = _LEGACY_ROLE_KEYS[key]
            level = self.qualification_level(qualification_key)
            return level == exact_level if exact_level is not None else level >= 1
        return self.has_qualification(key)

    def validate(self) -> None:
        if not self.last_name.strip():
            raise ValueError("Nazwisko nie może być puste")

        # Imię jest opcjonalne - klient może nie znać/nie chcieć podawać
        # imion pracowników, samo nazwisko wystarcza do identyfikacji.

        seen_qualifications = set()
        for qualification in self.qualifications:
            qualification.validate()
            if qualification.qualification_id in seen_qualifications:
                raise ValueError(
                    f"Pracownik ma dwa razy tę samą kwalifikację: {qualification.qualification_id}"
                )
            seen_qualifications.add(qualification.qualification_id)

        # 🔧 ZMIANA – luzujemy ograniczenie
        if self.daily_hours <= 0:
            raise ValueError("Dzienna liczba godzin musi być większa od 0")

        # 🔥 NOWA WALIDACJA
        if self.employment_fraction <= 0 or self.employment_fraction > 1.01:
            raise ValueError("Wymiar etatu musi być w zakresie (0, 1]")

        for wd, cfg in self.availability.items():
            if wd < 0 or wd > 6:
                raise ValueError("Nieprawidłowy dzień tygodnia")

            # The mapper accepts several availability windows for one weekday.
            rules = cfg if isinstance(cfg, list) else [cfg]
            for rule in rules:
                if "start" not in rule or "end" not in rule:
                    raise ValueError("Brak godzin w availability")
                if rule.get("mode") not in ("hard", "soft"):
                    raise ValueError("Nieprawidłowy tryb availability")

        email = self.email.strip()
        if email and (email.count("@") != 1 or "." not in email.split("@")[1] or " " in email):
            raise ValueError("Nieprawidłowy adres e-mail")
        if self.phone.strip() and not re.fullmatch(r"\+?[0-9 ()-]{6,20}", self.phone.strip()):
            raise ValueError("Nieprawidłowy numer telefonu (dozwolone cyfry, spacje, „+”, „-”)")
        if self.postal_code.strip() and not re.fullmatch(r"\d{2}-\d{3}", self.postal_code.strip()):
            raise ValueError("Kod pocztowy musi mieć format 00-000")

