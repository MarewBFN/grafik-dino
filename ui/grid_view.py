import calendar

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPixmap, QPen
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
        self.compact_mode = False

        self.hovered_row = None
        self.active_row = None
        self.setMouseTracking(True)

        self.icon_open = QIcon("assets/key.png")
        self.icon_meat = QIcon("assets/meat.png")
        self.icon_open_meat = QIcon("assets/keymeat.png")

        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setAlternatingRowColors(False)

        self.cellClicked.connect(self._handle_click)
        self.cellDoubleClicked.connect(self._handle_double_click)
        self.viewport().setContextMenuPolicy(Qt.CustomContextMenu)
        self.viewport().customContextMenuRequested.connect(self._open_cell_context_menu)
        self.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self._open_header_context_menu)

    def mouseMoveEvent(self, event):
        item = self.itemAt(event.pos())
        if item:
            row = item.row()
            if row != self.hovered_row:
                self.hovered_row = row
                self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hovered_row = None
        self.viewport().update()
        super().leaveEvent(event)

    def set_data(
        self,
        schedule,
        shop_config,
        controller,
        main_window=None,
        on_edit_day=None,
        on_edit_employee=None,
        on_context_menu=None,
        on_header_menu=None,
    ):
        self.schedule = schedule
        self.shop_config = shop_config
        self.controller = controller
        self.main_window = main_window
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
        headers.extend(["Praca\n(h)", "Urlop\n(h)", "L4\n(h)", "Razem\n(h)"])

        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.setRowCount(len(self.schedule.employees) + 3)

        self.setColumnWidth(0, 180)
        for col in range(1, days + 1):
            if self.compact_mode:
                self.setColumnWidth(col, 30)
            else:
                self.setColumnWidth(col, 60)
        for col in range(days + 1, days + 5):
            self.setColumnWidth(col, 60)

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

        if emp.is_opener and emp.is_meat:
            size = 32
            pixmap = QPixmap(size * 2, size)
            pixmap.fill(Qt.transparent)

            painter = QPainter(pixmap)
            painter.drawPixmap(0, 0, self.icon_open.pixmap(size, size))
            painter.drawPixmap(size, 0, self.icon_meat.pixmap(size, size))
            painter.end()

            item.setIcon(QIcon(pixmap))
            item.setIcon(self.icon_open_meat)

        elif emp.is_opener:
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
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            item.setData(Qt.UserRole, (emp, day))

            # 🔥 ręczne wolne (locked)
            if getattr(ds, "is_locked", False) and not ds.start and not ds.end and not ds.is_leave and not getattr(ds, "is_sick", False):
                item.setText("Wolne")
                item.setToolTip("Dzień wolny (ręcznie ustawione dla generatora)")
                self.setItem(row, day, item)
                continue

            if hasattr(ds, "is_sick") and ds.is_sick:
                item.setText("🤒")
                item.setBackground(QBrush(QColor("#FFA07A")))
                item.setToolTip("Chorobowe")
                self.setItem(row, day, item)
                continue

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

            if self.compact_mode:
                text = ""
                hours = self.shop_config.get_open_hours_for_day(day)

                if hours and ds.start:
                    open_start, open_end = hours
                    from datetime import datetime

                    fmt = "%H:%M"
                    start = datetime.strptime(ds.start, fmt)
                    shop_start = datetime.strptime(open_start, fmt)

                    diff = (start - shop_start).total_seconds() / 60
                    text = "2" if diff >= 120 else "1"

                item.setText(text)
            else:
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
            QTableWidgetItem(self.schedule.sick_hours_for_employee(emp)),
            QTableWidgetItem(self.schedule.total_with_leave_and_sick_for_employee(emp)),
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

            for col in range(days + 1, days + 5):
                filler = QTableWidgetItem("")
                filler.setBackground(QBrush(QColor(theme.BG_PANEL)))
                self.setItem(row, col, filler)

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self.viewport())

        if self.active_row is not None:
            color = QColor(60, 120, 200, 60)
            for col in range(self.columnCount()):
                rect = self.visualRect(self.model().index(self.active_row, col))
                painter.fillRect(rect, color)

        if self.hovered_row is not None:
            pen = QPen(QColor(100, 150, 255), 2)
            painter.setPen(pen)

            rect = self.visualRect(self.model().index(self.hovered_row, 0))
            full_rect = QRect(rect)

            for col in range(1, self.columnCount()):
                r = self.visualRect(self.model().index(self.hovered_row, col))
                full_rect = full_rect.united(r)

            painter.drawRect(full_rect)

    def _handle_click(self, row, col):
        self.active_row = row
        self.viewport().update()

        if not self.schedule or not self.main_window:
            return

        emp_count = len(self.schedule.employees)
        days = self.schedule.days_in_month

        if row < emp_count and 1 <= col <= days:
            if (
                self.main_window.quick_mode_enabled
                and self.main_window.quick_selected_shift
            ):
                self._apply_quick_shift(row, col)

    def _handle_double_click(self, row, col):
        if not self.schedule or not self.main_window:
            return

        emp_count = len(self.schedule.employees)
        days = self.schedule.days_in_month

        if row < emp_count and col == 0 and self.on_edit_employee:
            self.on_edit_employee(self.schedule.employees[row])
            return

        if row < emp_count and 1 <= col <= days:
            if (
                self.main_window.quick_mode_enabled
                and self.main_window.quick_selected_shift
            ):
                self._apply_quick_shift(row, col)
            elif self.on_edit_day:
                self.on_edit_day(self.schedule.employees[row], col)

    def _apply_quick_shift(self, row, col):
        if not self.main_window:
            return

        emp = self.schedule.employees[row]
        day = col
        shift = self.main_window.quick_selected_shift

        start = None
        end = None

        if shift == "WORK":
            start = self.main_window.start_input.time().toString("HH:mm")
            end = self.main_window.end_input.time().toString("HH:mm")

        elif shift == "SICK":
            ds = self.schedule.get_day(emp, day)
            ds.is_locked = False

            self.controller.set_day_sick(emp, day)
            self.refresh()
            return

        elif shift == "OFF":
            ds = self.schedule.get_day(emp, day)

            # 🔥 jeśli już jest wolne → nic nie rób
            if getattr(ds, "is_locked", False) and not ds.start and not ds.end and not ds.is_leave and not getattr(ds, "is_sick", False):
                return

            # 🔥 ustaw wolne ręczne
            ds.start = None
            ds.end = None
            ds.is_leave = False
            ds.is_sick = False
            ds.is_locked = True

            self.refresh()
            return

        ds = self.schedule.get_day(emp, day)

        current = (
            ds.start,
            ds.end,
            ds.is_leave,
            getattr(ds, "is_sick", False)
        )

        new = (start, end, shift == "LEAVE", shift == "SICK")

        if current == new:
            return

        ds.is_locked = False

        self.controller.set_shift(emp, day, shift, start, end)
        self.refresh()

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

    def set_compact_mode(self, enabled: bool):
        self.compact_mode = enabled
        self.refresh()