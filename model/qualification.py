"""Kwalifikacje pracowników: role, umiejętności i uprawnienia.

Zastępują dawne, zaszyte na sztywno pola roli w Employee (is_opener,
is_meat, is_meat_light, is_manager) i słownik custom_roles jednym
mechanizmem:

- Qualification - pozycja katalogu projektu (MonthlyProject.qualifications):
  "co w ogóle można umieć" - nazwa, kod, ikona, rodzaj, opcjonalna skala
  poziomów, czy wymaga dat ważności.
- EmployeeQualification - przypisanie do konkretnego pracownika
  (Employee.qualifications): poziom, opcjonalne daty ważności i placówki,
  w których kwalifikacja obowiązuje (puste = wszystkie).

Klucz kwalifikacji (`Qualification.id` / `EmployeeQualification.
qualification_id`) to stały, czytelny identyfikator - dla ról przeniesionych
z profili custom to dokładnie dawny klucz z custom_roles ("umowa",
"nie_chce_24h", ...), więc reguły i pliki dalej się do siebie odnoszą.

no_night/no_afternoon to ograniczenia pracownika, nie kwalifikacje - zostają
osobnymi polami Employee (osobny krok migracji).
"""

from dataclasses import dataclass, field
from datetime import date

KIND_ROLE = "role"
KIND_SKILL = "skill"
KIND_CERTIFICATE = "certificate"
KINDS = (KIND_ROLE, KIND_SKILL, KIND_CERTIFICATE)
KIND_LABELS = {
    KIND_ROLE: "Rola",
    KIND_SKILL: "Umiejętność",
    KIND_CERTIFICATE: "Uprawnienie / certyfikat",
}

# Kwalifikacje powstałe z dawnych pól roli profilu Dino.
QUAL_OPENER = "otwarcie"
QUAL_MEAT = "mieso"
QUAL_MANAGER = "kierownik"
# Poziomy kwalifikacji "Mięso": 1 = dawne is_meat_light ("może stanąć na
# chwilę"), 2 = dawne is_meat (pełna obsługa stoiska).
MEAT_LEVEL_LIGHT = 1
MEAT_LEVEL_FULL = 2

# Pole poziomu, gdy kwalifikacja nie ma skali poziomów.
DEFAULT_LEVEL = 1


def _parse_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


@dataclass(frozen=True)
class QualificationLevel:
    value: int
    name: str

    def to_dict(self):
        return {"value": self.value, "name": self.name}

    @classmethod
    def from_dict(cls, data):
        return cls(value=int(data["value"]), name=data.get("name", ""))


@dataclass(frozen=True)
class Qualification:
    id: str
    name: str
    code: str = ""
    icon: str = ""
    kind: str = KIND_ROLE
    # Opcjonalna skala, rosnąco (np. 1 "pomocniczo", 2 "pełna obsługa").
    # Pusta = kwalifikacja bez poziomów (ma się ją albo nie, poziom 1).
    levels: tuple = ()
    requires_validity: bool = False
    # Dłuższy opis do podpowiedzi w UI (np. dawny opis roli z profilu).
    description: str = ""

    def level_values(self) -> tuple:
        return tuple(level.value for level in self.levels) or (DEFAULT_LEVEL,)

    def level_name(self, value: int) -> str:
        for level in self.levels:
            if level.value == value:
                return level.name
        return ""

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Kwalifikacja musi mieć klucz")
        if not self.name.strip():
            raise ValueError("Kwalifikacja musi mieć nazwę")
        if self.kind not in KINDS:
            raise ValueError(f"Nieznany rodzaj kwalifikacji: {self.kind}")
        values = [level.value for level in self.levels]
        if any(v < 1 for v in values) or len(set(values)) != len(values):
            raise ValueError("Poziomy kwalifikacji muszą być różnymi liczbami od 1 w górę")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "icon": self.icon,
            "kind": self.kind,
            "levels": [level.to_dict() for level in self.levels],
            "requires_validity": self.requires_validity,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data["id"],
            name=data.get("name") or data["id"],
            code=data.get("code", ""),
            icon=data.get("icon", ""),
            kind=data.get("kind", KIND_ROLE),
            levels=tuple(
                sorted((QualificationLevel.from_dict(level) for level in data.get("levels", [])),
                       key=lambda level: level.value)
            ),
            requires_validity=bool(data.get("requires_validity", False)),
            description=data.get("description", ""),
        )


