from dataclasses import dataclass, field
import uuid
from typing import Dict

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
    monthly_target_hours: int = field(default=160, compare=False)
    daily_hours: int = field(default=8, compare=False)

    # 🔥 NOWE POLE
    employment_fraction: float = field(default=1.0, compare=False)

    id: str = field(default_factory=lambda: str(uuid.uuid4()), compare=False)
    availability: Dict[int, dict] = field(default_factory=dict, compare=False)

    def display_name(self) -> str:
        return f"{self.last_name} {self.first_name}"

    def validate(self) -> None:
        if not self.last_name.strip():
            raise ValueError("Nazwisko nie może być puste")

        if not self.first_name.strip():
            raise ValueError("Imię nie może być puste")

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
