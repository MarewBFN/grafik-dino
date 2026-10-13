"""Declarative description of a business type (Dino retail, security guards, ...).

A BusinessProfile drives which employee roles, constraint policy toggles and
grid summary rows are shown in the UI, and which constraint set the generator
runs. Everything defaults to the "dino_retail" profile so existing projects
and UI keep behaving exactly as before this concept existed.
"""

from dataclasses import dataclass, field

from release_channel import RELEASE_CHANNEL


@dataclass(frozen=True)
class RoleDef:
    """Rola/atrybut pracownika opisany przez profil.

    - `key` będący polem Employee (no_night/no_afternoon) - ograniczenie
      pracownika z etykietą tego profilu (checkbox w oknie pracownika);
    - każdy inny klucz - rola profilu custom (nazwa, ikona). Pracownikom
      przypisuje się ją jako kwalifikację z katalogu projektu
      (model.qualification, MonthlyProject.qualifications), do którego
      trafia przez default_qualifications().
    """

    key: str
    label: str
    description: str = ""
    icon: str = ""


@dataclass(frozen=True)
class BusinessProfile:
    key: str
    display_name: str
    roles: tuple[RoleDef, ...] = field(default_factory=tuple)
    policy_labels: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    # policy_name -> jednozdaniowy opis, co ta zasada robi (nie co znaczy
    # Wymagane/Preferowane/Wyłączone - to już tłumaczy ui/config_dialog.py::
    # POLICY_STATE_TOOLTIPS - tylko SAMA zasada, np. "Dostępność pracownika"
    # -> "Nie przydziela pracownikowi zmian poza godzinami, w których zgłosił
    # dostępność."). Pokazywane w Konfiguracji -> Zasady generatora jako
    # tooltip ikonki "?" przy nazwie zasady. Brak wpisu (stary profil custom
    # sprzed tego pola, albo nierozpoznany typ reguły) = brak ikonki.
    policy_descriptions: dict[str, str] = field(default_factory=dict)
    summary_rows: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    # "Dni handlowe" (trade Sundays / public holidays) is a Polish-retail-
    # specific concept - most businesses (a security company, say) don't
    # have it at all and every day is a normal working day. False by
    # default for every profile except dino_retail.
    uses_trade_calendar: bool = False


DEFAULT_BUSINESS_TYPE = "dino_retail"
# Zdefiniowane tu (a nie przy build_default_ochrona_profile() niżej), bo
# _load_persisted_custom_profiles() poniżej odwołuje się do tej stałej
# pośrednio (przez custom_profile_wiring -> opening_hours_coverage) już przy
# imporcie tego modułu - musi istnieć, zanim ta funkcja zostanie wywołana.
DEFAULT_OCHRONA_PROFILE_KEY = "custom_ochrona"

BUSINESS_PROFILES: dict[str, BusinessProfile] = {}


def register_profile(profile: BusinessProfile) -> None:
    BUSINESS_PROFILES[profile.key] = profile


def get_profile(business_type: str | None) -> BusinessProfile:
    return BUSINESS_PROFILES.get(business_type, BUSINESS_PROFILES[DEFAULT_BUSINESS_TYPE])


def visible_profiles() -> list[BusinessProfile]:
    """Profiles a business-profile picker should actually list for a human
    to choose from - see ENYO_ONLY_CHANGES.md. On the "enyo" release channel
    this excludes dino_retail so that build never shows it or lets you
    switch back to it. On every other channel (default: "dino") all
    registered profiles are shown, Dino included. Purely a UI display
    filter: dino_retail stays registered and fully functional
    (BUSINESS_PROFILES/get_profile() are untouched either way), nothing
    about the profile system itself is removed."""
    if RELEASE_CHANNEL == "enyo":
        return [p for p in BUSINESS_PROFILES.values() if p.key != DEFAULT_BUSINESS_TYPE]
    return list(BUSINESS_PROFILES.values())


