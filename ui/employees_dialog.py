"""Pracownicy (pasek menu) - lista wszystkich pracowników projektu w jednym
miejscu: podgląd danych i flag, dodawanie, edycja, usuwanie. Dane kontaktowe
(telefon/e-mail/adres) edytuje się w EmployeeDialog (ui/employee_dialog.py,
sekcja "Zaawansowane" -> "Dane kontaktowe") - dwuklik na odpowiedniej komórce
tej tabeli otwiera ją od razu rozwiniętą (patrz _on_cell_double_clicked).

Wszystkie zmiany idą przez ScheduleController (cofnij/ponów jak przy
edycji z tabeli grafiku); po każdej woła `on_changed`, żeby główne okno
odświeżyło grafik."""

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
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

# Dwuklik na komórce telefonu/e-maila/adresu otwiera EmployeeDialog z
# sekcją "Dane kontaktowe" (patrz ui/employee_dialog.py) od razu rozwiniętą
# i kursorem w tym polu, zamiast zwykłego "Edytuj" - patrz
# _on_cell_double_clicked. "Adres" w tabeli to w EmployeeDialog trzy osobne
# pola (ulica/kod/miasto) - dwuklik fokusuje pierwsze z nich.
CONTACT_FOCUS_FIELDS = {4: "phone", 5: "email", 6: "street"}

# Wysokość wiersza wymuszona po resizeRowsToContents(). Domyślny padding
# przycisków z globalnego QSS (ui/theme.py#QPushButton, 9px pionowo) daje
# wysokość bliską granicy wiersza, więc akcje w tabeli (patrz
# _actions_widget) dostają własny, ciaśniejszy padding (_ACTION_BUTTON_STYLE)
# zamiast polegać na zaniżonym sizeHint() - inaczej "Edytuj/Usuń" wychodziły
# poza wiersz.
_ROW_HEIGHT = 42
_ACTION_BUTTON_STYLE = "padding: 3px 10px; font-size: 9pt;"


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
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
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

    def _on_cell_double_clicked(self, row, col):
        emp = self._row_employees[row]
        focus_field = CONTACT_FOCUS_FIELDS.get(col)
        self._edit_employee(emp, expand_contact=focus_field is not None, focus_field=focus_field)

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
        # dociśnięcie do _ROW_HEIGHT, żeby "Edytuj"/"Usuń" zawsze mieściły
        # się w całości w wierszu.
        for row in range(self.table.rowCount()):
            if self.table.rowHeight(row) < _ROW_HEIGHT:
                self.table.setRowHeight(row, _ROW_HEIGHT)

    def _actions_widget(self, emp) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)
        for text, name, handler, tooltip in (
            ("Edytuj", "secondaryButton", self._edit_employee,
             "Dane do grafiku, flagi i dane kontaktowe pracownika"),
            ("Usuń", "dangerButton", self._delete_employee, "Usuń pracownika z grafiku"),
        ):
            btn = QPushButton(text)
            btn.setObjectName(name)
            btn.setToolTip(tooltip)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(_ACTION_BUTTON_STYLE)
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

    def _edit_employee(self, emp, expand_contact=False, focus_field=None):
        dialog = EmployeeDialog(
            self, employee=emp, shop_config=self.shop_config,
            expand_contact=expand_contact, focus_field=focus_field,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        if dialog.employee_result is None:  # „Usuń pracownika” w tym oknie
            self.controller.remove_employee(emp)
            self._changed("Usunięto pracownika.")
            return
        self._replace(emp, dialog.employee_result, "Zapisano pracownika.")

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
