import dataclasses
import json
from model.month_schedule import MonthSchedule
from model.monthly_project import MonthlyProject
from model.shop_config import ShopConfig

# Znacznik formatu wielomiesięcznego - patrz save_project_bundle/
# load_project_bundle niżej. Pliki bez tego klucza to stary,
# jednomiesięczny format (albo z przed pamięci wielu miesięcy, albo zapisany
# przez save_project() poniżej, wciąż używane np. przez demo/*.py i
# logic/generator/trace.py, gdzie pojedynczy migawkowy plik jest tym, co
# faktycznie potrzebne).
_BUNDLE_FORMAT_MARKER = "multi_month_project"


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


def _month_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _parse_month_key(key: str) -> tuple[int, int]:
    year_str, month_str = key.split("-")
    return int(year_str), int(month_str)


def save_project_bundle(path, project: MonthlyProject, active_year: int, active_month: int) -> None:
    """Zapisuje CAŁY projekt wielomiesięczny (patrz model/monthly_project.py)
    - każdy miesiąc, jaki kiedykolwiek istniał w tej sesji, nie tylko
    aktualnie otwarty. To jest format .myp/last_project.json od pamięci
    wielu miesięcy - patrz load_project_bundle() niżej po wczytanie
    (rozumie też stary, jednomiesięczny format tych samych plików)."""
    data = {
        "format": _BUNDLE_FORMAT_MARKER,
        "format_version": 1,
        "active_month": _month_key(active_year, active_month),
        "months": {
            _month_key(year, month): {
                "schedule": schedule.to_dict(),
                "shop_config": shop_config.to_dict(),
            }
            for (year, month), (schedule, shop_config) in project.months.items()
        },
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_project_bundle(path) -> tuple[MonthlyProject, int, int]:
    """Wczytuje projekt wielomiesięczny zapisany przez save_project_bundle().
    Rozumie też stary, jednomiesięczny format (pliki sprzed tej funkcji,
    albo zapisane przez save_project() - np. demo/install_client_sample_data.py) -
    taki plik trafia jako jedyny miesiąc świeżego MonthlyProject, dokładnie
    tak jak dotychczasowe load_project() go zwracało, tylko opakowany.
    Zwraca (project, aktywny_rok, aktywny_miesiąc)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    project = MonthlyProject()

    if data.get("format") != _BUNDLE_FORMAT_MARKER:
        schedule = MonthSchedule.from_dict(data["schedule"])
        shop_config = ShopConfig.from_dict(data["shop_config"])
        assign_missing_location_keys(schedule, shop_config)
        project.put(schedule.year, schedule.month, schedule, shop_config)
        return project, schedule.year, schedule.month

    for key, month_data in data["months"].items():
        schedule = MonthSchedule.from_dict(month_data["schedule"])
        shop_config = ShopConfig.from_dict(month_data["shop_config"])
        assign_missing_location_keys(schedule, shop_config)
        project.put(schedule.year, schedule.month, schedule, shop_config)

    active_key = data.get("active_month")
    active = _parse_month_key(active_key) if active_key else None
    if active is None or not project.has(*active):
        # Brak jawnie zapisanego aktywnego miesiąca (albo wskazuje na coś,
        # czego jednak nie ma w "months") - najnowszy zapamiętany miesiąc to
        # rozsądny domyślny wybór.
        active = project.sorted_keys()[-1]

    return project, active[0], active[1]
