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

        # Stylistyka spójna z ConfigDialog
        self.setStyleSheet("""
            QFrame#configCard {
                background-color: #f9f9f9;
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 5px;
            }
            QFrame#configCard:hover {
                background-color: #f0f7ff;
                border-color: #0078d4;
            }
            QCheckBox {
                font-size: 14px;
                font-weight: bold;
                spacing: 12px;
            }
            QCheckBox::indicator {
                width: 22px;
                height: 22px;
            }
            QLineEdit, QSpinBox, QComboBox {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border: 2px solid #0078d4;
            }
        """)

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
        self.employment_fraction.addItem("7/8", 0.875)
        self.employment_fraction.addItem("3/4", 0.75)
        self.employment_fraction.addItem("5/8", 0.625)
        self.employment_fraction.addItem("1/2 (pół etatu)", 0.5)
        self.employment_fraction.addItem("3/8", 0.375)
        self.employment_fraction.addItem("1/4", 0.25)

        form.addRow("Nazwisko:", self.last_name)
        form.addRow("Imię:", self.first_name)
        form.addRow("Cel miesięczny:", self.monthly_target_hours)
        form.addRow("Wymiar etatu:", self.employment_fraction)

        root.addLayout(form)

        # --- Karty Checkboxów ---
        self.is_opener = QCheckBox("Pracownik otwarcia")
        opener_card = QFrame()
        opener_card.setObjectName("configCard")
        opener_layout = QHBoxLayout(opener_card)
        opener_layout.addWidget(self.is_opener)
        root.addWidget(opener_card)

        self.is_meat = QCheckBox("Obsługa stoiska mięsnego")
        meat_card = QFrame()
        meat_card.setObjectName("configCard")
        meat_layout = QHBoxLayout(meat_card)
        meat_layout.addWidget(self.is_meat)
        root.addWidget(meat_card)

        root.addStretch()

        # --- Dolny pasek przycisków ---
        button_row = QHBoxLayout()

        # Przycisk Usuń (w lewym rogu)
        if self.employee:
            self.delete_btn = QPushButton("Usuń pracownika")
            self.delete_btn.setMinimumHeight(34)
            self.delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #fdf2f2;
                    color: #b00020;
                    border: 1px solid #f8b4b4;
                    border-radius: 4px;
                    padding: 0 15px;
                }
                QPushButton:hover {
                    background-color: #b00020;
                    color: white;
                }
            """)
            self.delete_btn.clicked.connect(self._delete_employee)
            button_row.addWidget(self.delete_btn)
        
        # Spacer przesuwa resztę na prawo
        button_row.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))

        # Przyciski Zapisz / Anuluj
        cancel_btn = QPushButton("Anuluj")
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