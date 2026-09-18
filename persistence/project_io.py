import dataclasses
import json
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig


def save_project(path, schedule: MonthSchedule, shop_config: ShopConfig):
    data = {
        "schedule": schedule.to_dict(),
        "shop_config": shop_config.to_dict()
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_project(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    schedule = MonthSchedule.from_dict(data["schedule"])
    shop_config = ShopConfig.from_dict(data["shop_config"])
    assign_missing_location_keys(schedule, shop_config)

    return schedule, shop_config


def assign_missing_location_keys(schedule: MonthSchedule, shop_config: ShopConfig) -> None:
    """Każdy projekt ma teraz zawsze >=1 lokalizację (patrz ShopConfig.from_dict) -
    dopina employee.location_key pracownikom, którzy nie mają jeszcze poprawnego
    przypisania: po migracji starego pliku (wszyscy trafiają do nowo utworzonej
    domyślnej lokalizacji), albo - dla już multi-lokalizacyjnego projektu z
    niekompletnymi przypisaniami (w tym po usunięciu lokalizacji w oknie
    "Lokalizacje" - patrz ui/main_window.py::_open_locations_dialog) - do
    pierwszej lokalizacji w kolejności."""
    if not shop_config.locations:
        return

    # Employee jest frozen (dataclasses.dataclass(frozen=True)) - nie da się
    # zmienić location_key w miejscu, trzeba podmienić element listy na kopię
    # z dataclasses.replace(). Bezpieczne dla MonthSchedule._data/settlement_targets
    # (słowniki kluczowane obiektem Employee): __eq__/__hash__ Employee liczy
    # się tylko z last_name/first_name (patrz model/employee.py - reszta pól
    # ma compare=False), więc kopia z inną location_key nadal trafia w ten
    # sam wpis słownika co oryginał.
    fallback_key = next(iter(shop_config.locations))
    migrated = getattr(shop_config, "_migrated_default_location", False)
    for i, emp in enumerate(schedule.employees):
        if migrated or emp.location_key not in shop_config.locations:
            schedule.employees[i] = dataclasses.replace(emp, location_key=fallback_key)

    # Ta funkcja jest teraz wołana wielokrotnie w trakcie życia projektu
    # (main_window.py::_sync_everything, jako bezpiecznik dla nowo dodanych
    # pracowników), nie tylko raz przy wczytaniu pliku - flaga migracji może
    # więc odpalić się tylko RAZ, inaczej każda kolejna synchronizacja
    # cofałaby ręczne przypisanie pracownika do innej lokalizacji z powrotem
    # na domyślną.
    if migrated:
        shop_config._migrated_default_location = False
