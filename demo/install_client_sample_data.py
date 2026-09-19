"""Dane testowe z REALNYCH grafików klienta (firma ochroniarska/serwisowa),
odczytane ręcznie ze zdjęć papierowych kart przez użytkownika - patrz
"ENYO_ONLY_CHANGES.md", sekcja "Dane testowe z realnych grafików klienta
(2026-09-19)" po pełny opis źródła, niepewnych odczytów i placówek
świadomie pominiętych (nie mieszczą się w dzisiejszym modelu duty_rotation
- patrz ta sama sekcja).

W przeciwieństwie do demo/install_demo.py (syntetyczny, wyimaginowany
przykład) - to są PRAWDZIWE nazwiska i PRAWDZIWE (choć częściowo niepewnie
odczytane) wzorce zmian dwóch placówek, które faktycznie pasują do modelu
duty_rotation (obie mają potwierdzoną zmianę dzienną I nocną/24h - patrz
normalize_duty_rotation(), które wymaga kompletnego schematu, nie da się
skonfigurować samej połowy doby):

1. Ubojnia Drobiu GOSZ - waga/biuro: 7 pracowników, obserwowany wzorzec
   8:00-20:00 (dzień) + 20:00-8:00 (noc), naprzemiennie, każdego dnia
   tygodnia (only_12_24h). Realny grafik NIGDY nie pokazuje pojedynczej
   zmiany 24h - stąd wszyscy pracownicy dostają rolę "nie_chce_24h", żeby
   generator też nigdy jej nie użył (weekend_full jest polem wymaganym
   przez normalize_duty_rotation, ale strukturalnie niedostępnym dla
   każdego, kto ma tę flagę - patrz add_duty_rotation_no24h_gate_constraint).
2. PGE Ustka, ul. Westerplatte 4: 4 pracowników (z 6 wypisanych - 2
   nazwiska nieczytelne/skreślone, pominięte), obserwowany wzorzec to
   powtarzające się "8/8" - czyli DOKŁADNIE zmiana 24h co dzień
   (only_12_24h, weekend_full). Świadomie ŻADEN pracownik nie ma tu flagi
   "nie_chce_24h" - real dane nigdy nie pokazują podziału 12h+12h w tej
   placówce, w przeciwieństwie do Ubojni. To dobry test na to, czy nowa
   preferencja generatora (12h+12h zamiast 24h,
   logic/generator/duty_rotation_preference.py) zacznie w praktyce
   proponować podział, którego ta konkretna placówka historycznie nigdy
   nie stosowała - do obserwacji przy generowaniu, nie zakładamy z góry,
   który wariant jest "poprawny" dla tego miejsca.

Żaden pracownik nie ma tu flagi "Umowa" - z samych zdjęć nie da się
stwierdzić, kto ją ma. To jedna z rzeczy do ustalenia z klientem (patrz
ENYO_ONLY_CHANGES.md) - profil poniżej i tak definiuje tę rolę, więc da
się ją zaznaczyć ręcznie w UI (Edytuj pracownika) dla konkretnych osób,
gdy klient to potwierdzi, bez ponownego generowania danych testowych.

Użycie:
    python demo/install_client_sample_data.py
    python main.py

Zapisuje projekt do test_data/dane_klienta_ochrona.json (NIE nadpisuje
last_project.json/demo istniejącego last_project - otwórz ręcznie przez
"Otwórz projekt..." w menu programu). Rejestruje też profil biznesowy w
%LOCALAPPDATA%\\GrafikDino\\custom_profiles.json (jak
ProfileWizardDialog/install_demo.py) - bez tego projekt otworzyłby się z
generatorem Dino zamiast Enyo (get_custom_profile() zwróciłaby None).
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

PROFILE_KEY = "ochrona_dane_klienta_test"
OUTPUT_PATH = ROOT / "test_data" / "dane_klienta_ochrona.json"

ROLE_UMOWA = "umowa"
ROLE_NIE_CHCE_24H = "nie_chce_24h"

YEAR, MONTH = 2026, 10  # najbliższy pełny miesiąc od dnia przygotowania danych


def build_profile() -> CustomBusinessProfile:
    return CustomBusinessProfile(
        key=PROFILE_KEY,
        display_name="Ochrona (dane klienta - test)",
        roles=[
            RoleDefinition(key=ROLE_UMOWA, label="Umowa", show_summary_row=False),
            RoleDefinition(key=ROLE_NIE_CHCE_24H, label="Nie chce 24h", show_summary_row=False),
        ],
        rules=[],
    )


def _ubojnia_gosz_location() -> LocationConfig:
    loc = LocationConfig(key="ubojnia_gosz_waga_biuro", name="Ubojnia Drobiu GOSZ - waga/biuro")
    loc.set_duty_rotation({
        "only_12_24h": True,
        # Obserwowany wzorzec: 8:00-20:00 dzień + 20:00-8:00 noc, każdego
        # dnia tygodnia. weekend_full wymagane przez normalize_duty_rotation
        # mimo że nigdy nieobserwowane w realnych danych tej placówki - patrz
        # docstring modułu (wszyscy dostają nie_chce_24h, więc strukturalnie
        # niedostępne).
        "weekend_full": {"start": "08:00"},
        "weekend_half_a": {"start": "08:00", "end": "20:00"},
        "weekend_half_b": {"start": "20:00", "end": "08:00"},
    })
    return loc


def _pge_ustka_location() -> LocationConfig:
    loc = LocationConfig(key="pge_ustka_westerplatte", name="PGE Ustka, ul. Westerplatte 4")
    loc.set_duty_rotation({
        "only_12_24h": True,
        # Obserwowany wzorzec: "8/8" powtarzające się - zmiana 24h co dzień.
        "weekend_full": {"start": "08:00"},
        # weekend_half_a/b wymagane przez normalize_duty_rotation, ale
        # NIEOBSERWOWANE w realnych danych tej placówki (nigdy nie widać
        # podziału 12h+12h tutaj) - placeholder na tych samych granicach co
        # weekend_full, do potwierdzenia z klientem czy w ogóle ma sens.
        "weekend_half_a": {"start": "08:00", "end": "20:00"},
        "weekend_half_b": {"start": "20:00", "end": "08:00"},
    })
    return loc


def build_shop_config(profile: CustomBusinessProfile) -> ShopConfig:
    shop = ShopConfig(YEAR, MONTH)
    shop.name = "Dane klienta (test) - Ubojnia Drobiu GOSZ + PGE Ustka"
    shop.business_type = profile.key

    ubojnia = _ubojnia_gosz_location()
    pge = _pge_ustka_location()
    shop.locations = {ubojnia.key: ubojnia, pge.key: pge}

    shop.constraint_policies.update(default_policies(profile))
    # Etap D (jak w demo/install_demo.py): klient nie chce w ogóle tych
    # constraintów dla profilu Ochrona - celujemy w pełne pokrycie, nie w
    # nominalny czas pracy.
    shop.constraint_policies["balance"] = ConstraintPolicy.DISABLED
    shop.constraint_policies["monthly_hours"] = ConstraintPolicy.DISABLED
    return shop


# (last_name, first_name) - imiona nieznane z samych zdjęć (tylko
# nazwiska), więc first_name = "?" jako jawny placeholder do uzupełnienia,
# nie zgadywane.
UBOJNIA_GOSZ_EMPLOYEES = [
    "Piepiórka", "Krefft", "Szyca", "Młyński", "Gołębiewski", "Krauze", "Stencel",
]

# 6 nazwisk wypisanych w źródle, 2 nieczytelne/skreślone - pominięte
# (patrz docstring modułu i ENYO_ONLY_CHANGES.md).
PGE_USTKA_EMPLOYEES = [
    ("Korzyński", "K."),
    ("Krzysztofiak", "Z."),
    ("Kaufman", "M."),
    ("Pośpiech", "J."),
]


def build_employees() -> list[Employee]:
    employees = []
    for last_name in UBOJNIA_GOSZ_EMPLOYEES:
        employees.append(Employee(
            last_name=last_name, first_name="?",
            employment_fraction=1.0,
            location_key="ubojnia_gosz_waga_biuro",
            custom_roles={ROLE_NIE_CHCE_24H: True},
        ))
    for last_name, first_initial in PGE_USTKA_EMPLOYEES:
        employees.append(Employee(
            last_name=last_name, first_name=first_initial,
            employment_fraction=1.0,
            location_key="pge_ustka_westerplatte",
            # Celowo BEZ nie_chce_24h - patrz docstring modułu.
        ))
    return employees


def install_profile() -> CustomBusinessProfile:
    profile = build_profile()
    save_custom_profile(profile)
    register_custom_profile(profile)
    return profile


def build_project() -> tuple[MonthSchedule, ShopConfig]:
    profile = install_profile()
    shop = build_shop_config(profile)

    schedule = MonthSchedule(YEAR, MONTH)
    for emp in build_employees():
        schedule.add_employee(emp)

    return schedule, shop


def main() -> None:
    schedule, shop = build_project()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    save_project(str(OUTPUT_PATH), schedule, shop)
    print(f"Zainstalowano profil '{PROFILE_KEY}' i zapisano projekt testowy w {OUTPUT_PATH}")
    print("W programie: Plik -> Otwórz projekt... i wskaż ten plik, albo Generuj grafik od razu po otwarciu.")


if __name__ == "__main__":
    main()