DINO_RETAIL_PROFILE = BusinessProfile(
    key=DEFAULT_BUSINESS_TYPE,
    display_name="Sklep (Dino)",
    # Otwarcie/Mięso/Kierowniczka to kwalifikacje (model.qualification.
    # DINO_QUALIFICATIONS), nie role profilu - tu tylko ograniczenia.
    roles=(
        RoleDef("no_night", "Nie pracuje w godzinach nocnych (przed 6:00 i po 22:00)"),
        RoleDef("no_afternoon", "Nie pracuje na popołudniu (tylko zmiany poranne)"),
    ),
    policy_descriptions={
        # Te pięć samo w sobie generyczne (patrz
        # logic/generator/base_specs.py::GENERIC_POLICY_DESCRIPTIONS - ten
        # sam tekst, zduplikowany zamiast zaimportowany, żeby ten moduł nie
        # musiał importować logic.generator na poziomie modułu - patrz lazy
        # importy niżej w tym pliku).
        "rest_11h": "Zapewnia co najmniej 11 godzin przerwy między kolejnymi zmianami tego samego pracownika.",
        "availability": "Nie przydziela pracownikowi zmian poza godzinami, w których zgłosił dostępność.",
        "monthly_hours": "Dąży do tego, żeby każdy pracownik przepracował w miesiącu tyle godzin, ile wynika z jego etatu.",
        "balance": "Stara się równo rozłożyć godziny pracy między pracowników, żeby nikt nie miał wyraźnie więcej albo mniej niż reszta.",
        "max_consecutive": "Ogranicza liczbę dni pracy pod rząd bez dnia wolnego.",
        "open": "Zapewnia minimalną liczbę pracowników na zmianie otwierającej sklep.",
        "close": "Zapewnia minimalną liczbę pracowników na zmianie zamykającej sklep.",
        "meat": "Na zmianie otwierającej i zamykającej musi być ktoś z rolą obsługi stoiska mięsnego.",
        "meat_coverage": "Stoisko mięsne ma obsadę przez cały czas otwarcia sklepu, nie tylko na otwarciu/zamknięciu.",
        "no_night": "Pracownikom oznaczonym „Nie pracuje w godzinach nocnych” nie przydziela zmian nocnych.",
        "no_afternoon": "Pracownikom oznaczonym „Nie pracuje na popołudniu” przydziela wyłącznie zmiany poranne.",
    },
    policy_labels=(
        ("rest_11h", "Odpoczynek 11 h"),
        ("open", "Obsada otwarcia"),
        ("close", "Obsada zamknięcia"),
        ("meat", "Mięso na zmianach"),
        ("meat_coverage", "Mięso przez cały dzień"),
        ("availability", "Dostępność pracownika"),
        ("no_night", "Zakaz pracy nocnej"),
        ("no_afternoon", "Zakaz pracy popołudniami"),
        ("monthly_hours", "Godziny miesięczne"),
        ("balance", "Bilans godzin"),
        ("max_consecutive", "Dni pod rząd"),
    ),
    summary_rows=(
        ("Otwarcie", "open"),
        ("Zamknięcie", "close"),
        ("Rano", "morning"),
        ("Popo", "afternoon"),
        ("Mięso", "meat"),
    ),
    uses_trade_calendar=True,
)

register_profile(DINO_RETAIL_PROFILE)


# --- User-authored (custom) profiles -----------------------------------
#
# Built at runtime by ui.profile_wizard_dialog and persisted via
# model.custom_profile_store. CUSTOM_PROFILES keeps the full rule data
# (needed by logic.generator.custom_profile_wiring to build constraints);
# BUSINESS_PROFILES gets the UI-facing BusinessProfile derived from it, so
# every screen that already reads get_profile()/BUSINESS_PROFILES works for
# custom profiles without further changes.

CUSTOM_PROFILES: dict = {}  # key -> CustomBusinessProfile


def get_custom_profile(business_type: str | None):
    return CUSTOM_PROFILES.get(business_type)


