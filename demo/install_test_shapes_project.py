"""Projekt testowy zbierający wszystkie "kształty" rotacji 24/7
przetestowane w tests/test_duty_rotation_shift_length_variants.py i
tests/test_leave_sick_generation_sweep.py - do wizualnej inspekcji w
programie (nie tylko przez asercje pytest). Zapisuje PROSTO do
last_project.json (plik auto-wczytywany przy starcie programu, patrz
ui/main_window.py::_try_load_last_project) - NADPISUJE dowolny wcześniejszy
last_project.json.

Siedem lokalizacji:

1. Ubojnia Drobiu GOSZ - waga/biuro - realny wzorzec klienta (12h+12h
   @08:00, wszyscy "nie_chce_24h" - wymusza podział każdego dnia).
2. PGE Ustka, ul. Westerplatte 4 - realny wzorzec klienta ("8/8" - zmiana
   24h @08:00, nikt bez "nie_chce_24h" - generator wybiera sam).
3-6. Cztery syntetyczne kształty z testów: 7/7 (24h @07:00), 8/16 i 9/17
   (podział asymetryczny 8h+16h, różne anchory), anchor na pół godziny
   (08:30) - wszystkie z wymuszonym podziałem via "nie_chce_24h" poza 7/7.
7. Tydzień @09:00-17:00 (8h/16h) + weekend @06:00 (12h/12h) - dwa
   niezależne anchory w jednym projekcie (only_12_24h=False).

Rejestruje profil biznesowy "test_duty_rotation_shapes" w
%LOCALAPPDATA%\\GrafikDino\\custom_profiles.json - bez tego projekt
otworzyłby się z generatorem Dino zamiast Enyo.

Użycie:
    python demo/install_test_shapes_project.py
    python main.py
"""

import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.generator.custom_profile_wiring import default_policies
from model.business_profile import register_custom_profile
from model.constraint_policy import ConstraintPolicy
from model.custom_profile import CustomBusinessProfile, RoleDefinition
from model.custom_profile_store import save_custom_profile
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from persistence.project_io import save_project

PROFILE_KEY = "test_duty_rotation_shapes"
OUTPUT_PATH = ROOT / "last_project.json"

ROLE_UMOWA = "umowa"
ROLE_NIE_CHCE_24H = "nie_chce_24h"

YEAR, MONTH = 2026, 10


def build_profile() -> CustomBusinessProfile:
    return CustomBusinessProfile(
        key=PROFILE_KEY,
        display_name="Test - kształty rotacji 24/7",
        roles=[
            RoleDefinition(key=ROLE_UMOWA, label="Umowa", show_summary_row=False),
            RoleDefinition(key=ROLE_NIE_CHCE_24H, label="Nie chce 24h", show_summary_row=False),
        ],
        rules=[],
    )


def _location(key: str, name: str, rotation: dict) -> LocationConfig:
    loc = LocationConfig(key=key, name=name)
    loc.set_duty_rotation(rotation)
    return loc


LOCATIONS = [
    _location(
        "ubojnia_gosz_waga_biuro", "Ubojnia Drobiu GOSZ - waga/biuro (realny klient, 12h+12h @08:00)",
        {"only_12_24h": True, "weekend_full": {"start": "08:00"},
         "weekend_half_a": {"start": "08:00", "end": "20:00"},
         "weekend_half_b": {"start": "20:00", "end": "08:00"}},
    ),
    _location(
        "pge_ustka_westerplatte", "PGE Ustka, ul. Westerplatte 4 (realny klient, \"8/8\" - 24h @08:00)",
        {"only_12_24h": True, "weekend_full": {"start": "08:00"},
         "weekend_half_a": {"start": "08:00", "end": "20:00"},
         "weekend_half_b": {"start": "20:00", "end": "08:00"}},
    ),
    _location(
        "test_7_7", "Test 7/7 (24h @07:00)",
        {"only_12_24h": True, "weekend_full": {"start": "07:00"},
         "weekend_half_a": {"start": "07:00", "end": "19:00"},
         "weekend_half_b": {"start": "19:00", "end": "07:00"}},
    ),
    _location(
        "test_8_16_split", "Test 8/16 (podział 8h+16h @08:00)",
        {"only_12_24h": True, "weekend_full": {"start": "08:00"},
         "weekend_half_a": {"start": "08:00", "end": "16:00"},
         "weekend_half_b": {"start": "16:00", "end": "08:00"}},
    ),
    _location(
        "test_9_17_split", "Test 9/17 (podział 8h+16h @09:00)",
        {"only_12_24h": True, "weekend_full": {"start": "09:00"},
         "weekend_half_a": {"start": "09:00", "end": "17:00"},
         "weekend_half_b": {"start": "17:00", "end": "09:00"}},
    ),
    _location(
        "test_anchor_0830", "Test anchor 08:30 (podział 8h+16h)",
        {"only_12_24h": True, "weekend_full": {"start": "08:30"},
         "weekend_half_a": {"start": "08:30", "end": "16:30"},
         "weekend_half_b": {"start": "16:30", "end": "08:30"}},
    ),
    _location(
        "test_weekday_9_17_weekend_6", "Test tydzień @09:00-17:00 + weekend @06:00 (dwa anchory)",
        {"only_12_24h": False,
         "weekday_long": {"start": "09:00", "end": "17:00"},
         "weekday_short": {"start": "17:00", "end": "09:00"},
         "weekend_full": {"start": "06:00"},
         "weekend_half_a": {"start": "06:00", "end": "18:00"},
         "weekend_half_b": {"start": "18:00", "end": "06:00"}},
    ),
]

