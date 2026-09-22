"""Dane testowe z REALNYCH grafików klienta (firma ochroniarska/serwisowa),
odczytane ręcznie ze zdjęć papierowych kart przez użytkownika, potem
doprecyzowane wprost przez użytkownika (konkretne godziny start/koniec dla
placówek, które pierwotnie nie dawały się odczytać ze zdjęć) - patrz
"ENYO_ONLY_CHANGES.md", sekcja "Dane testowe z realnych grafików klienta
(2026-09-19)" i jej kontynuacja "Rozszerzenie danych klienta o kolejne
placówki (2026-09-22)" po pełny opis źródła i placówek świadomie
pominiętych (nie mieszczą się w dzisiejszym modelu generatora - patrz ta
sama sekcja).

W przeciwieństwie do demo/install_demo.py (syntetyczny, wyimaginowany
przykład) - to są PRAWDZIWE nazwiska i PRAWDZIWE wzorce zmian sześciu
placówek, które faktycznie pasują do modelu duty_rotation (każda ma
potwierdzoną zmianę dzienną I nocną/24h - patrz normalize_duty_rotation(),
które wymaga kompletnego schematu, nie da się skonfigurować samej połowy
doby):

1. Ubojnia Drobiu GOSZ - waga/biuro: 7 pracowników, obserwowany wzorzec
   8:00-20:00 (dzień) + 20:00-8:00 (noc), naprzemiennie, każdego dnia
   tygodnia (only_12_24h). Realny grafik NIGDY nie pokazuje pojedynczej
   zmiany 24h - stąd wszyscy pracownicy dostają rolę "nie_chce_24h", żeby
   generator też nigdy jej nie użył (weekend_full jest polem wymaganym
   przez normalize_duty_rotation, ale strukturalnie niedostępnym dla
   każdego, kto ma tę flagę - patrz add_duty_rotation_no24h_gate_constraint).
2. PGE Ustka, ul. Westerplatte 4: 5 pracowników, obserwowany wzorzec to
   powtarzające się "8/8" - czyli DOKŁADNIE zmiana 24h co dzień
   (only_12_24h, weekend_full). Świadomie ŻADEN pracownik nie ma tu flagi
   "nie_chce_24h" - real dane nigdy nie pokazują podziału 12h+12h w tej
   placówce, w przeciwieństwie do Ubojni. To dobry test na to, czy nowa
   preferencja generatora (12h+12h zamiast 24h,
   logic/generator/duty_rotation_preference.py) zacznie w praktyce
   proponować podział, którego ta konkretna placówka historycznie nigdy
   nie stosowała.
3. GZUK Łęczyce: 5 pracowników, klient podał DWA alternatywne warianty tej
   samej doby - "7/7 24h" (jedna osoba, cała doba) LUB "15/7 16h" (16h
   wieczór/noc + uzupełniające 8h za dnia, dwie osoby). To dokładnie ten
   sam mechanizm co "24h kontra 12h+12h" w Ubojni/PGE, tylko z innym
   podziałem doby (16h/8h zamiast 12h/12h) - normalize_duty_rotation() nie
   wymaga, żeby podział był akurat po połowie, ani żeby weekend_full
   zaczynał się o tej samej godzinie co weekend_half_a. Solver wybiera sam,
   który wariant zastosować każdego dnia (ta sama miękka preferencja co w
   PGE) - żaden pracownik nie ma tu "nie_chce_24h", bo klient jawnie
   dopuścił oba warianty.
4. Łeba, Apartamenty Nadmorska 33: 3 pracowników, "jedna zmiana 8/8" -
   analogicznie do PGE, wyłącznie zmiana 24h startująca o 8:00. Pola
   weekend_half_a/b są mimo to wymagane przez normalize_duty_rotation()
   (nie da się skonfigurować samej zmiany 24h bez "wentylu bezpieczeństwa"
   podziału) - ustawione na granicach 08:00/20:00, tak jak w Ubojni/PGE,
   ale bez żadnej roli blokującej podział, więc solver technicznie MOŻE (i,
   sądząc po zachowaniu przy PGE, prawdopodobnie czasem będzie) zaproponować
   12h+12h zamiast czystej zmiany 24h - do obserwacji przy generowaniu,
   nie ma dziś mechanizmu "wymuś zawsze 24h" (jest tylko odwrotność,
   "nie_chce_24h").
5. LakPol Słupsk: 3 pracowników, "jedna zmiana 7/7 24h" - dokładnie ten sam
   przypadek co Łeba Apartamenty (czysta zmiana 24h, ten sam brak
   mechanizmu wymuszenia, ta sama możliwa miękka propozycja podziału).
6. P.P. Nadleśnictwo Cewice: 2 pracowników, klient wprost potwierdził BRAK
   jakichkolwiek danych o wzorcu zmian ("stwórz po prostu puste") - lokacja
   bez `duty_rotation`/`open_hours` niestandardowych (same wartości
   domyślne), sami pracownicy przypisani do niej. Profil "Ochrona" nie ma
   żadnej reguły wymuszającej obsadę zwykłych zmian OPEN/CLOSE (patrz niżej
   i plan profil ochrona...md), więc pusta konfiguracja tu oznacza
   dosłownie: generator nic tu nie przydzieli, dopóki klient nie poda
   konkretnego wzorca.

Cztery placówki z tej samej listy klienta ŚWIADOMIE pominięte (patrz
ENYO_ONLY_CHANGES.md po pełne uzasadnienie, potwierdzone z użytkownikiem
przed dopisaniem czegokolwiek) - żadna nie pasuje do dzisiejszych
mechanizmów generatora bez nowej pracy w kodzie:
- MZGK Krzywoustego: różna długość zmiany w różne dni tygodnia (8h/7h w
  tygodniu, 6h sobota, 4h niedziela) - `get_effective_daily_hours()`
  liczy JEDNĄ, stałą długość zmiany na pracownika, niezależną od dnia
  tygodnia; nie istnieje mechanizm zmiennej długości zmiany per-dzień.
- Brico Marche Wejcherowo, Brico Marche Lębork, Sprzątanie: pojedyncza,
  ciągła zmiana na cały okres otwarcia (np. 8:00-20:00, 12h). Profil
  "Ochrona" (rules=[]) nie wymusza w ogóle obsady zwykłych zmian
  OPEN/CLOSE (brak takiej reguły - to świadoma decyzja profilu, patrz
  build_profile() niżej), a długość zmiany OPEN/CLOSE jest zakotwiczona na
  jednej, wspólnej dla CAŁEGO ShopConfig wartości
  (`standard_daily_hours`) - dopasowanie jej naraz do 12h (Brico) i 7h
  (Sprzątanie) w jednym pliku wymagałoby kruchych sztuczek (globalne
  ustawienie + dostrajanie ułamków etatu na granicy zaokrągleń), które
  łatwo dają wynik NIEZGODNY z zadanymi godzinami zamiast go odtwarzać.

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
        # Obserwowany/potwierdzony wzorzec: "8/8" powtarzające się - zmiana
        # 24h co dzień.
        "weekend_full": {"start": "08:00"},
        # weekend_half_a/b wymagane przez normalize_duty_rotation, ale
        # NIEOBSERWOWANE w realnych danych tej placówki (nigdy nie widać
        # podziału 12h+12h tutaj) - placeholder na tych samych granicach co
        # weekend_full, do potwierdzenia z klientem czy w ogóle ma sens.
        "weekend_half_a": {"start": "08:00", "end": "20:00"},
        "weekend_half_b": {"start": "20:00", "end": "08:00"},
    })
    return loc


def _gzuk_leczyce_location() -> LocationConfig:
    loc = LocationConfig(key="gzuk_leczyce", name="GZUK Łęczyce")
    loc.set_duty_rotation({
        "only_12_24h": True,
        # Klient: "7/7 24h lub 15/7 16h" - dwa dopuszczone warianty tej
        # samej doby, solver wybiera sam który zastosować każdego dnia
        # (patrz docstring modułu, punkt 3).
        "weekend_full": {"start": "07:00"},
        "weekend_half_a": {"start": "15:00", "end": "07:00"},  # 16h wieczór/noc
        "weekend_half_b": {"start": "07:00", "end": "15:00"},  # 8h uzupełniające za dnia
    })
    return loc


def _apartamenty_leba_location() -> LocationConfig:
    loc = LocationConfig(key="apartamenty_leba", name="Łeba, Apartamenty Nadmorska 33")
    loc.set_duty_rotation({
        "only_12_24h": True,
        # Klient: "jedna zmiana 8/8" - wyłącznie zmiana 24h, patrz docstring
        # modułu punkt 4 (half_a/b to wymagany placeholder, nie potwierdzony
        # wzorzec).
        "weekend_full": {"start": "08:00"},
        "weekend_half_a": {"start": "08:00", "end": "20:00"},
        "weekend_half_b": {"start": "20:00", "end": "08:00"},
    })
    return loc


def _lakpol_slupsk_location() -> LocationConfig:
    loc = LocationConfig(key="lakpol_slupsk", name="LakPol Słupsk")
    loc.set_duty_rotation({
        "only_12_24h": True,
        # Klient: "jedna zmiana 7/7 24h" - ten sam przypadek co Łeba
        # Apartamenty, patrz docstring modułu punkt 5.
        "weekend_full": {"start": "07:00"},
        "weekend_half_a": {"start": "07:00", "end": "19:00"},
        "weekend_half_b": {"start": "19:00", "end": "07:00"},
    })
    return loc


def _nadlesnictwo_cewice_location() -> LocationConfig:
    # Klient: brak jakichkolwiek danych o wzorcu zmian - świadomie pusta,
    # patrz docstring modułu punkt 6. WAŻNE: domyślne LocationConfig.open_hours
    # to gotowy, prawie całodobowy wzorzec sklepowy (05:30-23:00ish,
    # DEFAULT_OPEN_HOURS) - zostawienie go bez zmian nie znaczy "brak
    # wzorca", tylko "przejmij wzorzec Dino retail" i generator automatycznie
    # wykrywa z tego zmianę nocną (get_night_shift_hours(), nachodzi na
    # 22:00-06:00) i próbuje obsadzać OPEN/CLOSE - zweryfikowane empirycznie
    # (patrz ENYO_ONLY_CHANGES.md). Żeby faktycznie nie mieć TU żadnego
    # wzorca, trzeba jawnie zamknąć lokalizację na każdy dzień tygodnia.
    loc = LocationConfig(key="nadlesnictwo_cewice", name="P.P. Nadleśnictwo Cewice")
    loc.open_hours = {wd: (None, None) for wd in range(7)}
    return loc


def build_shop_config(profile: CustomBusinessProfile) -> ShopConfig:
    shop = ShopConfig(YEAR, MONTH)
    shop.name = "Dane klienta (test) - Ochrona (6 placówek)"
    shop.business_type = profile.key

    locations = [
        _ubojnia_gosz_location(),
        _pge_ustka_location(),
        _gzuk_leczyce_location(),
        _apartamenty_leba_location(),
        _lakpol_slupsk_location(),
        _nadlesnictwo_cewice_location(),
    ]
    shop.locations = {loc.key: loc for loc in locations}

    shop.constraint_policies.update(default_policies(profile))
    # Etap D (jak w demo/install_demo.py): klient nie chce w ogóle tych
    # constraintów dla profilu Ochrona - celujemy w pełne pokrycie, nie w
    # nominalny czas pracy.
    shop.constraint_policies["balance"] = ConstraintPolicy.DISABLED
    shop.constraint_policies["monthly_hours"] = ConstraintPolicy.DISABLED
    return shop


# (last_name, first_name) - "?" jako jawny placeholder tam, gdzie klient
# podał tylko nazwisko bez imienia/inicjału, nie zgadywane.
UBOJNIA_GOSZ_EMPLOYEES = [
    "Piepiórka", "Krefft", "Szyca", "Młyński", "Gołębiewski", "Krauze", "Stencel",
]

PGE_USTKA_EMPLOYEES = [
    ("Korzyński", "K."),
    ("Krzysztofiak", "Z."),
    ("Kaufman", "M."),
    ("Pośpiech", "J."),
    ("Sowiecki", "?"),
]

GZUK_LECZYCE_EMPLOYEES = [
    "Szmydtka", "Reszke", "Gojtowski", "Bohdan", "Długosz",
]

APARTAMENTY_LEBA_EMPLOYEES = [
    "Witkowski", "Mejna", "Morawiak",
]

LAKPOL_SLUPSK_EMPLOYEES = [
    "Kardaś", "Rijewski", "Wardyn",
]

NADLESNICTWO_CEWICE_EMPLOYEES = [
    "Cybula", "Szwarc",
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
    for last_name, first_name in PGE_USTKA_EMPLOYEES:
        employees.append(Employee(
            last_name=last_name, first_name=first_name,
            employment_fraction=1.0,
            location_key="pge_ustka_westerplatte",
            # Celowo BEZ nie_chce_24h - patrz docstring modułu.
        ))
    for last_name in GZUK_LECZYCE_EMPLOYEES:
        employees.append(Employee(
            last_name=last_name, first_name="?",
            employment_fraction=1.0,
            location_key="gzuk_leczyce",
            # Celowo BEZ nie_chce_24h - klient dopuścił oba warianty (24h/16h).
        ))
    for last_name in APARTAMENTY_LEBA_EMPLOYEES:
        employees.append(Employee(
            last_name=last_name, first_name="?",
            employment_fraction=1.0,
            location_key="apartamenty_leba",
            # Celowo BEZ nie_chce_24h - patrz docstring modułu.
        ))
    for last_name in LAKPOL_SLUPSK_EMPLOYEES:
        employees.append(Employee(
            last_name=last_name, first_name="?",
            employment_fraction=1.0,
            location_key="lakpol_slupsk",
        ))
    for last_name in NADLESNICTWO_CEWICE_EMPLOYEES:
        employees.append(Employee(
            last_name=last_name, first_name="?",
            employment_fraction=1.0,
            location_key="nadlesnictwo_cewice",
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
    print(f"Placówki: {', '.join(shop.locations.keys())}")
    print("W programie: Plik -> Otwórz projekt... i wskaż ten plik, albo Generuj grafik od razu po otwarciu.")


if __name__ == "__main__":
    main()
