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


@dataclass(frozen=True)
class BusinessProfile:
    key: str
    display_name: str
    roles: tuple[RoleDef, ...] = field(default_factory=tuple)
    policy_labels: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    summary_rows: tuple[tuple[str, str], ...] = field(default_factory=tuple)


DEFAULT_BUSINESS_TYPE = "dino_retail"

BUSINESS_PROFILES: dict[str, BusinessProfile] = {}


def register_profile(profile: BusinessProfile) -> None:
    BUSINESS_PROFILES[profile.key] = profile


def get_profile(business_type: str | None) -> BusinessProfile:
    return BUSINESS_PROFILES.get(business_type, BUSINESS_PROFILES[DEFAULT_BUSINESS_TYPE])


DINO_RETAIL_PROFILE = BusinessProfile(
    key=DEFAULT_BUSINESS_TYPE,
    display_name="Sklep (Dino)",
    roles=(
        RoleDef("is_opener", "Pracownik otwarcia"),
        RoleDef("is_meat", "Obsługa stoiska mięsnego"),
        RoleDef("is_meat_light", "mooooże stanąć na chwilę na mięsie"),
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

    CUSTOM_PROFILES[custom.key] = custom

    summary_rows = [("Otwarcie", "open"), ("Zamknięcie", "close")]
    summary_rows.extend(
        (role.label, f"role:{role.key}") for role in custom.roles if role.show_summary_row
    )

    register_profile(BusinessProfile(
        key=custom.key,
        display_name=custom.display_name,
        roles=tuple(RoleDef(role.key, role.label) for role in custom.roles),
        policy_labels=custom_profile_wiring.build_policy_labels(custom),
        summary_rows=tuple(summary_rows),
    ))


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
