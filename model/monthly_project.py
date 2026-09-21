from typing import Dict, Optional, Tuple

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

    def has(self, year: int, month: int) -> bool:
        return (year, month) in self.months

    def get(self, year: int, month: int) -> Optional[Tuple[MonthSchedule, ShopConfig]]:
        return self.months.get((year, month))

    def put(self, year: int, month: int, schedule: MonthSchedule, shop_config: ShopConfig) -> None:
        self.months[(year, month)] = (schedule, shop_config)

    def sorted_keys(self) -> list[MonthKey]:
        return sorted(self.months.keys())


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
