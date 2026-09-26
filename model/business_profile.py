"""Declarative description of a business type (Dino retail, security guards, ...).

A BusinessProfile drives which employee roles, constraint policy toggles and
grid summary rows are shown in the UI, and which constraint set the generator
runs. Everything defaults to the "dino_retail" profile so existing projects
and UI keep behaving exactly as before this concept existed.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RoleDef:
    """One employee role/attribute checkbox.

    `key` matching an existing Employee dataclass field (e.g. "is_opener")
    is read/written on the Employee object directly, like today. Any other
    key is read/written through Employee.custom_roles instead, so new
    business profiles don't need new Employee fields.
    """

    key: str
    label: str
    description: str = ""
    icon: str = ""
    # When set, this role is only shown/usable while
    # shop.constraint_policies[linked_policy] isn't DISABLED - e.g. Dino's
    # meat-counter roles disappear from the UI once the "meat" policy is
    # turned off, instead of showing a checkbox for a constraint that no
    # longer does anything.
    linked_policy: str = ""


@dataclass(frozen=True)
class BusinessProfile:
    key: str
    display_name: str
    roles: tuple[RoleDef, ...] = field(default_factory=tuple)
    policy_labels: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    summary_rows: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    # "Dni handlowe" (trade Sundays / public holidays) is a Polish-retail-
    # specific concept - most businesses (a security company, say) don't
    # have it at all and every day is a normal working day. False by
    # default for every profile except dino_retail.
    uses_trade_calendar: bool = False


DEFAULT_BUSINESS_TYPE = "dino_retail"

BUSINESS_PROFILES: dict[str, BusinessProfile] = {}


def register_profile(profile: BusinessProfile) -> None:
    BUSINESS_PROFILES[profile.key] = profile


def get_profile(business_type: str | None) -> BusinessProfile:
    return BUSINESS_PROFILES.get(business_type, BUSINESS_PROFILES[DEFAULT_BUSINESS_TYPE])


def visible_profiles() -> list[BusinessProfile]:
    """Profiles a business-profile picker should actually list for a human
    to choose from - see ENYO_ONLY_CHANGES.md. Excludes dino_retail so a
    build dedicated to a non-Dino client never shows it or lets you switch
    back to it. Purely a UI display filter: dino_retail stays registered
    and fully functional (BUSINESS_PROFILES/get_profile() are untouched),
    nothing about the profile system itself is removed."""
    return [p for p in BUSINESS_PROFILES.values() if p.key != DEFAULT_BUSINESS_TYPE]


DINO_RETAIL_PROFILE = BusinessProfile(
    key=DEFAULT_BUSINESS_TYPE,
    display_name="Sklep (Dino)",
    roles=(
        RoleDef("is_opener", "Pracownik otwarcia"),
        RoleDef("is_meat", "Obsługa stoiska mięsnego", linked_policy="meat"),
        RoleDef("is_meat_light", "mooooże stanąć na chwilę na mięsie", linked_policy="meat"),
        RoleDef(
            "is_manager",
            "Kierowniczka (sztywny grafik: pon. wolne, wt-pt 7:00-15:00, sob 6:00-14:00)",
        ),
        RoleDef("no_night", "Nie pracuje w godzinach nocnych (przed 6:00 i po 22:00)"),
        RoleDef("no_afternoon", "Nie pracuje na popołudniu (tylko zmiany poranne)"),
    ),
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
        summary_rows=tuple(summary_rows),
    ))


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
# Ten build ma profile management (ProfileWizardDialog i wszystkie wejścia
# do niego) świadomie schowane z UI - klient nigdy nie tworzy/nie edytuje
# profilu samodzielnie. Ale %LOCALAPPDATA%\GrafikDino\custom_profiles.json
# NIE jest częścią instalatora (to per-maszynowy plik danych, nie
# repo/build) - świeża instalacja na maszynie klienta zaczyna z ZUPEŁNIE
# pustym magazynem profili. Bez tego bloku visible_profiles() (wyklucza
# dino_retail) zwracałaby pustą listę, więc kreator pierwszego uruchomienia
# (ui/first_run_wizard.py) nie miałby czego zaproponować, a klient
# utknąłby na starcie bez żadnego działającego profilu.
#
# Synchronizowane BEZWARUNKOWO przy każdym starcie (nie tylko gdy brakuje),
# żeby też naprawić już zarejestrowany, ale przestarzały profil - znalezione
# podczas testów na tej maszynie: profil "custom_ochrona" z porzuconą rolą
# "Obłożenie" (checkbox per pracownik) sprzed właściwego mechanizmu
# LocationConfig.duty_rotation, który dziś liczy obłożenie automatycznie
# per lokalizacja, nie jako ręczną flagę pracownika.
DEFAULT_OCHRONA_PROFILE_KEY = "custom_ochrona"


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


def _ensure_default_ochrona_profile() -> None:
    canonical = build_default_ochrona_profile()
    current = CUSTOM_PROFILES.get(DEFAULT_OCHRONA_PROFILE_KEY)
    if current is not None and current.to_dict() == canonical.to_dict():
        return

    try:
        from model.custom_profile_store import save_custom_profile
        save_custom_profile(canonical)
    except Exception:
        # Same defensive fallback as _load_persisted_custom_profiles() - a
        # missing/broken app-data location must not break importing this
        # module. register_custom_profile() below still makes the profile
        # usable for THIS run even if it couldn't be persisted to disk.
        pass

    register_custom_profile(canonical)


_ensure_default_ochrona_profile()
