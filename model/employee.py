from dataclasses import dataclass, field
import uuid

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
    monthly_target_hours: int = field(default=160, compare=False)
    daily_hours: int = field(default=8, compare=False)

    id: str = field(default_factory=lambda: str(uuid.uuid4()), compare=False)

    def display_name(self) -> str:
        return f"{self.last_name} {self.first_name}"

    def validate(self) -> None:
        if not self.last_name.strip():
            raise ValueError("Nazwisko nie może być puste")

        if not self.first_name.strip():
            raise ValueError("Imię nie może być puste")

        if self.daily_hours < 6 or self.daily_hours > 8:
            raise ValueError("Dzienna liczba godzin musi być w zakresie 6–8")