# (location_key, [(last_name, first_name, nie_chce_24h)])
UBOJNIA_GOSZ_EMPLOYEES = [
    ("Piepiórka", "?", True), ("Krefft", "?", True), ("Szyca", "?", True),
    ("Młyński", "?", True), ("Gołębiewski", "?", True), ("Krauze", "?", True), ("Stencel", "?", True),
]
PGE_USTKA_EMPLOYEES = [
    ("Korzyński", "K.", False), ("Krzysztofiak", "Z.", False),
    ("Kaufman", "M.", False), ("Pośpiech", "J.", False),
]


def _synthetic_employees(prefix: str, count: int, nie_chce_24h: bool) -> list:
    return [(f"{prefix}{i}", "Test", nie_chce_24h) for i in range(1, count + 1)]


EMPLOYEES_BY_LOCATION = {
    "ubojnia_gosz_waga_biuro": UBOJNIA_GOSZ_EMPLOYEES,
    "pge_ustka_westerplatte": PGE_USTKA_EMPLOYEES,
    "test_7_7": _synthetic_employees("Siedem", 3, nie_chce_24h=False),
    "test_8_16_split": _synthetic_employees("Osiem", 4, nie_chce_24h=True),
    "test_9_17_split": _synthetic_employees("Dziewiec", 4, nie_chce_24h=True),
    "test_anchor_0830": _synthetic_employees("Wpol", 4, nie_chce_24h=True),
    "test_weekday_9_17_weekend_6": _synthetic_employees("Tydzien", 4, nie_chce_24h=False),
}


def build_shop_config(profile: CustomBusinessProfile) -> ShopConfig:
    shop = ShopConfig(YEAR, MONTH)
    shop.name = "Test - kształty rotacji 24/7 (wszystkie placówki z testów)"
    shop.business_type = profile.key
    shop.locations = {loc.key: loc for loc in LOCATIONS}
    shop.constraint_policies.update(default_policies(profile))
    # Etap D (jak w innych projektach Enyo): pełne pokrycie > nominalny czas pracy.
    shop.constraint_policies["balance"] = ConstraintPolicy.DISABLED
    shop.constraint_policies["monthly_hours"] = ConstraintPolicy.DISABLED
    return shop


def build_employees() -> list:
    employees = []
    for location_key, roster in EMPLOYEES_BY_LOCATION.items():
        for last_name, first_name, nie_chce_24h in roster:
            employees.append(Employee(
                last_name=last_name, first_name=first_name,
                employment_fraction=1.0, location_key=location_key,
                custom_roles={ROLE_NIE_CHCE_24H: True} if nie_chce_24h else {},
            ))
    return employees


def install_profile() -> CustomBusinessProfile:
    profile = build_profile()
    save_custom_profile(profile)
    register_custom_profile(profile)
    return profile


def build_project():
    profile = install_profile()
    shop = build_shop_config(profile)

    schedule = MonthSchedule(YEAR, MONTH)
    for emp in build_employees():
        schedule.add_employee(emp)

    return schedule, shop


def main() -> None:
    schedule, shop = build_project()
    save_project(str(OUTPUT_PATH), schedule, shop)
    print(f"Zainstalowano profil '{PROFILE_KEY}' i zapisano projekt w {OUTPUT_PATH}")
    print(f"Lokalizacje: {', '.join(loc.name for loc in LOCATIONS)}")
    print(f"Pracowników: {len(schedule.employees)}")
    print("Uruchom: python main.py - projekt wczyta się automatycznie (last_project.json).")


if __name__ == "__main__":
    main()
