"""Pracownicy (pasek menu) - lista wszystkich pracowników projektu w jednym
miejscu: podgląd danych i flag, dodawanie, edycja, usuwanie oraz dane
osobowe („Zaawansowane”: imię, nazwisko, telefon, e-mail, adres) pod
przyszłe wnioski urlopowe.

Wszystkie zmiany idą przez ScheduleController (cofnij/ponów jak przy
edycji z tabeli grafiku); po każdej woła `on_changed`, żeby główne okno
odświeżyło grafik."""

import dataclasses
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from logic.generator.duty_rotation_constraint import NIE_CHCE_24H_ROLE_KEY
from logic.utils.time_utils import month_scope_note
from model.business_profile import get_profile
from ui.employee_dialog import EmployeeDialog
from ui.theme import ACCENT, ACCENT_SOFT

EMPLOYMENT_FRACTION_LABELS = {
    1.01: "1/1 (max 8:00)",
    1.0: "1/1",
    0.875: "7/8",
    0.75: "3/4",
    0.625: "5/8",
    0.5: "1/2",
    0.375: "3/8",
    0.25: "1/4",
}

# Flagi z dedykowanymi checkboxami w EmployeeDialog (poza profile.roles).
_EXTRA_FLAG_LABELS = {
    NIE_CHCE_24H_ROLE_KEY: "Nie chce 24h",
    "no_night": "Bez nocy",
    "no_afternoon": "Bez popołudni",
}

COLUMNS = ("Pracownik", "Placówka", "Etat", "Flagi", "Telefon", "E-mail", "Adres", "")
COL_ACTIONS = len(COLUMNS) - 1

# Wysokość wiersza wymuszona po resizeRowsToContents() - sizeHint()
# przyciskow stylowanych przez QSS (ui/theme.py#QPushButton) bywa zaniżony
# względem realnie renderowanej wysokości, przez co dół przycisków
# "Edytuj/Zaawansowane/Usuń" (patrz _actions_widget) wychodził poza wiersz.
_ROW_HEIGHT = 44


def employee_flag_labels(emp, shop_config) -> list[str]:
    """Nazwy ról/ograniczeń, które pracownik ma zaznaczone."""
    profile = get_profile(shop_config.business_type if shop_config else None)
    labels, seen = [], set()
    for role in profile.roles:
        if role.key not in seen and emp.has_role(role.key):
            labels.append(role.label)
        seen.add(role.key)
    for key, label in _EXTRA_FLAG_LABELS.items():
        if key not in seen and emp.has_role(key):
            labels.append(label)
    return labels


def short_flag_label(label: str) -> str:
    """Etykieta roli bez dopisku w nawiasie - do kolumny „Flagi” (pełna w
    podpowiedzi)."""
    return re.sub(r"\s*\(.*\)\s*$", "", label) or label


def employment_fraction_label(fraction: float) -> str:
    return EMPLOYMENT_FRACTION_LABELS.get(fraction, f"{fraction:g}")


def _etat_cell_widget(label: str) -> QWidget:
    chip = QLabel(label)
    chip.setAlignment(Qt.AlignCenter)
    chip.setStyleSheet(
        f"background: {ACCENT_SOFT}; color: {ACCENT}; border-radius: 9px; "
        "padding: 2px 10px; font-size: 10px; font-weight: 700;"
    )
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(6, 4, 6, 4)
    layout.addStretch()
    layout.addWidget(chip)
    layout.addStretch()
    return widget


def _flags_cell_widget(flags: list[str]) -> QWidget:
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(6, 4, 6, 4)
    layout.setSpacing(4)
    if flags:
        for label in flags:
            chip = QLabel(short_flag_label(label))
            chip.setStyleSheet(
                "background: #eef2f7; color: #334155; border-radius: 9px; "
                "padding: 2px 9px; font-size: 10px; font-weight: 600;"
            )
            layout.addWidget(chip)
        widget.setToolTip("\n".join(flags))
    else:
        empty = QLabel("—")
        empty.setObjectName("mutedHint")
        layout.addWidget(empty)
    layout.addStretch()
    return widget


