from typing import Dict, Optional, Tuple

from model.company import Company
from model.qualification import Qualification, merge_catalog, placeholder_qualification
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig

MonthKey = Tuple[int, int]  # (year, month)


class MonthlyProject:
    """"Pamięć wielu miesięcy" - kontener trzymający jeden (MonthSchedule,
    ShopConfig) na każdy miesiąc, jaki kiedykolwiek istniał w tym projekcie,
    zamiast tylko tego aktualnie otwartego. Pozwala swobodnie wracać do
    wcześniej odwiedzonych miesięcy bez utraty danych (patrz
    ui/main_window.py::_switch_to_month) i jest tym, co faktycznie
    zapisuje/wczytuje persistence/project_io.py::save_project_bundle/
    load_project_bundle.

    Każdy miesiąc ma WŁASNY, niezależny ShopConfig (a nie jeden, współdzielony
    i zerowany przy każdej zmianie miesiąca jak wcześniej) - dzięki temu
    powrót do starego miesiąca pokazuje dokładnie te niedziele
    handlowe/nadpisania dni/święta, jakie tam faktycznie ustawiono, a nie
    stan wyzerowany przez późniejszą zmianę miesiąca."""

    def __init__(self):
        self.months: Dict[MonthKey, Tuple[MonthSchedule, ShopConfig]] = {}
        # Dane firm (Plik -> "Dane firmy") - wspólne dla wszystkich
        # miesięcy, patrz model/company.py.
        self.companies: Dict[str, Company] = {}
        # Katalog kwalifikacji projektu (id -> model.qualification.
        # Qualification) - jeden dla wszystkich miesięcy, z niego powstaje
        # lista ról w oknie pracownika. Uzupełniany przez
        # ensure_qualification_catalog().
        self.qualifications: Dict[str, Qualification] = {}

    def has(self, year: int, month: int) -> bool:
        return (year, month) in self.months

    def get(self, year: int, month: int) -> Optional[Tuple[MonthSchedule, ShopConfig]]:
        return self.months.get((year, month))

    def put(self, year: int, month: int, schedule: MonthSchedule, shop_config: ShopConfig) -> None:
        self.months[(year, month)] = (schedule, shop_config)

    def sorted_keys(self) -> list[MonthKey]:
        return sorted(self.months.keys())

    def ensure_qualification_catalog(self) -> None:
        """Uzupełnia katalog kwalifikacji:

        - o domyślne kwalifikacje profilu każdego miesiąca (model.
          business_profile.default_qualifications) - także później, gdy
          profil dostanie nową rolę albo miesiąc zmieni profil;
        - każda kwalifikacja, którą ma jakikolwiek pracownik, a której katalog
          nie zna (np. profil custom usunięty z tego komputera), dostaje
          pozycję zastępczą - żeby żadne przypisanie nie zniknęło.

        Istniejących pozycji nie zmienia ani nie usuwa (użytkownik mógł je
        edytować w Plik -> "Kwalifikacje")."""
        from model.business_profile import default_qualifications

        for key in self.sorted_keys():
            merge_catalog(self.qualifications, default_qualifications(self.months[key][1].business_type))

        for key in self.sorted_keys():
            schedule, _shop_config = self.months[key]
            for employee in schedule.employees:
                for qualification in employee.qualifications:
                    if qualification.qualification_id not in self.qualifications:
                        self.qualifications[qualification.qualification_id] = placeholder_qualification(
                            qualification.qualification_id
                        )

    def protected_qualifications(self) -> set:
        """Klucze kwalifikacji, których nie da się usunąć z katalogu:
        domyślne kwalifikacje profilu któregoś miesiąca (wróciłyby przy
        najbliższym uzupełnieniu katalogu, odwołują się do nich zasady
        generatora) i kwalifikacje użyte w regułach profilu custom."""
        from model.business_profile import default_qualifications, get_custom_profile

        protected = set()
        for key in self.sorted_keys():
            business_type = self.months[key][1].business_type
            protected.update(q.id for q in default_qualifications(business_type))
            custom = get_custom_profile(business_type)
            if custom is not None:
                protected.update(rule.qualification_key for rule in custom.rules if rule.qualification_key)
        return protected

    def qualification_usage(self) -> dict:
        """{klucz kwalifikacji: (liczba pracowników, najwyższy poziom)} we
        wszystkich miesiącach projektu (pracownik liczony raz)."""
        holders = {}
        top = {}
        for key in self.sorted_keys():
            for employee in self.months[key][0].employees:
                for qualification in employee.qualifications:
                    holders.setdefault(qualification.qualification_id, set()).add(employee.display_name())
                    top[qualification.qualification_id] = max(top.get(qualification.qualification_id, 0), qualification.level)
        return {key: (len(names), top[key]) for key, names in holders.items()}


