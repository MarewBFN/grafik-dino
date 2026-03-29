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
        
        # 1. Wyłączenie domyślnego niebieskiego tła zaznaczenia QTableWidget
        self.setStyleSheet("selection-background-color: transparent; selection-color: inherit;")
        self.setFocusPolicy(Qt.NoFocus)

        self.cellClicked.connect(self._handle_click)
        self.cellDoubleClicked.connect(self._handle_double_click)
        
        # 4. Podwójny klik na nagłówku (zamiast PPM)
        self.horizontalHeader().sectionDoubleClicked.connect(self._handle_header_double_click)
        self.horizontalHeader().setToolTip("Kliknij dwukrotnie, aby zmienić godziny pracy")
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
        self.setRowCount(len(self.schedule.employees) + 4)

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

        # 3. Flaga sprawdzania limitu dni pod rząd z konfiguracji (domyślnie False)
        hl_consecutive = self.shop_config.constraints.get("highlight_max_consecutive", False)

        days = self.schedule.days_in_month
        emp_count = len(self.schedule.employees)

        for row, emp in enumerate(self.schedule.employees):
            self._fill_employee_name(row, emp)
            self._fill_day_cells(row, emp, days, presenter, constraint_presenter, hl_consecutive)
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

    def _fill_day_cells(self, row, emp, days, presenter, constraint_presenter, hl_consecutive):
        for day in range(1, days + 1):
            ds = self.schedule.get_day(emp, day)
            item = QTableWidgetItem()
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            item.setData(Qt.UserRole, (emp, day))

            if getattr(ds, "is_locked", False) and not ds.start and not ds.end and not ds.is_leave and not getattr(ds, "is_sick", False):
                item.setText("")  # Czyścimy tekst, żeby nie śmiecił
                
                # Tworzymy profesjonalne szrafowanie (ukośne linie)
                brush = QBrush(QColor(205, 205, 205)) # Bardzo jasny szary
                brush.setStyle(Qt.BDiagPattern)       # Wzór: ukośne linie (Back Diagonal)
                
                item.setBackground(brush)
                item.setToolTip("Dzień wolny (Zablokowany: Generator nie zmieni tego ustawienia)")
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

            # 3. Sprawdzanie błędów z flagą highlight_max_consecutive oraz zabezpieczenie przed błędem typu
            error = constraint_presenter.get_cell_error(emp, day)
            if error:
                is_cons_err = False
                if isinstance(error, str):
                    is_cons_err = "dni pod rząd" in error.lower()
                
                if not is_cons_err or hl_consecutive:
                    item.setBackground(QBrush(QColor(theme.ERR_RED)))
                    if isinstance(error, str):
                        item.setToolTip(error)

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
        # Definiujemy wiersze podsumowania
        rows = [
            ("Otwarcie", "open"), 
            ("Zamknięcie", "close"), 
            ("Rano/Popo", "morning_afternoon"), 
            ("Mięso", "meat")
        ]

        for offset, (label, key) in enumerate(rows):
            row = emp_count + offset

            # Etykieta wiersza (lewa kolumna)
            name_item = QTableWidgetItem(label)
            name_item.setBackground(QBrush(QColor(theme.BG_HEADER)))
            name_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self.setItem(row, 0, name_item)

            for day in range(1, days + 1):
                # Liczniki dla danego dnia
                at_opening = 0
                at_closing = 0
                total_morning = 0
                total_afternoon = 0
                count_meat = 0

                # Pobieramy godziny pracy sklepu z konfiguracji
                hours = self.shop_config.get_open_hours_for_day(day)
                if not hours:
                    continue
                shop_open_str, shop_close_str = hours
                
                try:
                    shop_open_h = int(shop_open_str.split(":")[0])
                    shop_close_h = int(shop_close_str.split(":")[0])
                except:
                    continue

                for emp in self.schedule.employees:
                    ds = self.schedule.get_day(emp, day)
                    
                    # Ignorujemy osoby, które nie pracują, są na urlopie lub L4
                    if not ds.start or ds.is_leave or getattr(ds, "is_sick", False):
                        continue

                    try:
                        emp_start_h = int(ds.start.split(":")[0])
                        emp_end_h = int(ds.end.split(":")[0])

                        # --- LOGIKA ZGODNA Z GENERATOREM ---
                        
                        # 1. Dokładne Otwarcie/Zamknięcie (walidacja)
                        if ds.start == shop_open_str:
                            at_opening += 1
                        if ds.end == shop_close_str:
                            at_closing += 1

                        # 2. Rano / Popołudnie (wszystkie zmiany rano i po południu)
                        # Rano: Zaczyna tak jak sklep LUB przed 12:00
                        if emp_start_h <= shop_open_h or emp_start_h < 12:
                            total_morning += 1
                        
                        # Popołudnie: Kończy tak jak sklep LUB zaczyna od 12:00 wzwyż
                        if emp_end_h >= shop_close_h or emp_start_h >= 12:
                            total_afternoon += 1

                        # 3. Mięso
                        if emp.is_meat and ds.start and not ds.is_leave and not getattr(ds, "is_sick", False):
                            count_meat += 1
                    except:
                        continue

                # Budowanie tekstu do wyświetlenia
                if key == "open":
                    display_text = str(at_opening)
                elif key == "close":
                    display_text = str(at_closing)
                elif key == "morning_afternoon":
                    # Wyświetlamy w formacie Rano / Popo
                    display_text = f"{total_morning}  /  {total_afternoon}"
                elif key == "meat":
                    view = constraint_presenter.get_validation_cell_view("meat", day)
                    display_text = "❌" if view.bg == theme.ERR_RED else "✅"

                item = QTableWidgetItem(display_text)
                item.setTextAlignment(Qt.AlignCenter)

                # Kolorowanie tła
                if key == "morning_afternoon":
                    # Wiersz informacyjny ma stały kolor panelu (taki jak prawidłowe otw/zam)
                    item.setBackground(QBrush(QColor(theme.BG_PANEL)))
                else:
                    # Reszta wierszy używa walidatora błędów
                    view = constraint_presenter.get_validation_cell_view(key, day)
                    item.setBackground(QBrush(QColor(view.bg)))
                    if view.tooltip:
                        item.setToolTip(view.tooltip)

                self.setItem(row, day, item)

            # Wypełnienie komórek sumarycznych (ostatnie 4 kolumny) szarym kolorem
            for col in range(days + 1, days + 5):
                filler = QTableWidgetItem("")
                filler.setBackground(QBrush(QColor(theme.BG_PANEL)))
                self.setItem(row, col, filler)

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing)

        # 1. Obramówka aktywnego wiersza (grubsza)
        if self.active_row is not None:
            pen = QPen(QColor(0, 120, 215), 2)
            painter.setPen(pen)
            rect = self._get_full_row_rect(self.active_row)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))

        # 1. Obramówka najechanego wiersza (cieńsza, subtelniejsza)
        if self.hovered_row is not None and self.hovered_row != self.active_row:
            pen = QPen(QColor(0, 120, 215, 80), 1)
            painter.setPen(pen)
            rect = self._get_full_row_rect(self.hovered_row)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))

    def _get_full_row_rect(self, row):
        rect = self.visualRect(self.model().index(row, 0))
        for col in range(1, self.columnCount()):
            rect = rect.united(self.visualRect(self.model().index(row, col)))
        return rect

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

    def _handle_header_double_click(self, col):
        # 4. Dwuklik na nagłówku
        if 1 <= col <= self.schedule.days_in_month:
            if self.on_header_menu:
                self.on_header_menu(col, None)

    def contextMenuEvent(self, event):
        # 100% pewna metoda na wyłapanie prawego przycisku myszy w Qt
        global_pos = event.globalPos()
        
        # Mapujemy globalną pozycję myszy na obszar viewportu tabeli
        vp_pos = self.viewport().mapFromGlobal(global_pos)
        row = self.rowAt(vp_pos.y())
        col = self.columnAt(vp_pos.x())
        
        if row == -1 or col == -1:
            return
            
        emp_count = len(self.schedule.employees)
        days = self.schedule.days_in_month

        if row >= emp_count or not (1 <= col <= days):
            return

        emp = self.schedule.employees[row]
        day = col
        ds = self.schedule.get_day(emp, day)
        
        menu = QMenu(self)
        
        act_copy = menu.addAction("Kopiuj dzień")
        act_paste = menu.addAction("Wklej dzień")
        act_paste.setEnabled(self._clipboard_day is not None)
        
        menu.addSeparator()
        
        act_unlock = menu.addAction("Odblokuj")
        act_unlock.setEnabled(getattr(ds, "is_locked", False))

        action = menu.exec(global_pos)
        
        if action == act_copy:
            self._clipboard_day = {
                "start": ds.start, "end": ds.end, 
                "is_leave": ds.is_leave, "is_sick": getattr(ds, "is_sick", False)
            }
            if self.main_window:
                self.main_window.statusBar().showMessage("Skopiowano dzień.", 2000)
        elif action == act_paste:
            self.controller.set_day_hours(emp, day, self._clipboard_day["start"], self._clipboard_day["end"])
            self.refresh()
        elif action == act_unlock:
            self.controller.snapshot() # Ręczny zapis przed manipulacją obiektem
            ds.is_locked = False
            self.refresh()

    def _open_header_context_menu(self, pos):
        # Zachowuję sygnaturę z Twojego oryginalnego kodu (teraz zastąpione przez double_click)
        pass

    def _apply_quick_shift(self, row, col):
        if not self.main_window:
            return

        emp = self.schedule.employees[row]
        day = col
        shift = self.main_window.quick_selected_shift

        start = None
        end = None

        if shift == "WORK":
            # 🔥 Poprawione odwołanie do nowej metody w TimeInputWidget
            start = self.main_window.start_input.get_time_str()
            end = self.main_window.end_input.get_time_str()

        elif shift == "SICK":
            self.controller.snapshot() # Zabezpieczenie undo
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

            self.controller.snapshot() # Zabezpieczenie undo
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

        self.controller.snapshot() # Zabezpieczenie undo
        ds.is_locked = False

        self.controller.set_shift(emp, day, shift, start, end)
        self.refresh()

    def set_clipboard(self, value):
        self._clipboard_day = value

    def clipboard(self):
        return self._clipboard_day

    def set_compact_mode(self, enabled: bool):
        self.compact_mode = enabled
        self.refresh()