def register_custom_profile(custom) -> None:
    from logic.generator import custom_profile_wiring
    from model.custom_profile import GENERIC_SUMMARY_ROWS

    CUSTOM_PROFILES[custom.key] = custom

    # W przeciwieństwie do Dino, profile custom nie mają "na sztywno" żadnego
    # z tych ogólnych wskaźników (obsada otwarcia/zamknięcia, rano/popo,
    # mięso) - to czysto informacyjne wiersze (patrz
    # ui/grid_view.py::_fill_validation_rows, generyczne dla każdego profilu),
    # nie egzekwowane przez żadną regułę generatora dla profili custom, więc
    # użytkownik wybiera je świadomie w kreatorze ("Wiersze podsumowania" w
    # ui/profile_wizard_dialog.py) zamiast dziedziczyć dwa wiersze
    # specyficzne dla Dino.
    enabled = set(custom.enabled_summary_rows)
    summary_rows = [
        (label, key) for key, label in GENERIC_SUMMARY_ROWS if key in enabled
    ]
    summary_rows.extend(
        (role.label, f"role:{role.key}") for role in custom.roles if role.show_summary_row
    )

    register_profile(BusinessProfile(
        key=custom.key,
        display_name=custom.display_name,
        roles=tuple(RoleDef(role.key, role.label, icon=role.icon) for role in custom.roles),
        policy_labels=custom_profile_wiring.build_policy_labels(custom),
        policy_descriptions=custom_profile_wiring.build_policy_descriptions(custom),
        summary_rows=tuple(summary_rows),
    ))


def default_qualifications(business_type: str | None) -> tuple:
    """Kwalifikacje, od których zaczyna katalog projektu tego profilu
    (MonthlyProject.qualifications): dla Dino - "Otwarcie", "Mięso"
    (poziomy 1/2) i "Kierowniczka"; dla profilu custom - jego role (role
    znane programowi, np. "Umowa"/"Nie chce 24h" Ochrony, z rysowaną ikoną
    i opisem z model.qualification.KNOWN_QUALIFICATIONS)."""
    from dataclasses import replace

    from model.qualification import DINO_QUALIFICATIONS, KNOWN_QUALIFICATIONS, Qualification

    custom = CUSTOM_PROFILES.get(business_type)
    if custom is None:
        if business_type in BUSINESS_PROFILES and business_type != DEFAULT_BUSINESS_TYPE:
            return ()
        return DINO_QUALIFICATIONS
    return tuple(
        replace(KNOWN_QUALIFICATIONS[role.key], name=role.label)
        if role.key in KNOWN_QUALIFICATIONS
        else Qualification(id=role.key, name=role.label, icon=role.icon)
        for role in custom.roles
    )


def catalog_or_default(catalog: dict | None, business_type: str | None) -> dict:
    """Katalog kwalifikacji projektu albo - gdy go nie ma (okno/siatka poza
    projektem) - domyślny katalog profilu."""
    if catalog is not None:
        return catalog
    return {qualification.id: qualification for qualification in default_qualifications(business_type)}


def unregister_custom_profile(key: str) -> None:
    """Drop a custom profile from the in-memory registries. Projects that
    already reference this key are untouched - get_profile() already falls
    back to dino_retail for any unknown key, so they just start doing that
    the next time they're opened."""
    CUSTOM_PROFILES.pop(key, None)
    BUSINESS_PROFILES.pop(key, None)


def _load_persisted_custom_profiles() -> None:
    from model.custom_profile_store import load_custom_profiles

    try:
        profiles = load_custom_profiles()
    except Exception:
        # A missing/broken app-data location (e.g. no LOCALAPPDATA on this
        # machine, or a corrupted store) must not break importing this
        # module - every project still gets dino_retail.
        return

    for custom in profiles:
        register_custom_profile(custom)


_load_persisted_custom_profiles()


