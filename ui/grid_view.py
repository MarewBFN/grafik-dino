import calendar
import math
from datetime import datetime
from functools import lru_cache

from PySide6.QtCore import Qt, QPointF, QRectF, QSize, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QIcon, QImage, QKeySequence, QPainter, QPixmap, QPen, QPolygonF, qGray
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHeaderView,
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
from logic.duty_coverage_presenter import is_day_fully_covered, project_uses_duty_rotation
from logic.generator.duty_rotation_constraint import NIE_CHCE_24H_ROLE_KEY
from logic.monthly_hours_status import monthly_hours_status
from logic.schedule_presenter import SchedulePresenter
from logic.utils.time_utils import classify_shift_as_morning_or_afternoon, format_hours_as_fraction
from model.business_profile import DEFAULT_BUSINESS_TYPE, get_profile
from model.constraint_policy import ConstraintPolicy
from model.month_schedule import PREVIOUS_MONTH_MEMORY_ENABLED
from utils import resource_path
from ui import theme


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


def _build_no_24h_icon(size: int = 32) -> QIcon:
    """"24h" + prohibition slash, for the 'nie_chce_24h' custom role (no
    asset file) - same hand-drawn style as _build_no_night_icon/
    _build_no_afternoon_icon."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    font = QFont()
    font.setBold(True)
    font.setPointSize(int(size * 0.34))
    painter.setFont(font)
    painter.setPen(QColor("#37474f"))
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, "24h")

    _draw_prohibition_slash(painter, size)
    painter.end()

    return QIcon(pixmap)


def _build_contract_icon(size: int = 32) -> QIcon:
    """Small document/contract badge, for the 'umowa' custom role (no asset
    file) - same hand-drawn style as the other restriction/role icons."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    margin_x, margin_y = size * 0.26, size * 0.12
    page = QRectF(margin_x, margin_y, size - 2 * margin_x, size - 2 * margin_y)
    painter.setPen(QPen(QColor("#37474f"), max(1.2, size * 0.06)))
    painter.setBrush(QBrush(QColor("#eceff1")))
    painter.drawRoundedRect(page, size * 0.04, size * 0.04)

    line_pen = QPen(QColor("#37474f"), max(1.0, size * 0.045))
    painter.setPen(line_pen)
    for i in range(3):
        ly = page.top() + page.height() * (0.32 + i * 0.22)
        painter.drawLine(QPointF(page.left() + size * 0.08, ly), QPointF(page.right() - size * 0.08, ly))

    painter.end()
    return QIcon(pixmap)


