import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from model.business_profile import CUSTOM_PROFILES, register_custom_profile
from model.constraint_policy import ConstraintPolicy
from model.custom_profile import (
    CustomBusinessProfile,
    RoleDefinition,
    RuleInstance,
    RULE_TYPE_MIN_STAFF_WITH_ROLE,
    RULE_TYPE_ROLE_TIME_RESTRICTION,
)
from model.custom_profile_store import save_custom_profile

POLICY_OPTIONS = (
    ("Preferowane", ConstraintPolicy.PREFERRED.value),
    ("Wymagane", ConstraintPolicy.MANDATORY.value),
    ("Wyłączone", ConstraintPolicy.DISABLED.value),
)

RULE_TYPE_OPTIONS = (
    ("Minimalna liczba osób z rolą", RULE_TYPE_MIN_STAFF_WITH_ROLE),
    ("Zakaz pracy w oknie czasowym", RULE_TYPE_ROLE_TIME_RESTRICTION),
)

SCOPE_OPTIONS = (
    ("na otwarciu", "open"),
    ("na zamknięciu", "close"),
    ("w dowolnym momencie dnia", "any_shift"),
)


def _slugify(label: str, taken: set) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_") or "rola"
    key = base
    i = 2
    while key in taken:
        key = f"{base}_{i}"
        i += 1
    return key


class _RoleRow(QFrame):
    def __init__(self, on_remove, on_changed, label="", show_summary_row=True):
        super().__init__()
        self.setObjectName("configCard")
        layout = QHBoxLayout(self)

        self.label_edit = QLineEdit(label)
        self.label_edit.setPlaceholderText("np. Uzbrojony")
        self.label_edit.textChanged.connect(on_changed)
        layout.addWidget(self.label_edit, 1)

        self.summary_row_check = QCheckBox("Pokaż wiersz podsumowania")
        self.summary_row_check.setChecked(show_summary_row)
        layout.addWidget(self.summary_row_check)

        remove_btn = QPushButton("Usuń")
        remove_btn.setObjectName("dangerButton")
        remove_btn.clicked.connect(lambda: on_remove(self))
        layout.addWidget(remove_btn)

    def label(self) -> str:
        return self.label_edit.text().strip()


class _RuleParamsWidget(QStackedWidget):
    """Swaps its visible parameter fields based on the selected rule type."""

    def __init__(self):
        super().__init__()

        self.min_staff = QSpinBox()
        self.min_staff.setRange(1, 50)
        self.min_staff.setValue(1)
        self.scope = QComboBox()
        for text, value in SCOPE_OPTIONS:
            self.scope.addItem(text, value)
        min_staff_page = QWidget()
        min_staff_form = QFormLayout(min_staff_page)
        min_staff_form.addRow("Min. liczba osób:", self.min_staff)
        min_staff_form.addRow("Zakres:", self.scope)
        self.addWidget(min_staff_page)

        self.window_start = QSpinBox()
        self.window_start.setRange(0, 23)
        self.window_start.setValue(22)
        self.window_end = QSpinBox()
        self.window_end.setRange(0, 23)
        self.window_end.setValue(6)
        time_page = QWidget()
        time_form = QFormLayout(time_page)
        time_form.addRow("Zakaz od godziny:", self.window_start)
        time_form.addRow("do godziny:", self.window_end)
        self.addWidget(time_page)

    def show_for_type(self, rule_type: str):
        self.setCurrentIndex(0 if rule_type == RULE_TYPE_MIN_STAFF_WITH_ROLE else 1)

    def params_for_type(self, rule_type: str) -> dict:
        if rule_type == RULE_TYPE_MIN_STAFF_WITH_ROLE:
            return {"min_count": self.min_staff.value(), "scope": self.scope.currentData()}
        return {"window_start_hour": self.window_start.value(), "window_end_hour": self.window_end.value()}

    def set_params(self, rule_type: str, params: dict):
        if rule_type == RULE_TYPE_MIN_STAFF_WITH_ROLE:
            self.min_staff.setValue(params.get("min_count", 1))
            idx = self.scope.findData(params.get("scope", "open"))
            if idx >= 0:
                self.scope.setCurrentIndex(idx)
        else:
            self.window_start.setValue(params.get("window_start_hour", 22))
            self.window_end.setValue(params.get("window_end_hour", 6))


