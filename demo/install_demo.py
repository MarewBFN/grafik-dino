"""Jednorazowy instalator danych demo dla klienta z firmy ochroniarskiej
(Enyo/Michał) - patrz CLIENT_DEMO_README.md w katalogu głównym repo.

Robi dokładnie to samo, co ProfileWizardDialog + "Nowy projekt" + "Generuj
grafik" zrobiłyby ręcznie w UI, tylko bez klikania:

1. Buduje profil biznesowy "Ochrona" (dwie role - "Umowa" i "Nie chce
   24h" - patrz "plan profil ochrona (analiza specyfikacji klienta).md",
   sekcja 9 pkt 1) i zapisuje go tam, gdzie normalnie zapisuje go kreator
   w UI (%LOCALAPPDATA%\\GrafikDino\\custom_profiles.json) - profil jest
   więc trwały i widoczny też w kreatorze/Konfiguracji, nie tylko w tym
   demo. Te dwie role celowo NIE mają żadnej reguły (custom.rules=[]) -
   to same checkboxy w EmployeeDialog, zapisywane w Employee.custom_roles
   i przechodzące przez zapis/odczyt projektu bez żadnego wpływu na
   generator - przyszłe flagi pod zmienne godziny/zmianę 24h (sekcje
   4.4/7 planu), które czekają na odpowiedzi klienta, nie gotowa reguła.
2. Buduje przykładowy projekt (obiekt otwarty 07:00-21:00 + zmiana nocna
   21:00-07:00, kilku pracowników z różnymi wymiarami etatu i rolami) i
   generuje dla niego grafik na bieżący miesiąc.
3. Zapisuje ten projekt jako last_project.json w katalogu repo - dokładnie
   ten plik, który MainWindow wczytuje automatycznie przy starcie
   (main_window.py::_try_load_last_project). Plik jest już w .gitignore,
   więc to nie rusza kontroli wersji.

Użycie:
    python demo/install_demo.py
    python main.py
"""

import sys
from datetime import date
from pathlib import Path

# Generator drukuje na stdout kilka linii z emoji (np. "✅ ROZWIĄZANIE
# ZNALEZIONE" w logic/generator/solution_mapper.py) - na domyślnej
# konsoli Windows (cp1250/852) to bez tego crashuje z UnicodeEncodeError
# zanim projekt demo zdąży się zapisać. Wymuszamy UTF-8 na wyjściu tylko
# tego procesu, bez ruszania samego generatora.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.auto_generator import AutoScheduleGenerator
from logic.generator.custom_profile_wiring import default_policies
from model.business_profile import register_custom_profile
from model.custom_profile import CustomBusinessProfile, RoleDefinition
from model.custom_profile_store import save_custom_profile
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from persistence.project_io import save_project

PROFILE_KEY = "ochrona_enyo"
LAST_PROJECT_PATH = ROOT / "last_project.json"

# Obiekt "otwarty" 07:00-21:00 (dwie zachodzące na siebie zmiany dzienne,
# OPEN 07:00-15:00 / CLOSE 13:00-21:00) + zmiana nocna 21:00-07:00
# (SHIFT_NIGHT, mechanizm gotowy od Etapu A-G "plan zmiany nocne (24-7).md")
# - razem pełna doba, bez sięgania po niezaimplementowaną jeszcze zmianę
# 24h/16h/12h per pracownik (patrz README, sekcja "Czego tu NIE ma").
DAY_OPEN = "07:00"
DAY_CLOSE = "21:00"
NIGHT_START = "21:00"
NIGHT_END = "07:00"

ROLE_UMOWA = "umowa"
ROLE_NIE_CHCE_24H = "nie_chce_24h"


def build_profile() -> CustomBusinessProfile:
    return CustomBusinessProfile(
        key=PROFILE_KEY,
        display_name="Ochrona",
        roles=[
            RoleDefinition(key=ROLE_UMOWA, label="Umowa", show_summary_row=False),
            RoleDefinition(key=ROLE_NIE_CHCE_24H, label="Nie chce 24h", show_summary_row=False),
        ],
        # Celowo bez żadnej reguły - patrz docstring modułu. Te dwie flagi
        # nie robią dziś nic w generatorze, tylko zapisują się na pracowniku.
        rules=[],
    )


def install_profile() -> CustomBusinessProfile:
    profile = build_profile()
    save_custom_profile(profile)
    register_custom_profile(profile)
    return profile


def build_shop_config(profile: CustomBusinessProfile, year: int, month: int) -> ShopConfig:
    shop = ShopConfig(year, month)
    shop.name = "Enyo Ochrona — obiekt testowy"
    shop.business_type = profile.key

    shop.standard_daily_hours = 8.0
    shop.constraints["force_fulltime_845"] = False
    for weekday in range(7):
        shop.open_hours[weekday] = (DAY_OPEN, DAY_CLOSE)
    shop.set_night_shift(NIGHT_START, NIGHT_END)

    shop.constraint_policies.update(default_policies(profile))
    return shop


def build_employees() -> list[Employee]:
    return [
        Employee(last_name="Kowalski", first_name="Jan", employment_fraction=1.0, custom_roles={ROLE_UMOWA: True}),
        Employee(last_name="Nowak", first_name="Anna", employment_fraction=1.0, custom_roles={ROLE_UMOWA: True}),
        Employee(
            last_name="Wiśniewski", first_name="Piotr",
            employment_fraction=0.75,  # "6/8"
            custom_roles={ROLE_NIE_CHCE_24H: True},
        ),
        Employee(
            last_name="Zielińska", first_name="Ewa",
            employment_fraction=0.5,
            custom_roles={ROLE_NIE_CHCE_24H: True},
        ),
        Employee(last_name="Kamiński", first_name="Tomasz", employment_fraction=1.0),
    ]


def _add_overtime_example(schedule: MonthSchedule, employee: Employee) -> None:
    """Ręcznie dokłada jedną dodatkową zmianę ponad to, co ułożył generator,
    żeby projekt demo od razu pokazywał podświetlenie przekroczenia limitu
    (logic/monthly_hours_status.py) bez polegania na tym, jak akurat trafi
    solver."""
    for day in range(1, schedule.days_in_month + 1):
        ds = schedule.get_day(employee, day)
        if ds.is_empty() and not ds.is_leave and not getattr(ds, "is_sick", False):
            ds.set_hours(DAY_OPEN, DAY_CLOSE)
            ds.is_locked = True
            return


def build_demo_project() -> tuple[MonthSchedule, ShopConfig]:
    profile = install_profile()

    today = date.today()
    shop = build_shop_config(profile, today.year, today.month)

    schedule = MonthSchedule(today.year, today.month)
    employees = build_employees()
    for emp in employees:
        schedule.add_employee(emp)

    result = AutoScheduleGenerator(shop=shop, schedule=schedule).generate(solver_time_limit_seconds=30)
    if not result["success"]:
        raise RuntimeError(f"Generator nie znalazł rozwiązania dla projektu demo: {result}")

    _add_overtime_example(schedule, employees[-1])

    return schedule, shop


def main() -> None:
    schedule, shop = build_demo_project()
    save_project(str(LAST_PROJECT_PATH), schedule, shop)
    print(f"Zainstalowano profil '{PROFILE_KEY}' i zapisano projekt demo w {LAST_PROJECT_PATH}")
    print("Uruchom teraz: python main.py")


if __name__ == "__main__":
    main()
