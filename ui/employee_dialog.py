import dataclasses

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QComboBox,
    QFrame,
    QSpacerItem,
    QSizePolicy,
    QWidget,
)

from model.employee import Employee
from model.business_profile import get_profile
from model.constraint_policy import ConstraintPolicy
from logic.generator.duty_rotation_constraint import NIE_CHCE_24H_ROLE_KEY

# RoleDef.key values that map directly onto an Employee dataclass field
# (the six legacy Dino flags). Any other key lives in Employee.custom_roles
# instead, so new business profiles don't need new Employee fields.
_EMPLOYEE_FIELDS = {f.name for f in dataclasses.fields(Employee)}


class EmployeeDialog(QDialog):
    def __init__(self, parent=None, employee=None, shop_config=None, default_location_key=None):
        super().__init__(parent)
        self.employee = employee
        self.shop_config = shop_config
        self.profile = get_profile(shop_config.business_type if shop_config else None)
        self.locations = shop_config.locations if shop_config else {}
        # Lokalizacja, na którą ma się domyślnie ustawić kombo poniżej dla
        # NOWEGO pracownika (patrz _fill_from_employee) - zwykle aktualnie
        # przeglądana placówka (main_window.selected_location_key), żeby
        # dodany właśnie pracownik od razu pojawił się w widocznej tabeli
        # zamiast "zniknąć" w nieprzefiltrowanej lokalizacji.
        self.default_location_key = default_location_key
        self.role_checkboxes: dict[str, QCheckBox] = {}
        self.location_combo: QComboBox | None = None
        self.setWindowTitle("Edytuj pracownika" if employee else "Dodaj pracownika")
        self.setModal(True)
        self.setMinimumWidth(460)

        # Wygląd pochodzi ze wspólnego arkusza stylów aplikacji (ui/theme.py).
        self._build_ui()
        self._fill_from_employee()

    def _role_is_hidden(self, role) -> bool:
        """True when this role's linked_policy (e.g. Dino's meat roles ->
        "meat") is DISABLED for the active project, so the checkbox for it
        shouldn't be shown at all."""
        if not role.linked_policy or not self.shop_config:
            return False
        return self.shop_config.constraint_policies.get(role.linked_policy) == ConstraintPolicy.DISABLED

    def _project_uses_duty_rotation(self) -> bool:
        """Ten sam warunek co "Rotacja 24/7" w ui/config_dialog.py -
        projekt/którakolwiek lokalizacja ma faktycznie skonfigurowaną
        LocationConfig.duty_rotation (patrz normalize_duty_rotation)."""
        if not self.shop_config:
            return False
        if self.shop_config.get_duty_rotation():
            return True
        return any(loc.get_duty_rotation() for loc in self.shop_config.locations.values())

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(15)

        title = QLabel("Dane pracownika")
        title.setObjectName("sectionLabel")
        root.addWidget(title)

        # Karta ról rośnie z liczbą ról custom profilu (kreator pozwala
        # dodać dowolnie wiele) - bez scrolla treść (i przyciski Zapisz/
        # Anuluj) wypadały poza okno. Wzorem sidebaru głównego okna
        # (ui/main_window.py::_build_left_panel).
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(scroll, 1)

        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(15)

        # --- Formularz ---
        form = QFormLayout()
        form.setSpacing(10)

        self.last_name = QLineEdit()
        self.first_name = QLineEdit()
        
        self.monthly_target_hours = QSpinBox()
        self.monthly_target_hours.setRange(0, 400)
        self.monthly_target_hours.setValue(160)
        self.monthly_target_hours.setSuffix(" h")

        self.employment_fraction = QComboBox()
        self.employment_fraction.addItem("1/1 (pełny etat)", 1.0)
        self.employment_fraction.addItem("1/1 (pełny etat) max 8:00", 1.01)
        self.employment_fraction.addItem("7/8", 0.875)
        self.employment_fraction.addItem("3/4", 0.75)
        self.employment_fraction.addItem("5/8", 0.625)
        self.employment_fraction.addItem("1/2 (pół etatu)", 0.5)
        self.employment_fraction.addItem("3/8", 0.375)
        self.employment_fraction.addItem("1/4", 0.25)

        form.addRow("Nazwisko:", self.last_name)
        form.addRow("Imię:", self.first_name)
        form.addRow("Wymiar etatu:", self.employment_fraction)

        if self.locations:
            # Bez opcji "Brak" - projekt ma zawsze co najmniej jedną
            # lokalizację (patrz model/shop_config.py), a tabela grafiku
            # filtruje się teraz po lokalizacji (ui/grid_view.py), więc
            # pracownik bez żadnej przypisanej byłby trwale niewidoczny w
            # każdym widoku - patrz _fill_from_employee() niżej dla wyboru
            # domyślnej wartości.
            self.location_combo = QComboBox()
            for loc in self.locations.values():
                self.location_combo.addItem(loc.name, loc.key)
            form.addRow("Lokalizacja:", self.location_combo)

        content_layout.addLayout(form)

        # --- Role i ograniczenia: jedna karta zamiast osobnej ramki na checkbox ---
        flags_card = QFrame()
        flags_card.setObjectName("configCard")
        flags_layout = QVBoxLayout(flags_card)
        flags_layout.setSpacing(10)

        for role in self.profile.roles:
            if self._role_is_hidden(role):
                continue
            checkbox = QCheckBox(role.label)
            if role.description:
                checkbox.setToolTip(role.description)
            flags_layout.addWidget(checkbox)
            self.role_checkboxes[role.key] = checkbox

        # Zachowania specyficzne dla konkretnych ról (wykluczanie się mięsa/
        # mięsa-lekkiego, wymuszanie wymiaru etatu kierowniczki) są pinowane
        # po kluczu roli, nie generyczną regułą - inne profile ich nie mają.
        meat_cb = self.role_checkboxes.get("is_meat")
        meat_light_cb = self.role_checkboxes.get("is_meat_light")
        if meat_cb and meat_light_cb:
            meat_cb.toggled.connect(self._on_meat_toggled)
            meat_light_cb.toggled.connect(self._on_meat_light_toggled)

        manager_cb = self.role_checkboxes.get("is_manager")
        if manager_cb:
            manager_cb.toggled.connect(self._on_manager_toggled)

        # Flaga dla rotacji służby 24/7 (patrz LocationConfig.duty_rotation,
        # logic/generator/duty_rotation_constraint.py) - osobna od systemu
        # ról profilu, bo dotyczy generatora niezależnie od tego, jakie role
        # ma dany profil. Widoczna tylko gdy projekt faktycznie używa tego
        # mechanizmu (na poziomie projektu albo którejkolwiek lokalizacji) -
        # dla profili bez rotacji nic by nie robiła.
        self.no_24h_check = None
        if self._project_uses_duty_rotation():
            self.no_24h_check = QCheckBox("Nie chce pracować zmian 24h")
            self.no_24h_check.setToolTip(
                "Przy rotacji służby 24/7: ta osoba nigdy nie dostanie zmiany "
                "24h w weekend (dostanie dwie 12h zamiast tego)."
            )
            flags_layout.addWidget(self.no_24h_check)

        content_layout.addWidget(flags_card)
        content_layout.addStretch()

        # --- Dolny pasek przycisków ---
        button_row = QHBoxLayout()

        # Przycisk Usuń (w lewym rogu)
        if self.employee:
            self.delete_btn = QPushButton("Usuń pracownika")
            self.delete_btn.setObjectName("dangerButton")
            self.delete_btn.setMinimumHeight(34)
            self.delete_btn.clicked.connect(self._delete_employee)
            button_row.addWidget(self.delete_btn)
        
        # Spacer przesuwa resztę na prawo
        button_row.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))

        # Przyciski Zapisz / Anuluj
        cancel_btn = QPushButton("Anuluj")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.setMinimumHeight(34)
        cancel_btn.setMinimumWidth(80)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Zapisz")
        save_btn.setObjectName("primaryButton")
        save_btn.setMinimumHeight(34)
        save_btn.setMinimumWidth(100)
        save_btn.clicked.connect(self._save)

        button_row.addWidget(cancel_btn)
        button_row.addWidget(save_btn)

        root.addLayout(button_row)

    def _on_meat_toggled(self, checked):
        meat_light_cb = self.role_checkboxes["is_meat_light"]
        if checked and meat_light_cb.isChecked():
            meat_light_cb.setChecked(False)

    def _on_meat_light_toggled(self, checked):
        meat_cb = self.role_checkboxes["is_meat"]
        if checked and meat_cb.isChecked():
            meat_cb.setChecked(False)

    def _on_manager_toggled(self, checked):
        # Jej zmiany są zawsze dokładnie 8h - "1/1 max 8:00" jest jedynym
        # wymiarem etatu, który tego gwarantuje (patrz force_fulltime_845).
        if checked:
            idx = self.employment_fraction.findData(1.01)
            if idx >= 0:
                self.employment_fraction.setCurrentIndex(idx)

    def _fill_from_employee(self):
        if not self.employee:
            # Nowy pracownik: kombo lokalizacji i tak zawsze ma co najmniej
            # jedną pozycję (patrz _build_ui) - ustawiamy ją od razu na
            # aktualnie przeglądaną placówkę, żeby domyślnie trafił tam,
            # gdzie użytkownik go dodaje, zamiast na pierwszą z listy.
            if self.location_combo is not None:
                idx = self.location_combo.findData(self.default_location_key or "")
                self.location_combo.setCurrentIndex(idx if idx >= 0 else 0)
            return
        self.last_name.setText(self.employee.last_name)
        self.first_name.setText(self.employee.first_name)
        for key, checkbox in self.role_checkboxes.items():
            if key in _EMPLOYEE_FIELDS:
                checkbox.setChecked(getattr(self.employee, key, False))
            else:
                checkbox.setChecked(self.employee.custom_roles.get(key, False))
        self.monthly_target_hours.setValue(self.employee.monthly_target_hours)
        idx = self.employment_fraction.findData(self.employee.employment_fraction)
        if idx >= 0:
            self.employment_fraction.setCurrentIndex(idx)
        if self.no_24h_check is not None:
            self.no_24h_check.setChecked(self.employee.custom_roles.get(NIE_CHCE_24H_ROLE_KEY, False))
        if self.location_combo is not None:
            idx = self.location_combo.findData(self.employee.location_key)
            self.location_combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _save(self):
        ln = self.last_name.text().strip()
        fn = self.first_name.text().strip()

        if not ln or not fn:
            QMessageBox.critical(self, "Błąd", "Imię i nazwisko nie mogą być puste.")
            return

        legacy_roles = {}
        custom_roles = {}
        for role in self.profile.roles:
            key = role.key
            if key in self.role_checkboxes:
                value = self.role_checkboxes[key].isChecked()
            else:
                # Hidden because its linked_policy is DISABLED - preserve
                # whatever the employee already had instead of silently
                # wiping it to False (e.g. turning the "meat" policy off
                # must not un-flag every meat-counter employee).
                if key in _EMPLOYEE_FIELDS:
                    value = getattr(self.employee, key, False) if self.employee else False
                else:
                    value = self.employee.custom_roles.get(key, False) if self.employee else False

            if key in _EMPLOYEE_FIELDS:
                legacy_roles[key] = value
            else:
                custom_roles[key] = value

        if self.no_24h_check is not None:
            custom_roles[NIE_CHCE_24H_ROLE_KEY] = self.no_24h_check.isChecked()
        elif self.employee is not None:
            # Checkbox niewidoczny (projekt nie używa rotacji 24/7) - nie
            # wolno cicho zgubić wartości, gdyby jednak była już ustawiona
            # (np. lokalizacja z rotacją została w międzyczasie usunięta).
            custom_roles[NIE_CHCE_24H_ROLE_KEY] = self.employee.custom_roles.get(NIE_CHCE_24H_ROLE_KEY, False)

        location_key = self.location_combo.currentData() if self.location_combo is not None else ""

        try:
            emp = Employee(
                last_name=ln,
                first_name=fn,
                monthly_target_hours=self.monthly_target_hours.value(),
                employment_fraction=self.employment_fraction.currentData(),
                custom_roles=custom_roles,
                location_key=location_key,
                **legacy_roles,
            )
            emp.validate()
        except Exception as exc:
            QMessageBox.critical(self, "Błąd", str(exc))
            return

        self.employee_result = emp
        self.accept()

    def _delete_employee(self):
        reply = QMessageBox.question(
            self,
            "Usuń pracownika",
            f"Czy na pewno chcesz usunąć pracownika: {self.employee.first_name} {self.employee.last_name}?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self.employee_result = None
            self.accept()