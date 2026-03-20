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
        self.daily_hours = QSpinBox()
        self.daily_hours.setRange(6, 8)
        self.daily_hours.setValue(8)

        self.is_opener = QCheckBox("Pracownik otwarcia")
        self.is_meat = QCheckBox("Pracownik mięsa")

        form.addRow("Nazwisko", self.last_name)
        form.addRow("Imię", self.first_name)
        form.addRow("Cel miesięczny", self.monthly_target_hours)
        form.addRow("Godzin dziennie", self.daily_hours)

        root.addLayout(form)
        root.addWidget(self.is_opener)
        root.addWidget(self.is_meat)

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
        self.daily_hours.setValue(self.employee.daily_hours)

    def _save(self):
        try:
            emp = Employee(
                last_name=self.last_name.text().strip(),
                first_name=self.first_name.text().strip(),
                is_opener=self.is_opener.isChecked(),
                is_meat=self.is_meat.isChecked(),
                monthly_target_hours=self.monthly_target_hours.value(),
                daily_hours=self.daily_hours.value(),
            )
            emp.validate()
        except Exception as exc:
            QMessageBox.critical(self, "Błąd", str(exc))
            return

        self.employee_result = emp
        self.accept()