MONTH_STATE_EMPTY = "empty"
MONTH_STATE_EDITING = "editing"
MONTH_STATE_READY = "ready"


def month_state_class(pair: Optional[Tuple[MonthSchedule, ShopConfig]]) -> str:
    """Klasyfikacja stanu miesiąca do kolorowego oznaczenia kafelka w oknie
    wyboru miesiąca (ui/month_picker_dialog.py) - szary/pusty, żółty/w
    edycji, zielony/gotowy. Patrz describe_month_state() niżej po tekstowy
    opis tego samego stanu."""
    if pair is None:
        return MONTH_STATE_EMPTY

    schedule, _ = pair
    if schedule.is_generated:
        return MONTH_STATE_READY

    has_any_shift_data = any(
        not schedule.get_day(emp, day).is_empty()
        for emp in schedule.employees
        for day in range(1, schedule.days_in_month + 1)
    )
    return MONTH_STATE_EDITING if has_any_shift_data else MONTH_STATE_EMPTY


def describe_month_state(pair: Optional[Tuple[MonthSchedule, ShopConfig]]) -> str:
    """Krótki, liczony na żywo (nie logowany osobno) opis stanu miesiąca do
    kafelka w oknie wyboru miesiąca (ui/month_picker_dialog.py) - np. "12
    lokacji, 8 pracowników, grafik gotowy" / "Pusty grafik". Liczenie na
    bieżąco z rzeczywistych danych miesiąca (zamiast osobnego logu zdarzeń w
    stylu "dodano pracownika X") oznacza zero ryzyka rozjazdu po
    cofnięciu/edycji - opis zawsze zgadza się z tym, co faktycznie jest w
    danym miesiącu."""
    state = month_state_class(pair)
    if pair is None or (state == MONTH_STATE_EMPTY and not pair[0].employees):
        return "Pusty grafik"

    schedule, shop_config = pair
    n_locations = len(shop_config.locations) if shop_config else 0
    n_employees = len(schedule.employees)

    state_label = {
        MONTH_STATE_READY: "Grafik gotowy",
        MONTH_STATE_EDITING: "W trakcie edycji",
        MONTH_STATE_EMPTY: "Pusty grafik",
    }[state]

    counts = []
    if n_locations:
        counts.append(f"{n_locations} {_pl_plural(n_locations, 'lokacja', 'lokacje', 'lokacji')}")
    if n_employees:
        counts.append(f"{n_employees} {_pl_plural(n_employees, 'pracownik', 'pracowników', 'pracowników')}")

    if not counts:
        return state_label
    return ", ".join(counts) + ", " + state_label.lower()


def _pl_plural(n: int, one: str, few: str, many: str) -> str:
    """Polska odmiana liczebnikowa: 1 -> `one`, 2-4 (poza 12-14) -> `few`,
    w każdym innym wypadku (w tym 0) -> `many`."""
    if n == 1:
        return one
    tens_and_units = n % 100
    if 12 <= tens_and_units <= 14:
        return many
    if 2 <= n % 10 <= 4:
        return few
    return many
