from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from model.monthly_project import (
    MONTH_STATE_EDITING,
    MONTH_STATE_EMPTY,
    MONTH_STATE_READY,
    describe_month_state,
    month_state_class,
)

_MONTH_NAMES = [
    "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
    "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień",
]

# Ten sam trójstopniowy podział co model/monthly_project.py::month_state_class -
# szary (brak danych) / żółty (w trakcie edycji) / zielony (grafik gotowy).
_STATE_COLORS = {
    MONTH_STATE_EMPTY: "#b7c0cc",
    MONTH_STATE_EDITING: "#e0a92e",
    MONTH_STATE_READY: "#2f9e57",
}


class _MonthTile(QFrame):
    """Pojedynczy kafelek miesiąca w MonthPickerDialog - wzorowany na karcie
    pliku z ekranu startowego Photoshopa: nazwa + krótki, liczony na żywo
    opis stanu (patrz model/monthly_project.py::describe_month_state) +
    kolorowy akcent po lewej mówiący o stanie na pierwszy rzut oka. Klik
    zaznacza, dwuklik od razu otwiera (patrz MonthPickerDialog._open)."""

    clicked = Signal(int, int)
    opened = Signal(int, int)

    def __init__(self, year: int, month: int, pair, is_current: bool, parent=None):
        super().__init__(parent)
        self.year = year
        self.month = month
        self.setObjectName("monthTile")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(86)

        state = month_state_class(pair)
        accent = _STATE_COLORS[state]
        muted = state == MONTH_STATE_EMPTY

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(4)

        name_label = QLabel(_MONTH_NAMES[month - 1])
        name_label.setObjectName("monthTileName")
        layout.addWidget(name_label)

        status_label = QLabel(describe_month_state(pair))
        status_label.setObjectName("monthTileStatus")
        status_label.setWordWrap(True)
        layout.addWidget(status_label)

        layout.addStretch(1)

        if is_current:
            badge = QLabel("Aktualnie otwarty")
            badge.setObjectName("monthTileBadge")
            layout.addWidget(badge)

        text_color = "#9aa4b2" if muted else "#1f2937"
        status_color = "#b0b8c4" if muted else "#6b7280"
        self._selected_style = (
            f"QFrame#monthTile {{"
            f"  background: #ffffff;"
            f"  border: 2px solid #1d4ed8;"
            f"  border-left: 5px solid {accent};"
            f"  border-radius: 10px;"
            f"}}"
        )
        self._unselected_style = (
            f"QFrame#monthTile {{"
            f"  background: #ffffff;"
            f"  border: 1px solid #d7e0ea;"
            f"  border-left: 5px solid {accent};"
            f"  border-radius: 10px;"
            f"}}"
            f"QFrame#monthTile:hover {{"
            f"  border: 1px solid #94a9c9;"
            f"  border-left: 5px solid {accent};"
            f"}}"
        )
        name_label.setStyleSheet(f"font-weight: 600; font-size: 11pt; color: {text_color};")
        status_label.setStyleSheet(f"font-size: 9pt; color: {status_color};")
        if is_current:
            badge.setStyleSheet("font-size: 8pt; font-weight: 600; color: #1d4ed8;")
        self.set_selected(False)

    def set_selected(self, selected: bool) -> None:
        self.setStyleSheet(self._selected_style if selected else self._unselected_style)

    def mousePressEvent(self, event):
        self.clicked.emit(self.year, self.month)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.opened.emit(self.year, self.month)
        super().mouseDoubleClickEvent(event)