@dataclass(frozen=True)
class EmployeeQualification:
    qualification_id: str
    level: int = DEFAULT_LEVEL
    valid_from: date | None = None
    valid_to: date | None = None
    # Klucze placówek (LocationConfig.key), w których kwalifikacja
    # obowiązuje. Puste = wszystkie.
    location_ids: tuple = field(default_factory=tuple)

    def is_valid_on(self, day: date | None) -> bool:
        """Czy kwalifikacja obowiązuje w dniu `day` (obie daty włącznie).
        `day` None = bez kontekstu daty (np. widok listy pracowników)."""
        if day is None:
            return True
        if self.valid_from is not None and day < self.valid_from:
            return False
        if self.valid_to is not None and day > self.valid_to:
            return False
        return True

    def applies_to_location(self, location_key: str | None) -> bool:
        if not self.location_ids or location_key is None:
            return True
        return location_key in self.location_ids

    def validate(self) -> None:
        if not self.qualification_id.strip():
            raise ValueError("Przypisanie kwalifikacji bez klucza")
        if self.level < 1:
            raise ValueError("Poziom kwalifikacji musi być co najmniej 1")
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("Data początku ważności kwalifikacji jest późniejsza niż data końca")

    def to_dict(self):
        return {
            "id": self.qualification_id,
            "level": self.level,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "location_ids": list(self.location_ids),
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            qualification_id=data["id"],
            level=int(data.get("level", DEFAULT_LEVEL)),
            valid_from=_parse_date(data.get("valid_from")),
            valid_to=_parse_date(data.get("valid_to")),
            location_ids=tuple(data.get("location_ids") or ()),
        )


def qualifications_of(*items) -> tuple:
    """Skrót do budowania Employee.qualifications: każdy element to klucz
    kwalifikacji albo para (klucz, poziom)."""
    result = []
    for item in items:
        if isinstance(item, EmployeeQualification):
            result.append(item)
        elif isinstance(item, tuple):
            key, level = item
            result.append(EmployeeQualification(key, level))
        else:
            result.append(EmployeeQualification(item))
    return tuple(result)


# ---------------------------------------------------------------------------
# Migracja z dawnych pól roli
# ---------------------------------------------------------------------------

LEGACY_ROLE_FIELDS = ("is_opener", "is_meat", "is_meat_light", "is_manager", "custom_roles")


def qualifications_from_legacy(data: dict) -> tuple:
    """Kwalifikacje pracownika zapisanego w dawnym formacie (pola is_opener,
    is_meat, is_meat_light, is_manager i słownik custom_roles):

    - is_opener -> "otwarcie",
    - is_meat -> "mieso" poziom 2, is_meat_light -> "mieso" poziom 1,
    - is_manager -> "kierownik",
    - custom_roles[k] == True -> kwalifikacja o kluczu k.

    custom_roles[k] == False (zapisywane przez dawne okno pracownika) nie
    tworzy kwalifikacji - znaczyło dokładnie to samo co brak wpisu."""
    result = []
    if data.get("is_opener"):
        result.append(EmployeeQualification(QUAL_OPENER))
    if data.get("is_meat"):
        result.append(EmployeeQualification(QUAL_MEAT, MEAT_LEVEL_FULL))
    elif data.get("is_meat_light"):
        result.append(EmployeeQualification(QUAL_MEAT, MEAT_LEVEL_LIGHT))
    if data.get("is_manager"):
        result.append(EmployeeQualification(QUAL_MANAGER))
    for key, value in (data.get("custom_roles") or {}).items():
        if value and key not in {q.qualification_id for q in result}:
            result.append(EmployeeQualification(key))
    return tuple(result)


def is_legacy_employee_data(data: dict) -> bool:
    return "qualifications" not in data


# ---------------------------------------------------------------------------
# Katalog
# ---------------------------------------------------------------------------

DINO_QUALIFICATIONS = (
    Qualification(
        id=QUAL_OPENER,
        name="Otwarcie",
        code="OTW",
        icon="builtin:open",
        description="Pracownik otwarcia",
    ),
    Qualification(
        id=QUAL_MEAT,
        name="Mięso",
        code="MIĘ",
        icon="builtin:meat",
        levels=(
            QualificationLevel(MEAT_LEVEL_LIGHT, "Pomocniczo – może stanąć na chwilę"),
            QualificationLevel(MEAT_LEVEL_FULL, "Pełna obsługa"),
        ),
        description="Obsługa stoiska mięsnego",
    ),
    Qualification(
        id=QUAL_MANAGER,
        name="Kierowniczka",
        code="KIER",
        icon="builtin:manager",
        description="Kierowniczka (sztywny grafik: pon. wolne, wt-pt 7:00-15:00, sob 6:00-14:00)",
    ),
)


def placeholder_qualification(key: str) -> Qualification:
    """Pozycja katalogu dla klucza, który jest na pracowniku, ale nie ma go w
    żadnym znanym katalogu (np. profil custom usunięty z tego komputera) -
    żeby przypisanie nie zniknęło z projektu przy pierwszym zapisie."""
    return Qualification(id=key, name=key)


def merge_catalog(catalog: dict, qualifications) -> None:
    """Dokłada do `catalog` (id -> Qualification) pozycje, których jeszcze w
    nim nie ma - istniejących nie nadpisuje (użytkownik mógł je edytować)."""
    for qualification in qualifications:
        catalog.setdefault(qualification.id, qualification)
