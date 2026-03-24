from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QComboBox,
)

from model.employee import Employee


class EmployeeDialog(QDialog):
    def __init__(self, parent=None, employee=None):
        super().__init__(parent)
        self.employee = employee
        self.setWindowTitle("Edytuj pracownika" if employee else "Dodaj pracownika")
        self.setModal(True)
        self.setMinimumWidth(420)

        self._build_ui()
        self._fill_from_employee()

    def _build_ui(self):
        root = QVBoxLayout(self)

        title = QLabel("Dane pracownika")
        title.setObjectName("sectionLabel")
        root.addWidget(title)

        form = QFormLayout()

        self.last_name = QLineEdit()
        self.first_name = QLineEdit()
        self.monthly_target_hours = QSpinBox()
        self.monthly_target_hours.setRange(0, 400)
        self.monthly_target_hours.setValue(160)
        self.employment_fraction = QComboBox()

        self.employment_fraction.addItem("1/1 (pełny etat)", 1.0)
        self.employment_fraction.addItem("7/8", 0.875)
        self.employment_fraction.addItem("3/4", 0.75)
        self.employment_fraction.addItem("5/8", 0.625)
        self.employment_fraction.addItem("1/2 (pół etatu)", 0.5)
        self.employment_fraction.addItem("3/8", 0.375)
        self.employment_fraction.addItem("1/4", 0.25)

        self.is_opener = QCheckBox("Pracownik otwarcia")
        self.is_meat = QCheckBox("Pracownik mięsa")

        form.addRow("Nazwisko", self.last_name)
        form.addRow("Imię", self.first_name)
        form.addRow("Cel miesięczny", self.monthly_target_hours)
        form.addRow("Wymiar etatu", self.employment_fraction)

        root.addLayout(form)
        root.addWidget(self.is_opener)
        root.addWidget(self.is_meat)

        # 🔥 przycisk usuwania (tylko przy edycji)
        if self.employee:
            self.delete_btn = QPushButton("Usuń pracownika")
            self.delete_btn.setStyleSheet("background-color: #b00020; color: white;")
            self.delete_btn.clicked.connect(self._delete_employee)
            root.addWidget(self.delete_btn)

        buttons = QDialogButtonBox()
        cancel_btn = QPushButton("Anuluj")
        save_btn = QPushButton("Zapisz")
        save_btn.setObjectName("primaryButton")
        buttons.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        buttons.addButton(save_btn, QDialogButtonBox.AcceptRole)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._save)

        root.addWidget(buttons)

    def _fill_from_employee(self):
        if not self.employee:
            return
        self.last_name.setText(self.employee.last_name)
        self.first_name.setText(self.employee.first_name)
        self.is_opener.setChecked(self.employee.is_opener)
        self.is_meat.setChecked(self.employee.is_meat)
        self.monthly_target_hours.setValue(self.employee.monthly_target_hours)
        idx = self.employment_fraction.findData(self.employee.employment_fraction)
        if idx >= 0:
            self.employment_fraction.setCurrentIndex(idx)

    def _save(self):
        try:
            emp = Employee(
                last_name=self.last_name.text().strip(),
                first_name=self.first_name.text().strip(),
                is_opener=self.is_opener.isChecked(),
                is_meat=self.is_meat.isChecked(),
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
            "Czy na pewno chcesz usunąć tego pracownika?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self.employee_result = None
            self.accept()