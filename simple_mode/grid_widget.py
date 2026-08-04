import calendar

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QAbstractItemView, QTableWidget, QTableWidgetItem

from ui import theme

CODE_COLORS = {
    "": QColor(theme.BG_PANEL),
    "1": QColor(theme.SHIFT_MORNING),
    "2": QColor(theme.SHIFT_CLOSE),
    "W": QColor(theme.BG_DISABLED),
}

WEEKDAY_NAMES = ["Pn", "Wt", "Śr", "Cz", "Pt", "So", "Nd"]


class SimpleModeGrid(QTableWidget):
    """Osobna, niezależna siatka trybu uproszczonego.

    Kliknięcie lewym przyciskiem cyklicznie ustawia kod komórki:
    "" -> "1" -> "2" -> "W" -> "".
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

        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setFocusPolicy(Qt.StrongFocus)
        self.cellClicked.connect(self._handle_click)

    def set_data(self, schedule, simple_data):
        self.schedule = schedule
        self.simple_data = simple_data
        self.build()

    def build(self):
        self.clear()

        if not self.schedule:
            self.setRowCount(0)
            self.setColumnCount(0)
            return

        days = self.schedule.days_in_month
        headers = ["Pracownik"]
        for day in range(1, days + 1):
            wd = calendar.weekday(self.schedule.year, self.schedule.month, day)
            headers.append(f"{WEEKDAY_NAMES[wd]}\n{day}")

        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.setRowCount(len(self.schedule.employees))

        self.setColumnWidth(0, 180)
        for col in range(1, days + 1):
            self.setColumnWidth(col, 32)

        for row, emp in enumerate(self.schedule.employees):
            name_item = QTableWidgetItem(emp.display_name())
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.setItem(row, 0, name_item)

            for day in range(1, days + 1):
                self._render_cell(row, day, emp)

        if self.schedule.employees and days:
            self.setCurrentCell(0, 1)

    def _render_cell(self, row, day, emp):
        code = self.simple_data.get(emp, day)
        item = QTableWidgetItem(code)
        item.setTextAlignment(Qt.AlignCenter)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        item.setBackground(QBrush(CODE_COLORS.get(code, CODE_COLORS[""])))
        self.setItem(row, day, item)

    def _handle_click(self, row, col):
        if col == 0 or not self.schedule:
            return

        emp = self.schedule.employees[row]
        day = col
        self.simple_data.cycle(emp, day)
        self._render_cell(row, day, emp)

    def keyPressEvent(self, event):
        row = self.currentRow()
        col = self.currentColumn()

        if col > 0 and self.schedule:
            emp = self.schedule.employees[row]
            day = col

            if event.key() in self.KEY_CODES:
                code = self.KEY_CODES[event.key()]
                self.simple_data.set(emp, day, code)
                self._render_cell(row, day, emp)
                return

            if event.key() in self.CLEAR_KEYS:
                self.simple_data.set(emp, day, "")
                self._render_cell(row, day, emp)
                return

        super().keyPressEvent(event)
