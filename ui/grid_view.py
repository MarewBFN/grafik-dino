import calendar
import math
from datetime import datetime

from PySide6.QtCore import Qt, QPointF, QRectF, QSize, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QIcon, QImage, QPainter, QPixmap, QPen, QPolygonF, qGray
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QLabel,
    QMenu,
    QSpinBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QTableView,
    QVBoxLayout,
)
from logic.constraint_presenter import ConstraintPresenter
from logic.schedule_presenter import SchedulePresenter
from logic.utils.time_utils import classify_shift_as_morning_or_afternoon
from utils import resource_path
from ui import theme


# Edit this tuple to add, remove or reorder the summary rows at the bottom.
SUMMARY_ROWS = (
    ("Otwarcie", "open"),
    ("Zamknięcie", "close"),
    ("Rano", "morning"),
    ("Popo", "afternoon"),
    ("Mięso", "meat"),
)


def _grayed_icon(icon: QIcon, size: int = 64, opacity: float = 0.55) -> QIcon:
    """Build a desaturated, faded variant of an icon (no separate asset file)."""
    image = icon.pixmap(size, size).toImage().convertToFormat(QImage.Format_ARGB32)
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() == 0:
                continue
            gray = qGray(color.rgb())
            color.setRgb(gray, gray, gray, int(color.alpha() * opacity))
            image.setPixelColor(x, y, color)
    return QIcon(QPixmap.fromImage(image))


def _build_star_icon(size: int = 64, fill_color: str = "#f4b400", outline_color: str = "#8a6100") -> QIcon:
    """Draw a simple 5-point star badge for the manager flag (no asset file)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    center = size / 2
    outer_r = size * 0.46
    inner_r = outer_r * 0.42
    points = []
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5
        r = outer_r if i % 2 == 0 else inner_r
        points.append(QPointF(center + r * math.cos(angle), center - r * math.sin(angle)))

    painter.setPen(QPen(QColor(outline_color), max(1.0, size * 0.04)))
    painter.setBrush(QBrush(QColor(fill_color)))
    painter.drawPolygon(QPolygonF(points))
    painter.end()

    return QIcon(pixmap)


def _draw_prohibition_slash(painter: QPainter, size: int) -> None:
    """Overlay the universal 'no' circle-slash on whatever was already painted."""
    pen = QPen(QColor("#d64545"), max(1.5, size * 0.12))
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    margin = size * 0.08
    painter.drawEllipse(QRectF(margin, margin, size - 2 * margin, size - 2 * margin))
    painter.drawLine(QPointF(size * 0.22, size * 0.22), QPointF(size * 0.78, size * 0.78))


def _build_no_night_icon(size: int = 32) -> QIcon:
    """Crescent moon + prohibition slash, for the 'no_night' flag (no asset file)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    center = QPointF(size * 0.46, size * 0.46)
    moon_r = size * 0.30

    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor("#37474f")))
    painter.drawEllipse(center, moon_r, moon_r)

    painter.setCompositionMode(QPainter.CompositionMode_DestinationOut)
    painter.drawEllipse(
        QPointF(center.x() + moon_r * 0.55, center.y() - moon_r * 0.35),
        moon_r * 0.85, moon_r * 0.85,
    )
    painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

    _draw_prohibition_slash(painter, size)
    painter.end()

    return QIcon(pixmap)


