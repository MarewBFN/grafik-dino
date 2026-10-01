from dataclasses import dataclass, field
import re
import uuid
from typing import Dict

# Pola danych osobowych - patrz Employee.phone itd. niżej.
PERSONAL_DATA_FIELDS = ("phone", "email", "street", "postal_code", "city")

_ROLE_FIELDS = {
    "is_opener", "is_meat", "is_meat_light", "is_manager", "no_night", "no_afternoon",
}

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
    is_opener: bool = field(default=False, compare=False)
    is_meat: bool = field(default=False, compare=False)
    is_meat_light: bool = field(default=False, compare=False)
    is_manager: bool = field(default=False, compare=False)
    no_night: bool = field(default=False, compare=False)
    no_afternoon: bool = field(default=False, compare=False)
    monthly_target_hours: int = field(default=160, compare=False)
    daily_hours: int = field(default=8, compare=False)

    # 🔥 NOWE POLE
    employment_fraction: float = field(default=1.0, compare=False)

    id: str = field(default_factory=lambda: str(uuid.uuid4()), compare=False)
    availability: Dict[int, dict] = field(default_factory=dict, compare=False)

    # Role spoza sześciu pól powyżej (np. dla innych profili działalności niż
    # Dino), trzymane jako słownik zamiast kolejnych pól dataclass.
    custom_roles: Dict[str, bool] = field(default_factory=dict, compare=False)

    # Klucz lokalizacji (model.location.LocationConfig) do której przypisany
    # jest pracownik. Puste = brak przypisania (dzisiejsze, jednolokalizacyjne
    # zachowanie) - patrz ShopConfig.locations.
    location_key: str = field(default="", compare=False)

    # Dane osobowe (Pracownicy -> Zaawansowane) - pod przyszłe wnioski
    # urlopowe; generator ich nie używa. Puste = nie podano.
    phone: str = field(default="", compare=False)
    email: str = field(default="", compare=False)
    street: str = field(default="", compare=False)
    postal_code: str = field(default="", compare=False)
    city: str = field(default="", compare=False)

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

    def has_role(self, key: str) -> bool:
        """True if this employee carries role `key`, whether it's one of the
        six legacy Dino fields (is_opener, is_meat, ...) or a custom_roles
        entry from another business profile."""
        if key in _ROLE_FIELDS:
            return bool(getattr(self, key))
        return bool(self.custom_roles.get(key, False))

    def validate(self) -> None:
        if not self.last_name.strip():
            raise ValueError("Nazwisko nie może być puste")

        # Imię jest opcjonalne - klient może nie znać/nie chcieć podawać
        # imion pracowników, samo nazwisko wystarcza do identyfikacji.

        if self.is_meat and self.is_meat_light:
            raise ValueError("Pracownik nie może mieć jednocześnie flagi mięsa i \"może stanąć na chwilę na mięsie\"")

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
