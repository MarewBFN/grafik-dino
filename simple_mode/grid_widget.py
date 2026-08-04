import calendar

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QTableWidget, QTableWidgetItem

from ui import theme

CODE_COLORS = {
    "": QColor(theme.BG_PANEL),
    "1": QColor(theme.SHIFT_MORNING),
    "2": QColor(theme.SHIFT_CLOSE),
    "W": QColor(theme.BG_DISABLED),
}

WEEKDAY_NAMES = ["Pn", "Wt", "Śr", "Cz", "Pt", "So", "Nd"]

# (etykieta wiersza, kod liczony w podsumowaniu)
SUMMARY_ROWS = (
    ("Rano", "1"),
    ("Popo", "2"),
)

HIGHLIGHT_BG = QColor(theme.ACCENT)
HIGHLIGHT_FG = QColor("#ffffff")


class SimpleModeGrid(QTableWidget):
    """Osobna, niezależna siatka trybu uproszczonego.

    Kliknięcie lewym przyciskiem lub klawisze 1 / 2 / W ustawiają kod komórki.
    Nie korzysta z ScheduleGrid/DaySchedule/ScheduleController — dane trzyma
    wyłącznie SimpleModeData.
    """

    KEY_CODES = {
        Qt.Key_1: "1",
        Qt.Key_2: "2",
        Qt.Key_W: "W",
    }
    CLEAR_KEYS = (Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_0)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.schedule = None
        self.simple_data = None
        self._employee_count = 0
        self._highlighted_col = None
        self._highlighted_row = None

        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setFocusPolicy(Qt.StrongFocus)
        self.cellClicked.connect(self._handle_click)
        self.currentCellChanged.connect(self._handle_current_cell_changed)

    def set_data(self, schedule, simple_data):
        self.schedule = schedule
        self.simple_data = simple_data
        self.build()

    def build(self):
        self.clear()
        self._highlighted_col = None
        self._highlighted_row = None

        if not self.schedule:
            self.setRowCount(0)
            self.setColumnCount(0)
            return

        days = self.schedule.days_in_month
        self._employee_count = len(self.schedule.employees)

        headers = ["Pracownik"]
        for day in range(1, days + 1):
            wd = calendar.weekday(self.schedule.year, self.schedule.month, day)
            headers.append(f"{WEEKDAY_NAMES[wd]}\n{day}")

        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.setRowCount(self._employee_count + len(SUMMARY_ROWS))

        self.setColumnWidth(0, 180)
        for col in range(1, days + 1):
            self.setColumnWidth(col, 32)

        for row, emp in enumerate(self.schedule.employees):
            name_item = QTableWidgetItem(emp.display_name())
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.setItem(row, 0, name_item)

            for day in range(1, days + 1):
                self._render_cell(row, day, emp)

        for offset, (label, _code) in enumerate(SUMMARY_ROWS):
            row = self._employee_count + offset
            label_item = QTableWidgetItem(label)
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            font = QFont()
            font.setBold(True)
            label_item.setFont(font)
            label_item.setBackground(QBrush(QColor(theme.BG_HEADER)))
            self.setItem(row, 0, label_item)

            for day in range(1, days + 1):
                self._render_summary_cell(day)

        if self._employee_count and days:
            self.setCurrentCell(0, 1)

    def _render_cell(self, row, day, emp):
        code = self.simple_data.get(emp, day)
        item = QTableWidgetItem(code)
        item.setTextAlignment(Qt.AlignCenter)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        item.setBackground(QBrush(CODE_COLORS.get(code, CODE_COLORS[""])))
        self.setItem(row, day, item)

    def _render_summary_cell(self, day):
        for offset, (_label, target_code) in enumerate(SUMMARY_ROWS):
            row = self._employee_count + offset
            count = sum(
                1
                for emp in self.schedule.employees
                if self.simple_data.get(emp, day) == target_code
            )

            item = QTableWidgetItem(str(count) if count else "")
            item.setTextAlignment(Qt.AlignCenter)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            item.setBackground(QBrush(QColor(theme.BG_HEADER)))
            self.setItem(row, day, item)

    def _handle_click(self, row, col):
        if col == 0 or not self.schedule or row >= self._employee_count:
            return

        emp = self.schedule.employees[row]
        day = col
        self.simple_data.cycle(emp, day)
        self._render_cell(row, day, emp)
        self._render_summary_cell(day)

    def keyPressEvent(self, event):
        row = self.currentRow()
        col = self.currentColumn()

        if col > 0 and self.schedule and 0 <= row < self._employee_count:
            emp = self.schedule.employees[row]
            day = col

            if event.key() in self.KEY_CODES:
                code = self.KEY_CODES[event.key()]
                self.simple_data.set(emp, day, code)
                self._render_cell(row, day, emp)
                self._render_summary_cell(day)
                return

            if event.key() in self.CLEAR_KEYS:
                self.simple_data.set(emp, day, "")
                self._render_cell(row, day, emp)
                self._render_summary_cell(day)
                return

        super().keyPressEvent(event)

    def _handle_current_cell_changed(self, row, col, prev_row, prev_col):
        # Pozioma belka: podświetl komórkę z nazwiskiem pracownika w wybranym wierszu.
        if prev_row is not None and prev_row >= 0 and prev_row < self._employee_count:
            self._reset_name_cell(prev_row)
        if row is not None and 0 <= row < self._employee_count:
            self._highlight_name_cell(row)

        # Pionowa belka: podświetl nagłówek kolumny wybranego dnia.
        if self._highlighted_col is not None:
            self._reset_header(self._highlighted_col)
            self._highlighted_col = None
        if col is not None and col > 0:
            self._highlight_header(col)
            self._highlighted_col = col

    def _highlight_name_cell(self, row):
        item = self.item(row, 0)
        if item:
            item.setBackground(QBrush(HIGHLIGHT_BG))
            item.setForeground(QBrush(HIGHLIGHT_FG))
        self._highlighted_row = row

    def _reset_name_cell(self, row):
        item = self.item(row, 0)
        if item:
            item.setBackground(QBrush(QColor(theme.BG_PANEL)))
            item.setForeground(QBrush(QColor(theme.TEXT_MAIN)))

    def _highlight_header(self, col):
        header_item = self.horizontalHeaderItem(col)
        if header_item:
            header_item.setBackground(QBrush(HIGHLIGHT_BG))
            header_item.setForeground(QBrush(HIGHLIGHT_FG))

    def _reset_header(self, col):
        header_item = self.horizontalHeaderItem(col)
        if header_item:
            header_item.setBackground(QBrush())
            header_item.setForeground(QBrush())