class PersonalDataDialog(QDialog):
    """Zaawansowane: dane osobowe jednego pracownika. `employee_result` to
    kopia pracownika z nowymi danymi (pozostałe pola bez zmian)."""

    def __init__(self, parent, employee):
        super().__init__(parent)
        self.employee = employee
        self.employee_result = None
        self.setWindowTitle(f"Dane osobowe — {employee.display_name()}")
        self.setModal(True)
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        root.setSpacing(12)

        title = QLabel("Dane osobowe")
        title.setObjectName("sectionLabel")
        root.addWidget(title)
        hint = QLabel("Potrzebne do wniosków urlopowych. Generator grafiku ich nie używa.")
        hint.setObjectName("mutedHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(10)
        self.first_name = QLineEdit(employee.first_name)
        self.last_name = QLineEdit(employee.last_name)
        self.phone = QLineEdit(employee.phone)
        self.phone.setPlaceholderText("np. 600 123 456")
        self.email = QLineEdit(employee.email)
        self.email.setPlaceholderText("np. jan.kowalski@firma.pl")
        self.street = QLineEdit(employee.street)
        self.street.setPlaceholderText("ulica, nr domu / mieszkania")
        self.postal_code = QLineEdit(employee.postal_code)
        self.postal_code.setPlaceholderText("00-000")
        self.postal_code.setMaxLength(6)
        self.city = QLineEdit(employee.city)
        form.addRow("Imię:", self.first_name)
        form.addRow("Nazwisko:", self.last_name)
        form.addRow("Telefon:", self.phone)
        form.addRow("E-mail:", self.email)
        form.addRow("Adres:", self.street)
        form.addRow("Kod pocztowy:", self.postal_code)
        form.addRow("Miejscowość:", self.city)
        root.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_btn = QPushButton("Anuluj")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Zapisz")
        save_btn.setObjectName("primaryButton")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        root.addLayout(buttons)

    def _save(self):
        try:
            emp = dataclasses.replace(
                self.employee,
                first_name=self.first_name.text().strip(),
                last_name=self.last_name.text().strip(),
                phone=self.phone.text().strip(),
                email=self.email.text().strip(),
                street=self.street.text().strip(),
                postal_code=self.postal_code.text().strip(),
                city=self.city.text().strip(),
            )
            emp.validate()
        except ValueError as exc:
            QMessageBox.critical(self, "Błąd", str(exc))
            return
        self.employee_result = emp
        self.accept()


class EmployeesDialog(QDialog):
    def __init__(self, parent, controller, shop_config, on_changed=None, default_location_key=None):
        super().__init__(parent)
        self.controller = controller
        self.shop_config = shop_config
        self.on_changed = on_changed
        self.default_location_key = default_location_key
        self.setWindowTitle("Pracownicy")
        self.setModal(True)
        self.resize(1250, 600)

        root = QVBoxLayout(self)
        root.setSpacing(12)

        header = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setObjectName("sectionLabel")
        header.addWidget(self.title_label)
        header.addStretch()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Szukaj pracownika…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumWidth(220)
        self.search_edit.textChanged.connect(self.refresh)
        header.addWidget(self.search_edit)
        self.add_btn = QPushButton("+ Dodaj pracownika")
        self.add_btn.setObjectName("primaryButton")
        self.add_btn.clicked.connect(self._add_employee)
        header.addWidget(self.add_btn)
        root.addLayout(header)

        hint = QLabel(
            "Wszyscy pracownicy tego projektu - dane do grafiku, role i dane "
            "kontaktowe w jednym miejscu."
        )
        hint.setObjectName("mutedHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        if shop_config is not None:
            scope_note = QLabel(month_scope_note(shop_config.year, shop_config.month))
            scope_note.setObjectName("quickInfoHint")
            scope_note.setWordWrap(True)
            root.addWidget(scope_note)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setObjectName("employeesTable")
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setWordWrap(True)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(
            "QTableWidget#employeesTable { alternate-background-color: #f8fafc; }"
            "QTableWidget#employeesTable::item { padding: 4px 8px; }"
        )
        self.table.cellDoubleClicked.connect(lambda row, _col: self._edit_employee(self._row_employees[row]))
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.Stretch)
        header_view.setMinimumSectionSize(60)
        root.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        bottom.addStretch()
        close_btn = QPushButton("Zamknij")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        root.addLayout(bottom)

        self._row_employees = []
        self.refresh()

    @property
    def schedule(self):
        return self.controller.schedule

    def _location_name(self, emp) -> str:
        loc = self.shop_config.locations.get(emp.location_key) if self.shop_config else None
        return loc.name if loc is not None else ""

    def refresh(self):
        employees = list(self.schedule.employees)
        self.title_label.setText(f"Pracownicy ({len(employees)})")
        query = self.search_edit.text().strip().casefold()
        if query:
            employees = [
                e for e in employees
                if query in e.display_name().casefold() or query in self._location_name(e).casefold()
            ]

        self._row_employees = employees
        self.table.setRowCount(len(employees))
        for row, emp in enumerate(employees):
            flags = employee_flag_labels(emp, self.shop_config)
            # Kolumny 1/4/5/6 zostają zwykłymi QTableWidgetItem (tekst do
            # testów/wyszukiwania); 2/3 dostają dodatkowo widget rysowany NAD
            # itemem - "chip" etatu, "chipy" flag (patrz
            # _etat_cell_widget/_flags_cell_widget).
            text_columns = {
                0: emp.display_name(),
                1: self._location_name(emp),
                4: emp.phone,
                5: emp.email,
                6: emp.address(),
            }
            for col, text in text_columns.items():
                item = QTableWidgetItem(text)
                if col == 0:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.table.setItem(row, col, item)
            self.table.setCellWidget(
                row, 2, _etat_cell_widget(employment_fraction_label(emp.employment_fraction))
            )
            self.table.setCellWidget(row, 3, _flags_cell_widget(flags))
            self.table.setCellWidget(row, COL_ACTIONS, self._actions_widget(emp))
        self.table.resizeRowsToContents()
        # resizeRowsToContents() liczy po sizeHint() przycisków, który bywa
        # zaniżony względem realnie renderowanej wysokości - stąd twarde
        # dociśnięcie do _ROW_HEIGHT, żeby "Edytuj/Zaawansowane/Usuń" zawsze
        # mieściły się w całości w wierszu.
        for row in range(self.table.rowCount()):
            if self.table.rowHeight(row) < _ROW_HEIGHT:
                self.table.setRowHeight(row, _ROW_HEIGHT)

    def _actions_widget(self, emp) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)
        for text, name, handler, tooltip in (
            ("Edytuj", "secondaryButton", self._edit_employee, "Dane do grafiku i flagi pracownika"),
            ("Zaawansowane", "secondaryButton", self._edit_personal_data,
             "Dane osobowe: imię, nazwisko, telefon, e-mail, adres"),
            ("Usuń", "dangerButton", self._delete_employee, "Usuń pracownika z grafiku"),
        ):
            btn = QPushButton(text)
            btn.setObjectName(name)
            btn.setToolTip(tooltip)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(30)
            btn.clicked.connect(lambda _checked=False, e=emp, h=handler: h(e))
            layout.addWidget(btn)
        return widget

    def _changed(self, message: str):
        self.refresh()
        if self.on_changed is not None:
            self.on_changed(message)

    def _name_taken(self, old, new) -> bool:
        return new != old and new in self.schedule.employees

    def _add_employee(self):
        dialog = EmployeeDialog(self, shop_config=self.shop_config, default_location_key=self.default_location_key)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.controller.add_employee(dialog.employee_result)
        except ValueError as exc:
            QMessageBox.critical(self, "Błąd", str(exc))
            return
        self._changed("Dodano pracownika.")

    def _edit_employee(self, emp):
        dialog = EmployeeDialog(self, employee=emp, shop_config=self.shop_config)
        if dialog.exec() != QDialog.Accepted:
            return
        if dialog.employee_result is None:  # „Usuń pracownika” w tym oknie
            self.controller.remove_employee(emp)
            self._changed("Usunięto pracownika.")
            return
        self._replace(emp, dialog.employee_result, "Zapisano pracownika.")

    def _edit_personal_data(self, emp):
        dialog = PersonalDataDialog(self, emp)
        if dialog.exec() != QDialog.Accepted:
            return
        self._replace(emp, dialog.employee_result, "Zapisano dane osobowe.")

    def _replace(self, old, new, message):
        # replace_employee usuwa starego przed dodaniem nowego - kolizja
        # imienia i nazwiska zgubiłaby jego grafik, więc sprawdzamy wcześniej.
        if self._name_taken(old, new):
            QMessageBox.critical(self, "Błąd", f"Pracownik „{new.display_name()}” już istnieje.")
            return
        self.controller.replace_employee(old, new)
        self._changed(message)

    def _delete_employee(self, emp):
        reply = QMessageBox.question(
            self,
            "Usuń pracownika",
            f"Czy na pewno chcesz usunąć pracownika: {emp.display_name()}?\n"
            "Jego grafik w tym miesiącu zostanie usunięty.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.controller.remove_employee(emp)
        self._changed("Usunięto pracownika.")
