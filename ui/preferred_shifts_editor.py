from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from model.location import MAX_PREFERRED_SHIFTS, normalize_preferred_shifts
from ui.time_input import TimeInputWidget


class _PreferredShiftRow(QWidget):
    def __init__(self, on_remove, start="", end=""):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("od"))
        self.start_input = TimeInputWidget()
        if start:
            self.start_input.set_time_str(start)
        layout.addWidget(self.start_input)

        layout.addWidget(QLabel("do"))
        self.end_input = TimeInputWidget()
        if end:
            self.end_input.set_time_str(end)
        layout.addWidget(self.end_input)

        self.remove_btn = QPushButton("Usuń")
        self.remove_btn.setObjectName("secondaryButton")
        self.remove_btn.clicked.connect(lambda: on_remove(self))
        layout.addWidget(self.remove_btn)
        layout.addStretch()

    def get_pair(self) -> dict:
        return {"start": self.start_input.get_time_str(), "end": self.end_input.get_time_str()}


class PreferredShiftsEditor(QFrame):
    """"Preferowane godziny pracy" (LocationConfig.preferred_shifts) - opcje
    zaawansowane lokalizacji modelu godzin otwarcia (profil Ochrony bez
    rotacji 24/7, ui/locations_dialog.py). Zamiast jednej zmiany na całe
    okno dnia, użytkownik podaje tu konkretne godziny podziału (np.
    7:00-15:00 + 15:00-22:00 zamiast jednej osoby 7:00-22:00), których
    generator w miarę możliwości używa zamiast domyślnego kształtu (patrz
    logic/generator/opening_hours_coverage.py::window_shapes/
    prefer_preferred_shifts_terms) - miękka preferencja, nie twardy wymóg.

    Walidacja (normalize_preferred_shifts - każdy przedział musi się mieścić
    w co najmniej jednym dniu godzin otwarcia tej lokalizacji) następuje
    dopiero w get_preferred_shifts(), wołanym przez wywołującego z aktualnymi
    godzinami otwarcia (LocationsDialog._save() - patrz komentarz tam), nie
    na bieżąco przy wpisywaniu."""

    def __init__(self, enabled=False, preferred_shifts=None, parent=None):
        super().__init__(parent)
        self.setObjectName("configCard")
        outer = QVBoxLayout(self)

        self.enabled_check = QCheckBox("Preferowane godziny pracy")
        self.enabled_check.setChecked(bool(enabled))
        self.enabled_check.toggled.connect(self._update_visibility)
        outer.addWidget(self.enabled_check)

        hint = QLabel(
            "Zamiast jednej zmiany na całe okno dnia, generator w miarę "
            "możliwości użyje podanych tu godzin (np. 7:00-15:00 i "
            "15:00-22:00 zamiast jednej osoby 7:00-22:00) - każdy przedział "
            "musi się mieścić w godzinach otwarcia tej lokalizacji. To "
            "preferencja, nie twardy wymóg - gdy zabraknie ludzi, generator "
            "nadal może wrócić do jednej zmiany."
        )
        hint.setObjectName("mutedHint")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        self.rows_container = QVBoxLayout()
        outer.addLayout(self.rows_container)

        self.add_btn = QPushButton("Dodaj godziny")
        self.add_btn.setObjectName("secondaryButton")
        self.add_btn.clicked.connect(lambda: self._add_row())
        outer.addWidget(self.add_btn)

        self._rows: list[_PreferredShiftRow] = []
        for entry in preferred_shifts or []:
            self._add_row(entry.get("start", ""), entry.get("end", ""))

        self._update_visibility()

    def _add_row(self, start="", end="") -> None:
        if len(self._rows) >= MAX_PREFERRED_SHIFTS:
            return
        row = _PreferredShiftRow(self._remove_row, start, end)
        row.setVisible(self.enabled_check.isChecked())
        self._rows.append(row)
        self.rows_container.addWidget(row)
        self._update_add_button()

    def _remove_row(self, row) -> None:
        self._rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._update_add_button()

    def _update_add_button(self) -> None:
        self.add_btn.setEnabled(len(self._rows) < MAX_PREFERRED_SHIFTS)

    def _update_visibility(self) -> None:
        enabled = self.enabled_check.isChecked()
        for row in self._rows:
            row.setVisible(enabled)
        self.add_btn.setVisible(enabled)

    def get_preferred_shifts(self, open_hours: dict) -> tuple[bool, list]:
        """(enabled, znormalizowana lista) dla LocationConfig - może rzucić
        ValueError (patrz normalize_preferred_shifts), gdy któryś przedział
        jest niejednoznaczny albo wykracza poza `open_hours` tej lokalizacji
        (wywołujący - LocationsDialog._save() - łapie i pokazuje
        użytkownikowi, z nazwą lokalizacji)."""
        enabled = self.enabled_check.isChecked()
        if not enabled:
            return False, [row.get_pair() for row in self._rows]
        return True, normalize_preferred_shifts([row.get_pair() for row in self._rows], open_hours)
