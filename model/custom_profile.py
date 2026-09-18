"""User-authored business profiles (the "kreator profilu" in the UI).

Unlike model.business_profile.BUSINESS_PROFILES (hard-coded Python), these
are built at runtime through ui.profile_wizard_dialog, persisted as JSON via
model.custom_profile_store, and turned into constraint wiring by
logic.generator.custom_profile_wiring. A CustomBusinessProfile carries the
full rule data; model.business_profile only needs the UI-facing shape
(roles/policy_labels/summary_rows) derived from it.
"""

from dataclasses import dataclass, field
import uuid

# Rule types the wizard can compose - a closed catalog of parameterized
# templates, not an open-ended rule language. See logic.generator.generic_rules
# for what each type actually builds.
RULE_TYPE_MIN_STAFF_WITH_ROLE = "min_staff_with_role"
RULE_TYPE_ROLE_TIME_RESTRICTION = "role_time_restriction"

# Ogólne (nie powiązane z żadną konkretną rolą) wiersze podsumowania, jakie
# program w ogóle potrafi narysować nad tabelą grafiku (patrz
# ui/grid_view.py::_fill_validation_rows - ta logika liczenia jest generyczna,
# nie specyficzna dla Dino) - (klucz, etykieta). Profil custom decyduje, które
# z nich pokazać przez CustomBusinessProfile.enabled_summary_rows poniżej;
# domyślnie żaden (w przeciwieństwie do wbudowanego profilu Dino, dla którego
# wszystkie mają sens i są zawsze włączone na sztywno w model/business_profile.py).
# "Obłożenie" (rotacja służby 24/7) świadomie tu NIE występuje - to osobny,
# automatyczny mechanizm zależny od LocationConfig.duty_rotation, nie prosty
# przełącznik profilu (patrz ScheduleGrid._summary_rows).
GENERIC_SUMMARY_ROWS = (
    ("open", "Otwarcie"),
    ("close", "Zamknięcie"),
    ("morning", "Rano"),
    ("afternoon", "Popo"),
    ("meat", "Mięso"),
)


@dataclass
class RoleDefinition:
    key: str
    label: str
    show_summary_row: bool = True
    icon: str = ""

    def to_dict(self):
        return {
            "key": self.key,
            "label": self.label,
            "show_summary_row": self.show_summary_row,
            "icon": self.icon,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            key=data["key"],
            label=data["label"],
            show_summary_row=data.get("show_summary_row", True),
            icon=data.get("icon", ""),
        )


@dataclass
class RuleInstance:
    type: str
    role_key: str
    policy: str = "PREFERRED"
    weight: int = 1000
    params: dict = field(default_factory=dict)
    # Stable id so two rules of the same type/role (e.g. two different
    # forbidden time windows for the same role) get distinct
    # constraint_policies keys instead of colliding.
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_dict(self):
        return {
            "type": self.type,
            "role_key": self.role_key,
            "policy": self.policy,
            "weight": self.weight,
            "params": self.params,
            "id": self.id,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            type=data["type"],
            role_key=data["role_key"],
            policy=data.get("policy", "PREFERRED"),
            weight=data.get("weight", 1000),
            params=dict(data.get("params", {})),
            id=data.get("id") or uuid.uuid4().hex[:8],
        )


@dataclass
class CustomBusinessProfile:
    key: str
    display_name: str
    roles: list = field(default_factory=list)   # list[RoleDefinition]
    rules: list = field(default_factory=list)   # list[RuleInstance]
    # Które klucze z GENERIC_SUMMARY_ROWS pokazać nad tabelą grafiku dla tego
    # profilu (patrz ui/profile_wizard_dialog.py "Wiersze podsumowania").
    # Puste domyślnie - w przeciwieństwie do Dino, żaden z tych wskaźników
    # nie jest z góry oczywisty dla dowolnej, nowo tworzonej branży.
    enabled_summary_rows: list = field(default_factory=list)

    def to_dict(self):
        return {
            "key": self.key,
            "display_name": self.display_name,
            "roles": [r.to_dict() for r in self.roles],
            "rules": [r.to_dict() for r in self.rules],
            "enabled_summary_rows": list(self.enabled_summary_rows),
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            key=data["key"],
            display_name=data["display_name"],
            roles=[RoleDefinition.from_dict(r) for r in data.get("roles", [])],
            rules=[RuleInstance.from_dict(r) for r in data.get("rules", [])],
            enabled_summary_rows=list(data.get("enabled_summary_rows", [])),
        )

    def rule_policy_key(self, rule: RuleInstance) -> str:
        return f"rule:{rule.id}"

    def role_label(self, role_key: str) -> str:
        for role in self.roles:
            if role.key == role_key:
                return role.label
        return role_key

    def rule_label(self, rule: RuleInstance) -> str:
        role_label = self.role_label(rule.role_key)
        if rule.type == RULE_TYPE_MIN_STAFF_WITH_ROLE:
            scope_labels = {
                "open": "na otwarciu",
                "close": "na zamknięciu",
                "any_shift": "w ciągu dnia",
                "night": "na zmianie nocnej",
            }
            scope = scope_labels.get(rule.params.get("scope"), rule.params.get("scope", ""))
            min_count = rule.params.get("min_count", 1)
            return f"{role_label}: min. {min_count} os. {scope}"
        if rule.type == RULE_TYPE_ROLE_TIME_RESTRICTION:
            start = rule.params.get("window_start_hour", "?")
            end = rule.params.get("window_end_hour", "?")
            return f"{role_label}: zakaz pracy {start}:00–{end}:00"
        return f"{role_label}: {rule.type}"