class _RuleRow(QFrame):
    def __init__(self, on_remove, get_role_labels, rule: RuleInstance | None = None):
        super().__init__()
        self.setObjectName("configCard")
        self.get_role_labels = get_role_labels

        outer = QVBoxLayout(self)
        top_row = QHBoxLayout()

        self.type_combo = QComboBox()
        for text, value in RULE_TYPE_OPTIONS:
            self.type_combo.addItem(text, value)
        top_row.addWidget(self.type_combo)

        self.role_combo = QComboBox()
        top_row.addWidget(self.role_combo)

        self.policy_combo = QComboBox()
        for text, value in POLICY_OPTIONS:
            self.policy_combo.addItem(text, value)
        top_row.addWidget(QLabel("Polityka:"))
        top_row.addWidget(self.policy_combo)

        self.weight_spin = QSpinBox()
        self.weight_spin.setRange(1, 20000)
        self.weight_spin.setValue(1000)
        top_row.addWidget(QLabel("Waga:"))
        top_row.addWidget(self.weight_spin)

        remove_btn = QPushButton("Usuń")
        remove_btn.setObjectName("dangerButton")
        remove_btn.clicked.connect(lambda: on_remove(self))
        top_row.addWidget(remove_btn)

        outer.addLayout(top_row)

        self.params_widget = _RuleParamsWidget()
        outer.addWidget(self.params_widget)

        self.type_combo.currentIndexChanged.connect(
            lambda _: self.params_widget.show_for_type(self.type_combo.currentData())
        )
        self.policy_combo.currentIndexChanged.connect(self._sync_weight_enabled)

        self.refresh_roles()
        if rule is not None:
            idx = self.type_combo.findData(rule.type)
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)
            self.params_widget.set_params(rule.type, rule.params)
            idx = self.policy_combo.findData(rule.policy)
            if idx >= 0:
                self.policy_combo.setCurrentIndex(idx)
            self.weight_spin.setValue(rule.weight)
            self._selected_role_key = rule.role_key
        else:
            self._selected_role_key = None

        self.params_widget.show_for_type(self.type_combo.currentData())
        self._sync_weight_enabled()

    def _sync_weight_enabled(self):
        self.weight_spin.setEnabled(self.policy_combo.currentData() == ConstraintPolicy.PREFERRED.value)

    def refresh_roles(self):
        current = self.role_combo.currentData()
        self.role_combo.blockSignals(True)
        self.role_combo.clear()
        for key, label in self.get_role_labels():
            self.role_combo.addItem(label, key)
        idx = self.role_combo.findData(current or getattr(self, "_selected_role_key", None))
        if idx >= 0:
            self.role_combo.setCurrentIndex(idx)
        self.role_combo.blockSignals(False)

    def to_rule_instance(self) -> RuleInstance | None:
        role_key = self.role_combo.currentData()
        if not role_key:
            return None
        rule_type = self.type_combo.currentData()
        return RuleInstance(
            type=rule_type,
            role_key=role_key,
            policy=self.policy_combo.currentData(),
            weight=self.weight_spin.value(),
            params=self.params_widget.params_for_type(rule_type),
        )


