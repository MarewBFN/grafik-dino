"""Legenda kolorów/zakreśleń komórek siatki grafiku (ui/grid_view.py) - na
życzenie użytkownika, zawsze pod ScheduleGrid (ui/main_window.py::
_build_right_panel). Wymienia wyłącznie stany widoczne w WIERSZACH
pracowników (kolory dnia) - wiersze podsumowania/walidacji pod spodem mają
już własne, samotłumaczące się etykiety ("Pokrycie", "Otwarcie" itd.), więc
nie potrzebują osobnej legendy.

Kolory i ich znaczenie zsynchronizowane ręcznie z
logic/schedule_presenter.py::get_cell_view() i
ui/grid_view.py::_fill_day_cells() - jeśli tam przybędzie nowy stan
wizualny, dopisz go też tutaj."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QWidget

from ui import theme

# (rodzaj, kolor, etykieta) - rodzaj "solid" maluje pełny kolor, "hatch"
# rysuje to samo szare ukośne kreskowanie co zablokowane/wolne dni w
# grid_view.py (QColor(205,205,205) + Qt.BDiagPattern - nie ma tam osobnej
# stałej w theme.py, więc powielone tu jawnie z tą samą wartością).
_HATCH_COLOR = QColor(205, 205, 205)

LEGEND_ENTRIES = [
    ("solid", theme.SHIFT_MORNING, "Zmiana otwierająca"),
    ("solid", theme.SHIFT_CLOSE, "Zmiana zamykająca"),
    ("solid", theme.SHIFT_NIGHT, "Zmiana nocna (przez północ)"),
    ("solid", theme.BG_MAIN, "Zwykła zmiana"),
    ("solid", theme.OK_GREEN, "Urlop"),
    ("solid", "#FFA07A", "Chorobowe (L4)"),
    ("solid", theme.BG_DISABLED, "Lokalizacja nieczynna"),
    ("hatch", None, "Zablokowane (dzień wolny / typ zmiany)"),
]

_SWATCH_SIZE = 16
_COLUMNS = 4


class _ColorSwatch(QWidget):
    """Mały kwadrat pokazujący dokładnie ten sam kolor/wzór, co komórka w
    siatce grafiku - żeby nie polegać na opisie słownym koloru."""

    def __init__(self, color: str | None, hatch: bool, parent=None):
        super().__init__(parent)
        self._color = QColor(color) if color else None
        self._hatch = hatch
        self.setFixedSize(_SWATCH_SIZE, _SWATCH_SIZE)

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.rect().adjusted(0, 0, -1, -1)

        if self._hatch:
            painter.fillRect(rect, QColor("white"))
            brush = QBrush(_HATCH_COLOR)
            brush.setStyle(Qt.BDiagPattern)
            painter.fillRect(rect, brush)
        else:
            painter.fillRect(rect, self._color)

        painter.setPen(QColor(theme.GRID_BORDER))
        painter.drawRect(rect)


class GridLegendWidget(QFrame):
    """Legenda kolorów komórek grafiku - patrz moduł. `set_compact_section`
    przełącza jej wygląd między "wtopioną" w panel (mało pracowników, dużo
    miejsca) a wyraźnie oddzieloną "kartą" (dużo pracowników, siatka i tak
    zajmuje większość ekranu) - patrz ui/main_window.py::_update_grid_legend."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("gridLegend")

        layout = QGridLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setHorizontalSpacing(18)
        layout.setVerticalSpacing(6)

        for index, (kind, color, label) in enumerate(LEGEND_ENTRIES):
            row, col = divmod(index, _COLUMNS)

            pair = QWidget()
            pair_layout = QHBoxLayout(pair)
            pair_layout.setContentsMargins(0, 0, 0, 0)
            pair_layout.setSpacing(6)

            swatch = _ColorSwatch(color, hatch=(kind == "hatch"))
            pair_layout.addWidget(swatch)

            text = QLabel(label)
            text.setObjectName("legendLabel")
            pair_layout.addWidget(text)
            pair_layout.addStretch(1)

            layout.addWidget(pair, row, col)

        self.set_compact_section(False)

    def set_compact_section(self, compact_section: bool) -> None:
        """`compact_section=True` (>10 widocznych pracowników - patrz
        _update_grid_legend) - stylizuje legendę jako wyraźnie oddzieloną
        sekcję (obramowanie + delikatne tło), żeby nie wyglądała jak dalszy
        ciąg samej siatki, która już zajmuje większość dostępnego miejsca."""
        if compact_section:
            self.setStyleSheet(
                "QFrame#gridLegend {"
                f"  background: {theme.BG_PANEL};"
                f"  border-top: 2px solid {theme.SOFT_BORDER};"
                "  border-bottom-left-radius: 8px;"
                "  border-bottom-right-radius: 8px;"
                "  margin-top: 6px;"
                "}"
            )
        else:
            self.setStyleSheet("QFrame#gridLegend { background: transparent; }")