class MonthPickerDialog(QDialog):
    """Okno wyboru miesiąca, w formie kalendarza rocznego - zastępuje dawny
    spinbox + niszczące ostrzeżenie "zmiana miesiąca skasuje grafik" (patrz
    ENYO_ONLY_CHANGES.md, "Pamięć wielu miesięcy"). Siatka 4x3 kafelków, po
    jednym na każdy miesiąc widocznego roku, z krótkim opisem stanu; rok
    przełącza się strzałkami. Przełączanie NIGDY już nie kasuje danych
    (patrz ui/main_window.py::_switch_to_month), więc to zwykły wybór, nie
    decyzja obarczona ryzykiem - stąd brak dodatkowego potwierdzenia."""

    def __init__(self, project, current_year: int, current_month: int, parent=None):
        super().__init__(parent)
        self.project = project
        self.current_year = current_year
        self.current_month = current_month
        self._displayed_year = current_year
        self._selected = (current_year, current_month)
        self._tiles: dict[tuple[int, int], _MonthTile] = {}

        self.result_year = None
        self.result_month = None

        self.setWindowTitle("Wybór miesiąca")
        self.setModal(True)
        self.setMinimumWidth(640)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)

        header = QHBoxLayout()
        prev_btn = QPushButton("‹")
        prev_btn.setObjectName("secondaryButton")
        prev_btn.setFixedWidth(36)
        prev_btn.clicked.connect(lambda: self._shift_year(-1))
        header.addWidget(prev_btn)

        self.year_label = QLabel(str(self._displayed_year))
        self.year_label.setObjectName("sectionLabel")
        self.year_label.setAlignment(Qt.AlignCenter)
        header.addWidget(self.year_label, 1)

        next_btn = QPushButton("›")
        next_btn.setObjectName("secondaryButton")
        next_btn.setFixedWidth(36)
        next_btn.clicked.connect(lambda: self._shift_year(1))
        header.addWidget(next_btn)

        today_btn = QPushButton("Dziś")
        today_btn.setObjectName("secondaryButton")
        today_btn.clicked.connect(self._jump_to_today)
        header.addWidget(today_btn)

        root.addLayout(header)

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(10)
        root.addWidget(self.grid_container)

        legend = QLabel(
            f'<span style="color:{_STATE_COLORS[MONTH_STATE_EMPTY]}">●</span> Pusty grafik &nbsp;&nbsp;'
            f'<span style="color:{_STATE_COLORS[MONTH_STATE_EDITING]}">●</span> W trakcie edycji &nbsp;&nbsp;'
            f'<span style="color:{_STATE_COLORS[MONTH_STATE_READY]}">●</span> Grafik gotowy'
        )
        legend.setStyleSheet("color: #6b7280; font-size: 9pt;")
        root.addWidget(legend)

        buttons = QDialogButtonBox()
        cancel_btn = QPushButton("Anuluj")
        cancel_btn.setObjectName("secondaryButton")
        self.open_btn = QPushButton("Otwórz")
        self.open_btn.setObjectName("primaryButton")
        buttons.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        buttons.addButton(self.open_btn, QDialogButtonBox.AcceptRole)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._confirm_selected)
        root.addWidget(buttons)

        self._rebuild_grid()

    def _rebuild_grid(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._tiles = {}

        for month in range(1, 13):
            pair = self.project.get(self._displayed_year, month)
            is_current = (self._displayed_year, month) == (self.current_year, self.current_month)
            tile = _MonthTile(self._displayed_year, month, pair, is_current, self.grid_container)
            tile.clicked.connect(self._select)
            tile.opened.connect(self._open)
            row, col = divmod(month - 1, 4)
            self.grid_layout.addWidget(tile, row, col)
            self._tiles[(self._displayed_year, month)] = tile

        self.year_label.setText(str(self._displayed_year))
        self._refresh_selection_visuals()

    def _shift_year(self, delta: int) -> None:
        self._displayed_year += delta
        self._rebuild_grid()

    def _jump_to_today(self) -> None:
        today = date.today()
        self._displayed_year = today.year
        self._selected = (today.year, today.month)
        self._rebuild_grid()

    def _select(self, year: int, month: int) -> None:
        self._selected = (year, month)
        self._refresh_selection_visuals()

    def _refresh_selection_visuals(self) -> None:
        for key, tile in self._tiles.items():
            tile.set_selected(key == self._selected)

    def _open(self, year: int, month: int) -> None:
        self._selected = (year, month)
        self._confirm_selected()

    def _confirm_selected(self) -> None:
        self.result_year, self.result_month = self._selected
        self.accept()