def _build_no_afternoon_icon(size: int = 32) -> QIcon:
    """Sun + prohibition slash, for the 'no_afternoon' flag (no asset file)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    center = QPointF(size * 0.46, size * 0.5)
    sun_r = size * 0.19

    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor("#f2a13c")))
    painter.drawEllipse(center, sun_r, sun_r)

    ray_pen = QPen(QColor("#f2a13c"), max(1.2, size * 0.06))
    painter.setPen(ray_pen)
    for i in range(8):
        angle = i * math.pi / 4
        inner = sun_r * 1.35
        outer = sun_r * 1.85
        painter.drawLine(
            QPointF(center.x() + math.cos(angle) * inner, center.y() + math.sin(angle) * inner),
            QPointF(center.x() + math.cos(angle) * outer, center.y() + math.sin(angle) * outer),
        )

    _draw_prohibition_slash(painter, size)
    painter.end()

    return QIcon(pixmap)


def _employee_badges(table, employee):
    """Large corner-role badges (opener/meat/manager) shown for an employee."""
    badges = []
    if employee.is_opener:
        badges.append(table.icon_open)
    if employee.is_meat:
        badges.append(table.icon_meat)
    elif employee.is_meat_light:
        badges.append(table.icon_meat_light)
    if employee.is_manager:
        badges.append(table.icon_manager)
    return badges


def _employee_restriction_icons(table, employee):
    """Small inline icons shown next to the employment-fraction label."""
    icons = []
    if getattr(employee, "no_night", False):
        icons.append(table.icon_no_night)
    if getattr(employee, "no_afternoon", False):
        icons.append(table.icon_no_afternoon)
    return icons


def employment_fraction_label(employee):
    """Short labels for the employee column; full labels stay in EmployeeDialog."""
    labels = {
        1.0: "1/1",
        1.01: "1/1 8h",
        0.875: "7/8",
        0.75: "3/4",
        0.625: "5/8",
        0.5: "1/2",
        0.375: "3/8",
        0.25: "1/4",
    }
    return labels.get(round(employee.employment_fraction, 3), str(employee.employment_fraction))


class EmployeeNameDelegate(QStyledItemDelegate):
    """Paint employee name, role badges and a subdued employment fraction
    (plus small restriction icons) on one line.

    Badges/icons are painted directly at a fixed pixel size instead of via
    QTableWidgetItem.setIcon(), which would otherwise scale a wider composed
    pixmap down to fit the view's single shared iconSize() box - shrinking
    every individual icon as soon as an employee has more than one flag.
    """

    BADGE_SIZE = 20
    BADGE_GAP = 2
    RESTRICTION_ICON_SIZE = 16
    RESTRICTION_ICON_GAP = 2

    def paint(self, painter, option, index):
        employee = index.data(Qt.UserRole)
        if employee is None or not hasattr(employee, "employment_fraction"):
            super().paint(painter, option, index)
            return

        table = self.parent()

        style_option = QStyleOptionViewItem(option)
        self.initStyleOption(style_option, index)
        style_option.text = ""
        style_option.icon = QIcon()
        style = style_option.widget.style() if style_option.widget else QStyle()
        style.drawControl(QStyle.CE_ItemViewItem, style_option, painter, style_option.widget)

        text_rect = style.subElementRect(QStyle.SE_ItemViewItemText, style_option, style_option.widget)

        painter.save()

        # --- Odznaki roli (opener/mięso/kierowniczka), stały rozmiar ---
        badges = _employee_badges(table, employee) if table is not None else []
        badge_x = text_rect.left()
        badge_y = text_rect.top() + (text_rect.height() - self.BADGE_SIZE) // 2
        for icon in badges:
            icon.paint(painter, badge_x, badge_y, self.BADGE_SIZE, self.BADGE_SIZE)
            badge_x += self.BADGE_SIZE + self.BADGE_GAP

        name_left = badge_x + (6 if badges else 0)

        # --- Ikony ograniczeń (brak nocy / popołudnia), stały rozmiar ---
        restriction_icons = _employee_restriction_icons(table, employee) if table is not None else []
        restriction_width = len(restriction_icons) * (self.RESTRICTION_ICON_SIZE + self.RESTRICTION_ICON_GAP)

        name_font = QFont(style_option.font)
        name_font.setBold(True)
        fraction_font = QFont(name_font)
        fraction_font.setBold(False)
        fraction_font.setPointSize(max(name_font.pointSize() - 2, 8))

        fraction = employment_fraction_label(employee)
        name_metrics = QFontMetrics(name_font)
        fraction_metrics = QFontMetrics(fraction_font)
        gap = 7
        fraction_width = fraction_metrics.horizontalAdvance(fraction)
        available_name_width = max(
            0, text_rect.right() - name_left - fraction_width - gap - restriction_width
        )
        name = name_metrics.elidedText(employee.display_name(), Qt.ElideRight, available_name_width)

        name_rect = text_rect.adjusted(name_left - text_rect.left(), 0, 0, 0)
        painter.setFont(name_font)
        painter.setPen(style_option.palette.text().color())
        painter.drawText(name_rect, Qt.AlignVCenter | Qt.AlignLeft, name)

        name_width = name_metrics.horizontalAdvance(name)
        fraction_rect = name_rect.adjusted(name_width + gap, 0, 0, 0)
        painter.setFont(fraction_font)
        painter.setPen(QColor("#8a8a8a"))
        painter.drawText(fraction_rect, Qt.AlignVCenter | Qt.AlignLeft, fraction)

        icon_x = fraction_rect.left() + fraction_width + self.RESTRICTION_ICON_GAP
        icon_y = text_rect.top() + (text_rect.height() - self.RESTRICTION_ICON_SIZE) // 2
        for icon in restriction_icons:
            icon.paint(painter, icon_x, icon_y, self.RESTRICTION_ICON_SIZE, self.RESTRICTION_ICON_SIZE)
            icon_x += self.RESTRICTION_ICON_SIZE + self.RESTRICTION_ICON_GAP

        painter.restore()

class LockedCellDelegate(QStyledItemDelegate):
    """Rysuje standardową komórkę i nakłada szrafowanie na zablokowane dni."""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)

        data = index.data(Qt.UserRole)

        if not isinstance(data, tuple) or len(data) != 2:
            return

        emp, day = data
        if not isinstance(day, int):
            # Inne kolumny (np. "Cel") też przechowują dane w UserRole jako
            # krotka (emp, ...) — tu interesują nas tylko prawdziwe komórki dnia.
            return

        table = self.parent()
        if table is None or table.schedule is None:
            return

        ds = table.schedule.get_day(emp, day)

        if (
            not getattr(ds, "is_locked", False)
            or ds.is_leave
            or getattr(ds, "is_sick", False)
            or (not ds.start and not ds.end)
        ):
            return

        painter.save()

        # Nigdy nie rysuj poza komórką
        painter.setClipRect(option.rect)

        pen = QPen(QColor(205, 205, 205, 180), 1)
        painter.setPen(pen)

        step = 8
        r = option.rect

        for x in range(r.left() - r.height(), r.right(), step):
            painter.drawLine(
                x,
                r.bottom(),
                x + r.height(),
                r.top(),
            )

        painter.restore()

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
        self.settlement_mode = False
        self.setIconSize(QSize(20, 20))
        self._employee_name_delegate = EmployeeNameDelegate(self)
        self.setItemDelegateForColumn(0, self._employee_name_delegate)

        self._locked_cell_delegate = LockedCellDelegate(self)

        for col in range(1, 500):
            self.setItemDelegateForColumn(col, self._locked_cell_delegate)

        self.hovered_row = None
        self.active_row = None
        self.setMouseTracking(True)

        self.icon_open = QIcon(resource_path("assets/key.png"))
        self.icon_meat = QIcon(resource_path("assets/meat.png"))
        self.icon_open_meat = QIcon(resource_path("assets/keymeat.png"))
        self.icon_meat_light = _grayed_icon(self.icon_meat)
        self.icon_manager = _build_star_icon()
        self.icon_no_night = _build_no_night_icon()
        self.icon_no_afternoon = _build_no_afternoon_icon()

        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setAlternatingRowColors(False)
        
        # 1. Wyłączenie domyślnego niebieskiego tła zaznaczenia QTableWidget
        self.setStyleSheet("selection-background-color: transparent; selection-color: inherit;")
        self.setFocusPolicy(Qt.StrongFocus)

        self._create_frozen_name_column()

        self.cellClicked.connect(self._handle_click)
        self.cellDoubleClicked.connect(self._handle_double_click)
        
        # 4. Podwójny klik na nagłówku (zamiast PPM)
        self.horizontalHeader().sectionDoubleClicked.connect(self._handle_header_double_click)
        self.horizontalHeader().setToolTip("Kliknij dwukrotnie, aby zmienić godziny pracy")

    def _create_frozen_name_column(self):
        """Overlay a second view for column 0 so it stays visible horizontally."""
        self.frozen_name_column = QTableView(self)
        self.frozen_name_column.setModel(self.model())
        self.frozen_name_column.setSelectionModel(self.selectionModel())
        self.frozen_name_column.setItemDelegateForColumn(0, self._employee_name_delegate)
        self.frozen_name_column.setFocusPolicy(Qt.NoFocus)
        self.frozen_name_column.setFrameShape(QFrame.NoFrame)
        self.frozen_name_column.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.frozen_name_column.setSelectionMode(QAbstractItemView.SingleSelection)
        self.frozen_name_column.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.frozen_name_column.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frozen_name_column.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frozen_name_column.verticalHeader().setVisible(False)
        self.frozen_name_column.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)

        for column in range(1, self.model().columnCount()):
            self.frozen_name_column.setColumnHidden(column, True)

        self.verticalScrollBar().valueChanged.connect(self.frozen_name_column.verticalScrollBar().setValue)
        self.frozen_name_column.verticalScrollBar().valueChanged.connect(self.verticalScrollBar().setValue)
        self.verticalHeader().sectionResized.connect(self._sync_frozen_row_height)
        self.horizontalHeader().sectionResized.connect(self._sync_frozen_column_width)
        self.frozen_name_column.clicked.connect(lambda index: self._handle_click(index.row(), 0))
        self.frozen_name_column.doubleClicked.connect(lambda index: self._handle_double_click(index.row(), 0))
        self._update_frozen_name_column()

    def _sync_frozen_row_height(self, row, _old_size, new_size):
        if hasattr(self, "frozen_name_column"):
            self.frozen_name_column.setRowHeight(row, new_size)

    def _sync_frozen_column_width(self, column, _old_size, new_size):
        if column == 0 and hasattr(self, "frozen_name_column"):
            self.frozen_name_column.setColumnWidth(0, new_size)
            self._update_frozen_name_column()

    def _update_frozen_name_column(self):
        if not hasattr(self, "frozen_name_column"):
            return
        viewport_rect = self.viewport().geometry()
        header_rect = self.horizontalHeader().geometry()
        # The main header is taller because day labels use two lines (e.g. Pn\n1).
        # Keep this one equally tall so row 0 starts on exactly the same Y axis.
        self.frozen_name_column.horizontalHeader().setFixedHeight(header_rect.height())
        self.frozen_name_column.setGeometry(
            viewport_rect.x(),
            header_rect.y(),
            self.columnWidth(0),
            header_rect.height() + viewport_rect.height(),
        )
        self.frozen_name_column.setColumnWidth(0, self.columnWidth(0))
        self.frozen_name_column.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_frozen_name_column()
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
        if self.settlement_mode:
            headers.append("Cel\n(h)")

        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.setRowCount(len(self.schedule.employees) + len(SUMMARY_ROWS))

        for day in range(1, days + 1):
            header_item = self.horizontalHeaderItem(day)
            if header_item:
                header_item.setToolTip(self._day_header_tooltip(day))

        if self.settlement_mode:
            target_header_item = self.horizontalHeaderItem(days + 5)
            if target_header_item:
                target_header_item.setToolTip(
                    "Docelowa liczba godzin w miesiącu dla tego pracownika.\n"
                    "Kliknij dwukrotnie, aby ustawić."
                )

        for col in range(1, self.columnCount()):
            self.frozen_name_column.setColumnHidden(col, True)

        # 180 * 1.3 = 234, rounded up further so up to 3 role badges + name +
        # fraction + 2 restriction icons all fit without crowding/eliding.
        self.setColumnWidth(0, 260)
        for col in range(1, days + 1):
            if self.compact_mode:
                self.setColumnWidth(col, 30)
            else:
                self.setColumnWidth(col, 60)
        for col in range(days + 1, self.columnCount()):
            self.setColumnWidth(col, 60)

        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.horizontalHeader().setStretchLastSection(False)

        employee_row_height = 42
        # Height of the bottom summary rows. Change this value to adjust them.
        # 24 px = a further 25% reduction from the previous 32 px height.
        summary_row_height = 24
        for row in range(self.rowCount()):
            height = employee_row_height if row < len(self.schedule.employees) else summary_row_height
            self.setRowHeight(row, height)

        # QTableView has its own vertical header, so mirror the explicit heights.
        for row in range(self.rowCount()):
            self.frozen_name_column.setRowHeight(row, self.rowHeight(row))
        self._update_frozen_name_column()

        # Zmiana liczby kolumn (np. włączenie/wyłączenie trybu rozliczeniowego)
        # może w tym samym cyklu zdarzeń zmienić widoczność poziomego paska
        # przewijania, co zmienia wysokość viewportu already used above — Qt
        # przelicza to dopiero po tym wywołaniu. Domykamy synchronizację
        # jeszcze raz po przetworzeniu zdarzeń layoutu, żeby wiersze kolumny
        # z nazwiskami nie "uciekały" w pionie względem reszty siatki.
        QTimer.singleShot(0, self._update_frozen_name_column)

    def _day_header_tooltip(self, day):
        hours = self.shop_config.get_open_hours_for_day(day)
        if hours:
            hours_text = f"Godziny pracy sklepu: {hours[0]}–{hours[1]}"
        else:
            hours_text = "Sklep nieczynny tego dnia"
        return f"{hours_text}\nKliknij dwukrotnie, aby zmienić godziny pracy lub status dnia."

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
        # Badges and restriction icons are painted directly by
        # EmployeeNameDelegate at a fixed size, instead of going through
        # QTableWidgetItem.setIcon() - that would scale everything down to
        # fit a single shared iconSize() box as more flags are added.

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

            shift_class = getattr(ds, "shift_class", None)
            if shift_class and ds.is_empty():
                item.setText(shift_class)

                brush = QBrush(QColor(205, 205, 205))
                brush.setStyle(Qt.BDiagPattern)

                item.setBackground(brush)
                label = "rano" if shift_class == "1" else "popołudnie"
                item.setToolTip(
                    f"Zablokowany typ zmiany: {label} — generator dobierze godzinę."
                )
                self.setItem(row, day, item)
                continue

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

                if ds.start:
                    hours = self.shop_config.get_open_hours_for_day(day)
                    if hours:
                        shop_open_str, shop_close_str = hours
                        try:
                            shop_open_dt = datetime.strptime(shop_open_str, "%H:%M")
                            shop_close_dt = datetime.strptime(shop_close_str, "%H:%M")
                            emp_start_dt = datetime.strptime(ds.start, "%H:%M")
                            emp_end_dt = datetime.strptime(ds.end, "%H:%M")
                            classification = classify_shift_as_morning_or_afternoon(
                                emp_start_dt,
                                emp_end_dt,
                                shop_open_dt,
                                shop_close_dt,
                            )
                            text = "1" if classification == "morning" else "2"
                        except ValueError:
                            text = ""

                item.setText(text)
            else:
                lines = [line for line in [cell_view.text_start, cell_view.text_end, cell_view.text_total] if line]
                item.setText("\n".join(lines))

            item.setBackground(QBrush(QColor(cell_view.bg)))

            if cell_view.tooltip:
                item.setToolTip(cell_view.tooltip)

            if getattr(ds, "is_locked", False):
                tooltip = item.toolTip()

                lock_info = "🔒 Wprowadzono ręcznie – generator nie zmieni tej komórki."

                if tooltip:
                    item.setToolTip(f"{tooltip}\n\n{lock_info}")
                else:
                    item.setToolTip(lock_info)

            if shift_class:
                tooltip = item.toolTip()
                label = "rano" if shift_class == "1" else "popołudnie"
                class_info = f"🔒 Zablokowany typ zmiany: {label} — godzinę dobrał generator."

                if tooltip:
                    item.setToolTip(f"{tooltip}\n\n{class_info}")
                else:
                    item.setToolTip(class_info)

            # 3. Sprawdzanie błędów z flagą highlight_max_consecutive oraz zabezpieczenie przed błędem typu
            error = constraint_presenter.get_cell_error(emp, day)

            if error:
                has_consecutive = any(v.type == "max_consecutive_days" for v in error)

                if not has_consecutive or hl_consecutive:
                    item.setBackground(QBrush(QColor(theme.ERR_RED)))
                    item.setToolTip("\n".join(v.message for v in error if v.message))

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

        if self.settlement_mode:
            target_minutes = self.schedule.get_settlement_target(emp)
            if target_minutes is None:
                text = "-"
            else:
                text = f"{target_minutes // 60}:{target_minutes % 60:02d}"

            target_item = QTableWidgetItem(text)
            target_item.setTextAlignment(Qt.AlignCenter)
            target_item.setBackground(QBrush(QColor(theme.ACCENT_SOFT)))
            target_item.setData(Qt.UserRole, (emp, "settlement_target"))
            target_item.setToolTip("Dwuklik, aby ustawić docelową liczbę godzin w miesiącu.")
            self.setItem(row, days + 5, target_item)

    def _fill_validation_rows(self, emp_count, days, constraint_presenter):
        # Definiujemy wiersze podsumowania
        for offset, (label, key) in enumerate(SUMMARY_ROWS):
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

                fmt = "%H:%M"
                try:
                    shop_open_dt = datetime.strptime(shop_open_str, fmt)
                    shop_close_dt = datetime.strptime(shop_close_str, fmt)
                except ValueError:
                    continue

                for emp in self.schedule.employees:
                    ds = self.schedule.get_day(emp, day)

                    # Ignorujemy osoby, które nie pracują, są na urlopie lub L4
                    if not ds.start or ds.is_leave or getattr(ds, "is_sick", False):
                        continue

                    try:
                        emp_start_dt = datetime.strptime(ds.start, fmt)
                        emp_end_dt = datetime.strptime(ds.end, fmt)

                        # --- LOGIKA ZGODNA Z GENERATOREM ---

                        # 1. Dokładne Otwarcie/Zamknięcie (walidacja)
                        if ds.start == shop_open_str:
                            at_opening += 1
                        if ds.end == shop_close_str:
                            at_closing += 1

                        # 2. Rano / Popołudnie (jedno przypisanie na zmianę)
                        classification = classify_shift_as_morning_or_afternoon(
                            emp_start_dt,
                            emp_end_dt,
                            shop_open_dt,
                            shop_close_dt,
                        )
                        if classification == "morning":
                            total_morning += 1
                        elif classification == "afternoon":
                            total_afternoon += 1

                        # 3. Mięso (w tym zastępczo "mooooże stanąć na chwilę na mięsie")
                        if (emp.is_meat or emp.is_meat_light) and ds.start and not ds.is_leave and not getattr(ds, "is_sick", False):
                            count_meat += 1
                    except ValueError:
                        continue

                # Budowanie tekstu do wyświetlenia
                if key == "open":
                    display_text = str(at_opening)
                elif key == "close":
                    display_text = str(at_closing)
                elif key == "morning":
                    display_text = str(total_morning)
                elif key == "afternoon":
                    display_text = str(total_afternoon)
                elif key == "meat":
                    view = constraint_presenter.get_validation_cell_view("meat", day)
                    if view.bg == theme.ERR_RED:
                        display_text = "❌"
                    elif view.bg == theme.WARN_YELLOW:
                        display_text = "⚠️"
                    else:
                        display_text = "✅"

                item = QTableWidgetItem(display_text)
                item.setTextAlignment(Qt.AlignCenter)

                # Kolorowanie tła
                if key in ("morning", "afternoon"):
                    # Informacyjne wiersze mają stały kolor panelu.
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

    def keyPressEvent(self, event):
        if not self.schedule or not self.controller:
            super().keyPressEvent(event)
            return

        row = self.currentRow()
        col = self.currentColumn()
        emp_count = len(self.schedule.employees)
        days = self.schedule.days_in_month

        if (
            0 <= row < emp_count
            and 1 <= col <= days
            and self.shop_config
            and self.shop_config.is_trade_day(col)
        ):
            emp = self.schedule.employees[row]
            day = col

            if event.key() in (Qt.Key_1, Qt.Key_2):
                code = "1" if event.key() == Qt.Key_1 else "2"
                self.controller.set_shift_class(emp, day, code)
                self._sync_and_keep_position(row, col)
                return

            if event.key() == Qt.Key_W:
                self.controller.set_day_free(emp, day)
                self._sync_and_keep_position(row, col)
                return

        super().keyPressEvent(event)

    def _sync_and_keep_position(self, row, col):
        self.schedule = self.controller.schedule

        v_scroll = self.verticalScrollBar().value()
        h_scroll = self.horizontalScrollBar().value()

        if self.main_window:
            self.main_window._sync_everything()
        else:
            self.refresh()

        self.setCurrentCell(row, col)
        self.verticalScrollBar().setValue(v_scroll)
        self.horizontalScrollBar().setValue(h_scroll)
        self.setFocus()

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

        if self.settlement_mode and row < emp_count and col == days + 5:
            self._edit_settlement_target(self.schedule.employees[row])
            return

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

    def _edit_settlement_target(self, emp):
        # Ta sama wartość, co kolumna "Razem" w siatce.
        actual_minutes = self.schedule.total_with_leave_and_sick_minutes_for_employee(emp)

        existing_target = self.schedule.get_settlement_target(emp)
        default_minutes = existing_target if existing_target is not None else actual_minutes

        dialog = QDialog(self)
        dialog.setWindowTitle("Okres rozliczeniowy")
        layout = QVBoxLayout(dialog)

        info = QLabel(
            f"{emp.display_name()}\n"
            f"Aktualna suma w tym miesiącu: {actual_minutes // 60}:{actual_minutes % 60:02d}"
        )
        layout.addWidget(info)

        form = QFormLayout()

        hours_spin = QSpinBox()
        hours_spin.setRange(0, 400)
        hours_spin.setValue(default_minutes // 60)
        form.addRow("Cel — godziny:", hours_spin)

        minutes_spin = QSpinBox()
        minutes_spin.setRange(0, 59)
        minutes_spin.setSingleStep(15)
        minutes_spin.setValue(default_minutes % 60)
        form.addRow("Cel — minuty:", minutes_spin)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return

        target_minutes = hours_spin.value() * 60 + minutes_spin.value()
        self.schedule.set_settlement_target(emp, target_minutes)
        self.refresh()

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

        act_clear = menu.addAction("Wyczyść komórkę")

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

        elif action == act_clear:
            self.controller.snapshot()
            ds.start = None
            ds.end = None
            ds.is_leave = False
            ds.is_sick = False
            ds.is_locked = False
            ds.shift_class = None
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
            start = self.main_window.start_input.get_time_str()
            end = self.main_window.end_input.get_time_str()

            from datetime import datetime
            fmt = "%H:%M"

            try:
                start_dt = datetime.strptime(start, fmt)
                end_dt = datetime.strptime(end, fmt)
            except:
                return

            if end_dt <= start_dt:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Błąd", "Godzina zakończenia musi być późniejsza niż rozpoczęcia.")
                return

        elif shift == "SICK":
            self.controller.snapshot() # Zabezpieczenie undo
            ds = self.schedule.get_day(emp, day)
            ds.is_locked = False

            self.controller.set_day_sick(emp, day)
            self.refresh()
            return

        elif shift in ("MORNING_CLASS", "AFTERNOON_CLASS"):
            code = "1" if shift == "MORNING_CLASS" else "2"
            self.controller.set_shift_class(emp, day, code)
            self.refresh()
            return

        elif shift == "OFF":
            ds = self.schedule.get_day(emp, day)

            # 🔥 jeśli już jest wolne → nic nie rób
            if (
                getattr(ds, "is_locked", False)
                and not ds.start
                and not ds.end
                and not ds.is_leave
                and not getattr(ds, "is_sick", False)
                and not getattr(ds, "shift_class", None)
            ):
                return

            self.controller.snapshot() # Zabezpieczenie undo
            # 🔥 ustaw wolne ręczne
            ds.start = None
            ds.end = None
            ds.is_leave = False
            ds.is_sick = False
            ds.is_locked = True
            ds.shift_class = None

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

    def set_settlement_mode(self, enabled: bool):
        self.settlement_mode = enabled
        self.refresh()

    def clear_schedule(self):
        if not self.schedule or not self.controller:
            return

        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            "Potwierdzenie",
            "Czy na pewno chcesz skasować wszystkie dane na grafiku?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        self.controller.snapshot()

        for emp in self.schedule.employees:
            for day in range(1, self.schedule.days_in_month + 1):
                ds = self.schedule.get_day(emp, day)

                ds.start = None
                ds.end = None
                ds.is_leave = False
                ds.is_sick = False
                ds.is_locked = False

        self.refresh()
