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

import calendar
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

# Kwalifikacje profilu Ochrona (dawne custom_roles - ten sam klucz).
QUAL_CONTRACT = "umowa"
QUAL_NO_24H = "nie_chce_24h"

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
# Kwalifikacja pracownika w konkretnym dniu grafiku
# ---------------------------------------------------------------------------
#
# Generator, kolorowanie siatki i diagnostyka pytają zawsze o konkretny dzień
# miesiąca: liczy się tylko kwalifikacja ważna tego dnia (valid_from/valid_to)
# i obowiązująca w placówce pracownika (location_ids). `employee` jest
# duck-typed (model.employee.Employee), żeby ten moduł nie importował modelu
# pracownika.


def level_on(employee, key: str, year: int, month: int, day: int) -> int:
    """Poziom kwalifikacji `key` pracownika w dniu year-month-day (0 = brak)."""
    return employee.qualification_level(
        key, on=date(year, month, day), location_key=employee.location_key or None,
    )


def has_on(employee, key: str, year: int, month: int, day: int, min_level: int = 1) -> bool:
    return level_on(employee, key, year, month, day) >= min_level


def held_in_month(employee, key: str, year: int, month: int, min_level: int = 1) -> bool:
    """Czy pracownik ma kwalifikację `key` ważną choć jeden dzień miesiąca -
    dla zasad liczonych za cały miesiąc naraz (np. priorytet godzin "Umowy",
    liczba osób zdolnych do zmian 24h w formule odpoczynku)."""
    days = calendar.monthrange(year, month)[1]
    return any(has_on(employee, key, year, month, day, min_level) for day in range(1, days + 1))


def held_every_day(employee, key: str, year: int, month: int, min_level: int = 1) -> bool:
    """Czy pracownik ma kwalifikację `key` ważną każdego dnia miesiąca."""
    days = calendar.monthrange(year, month)[1]
    return all(has_on(employee, key, year, month, day, min_level) for day in range(1, days + 1))


def level_in_month(employee, key: str, year: int, month: int) -> int:
    """Najwyższy poziom kwalifikacji `key` ważnej choć jeden dzień miesiąca
    w placówce pracownika (0 = brak) - do widoków całego miesiąca (ikony w
    siatce, lista pracowników). To samo co max(level_on(...)) po dniach
    miesiąca, ale bez sprawdzania każdego dnia osobno."""
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    location_key = employee.location_key or None
    return max(
        (
            qualification.level
            for qualification in employee.qualifications
            if qualification.qualification_id == key
            and qualification.applies_to_location(location_key)
            and (qualification.valid_from is None or qualification.valid_from <= last)
            and (qualification.valid_to is None or qualification.valid_to >= first)
        ),
        default=0,
    )


def qualification_marks(employee, catalog: dict, shop_config) -> list:
    """[(Qualification, poziom)] kwalifikacji pracownika ważnych choć jeden
    dzień miesiąca `shop_config` (w jego placówce), w kolejności katalogu -
    bez tych, których zasada jest w projekcie Wyłączona (Dino: "Mięso").
    Do widoków całego miesiąca: ikony w siatce, kolumna "Flagi"."""
    from model.constraint_policy import ConstraintPolicy

    order = {key: index for index, key in enumerate(catalog)}
    marks = []
    for assignment in sorted(employee.qualifications, key=lambda q: order.get(q.qualification_id, len(order))):
        key = assignment.qualification_id
        policy = QUALIFICATION_POLICIES.get(key)
        if policy and shop_config.constraint_policies.get(policy) == ConstraintPolicy.DISABLED:
            continue
        level = level_in_month(employee, key, shop_config.year, shop_config.month)
        if level < 1:
            continue
        marks.append((catalog.get(key) or placeholder_qualification(key), level))
    return marks


def is_opener_on(employee, year, month, day) -> bool:
    return has_on(employee, QUAL_OPENER, year, month, day)


def is_full_meat_on(employee, year, month, day) -> bool:
    """Dawne is_meat: pełna obsługa stoiska mięsnego (poziom >= 2)."""
    return level_on(employee, QUAL_MEAT, year, month, day) >= MEAT_LEVEL_FULL


def is_light_meat_on(employee, year, month, day) -> bool:
    """Dawne is_meat_light: "może stanąć na chwilę" (dokładnie poziom 1)."""
    return level_on(employee, QUAL_MEAT, year, month, day) == MEAT_LEVEL_LIGHT


def is_manager_on(employee, year, month, day) -> bool:
    return has_on(employee, QUAL_MANAGER, year, month, day)


def refuses_24h_on(employee, year, month, day) -> bool:
    return has_on(employee, QUAL_NO_24H, year, month, day)


def can_work_24h_in_month(employee, year, month) -> bool:
    """Do liczby osób zdolnych do zmian 24 h (odpoczynek (N-1)x24 h po
    służbie 24 h) liczy się każdy, kto choć jeden dzień miesiąca nie ma
    kwalifikacji "Nie chce 24h"."""
    return not held_every_day(employee, QUAL_NO_24H, year, month)


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


CONTRACT_QUALIFICATION = Qualification(
    id=QUAL_CONTRACT,
    name="Umowa",
    icon="builtin:contract",
    description="Pierwszeństwo przy rozdzielaniu godzin (umowa o pracę).",
)
NO_24H_QUALIFICATION = Qualification(
    id=QUAL_NO_24H,
    name="Nie chce 24h",
    icon="builtin:no_24h",
    description=(
        "Ta osoba nie dostanie od generatora zmiany 24h w sobotę ani niedzielę - "
        "doba jest wtedy dzielona na dwie zmiany po 12h (rotacja 24/7 i placówki "
        "z dobą w godzinach otwarcia)."
    ),
)

# Pozycje katalogu, które program zna niezależnie od profilu (rysowane
# ikony w siatce, opisy) - źródło dla katalogów domyślnych i pozycji
# zastępczych.
KNOWN_QUALIFICATIONS = {
    qualification.id: qualification
    for qualification in (*DINO_QUALIFICATIONS, CONTRACT_QUALIFICATION, NO_24H_QUALIFICATION)
}

# Kwalifikacja ukrywana w oknie pracownika, gdy zasada generatora, która z
# niej korzysta, jest w projekcie Wyłączona (Dino: "Mięso" przy wyłączonych
# zasadach mięsa). Przypisania pracowników zostają bez zmian.
QUALIFICATION_POLICIES = {QUAL_MEAT: "meat"}

# Kwalifikacje, których poziomy generator czyta na sztywno (Dino "Mięso":
# 1 = pomocniczo, 2 = pełna obsługa) - w katalogu można zmienić tylko nazwy
# poziomów, nie ich liczbę.
FIXED_LEVEL_COUNTS = {QUAL_MEAT: 2}


def placeholder_qualification(key: str) -> Qualification:
    """Pozycja katalogu dla klucza, który jest na pracowniku, ale nie ma go w
    katalogu projektu (np. profil custom usunięty z tego komputera) - żeby
    przypisanie nie zniknęło z projektu przy pierwszym zapisie. Znane
    programowi kwalifikacje dostają swoją pełną definicję."""
    return KNOWN_QUALIFICATIONS.get(key) or Qualification(id=key, name=key)


def merge_catalog(catalog: dict, qualifications) -> None:
    """Dokłada do `catalog` (id -> Qualification) pozycje, których jeszcze w
    nim nie ma - istniejących nie nadpisuje (użytkownik mógł je edytować)."""
    for qualification in qualifications:
        catalog.setdefault(qualification.id, qualification)