class ProfileWizardDialog(QDialog):
    """Lets the user build a new, reusable business profile from a fixed
    catalog of role/rule building blocks - no code, no Python file to write.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nowy profil działalności")
        self.setModal(True)
        self.resize(640, 560)
        self.new_profile_key = None

        self._role_rows: list[_RoleRow] = []
        self._rule_rows: list[_RuleRow] = []

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        title = QLabel("Nowy profil działalności")
        title.setObjectName("sectionLabel")
        root.addWidget(title)

        hint = QLabel(
            "Zdefiniuj role pracowników i reguły generatora dla nowej branży. "
            "Profil zostanie zapisany i będzie można go wybrać dla dowolnego "
            "kolejnego projektu, tak jak dzisiejszy profil Dino."
        )
        hint.setWordWrap(True)
        hint.setObjectName("mutedHint")
        root.addWidget(hint)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("np. Ochrona Sp. z o.o.")
        form.addRow("Nazwa profilu:", self.name_edit)
        root.addLayout(form)

        root.addWidget(QLabel("Role:"))
        self.roles_container = QVBoxLayout()
        root.addLayout(self.roles_container)
        add_role_btn = QPushButton("Dodaj rolę")
        add_role_btn.setObjectName("secondaryButton")
        add_role_btn.clicked.connect(lambda: self._add_role_row())
        root.addWidget(add_role_btn)

        root.addWidget(QLabel("Reguły generatora:"))
        self.rules_container = QVBoxLayout()
        root.addLayout(self.rules_container)
        add_rule_btn = QPushButton("Dodaj regułę")
        add_rule_btn.setObjectName("secondaryButton")
        add_rule_btn.clicked.connect(lambda: self._add_rule_row())
        root.addWidget(add_rule_btn)

        root.addStretch()

        buttons = QDialogButtonBox()
        cancel_btn = QPushButton("Anuluj")
        cancel_btn.setObjectName("secondaryButton")
        save_btn = QPushButton("Zapisz profil")
        save_btn.setObjectName("primaryButton")
        buttons.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        buttons.addButton(save_btn, QDialogButtonBox.AcceptRole)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._save)
        root.addWidget(buttons)

        self._add_role_row()

    def _add_role_row(self, label="", show_summary_row=True):
        row = _RoleRow(self._remove_role_row, self._on_roles_changed, label, show_summary_row)
        self._role_rows.append(row)
        self.roles_container.addWidget(row)

    def _remove_role_row(self, row):
        if len(self._role_rows) <= 1:
            QMessageBox.information(self, "Profil", "Profil musi mieć przynajmniej jedną rolę.")
            return
        self._role_rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._on_roles_changed()

    def _on_roles_changed(self):
        for rule_row in self._rule_rows:
            rule_row.refresh_roles()

    def _current_role_labels(self):
        taken = set()
        result = []
        for row in self._role_rows:
            label = row.label()
            if not label:
                continue
            key = _slugify(label, taken)
            taken.add(key)
            result.append((key, label))
        return result

    def _add_rule_row(self, rule: RuleInstance | None = None):
        if not self._current_role_labels():
            QMessageBox.information(self, "Profil", "Najpierw dodaj przynajmniej jedną rolę z nazwą.")
            return
        row = _RuleRow(self._remove_rule_row, self._current_role_labels, rule)
        self._rule_rows.append(row)
        self.rules_container.addWidget(row)

    def _remove_rule_row(self, row):
        self._rule_rows.remove(row)
        row.setParent(None)
        row.deleteLater()

    def _save(self):
        display_name = self.name_edit.text().strip()
        if not display_name:
            QMessageBox.critical(self, "Błąd", "Podaj nazwę profilu.")
            return

        role_labels = self._current_role_labels()
        if not role_labels:
            QMessageBox.critical(self, "Błąd", "Dodaj przynajmniej jedną rolę z nazwą.")
            return

        role_keys = {key for key, _ in role_labels}
        roles = []
        for row, (key, label) in zip(
            (r for r in self._role_rows if r.label()), role_labels
        ):
            roles.append(RoleDefinition(
                key=key, label=label, show_summary_row=row.summary_row_check.isChecked()
            ))

        rules = []
        for row in self._rule_rows:
            rule = row.to_rule_instance()
            if rule is not None and rule.role_key in role_keys:
                rules.append(rule)

        base_key = _slugify(display_name, set())
        key = f"custom_{base_key}"
        suffix = 2
        while key in CUSTOM_PROFILES:
            key = f"custom_{base_key}_{suffix}"
            suffix += 1

        profile = CustomBusinessProfile(
            key=key, display_name=display_name, roles=roles, rules=rules,
        )

        try:
            save_custom_profile(profile)
        except OSError as exc:
            QMessageBox.critical(self, "Błąd zapisu", f"Nie udało się zapisać profilu: {exc}")
            return

        register_custom_profile(profile)
        self.new_profile_key = profile.key
        self.accept()
