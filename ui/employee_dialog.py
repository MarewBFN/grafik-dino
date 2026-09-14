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
    QSpinBox,
    QVBoxLayout,
    QComboBox,
    QFrame,
    QSpacerItem,
    QSizePolicy
)

from model.employee import Employee
from model.business_profile import get_profile

# RoleDef.key values that map directly onto an Employee dataclass field
# (the six legacy Dino flags). Any other key lives in Employee.custom_roles
# instead, so new business profiles don't need new Employee fields.
_EMPLOYEE_FIELDS = {f.name for f in dataclasses.fields(Employee)}


class EmployeeDialog(QDialog):
    def __init__(self, parent=None, employee=None, business_type=None):
        super().__init__(parent)
        self.employee = employee
        self.profile = get_profile(business_type)
        self.role_checkboxes: dict[str, QCheckBox] = {}
        self.setWindowTitle("Edytuj pracownika" if employee else "Dodaj pracownika")
        self.setModal(True)
        self.setMinimumWidth(460)

        # Wygląd pochodzi ze wspólnego arkusza stylów aplikacji (ui/theme.py).
        self._build_ui()
        self._fill_from_employee()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(15)

        title = QLabel("Dane pracownika")
        title.setObjectName("sectionLabel")
        root.addWidget(title)

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

        root.addLayout(form)

        # --- Role i ograniczenia: jedna karta zamiast osobnej ramki na checkbox ---
        flags_card = QFrame()
        flags_card.setObjectName("configCard")
        flags_layout = QVBoxLayout(flags_card)
        flags_layout.setSpacing(10)

        for role in self.profile.roles:
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

        root.addWidget(flags_card)
        root.addStretch()

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

    def _save(self):
        ln = self.last_name.text().strip()
        fn = self.first_name.text().strip()

        if not ln or not fn:
            QMessageBox.critical(self, "Błąd", "Imię i nazwisko nie mogą być puste.")
            return

        legacy_roles = {}
        custom_roles = {}
        for key, checkbox in self.role_checkboxes.items():
            if key in _EMPLOYEE_FIELDS:
                legacy_roles[key] = checkbox.isChecked()
            else:
                custom_roles[key] = checkbox.isChecked()

        try:
            emp = Employee(
                last_name=ln,
                first_name=fn,
                monthly_target_hours=self.monthly_target_hours.value(),
                employment_fraction=self.employment_fraction.currentData(),
                custom_roles=custom_roles,
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