import calendar

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon
from PySide6.QtWidgets import QAbstractItemView, QMenu, QTableWidget, QTableWidgetItem

from logic.constraint_presenter import ConstraintPresenter
from logic.schedule_presenter import SchedulePresenter
from ui import theme


class ScheduleGrid(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.schedule = None
        self.shop_config = None
        self.controller = None

        self.on_edit_day = None
        self.on_edit_employee = None
        self.on_context_menu = None
        self.on_header_menu = None

        self._clipboard_day = None

        # IKONY
        self.icon_open = QIcon("assets/key.png")
        self.icon_meat = QIcon("assets/meat.png")

        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setAlternatingRowColors(False)

        self.cellDoubleClicked.connect(self._handle_double_click)
        self.viewport().setContextMenuPolicy(Qt.CustomContextMenu)
        self.viewport().customContextMenuRequested.connect(self._open_cell_context_menu)
        self.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self._open_header_context_menu)

    def set_data(
        self,
        schedule,
        shop_config,
        controller,
        on_edit_day=None,
        on_edit_employee=None,
        on_context_menu=None,
        on_header_menu=None,
    ):
        self.schedule = schedule
        self.shop_config = shop_config
        self.controller = controller
        self.on_edit_day = on_edit_day
        self.on_edit_employee = on_edit_employee
        self.on_context_menu = on_context_menu
        self.on_header_menu = on_header_menu

    def build(self):
        self.clear()
        self.setSortingEnabled(False)

        if not self.schedule or not self.shop_config:
            self.setRowCount(0)
            self.setColumnCount(0)
            return

        days = self.schedule.days_in_month
        weekday_names = ["Pn", "Wt", "Śr", "Cz", "Pt", "So", "Nd"]

        headers = ["Pracownik"]
        for day in range(1, days + 1):
            wd = calendar.weekday(self.schedule.year, self.schedule.month, day)
            headers.append(f"{weekday_names[wd]}\n{day}")
        headers.extend(["Praca\n(h)", "Urlop\n(h)", "Razem\n(h)"])

        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.setRowCount(len(self.schedule.employees) + 3)

        self.setColumnWidth(0, 180)
        for col in range(1, days + 1):
            self.setColumnWidth(col, 60)
        for col in range(days + 1, days + 4):
            self.setColumnWidth(col, 80)

        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.horizontalHeader().setStretchLastSection(False)

        for row in range(self.rowCount()):
            self.setRowHeight(row, 42)

    def refresh(self):
        if not self.schedule or not self.shop_config:
            return

        self.build()
        presenter = SchedulePresenter(self.schedule, self.shop_config)
        constraint_presenter = ConstraintPresenter(self.schedule, self.shop_config)

        days = self.schedule.days_in_month
        emp_count = len(self.schedule.employees)

        for row, emp in enumerate(self.schedule.employees):
            self._fill_employee_name(row, emp)
            self._fill_day_cells(row, emp, days, presenter, constraint_presenter)
            self._fill_summary_cells(row, emp, days)

        self._fill_validation_rows(emp_count, days, constraint_presenter)
        self.viewport().update()

    def _fill_employee_name(self, row, emp):
        item = QTableWidgetItem(emp.display_name())
        item.setData(Qt.UserRole, emp)
        item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        # IKONY ZAMIAST TEKSTU OTW / MIĘSO
        if emp.is_opener:
            item.setIcon(self.icon_open)
        elif emp.is_meat:
            item.setIcon(self.icon_meat)

        font = QFont()
        font.setBold(True)
        item.setFont(font)
        item.setBackground(QBrush(QColor(theme.BG_PANEL)))
        self.setItem(row, 0, item)

    def _fill_day_cells(self, row, emp, days, presenter, constraint_presenter):
        for day in range(1, days + 1):
            ds = self.schedule.get_day(emp, day)
            item = QTableWidgetItem()
            item.setTextAlignment(Qt.AlignCenter)
            item.setData(Qt.UserRole, (emp, day))

            if ds.is_leave:
                item.setText("🌴")
                item.setBackground(QBrush(QColor(theme.OK_GREEN)))
                item.setToolTip("Urlop")
                self.setItem(row, day, item)
                continue

            if not self.shop_config.is_trade_day(day):
                item.setBackground(QBrush(QColor(theme.BG_DISABLED)))
                self.setItem(row, day, item)
                continue

            cell_view = presenter.get_cell_view(emp, day)
            lines = [line for line in [cell_view.text_start, cell_view.text_end, cell_view.text_total] if line]
            item.setText("\n".join(lines))
            item.setBackground(QBrush(QColor(cell_view.bg)))

            if cell_view.tooltip:
                item.setToolTip(cell_view.tooltip)

            if constraint_presenter.get_cell_error(emp, day):
                item.setBackground(QBrush(QColor(theme.ERR_RED)))

            self.setItem(row, day, item)

    def _fill_summary_cells(self, row, emp, days):
        items = [
            QTableWidgetItem(self.schedule.total_hours_for_employee(emp)),
            QTableWidgetItem(self.schedule.leave_hours_for_employee(emp)),
            QTableWidgetItem(self.schedule.total_with_leave_for_employee(emp)),
        ]

        for idx, item in enumerate(items, start=days + 1):
            item.setTextAlignment(Qt.AlignCenter)
            item.setBackground(QBrush(QColor(theme.BG_PANEL)))
            self.setItem(row, idx, item)

    def _fill_validation_rows(self, emp_count, days, constraint_presenter):
        rows = [("Otwarcie", "open"), ("Zamknięcie", "close"), ("Mięso", "meat")]

        for offset, (label, key) in enumerate(rows):
            row = emp_count + offset

            name_item = QTableWidgetItem(label)
            name_item.setBackground(QBrush(QColor(theme.BG_HEADER)))
            name_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self.setItem(row, 0, name_item)

            for day in range(1, days + 1):
                count = 0

                for emp in self.schedule.employees:
                    ds = self.schedule.get_day(emp, day)

                    hours = self.shop_config.get_open_hours_for_day(day)

                    if not hours:
                        continue

                    open_start, open_end = hours

                    if key == "open" and ds.start == open_start:
                        count += 1
                    elif key == "close" and ds.end == open_end:
                        count += 1
                    elif key == "meat" and emp.is_meat and not ds.is_leave and ds.start:
                        count += 1

                item = QTableWidgetItem(str(count))
                item.setTextAlignment(Qt.AlignCenter)

                view = constraint_presenter.get_validation_cell_view(key, day)
                item.setBackground(QBrush(QColor(view.bg)))
                if view.tooltip:
                    item.setToolTip(view.tooltip)
                self.setItem(row, day, item)

            for col in range(days + 1, days + 4):
                filler = QTableWidgetItem("")
                filler.setBackground(QBrush(QColor(theme.BG_PANEL)))
                self.setItem(row, col, filler)

    def _handle_double_click(self, row, col):
        if not self.schedule:
            return

        emp_count = len(self.schedule.employees)
        days = self.schedule.days_in_month

        if row < emp_count and col == 0 and self.on_edit_employee:
            self.on_edit_employee(self.schedule.employees[row])
            return

        if row < emp_count and 1 <= col <= days and self.on_edit_day:
            self.on_edit_day(self.schedule.employees[row], col)

    def _open_cell_context_menu(self, pos):
        if not self.schedule or not self.on_context_menu:
            return

        item = self.itemAt(pos)
        if not item:
            return

        row = item.row()
        col = item.column()
        emp_count = len(self.schedule.employees)
        days = self.schedule.days_in_month

        if row >= emp_count or not (1 <= col <= days):
            return

        emp = self.schedule.employees[row]
        day = col
        global_pos = self.viewport().mapToGlobal(pos)
        self.on_context_menu(emp, day, global_pos)

    def _open_header_context_menu(self, pos):
        if not self.schedule or not self.on_header_menu:
            return

        col = self.horizontalHeader().logicalIndexAt(pos)
        days = self.schedule.days_in_month
        if not (1 <= col <= days):
            return

        global_pos = self.horizontalHeader().mapToGlobal(pos)
        self.on_header_menu(col, global_pos)

    def set_clipboard(self, value):
        self._clipboard_day = value

    def clipboard(self):
        return self._clipboard_day