# --- Enyo-only: auto-provision the "Ochrona" profile (branch integration/
# enyo-only, patrz ENYO_ONLY_CHANGES.md "Auto-provisioning profilu Ochrona")
# -------------------------------------------------------------------------
#
# %LOCALAPPDATA%\GrafikDino\custom_profiles.json
# NIE jest częścią instalatora (to per-maszynowy plik danych, nie
# repo/build) - świeża instalacja na maszynie klienta zaczyna z ZUPEŁNIE
# pustym magazynem profili. Bez tego bloku visible_profiles() (wyklucza
# dino_retail) zwracałaby pustą listę, więc kreator pierwszego uruchomienia
# (ui/first_run_wizard.py) nie miałby czego zaproponować, a klient
# utknąłby na starcie bez żadnego działającego profilu.
#
# Sprawdzane przy każdym starcie (nie tylko gdy brakuje), żeby też naprawić
# już zarejestrowany, ale przestarzały profil - znalezione podczas testów:
# profil "custom_ochrona" z porzuconą rolą "Obłożenie" (checkbox per
# pracownik) sprzed właściwego mechanizmu LocationConfig.duty_rotation.
# Naprawa nie nadpisuje profilu - zmiany klienta z kreatora profilu (reguły
# kwalifikacji, własne role) zostają (patrz _repaired_ochrona_profile).


def build_default_ochrona_profile():
    """Kanoniczna definicja profilu "Ochrona" dla klienta Enyo - jedyne
    źródło prawdy (żadnych innych miejsc, gdzie ten kształt jest wpisany
    na sztywno). Role bez rules=[]: obsada/pokrycie 24/7 liczy się w całości
    automatycznie z LocationConfig.duty_rotation (patrz logic/generator/
    duty_rotation_*.py), a nie przez generyczny mechanizm reguł profilu."""
    from model.custom_profile import CustomBusinessProfile, RoleDefinition

    return CustomBusinessProfile(
        key=DEFAULT_OCHRONA_PROFILE_KEY,
        display_name="Ochrona",
        roles=[
            RoleDefinition(key="umowa", label="Umowa", show_summary_row=False),
            RoleDefinition(key="nie_chce_24h", label="Nie chce 24h", show_summary_row=False),
        ],
        rules=[],
    )


# Porzucona rola profilu Ochrona (checkbox "Obłożenie" per pracownik sprzed
# LocationConfig.duty_rotation, klucz "ob_o_enie" z dawnego slugify) -
# usuwana przy naprawie profilu razem z regułami na niej.
_ABANDONED_OCHRONA_ROLE_KEYS = {"ob_o_enie"}
_ABANDONED_OCHRONA_ROLE_LABELS = {"obłożenie"}


def _repaired_ochrona_profile(current, canonical):
    """Profil Ochrony po naprawie: bez porzuconej roli "Obłożenie" (i reguł
    na niej) i z rolami kanonicznymi, których brakuje. Wszystko inne - role,
    reguły, nazwa dodane albo zmienione przez użytkownika w kreatorze
    profilu - zostaje. Wcześniej profil był nadpisywany kanonicznym przy
    każdym starcie, bo zarządzanie profilami było schowane; od kiedy jest
    dostępne (reguły kwalifikacji ustawia się w kreatorze), nadpisanie
    kasowałoby pracę klienta."""
    from dataclasses import replace

    dropped = {
        role.key for role in current.roles
        if role.key in _ABANDONED_OCHRONA_ROLE_KEYS or role.label.strip().casefold() in _ABANDONED_OCHRONA_ROLE_LABELS
    }
    roles = [role for role in current.roles if role.key not in dropped]
    present = {role.key for role in roles}
    roles += [role for role in canonical.roles if role.key not in present]
    rules = [rule for rule in current.rules if rule.qualification_key not in dropped]
    return replace(current, roles=roles, rules=rules)


def _ensure_default_ochrona_profile() -> None:
    canonical = build_default_ochrona_profile()
    current = CUSTOM_PROFILES.get(DEFAULT_OCHRONA_PROFILE_KEY)
    target = canonical if current is None else _repaired_ochrona_profile(current, canonical)
    if current is not None and current.to_dict() == target.to_dict():
        return

    try:
        from model.custom_profile_store import save_custom_profile
        save_custom_profile(target)
    except Exception:
        # Same defensive fallback as _load_persisted_custom_profiles() - a
        # missing/broken app-data location must not break importing this
        # module. register_custom_profile() below still makes the profile
        # usable for THIS run even if it couldn't be persisted to disk.
        pass

    register_custom_profile(target)


_ensure_default_ochrona_profile()
