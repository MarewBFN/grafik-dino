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


class EmployeeDialog(QDialog):
    def __init__(self, parent=None, employee=None):
        super().__init__(parent)
        self.employee = employee
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

        self.is_opener = QCheckBox("Pracownik otwarcia")
        flags_layout.addWidget(self.is_opener)

        self.is_meat = QCheckBox("Obsługa stoiska mięsnego")
        flags_layout.addWidget(self.is_meat)

        self.is_meat_light = QCheckBox("mooooże stanąć na chwilę na mięsie")
        flags_layout.addWidget(self.is_meat_light)

        self.is_meat.toggled.connect(self._on_meat_toggled)
        self.is_meat_light.toggled.connect(self._on_meat_light_toggled)

        self.is_manager = QCheckBox(
            "Kierowniczka (sztywny grafik: pon. wolne, wt-pt 7:00-15:00, sob 6:00-14:00)"
        )
        flags_layout.addWidget(self.is_manager)
        self.is_manager.toggled.connect(self._on_manager_toggled)

        self.no_night = QCheckBox("Nie pracuje w godzinach nocnych (przed 6:00 i po 22:00)")
        flags_layout.addWidget(self.no_night)

        self.no_afternoon = QCheckBox("Nie pracuje na popołudniu (tylko zmiany poranne)")
        flags_layout.addWidget(self.no_afternoon)

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
        if checked and self.is_meat_light.isChecked():
            self.is_meat_light.setChecked(False)

    def _on_meat_light_toggled(self, checked):
        if checked and self.is_meat.isChecked():
            self.is_meat.setChecked(False)

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
        self.is_opener.setChecked(self.employee.is_opener)
        self.is_meat.setChecked(self.employee.is_meat)
        self.is_meat_light.setChecked(getattr(self.employee, "is_meat_light", False))
        self.is_manager.setChecked(getattr(self.employee, "is_manager", False))
        self.no_night.setChecked(getattr(self.employee, "no_night", False))
        self.no_afternoon.setChecked(getattr(self.employee, "no_afternoon", False))
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

        try:
            emp = Employee(
                last_name=ln,
                first_name=fn,
                is_opener=self.is_opener.isChecked(),
                is_meat=self.is_meat.isChecked(),
                is_meat_light=self.is_meat_light.isChecked(),
                is_manager=self.is_manager.isChecked(),
                no_night=self.no_night.isChecked(),
                no_afternoon=self.no_afternoon.isChecked(),
                monthly_target_hours=self.monthly_target_hours.value(),
                employment_fraction=self.employment_fraction.currentData(),
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