@lru_cache(maxsize=128)
def _emoji_icon(emoji: str, size: int = 64) -> QIcon:
    """Render one emoji character as a badge icon (no asset file), for
    custom-profile roles picked in the profile wizard (ui/emoji_palette.py)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    font = QFont()
    font.setPointSize(int(size * 0.6))
    painter.setFont(font)
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, emoji)
    painter.end()

    return QIcon(pixmap)


def _employee_badges(table, employee):
    """Large corner-role badges shown for an employee: Dino's hand-drawn
    opener/meat/manager icons, plus one emoji badge per custom-profile role
    that has an icon set and this employee carries."""
    badges = []
    meat_disabled = (
        table.shop_config is not None
        and table.shop_config.constraint_policies.get("meat") == ConstraintPolicy.DISABLED
    )
    if employee.is_opener:
        badges.append(table.icon_open)
    if not meat_disabled and employee.is_meat:
        badges.append(table.icon_meat)
    elif not meat_disabled and employee.is_meat_light:
        badges.append(table.icon_meat_light)
    if employee.is_manager:
        badges.append(table.icon_manager)

    if table.shop_config is not None:
        profile = get_profile(table.shop_config.business_type)
        for role in profile.roles:
            if role.icon and employee.has_role(role.key):
                badges.append(_emoji_icon(role.icon))

    return badges


def _employee_restriction_icons(table, employee):
    """Small inline icons shown next to the employment-fraction label."""
    icons = []
    if getattr(employee, "no_night", False):
        icons.append(table.icon_no_night)
    if getattr(employee, "no_afternoon", False):
        icons.append(table.icon_no_afternoon)
    if employee.has_role("umowa"):
        icons.append(table.icon_contract)
    if employee.has_role(NIE_CHCE_24H_ROLE_KEY):
        icons.append(table.icon_no_24h)
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


class DayHeaderView(QHeaderView):
    """Nagłówek dni z paskiem podświetlającym te dni, dla których godziny
    pracy sklepu zostały ręcznie nadpisane (ShopConfig.day_overrides).

    Zwykłe QTableWidgetItem.setBackground() nie działa tutaj, bo tło sekcji
    nagłówka jest rysowane przez arkusz stylów apki (QHeaderView::section) i
    to ono ma pierwszeństwo — stąd własny akcent dorysowywany na wierzchu.
    """

    OVERRIDE_BAR_COLOR = QColor("#f59e0b")
    OVERRIDE_BAR_HEIGHT = 3

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.overridden_days = set()
        # Ile kolumn PRZED dniem 1 (dziś: 0 albo 1, kolumna "pamięć
        # poprzedniego miesiąca" - patrz ScheduleGrid.build()) - potrzebne,
        # żeby przełożyć logicalIndex z powrotem na numer dnia dla
        # overridden_days (który wciąż operuje na surowych numerach dni).
        self.col_offset = 0
        # Indeks kolumny "pamięć poprzedniego miesiąca", albo None gdy jej
        # nie ma w ogóle w tym renderze - patrz ScheduleGrid.build().
        self.info_column = None

    def paintSection(self, painter, rect, logicalIndex):
        if logicalIndex == self.info_column:
            # Zwykłe QTableWidgetItem.setBackground() nie działa w nagłówku
            # (patrz docstring klasy) - to jedyny sposób, żeby ta kolumna
            # miała WYRAŹNIE inne tło niż zwykłe dni, sygnalizując, że to
            # dane czysto informacyjne z poprzedniego miesiąca.
            painter.save()
            painter.fillRect(rect, QColor(theme.BG_PREVIOUS_MONTH_HEADER))
            painter.setPen(QColor(theme.TEXT_MAIN))
            text = self.model().headerData(logicalIndex, self.orientation(), Qt.DisplayRole)
            painter.drawText(rect, Qt.AlignCenter, str(text) if text is not None else "")
            painter.restore()
            return

        super().paintSection(painter, rect, logicalIndex)
        if (logicalIndex - self.col_offset) in self.overridden_days:
            painter.save()
            painter.fillRect(
                rect.left(),
                rect.bottom() - self.OVERRIDE_BAR_HEIGHT + 1,
                rect.width(),
                self.OVERRIDE_BAR_HEIGHT,
                self.OVERRIDE_BAR_COLOR,
            )
            painter.restore()


class ScheduleGrid(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.schedule = None
        self.shop_config = None
        self.controller = None

        # Klucz aktualnie wybranej placówki (patrz set_data()) - tabela
        # pokazuje tylko pracowników do niej przypisanych. None = brak
        # filtrowania (pokaż wszystkich) - używane tylko zanim main_window
        # w ogóle ma jakąś wybraną placówkę. Patrz też właściwość
        # _visible_employees niżej.
        self._location_filter = None

        # Ile kolumn PRZED kolumną dnia 1 - 1 gdy pokazywana jest kolumna
        # "pamięć poprzedniego miesiąca" (patrz build()/_column_to_day()),
        # inaczej 0. Przeliczane od nowa w każdym build().
        self._prev_col_offset = 0

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
        self.icon_contract = _build_contract_icon()
        self.icon_no_24h = _build_no_24h_icon()

        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setAlternatingRowColors(False)
        
        # 1. Wyłączenie domyślnego niebieskiego tła zaznaczenia QTableWidget
        self.setStyleSheet("selection-background-color: transparent; selection-color: inherit;")
        self.setFocusPolicy(Qt.StrongFocus)

        self.setHorizontalHeader(DayHeaderView(Qt.Horizontal, self))

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

    def _summary_rows(self):
        business_type = self.shop_config.business_type if self.shop_config else None
        rows = get_profile(business_type).summary_rows

        # A summary row for a constraint that's currently DISABLED tracks
        # nothing meaningful - hide it instead of showing a dead indicator.
        # Each of these is independent (a project can disable "close" while
        # keeping "open" on, etc.).
        if self.shop_config is not None:
            disabled_keys = {
                key for key in ("meat", "open", "close")
                if self.shop_config.constraint_policies.get(key) == ConstraintPolicy.DISABLED
            }
            if disabled_keys:
                rows = tuple(row for row in rows if row[1] not in disabled_keys)

            # Rotacja 24/7 (np. ochrona) zastępuje Otwarcie/Zamknięcie -
            # koncepcje bez znaczenia dla tego mechanizmu - jednym wierszem
            # "Obłożenie" (patrz logic/duty_coverage_presenter.py).
            # project_uses_duty_rotation() pokrywa dino_retail-owe projekty,
            # które i tak skonfigurowały duty_rotation na jakiejś lokalizacji
            # (mechanizm jest generyczny, nieprzywiązany do business_type -
            # patrz "Generator pod klucz dla Enyo" w ENYO_ONLY_CHANGES.md).
            # Dodatkowo, dla KAŻDEGO profilu poza dino_retail wiersz jest
            # ZAWSZE widoczny, nawet zanim jakakolwiek lokalizacja ma
            # rotację ustawioną - klient tego typu (np. Enyo/ochrona) ma to
            # jako swój JEDYNY wiersz podsumowania, więc nie może on znikać
            # przy nowej, jeszcze nieskonfigurowanej lokalizacji (❌ w takim
            # wypadku poprawnie sygnalizuje "brak pokrycia").
            if (
                business_type != DEFAULT_BUSINESS_TYPE
                or project_uses_duty_rotation(self.shop_config, self._visible_employees)
            ):
                rows = tuple(row for row in rows if row[1] not in ("open", "close"))
                rows = (("Obłożenie", "coverage"),) + rows

        return rows

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
        location_filter=None,
    ):
        self.schedule = schedule
        self.shop_config = shop_config
        self.controller = controller
        self.main_window = main_window
        self.on_edit_day = on_edit_day
        self.on_edit_employee = on_edit_employee
        self.on_context_menu = on_context_menu
        self.on_header_menu = on_header_menu
        self._location_filter = location_filter

    def get_visible_employees(self) -> list:
        """Pracownicy aktualnie pokazywani w tabeli (po filtrze placówki,
        patrz set_data(location_filter=...)) - używane przez eksporty/druk w
        ui/main_window.py, żeby domyślnie obejmowały tylko wybraną placówkę."""
        return self._visible_employees

    @property
    def _visible_employees(self) -> list:
        # Liczone na żywo (nie cache'owane w build()) - interakcje takie jak
        # _apply_quick_shift/_handle_click muszą dawać poprawny wynik nawet
        # gdy coś wywoła je bez uprzedniego build() (patrz testy jednostkowe
        # w tests/test_grid_view_quick_preset.py, które pomijają pełny cykl
        # renderowania).
        if not self.schedule:
            return []
        if not self._location_filter:
            return list(self.schedule.employees)
        return [e for e in self.schedule.employees if e.location_key == self._location_filter]

    def build(self):
        self.clear()
        self.setSortingEnabled(False)

        if not self.schedule or not self.shop_config:
            self.setRowCount(0)
            self.setColumnCount(0)
            return

        days = self.schedule.days_in_month
        weekday_names = ["Pn", "Wt", "Śr", "Cz", "Pt", "So", "Nd"]

        prev_month_last_day = self._previous_month_last_day_if_shown()
        self._prev_col_offset = 1 if prev_month_last_day is not None else 0
        offset = self._prev_col_offset

        headers = ["Pracownik"]
        if prev_month_last_day is not None:
            prev_year, prev_month = self._previous_month_year_month()
            prev_wd = calendar.weekday(prev_year, prev_month, prev_month_last_day)
            headers.append(f"{weekday_names[prev_wd]}\n{prev_month_last_day}")
        for day in range(1, days + 1):
            wd = calendar.weekday(self.schedule.year, self.schedule.month, day)
            headers.append(f"{weekday_names[wd]}\n{day}")
        # "Nadgodziny" samo w sobie (130px przy tej czcionce) nie mieści
        # się nawet w poszerzonej kolumnie (patrz setColumnWidth niżej) -
        # zawinięte na dwie linie w najwęższym możliwym miejscu podziału
        # (min-max: żadna z dwóch części nie jest szersza niż to konieczne).
        headers.extend(["Praca\n(h)", "Urlop\n(h)", "L4\n(h)", "Razem\n(h)", "Nadg-\nodziny\n(h)"])
        if self.settlement_mode:
            headers.append("Cel\n(h)")

        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.setRowCount(len(self._visible_employees) + len(self._summary_rows()))

        if prev_month_last_day is not None:
            info_header_item = self.horizontalHeaderItem(1)
            if info_header_item:
                info_header_item.setToolTip(
                    "Koniec ostatniej zmiany z poprzedniego miesiąca (dzień "
                    f"{prev_month_last_day}) - dane informacyjne, nieedytowalne tutaj i "
                    "niebędące częścią tego grafiku."
                )

        for day in range(1, days + 1):
            header_item = self.horizontalHeaderItem(day + offset)
            if header_item:
                header_item.setToolTip(self._day_header_tooltip(day))

        header = self.horizontalHeader()
        if isinstance(header, DayHeaderView):
            # Nadpisania są teraz per-lokalizacja (patrz
            # main_window.py::_open_header_menu) - znacznik w nagłówku musi
            # patrzeć na tę samą lokalizację, którą ta siatka pokazuje.
            location = self.shop_config.locations.get(self._location_filter)
            overrides = location.day_overrides if location else self.shop_config.day_overrides
            header.overridden_days = set(overrides.keys())
            header.col_offset = offset
            header.info_column = 1 if prev_month_last_day is not None else None
            header.update()

        if self.settlement_mode:
            target_header_item = self.horizontalHeaderItem(days + offset + 6)
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
        if prev_month_last_day is not None:
            self.setColumnWidth(1, 30 if self.compact_mode else 60)
        for col in range(1 + offset, days + offset + 1):
            if self.compact_mode:
                self.setColumnWidth(col, 30)
            else:
                self.setColumnWidth(col, 60)
        for col in range(days + offset + 1, self.columnCount()):
            self.setColumnWidth(col, 60)
        # "Nadg-\nodziny" (patrz headers.extend wyżej) nie mieści się nawet
        # zawinięte w standardowych 60px - piąta kolumna podsumowania to
        # zawsze "Nadgodziny" (Praca/Urlop/L4/Razem/Nadgodziny[/Cel]).
        nadgodziny_col = days + offset + 5
        if nadgodziny_col < self.columnCount():
            self.setColumnWidth(nadgodziny_col, 80)

        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.horizontalHeader().setStretchLastSection(False)

        employee_row_height = 42
        # Height of the bottom summary rows. Change this value to adjust them.
        # 24 px = a further 25% reduction from the previous 32 px height.
        summary_row_height = 24
        for row in range(self.rowCount()):
            height = employee_row_height if row < len(self._visible_employees) else summary_row_height
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
        # Godziny wybranej placówki (patrz set_data(location_filter=...)),
        # nie ogólne godziny projektu - ten nagłówek jest teraz osadzony w
        # kontekście jednej, aktualnie przeglądanej lokalizacji.
        location = self.shop_config.locations.get(self._location_filter)
        uses_trade_calendar = get_profile(self.shop_config.business_type).uses_trade_calendar
        hours = (
            location.get_open_hours_for_day(self.schedule.year, self.schedule.month, day, uses_trade_calendar)
            if location else self.shop_config.get_open_hours_for_day(day)
        )
        if hours:
            hours_text = f"Godziny pracy: {hours[0]}–{hours[1]}"
        else:
            hours_text = "Nieczynne tego dnia"

        overrides = location.day_overrides if location else self.shop_config.day_overrides
        override_text = ""
        if day in overrides:
            override_text = "\n⚠ Godziny pracy zmienione ręcznie dla tego dnia."

        return f"{hours_text}{override_text}\nKliknij dwukrotnie, aby zmienić godziny pracy lub status dnia."

    def _previous_month_year_month(self) -> tuple[int, int]:
        """(rok, miesiąc) miesiąca bezpośrednio poprzedzającego aktualnie
        otwarty - współdzielone przez _previous_month_last_day_if_shown()
        i nagłówek kolumny w build() (potrzebuje tego samego roku/miesiąca,
        żeby policzyć dzień tygodnia ostatniego dnia)."""
        if self.schedule.month > 1:
            return self.schedule.year, self.schedule.month - 1
        return self.schedule.year - 1, 12

    def _previous_month_last_day_if_shown(self) -> int | None:
        """Numer ostatniego dnia poprzedniego miesiąca, jeśli kolumna
        "pamięć poprzedniego miesiąca" ma się w ogóle pokazać w tym
        renderze (patrz PreviousMonthShiftEnd) - None gdy ŻADEN aktualnie
        widoczny pracownik nie ma takich danych, więc kolumna w ogóle się
        nie pojawia (nie pokazujemy pustej/domyślnej)."""
        if not PREVIOUS_MONTH_MEMORY_ENABLED:
            return None
        has_data = any(
            self.schedule.get_previous_month_end_shift(emp) is not None
            for emp in self._visible_employees
        )
        if not has_data:
            return None

        prev_year, prev_month = self._previous_month_year_month()
        return calendar.monthrange(prev_year, prev_month)[1]

    def _column_to_day(self, col: int) -> int | None:
        """Numer dnia kalendarzowego odpowiadający kolumnie `col`, albo
        None gdy `col` to kolumna nazwiska / "pamięć poprzedniego
        miesiąca" / podsumowania - patrz _prev_col_offset w build()."""
        if not self.schedule:
            return None
        day = col - self._prev_col_offset
        if 1 <= day <= self.schedule.days_in_month:
            return day
        return None

    def _fill_previous_month_cell(self, row, emp):
        if not self._prev_col_offset:
            return

        item = QTableWidgetItem()
        item.setTextAlignment(Qt.AlignCenter)
        item.setBackground(QBrush(QColor(theme.BG_PREVIOUS_MONTH_CELL)))
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)

        carry = self.schedule.get_previous_month_end_shift(emp)
        if carry is not None:
            item.setText(f"{carry.end} →" if carry.crosses_midnight else carry.end)
            crossing_note = (
                " Zmiana wchodziła już w dzień 1 tego miesiąca."
                if carry.crosses_midnight else ""
            )
            item.setToolTip(
                f"Koniec ostatniej zmiany w poprzednim miesiącu: {carry.end}.{crossing_note}\n"
                "Dane informacyjne - nieedytowalne tutaj."
            )

        self.setItem(row, 1, item)

    def refresh(self):
        if not self.schedule or not self.shop_config:
            return

        # build() robi clear() i od nowa ustawia liczbę wierszy/kolumn, co
        # resetuje przewinięcie do (0, 0) — bez tego przełączenie np. trybu
        # rozliczeniowego albo kompaktowego "przeskakiwało" widok z powrotem
        # na początek grafiku.
        h_scroll = self.horizontalScrollBar().value()
        v_scroll = self.verticalScrollBar().value()

        self.build()
        presenter = SchedulePresenter(self.schedule, self.shop_config)
        constraint_presenter = ConstraintPresenter(self.schedule, self.shop_config)

        # 3. Flaga sprawdzania limitu dni pod rząd z konfiguracji (domyślnie False)
        hl_consecutive = self.shop_config.constraints.get("highlight_max_consecutive", False)

        days = self.schedule.days_in_month
        emp_count = len(self._visible_employees)

        for row, emp in enumerate(self._visible_employees):
            self._fill_employee_name(row, emp)
            self._fill_previous_month_cell(row, emp)
            self._fill_day_cells(row, emp, days, presenter, constraint_presenter, hl_consecutive)
            self._fill_summary_cells(row, emp, days)

        self._fill_validation_rows(emp_count, days, constraint_presenter)

        self.horizontalScrollBar().setValue(h_scroll)
        self.verticalScrollBar().setValue(v_scroll)

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
                self.setItem(row, day + self._prev_col_offset, item)
                continue

            if getattr(ds, "is_locked", False) and not ds.start and not ds.end and not ds.is_leave and not getattr(ds, "is_sick", False):
                item.setText("")  # Czyścimy tekst, żeby nie śmiecił
                
                # Tworzymy profesjonalne szrafowanie (ukośne linie)
                brush = QBrush(QColor(205, 205, 205)) # Bardzo jasny szary
                brush.setStyle(Qt.BDiagPattern)       # Wzór: ukośne linie (Back Diagonal)
                
                item.setBackground(brush)
                item.setToolTip("Dzień wolny (Zablokowany: Generator nie zmieni tego ustawienia)")
                self.setItem(row, day + self._prev_col_offset, item)
                continue

            if hasattr(ds, "is_sick") and ds.is_sick:
                item.setText("🤒")
                item.setBackground(QBrush(QColor("#FFA07A")))
                item.setToolTip("Chorobowe")
                self.setItem(row, day + self._prev_col_offset, item)
                continue

            if ds.is_leave:
                item.setText("🌴")
                item.setBackground(QBrush(QColor(theme.OK_GREEN)))
                item.setToolTip("Urlop")
                self.setItem(row, day + self._prev_col_offset, item)
                continue

            # Nieczynne = brak handlowej niedzieli/święta (is_trade_day) ALBO
            # dzień jawnie oznaczony "Nieczynne" (patrz WeeklyHoursEditor/
            # DayOverrideDialog - (None, None) w open_hours/day_overrides) -
            # get_open_hours_for_day() już sprawdza oba, per lokalizacja
            # tego pracownika (patrz model/location.py). Komórka ze zmianą
            # (np. kawałek doby rotacji służby z dnia poprzedniego po
            # północy) nie jest maskowana - tło "nieczynne" nadaje jej
            # SchedulePresenter.get_cell_view().
            if not self.shop_config.get_location(emp).get_open_hours_for_day(day) and ds.is_empty():
                item.setBackground(QBrush(QColor(theme.BG_DISABLED)))
                self.setItem(row, day + self._prev_col_offset, item)
                continue

            cell_view = presenter.get_cell_view(emp, day)

            if self.compact_mode:
                text = ""
                # Menu Wygląd -> "Wygląd komórek kompaktowych": w trybie "Ułamki"
                # widok kompaktowy pokazuje faktyczne godziny zmiany jako
                # ułamek, godzina początku nad godziną końca (np. "8" nad
                # "20"), zamiast dotychczasowych skrótów "N"/"1"/"2" - ten
                # sam format co logic/schedule_presenter.py dla widoku
                # rozszerzonego. Bez znacznika "(+1)" dla zmian nocnych -
                # usunięty całkiem na życzenie użytkownika, tło komórki
                # (SHIFT_NIGHT) i tak odróżnia zmianę przez północ.
                fraction_mode = getattr(self.shop_config, "hours_display_mode", "standard") == "fractions"

                if ds.start and fraction_mode:
                    text = format_hours_as_fraction(ds.start, ds.end)
                elif ds.start and ds.crosses_midnight():
                    text = "N"
                elif ds.start:
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

            self.setItem(row, day + self._prev_col_offset, item)

    def _fill_summary_cells(self, row, emp, days):
        items = [
            QTableWidgetItem(self.schedule.total_hours_for_employee(emp)),
            QTableWidgetItem(self.schedule.leave_hours_for_employee(emp)),
            QTableWidgetItem(self.schedule.sick_hours_for_employee(emp)),
            QTableWidgetItem(self.schedule.total_with_leave_and_sick_for_employee(emp)),
        ]

        for idx, item in enumerate(items, start=days + self._prev_col_offset + 1):
            item.setTextAlignment(Qt.AlignCenter)
            item.setBackground(QBrush(QColor(theme.BG_PANEL)))
            self.setItem(row, idx, item)

        # Kolumna "Praca" (pierwsza z items) - podświetlenie przekroczenia
        # miesięcznego limitu pełnego etatu, dokładnie tego samego, którego
        # pilnuje generator (logic/monthly_hours_status.py).
        hours_status = monthly_hours_status(self.schedule, self.shop_config, emp)
        over_h = hours_status["over_minutes"] // 60
        over_m = hours_status["over_minutes"] % 60
        if hours_status["is_over"]:
            work_item = items[0]
            work_item.setBackground(QBrush(QColor(theme.ERR_RED)))
            work_item.setToolTip(
                f"Przekroczony miesięczny limit godzin pełnego etatu o {over_h}:{over_m:02d}."
            )

        # Osobna kolumna "Nadgodziny" obok "Razem" - ta sama liczba co w
        # tooltipie wyżej, ale zawsze widoczna wprost, nie tylko po najechaniu.
        overtime_item = QTableWidgetItem(f"{over_h}:{over_m:02d}")
        overtime_item.setTextAlignment(Qt.AlignCenter)
        if hours_status["is_over"]:
            overtime_item.setBackground(QBrush(QColor(theme.ERR_RED)))
            overtime_item.setToolTip("Nadgodziny ponad miesięczny limit godzin pełnego etatu.")
        else:
            overtime_item.setBackground(QBrush(QColor(theme.BG_PANEL)))
        self.setItem(row, days + self._prev_col_offset + 5, overtime_item)

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
            self.setItem(row, days + self._prev_col_offset + 6, target_item)

    def _fill_validation_rows(self, emp_count, days, constraint_presenter):
        # Definiujemy wiersze podsumowania
        for offset, (label, key) in enumerate(self._summary_rows()):
            row = emp_count + offset

            # Etykieta wiersza (lewa kolumna)
            name_item = QTableWidgetItem(label)
            name_item.setBackground(QBrush(QColor(theme.BG_HEADER)))
            name_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self.setItem(row, 0, name_item)

            if self._prev_col_offset:
                # Kolumna "pamięć poprzedniego miesiąca" nie ma znaczenia
                # dla wierszy podsumowania - te dotyczą TEGO miesiąca.
                info_filler = QTableWidgetItem("")
                info_filler.setBackground(QBrush(QColor(theme.BG_PANEL)))
                self.setItem(row, 1, info_filler)

            for day in range(1, days + 1):
                if key == "coverage":
                    # Rotacja 24/7 - sprawdzane niezależnie od reszty tej
                    # pętli (open/close/morning/afternoon/meat nie mają tu
                    # zastosowania), patrz logic/duty_coverage_presenter.py.
                    covered = is_day_fully_covered(self.schedule, self.shop_config, self._visible_employees, day)
                    item = QTableWidgetItem("✅" if covered else "❌")
                    item.setTextAlignment(Qt.AlignCenter)
                    item.setBackground(QBrush(QColor(theme.OK_GREEN if covered else theme.ERR_RED)))
                    if not covered:
                        item.setToolTip(
                            "Doba nie jest obsadzona dokładnie jedną osobą "
                            "(luka albo dwie osoby naraz)."
                        )
                    self.setItem(row, day + self._prev_col_offset, item)
                    continue

                # Liczniki dla danego dnia
                at_opening = 0
                at_closing = 0
                total_morning = 0
                total_afternoon = 0
                count_meat = 0
                count_role = 0
                role_key = key[len("role:"):] if key.startswith("role:") else None
                fmt = "%H:%M"

                for emp in self._visible_employees:
                    ds = self.schedule.get_day(emp, day)

                    # Ignorujemy osoby, które nie pracują, są na urlopie lub L4
                    if not ds.start or ds.is_leave or getattr(ds, "is_sick", False):
                        continue

                    # Godziny rozwiązywane per lokalizacja pracownika (patrz
                    # ShopConfig.get_location) - bez lokalizacji to dokładnie
                    # jedna, wspólna konfiguracja sklepu co dziś.
                    hours = self.shop_config.get_location(emp).get_open_hours_for_day(day)
                    if not hours:
                        continue
                    shop_open_str, shop_close_str = hours

                    try:
                        shop_open_dt = datetime.strptime(shop_open_str, fmt)
                        shop_close_dt = datetime.strptime(shop_close_str, fmt)
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

                        # 4. Generyczna rola custom profilu (patrz "role:" wiersze)
                        if role_key and emp.has_role(role_key) and not ds.is_leave and not getattr(ds, "is_sick", False):
                            count_role += 1
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
                elif role_key:
                    display_text = str(count_role)

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

                self.setItem(row, day + self._prev_col_offset, item)

            # Wypełnienie komórek sumarycznych (ostatnie 5 kolumn) szarym kolorem
            for col in range(days + self._prev_col_offset + 1, days + self._prev_col_offset + 6):
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
        emp_count = len(self._visible_employees)
        day = self._column_to_day(col)

        if (
            0 <= row < emp_count
            and day is not None
            and self.shop_config
            and self.shop_config.is_trade_day(day)
        ):
            emp = self._visible_employees[row]

            if event.key() in (Qt.Key_1, Qt.Key_2):
                code = "1" if event.key() == Qt.Key_1 else "2"
                self.controller.set_shift_class(emp, day, code)
                self._sync_and_keep_position(row, col)
                return

            if event.key() == Qt.Key_W:
                self.controller.set_day_free(emp, day)
                self._sync_and_keep_position(row, col)
                return

            if event.matches(QKeySequence.Copy):
                self._clipboard_day = self.controller.copy_day_snapshot(emp, day)
                if self.main_window:
                    self.main_window.statusBar().showMessage("Skopiowano dzień.", 2000)
                return

            if event.matches(QKeySequence.Paste):
                if self._clipboard_day:
                    self.controller.paste_day_snapshot(emp, day, self._clipboard_day)
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

        emp_count = len(self._visible_employees)
        day = self._column_to_day(col)

        if row < emp_count and day is not None:
            if (
                self.main_window.quick_mode_enabled
                and self.main_window.quick_selected_shift
            ):
                self._apply_quick_shift(row, col)

    def _handle_double_click(self, row, col):
        if not self.schedule or not self.main_window:
            return

        emp_count = len(self._visible_employees)
        days = self.schedule.days_in_month
        day = self._column_to_day(col)

        if self.settlement_mode and row < emp_count and col == days + self._prev_col_offset + 6:
            self._edit_settlement_target(self._visible_employees[row])
            return

        if row < emp_count and col == 0 and self.on_edit_employee:
            self.on_edit_employee(self._visible_employees[row])
            return

        if row < emp_count and day is not None:
            if (
                self.main_window.quick_mode_enabled
                and self.main_window.quick_selected_shift
            ):
                self._apply_quick_shift(row, col)
            elif self.on_edit_day:
                self.on_edit_day(self._visible_employees[row], day)

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
        day = self._column_to_day(col)
        if day is not None:
            if self.on_header_menu:
                self.on_header_menu(day, None)

    def contextMenuEvent(self, event):
        # 100% pewna metoda na wyłapanie prawego przycisku myszy w Qt
        global_pos = event.globalPos()
        
        # Mapujemy globalną pozycję myszy na obszar viewportu tabeli
        vp_pos = self.viewport().mapFromGlobal(global_pos)
        row = self.rowAt(vp_pos.y())
        col = self.columnAt(vp_pos.x())
        
        if row == -1 or col == -1:
            return
            
        emp_count = len(self._visible_employees)
        day = self._column_to_day(col)

        if row >= emp_count or day is None:
            return

        emp = self._visible_employees[row]
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
            self._clipboard_day = self.controller.copy_day_snapshot(emp, day)
            if self.main_window:
                self.main_window.statusBar().showMessage("Skopiowano dzień.", 2000)
        elif action == act_paste:
            self.controller.paste_day_snapshot(emp, day, self._clipboard_day)
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

        emp = self._visible_employees[row]
        day = self._column_to_day(col)
        if day is None:
            return
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

        elif isinstance(shift, str) and shift.startswith("PRESET:"):
            preset_name = shift.split(":", 1)[1]
            presets = self.main_window.shop_config.quick_mode_presets
            preset = next((p for p in presets if p["name"] == preset_name), None)
            if preset is None:
                return

            self.controller.set_day_preset(emp, day, preset)
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
