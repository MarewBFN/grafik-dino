import os
from copy import deepcopy
from datetime import date

from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer, QUrl
from PySide6.QtGui import QPainter, QColor, QImage, QDesktopServices, QKeySequence
from PySide6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog
import tempfile
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QDialog,
    QInputDialog,
)

from export.excel_exporter import export_schedule_to_excel
from export.export_style import render_schedule_image
from export.employee_card_exporter import (
    export_employee_cards_to_excel,
    render_employee_card_image,
    save_employee_card_pages_to_pdf,
    sanitize_filename_part,
)
from logic.schedule_controller import ScheduleController
from logic.utils.time_utils import previous_calendar_month
from ui.export_preview_dialog import show_export_preview
from ui.previous_month_shift_dialog import PreviousMonthShiftDialog
from ui.marquee_text import MarqueeLabel, WrappingLocationButton
from model.business_profile import DEFAULT_BUSINESS_TYPE
from model.location import format_open_hours_summary
from model.month_schedule import MonthSchedule, PREVIOUS_MONTH_MEMORY_ENABLED
from model.monthly_project import MonthlyProject
from model.shop_config import ShopConfig
from persistence.project_io import (
    assign_missing_location_keys,
    load_project_bundle,
    save_project_bundle,
)
from ui.config_dialog import ConfigDialog
from ui.locations_dialog import LocationsDialog
from ui.day_edit_dialog import DayEditDialog
from ui.day_override_dialog import DayOverrideDialog
from ui.employee_dialog import EmployeeDialog
from ui.grid_legend import GridLegendWidget
from ui.grid_view import ScheduleGrid
from ui.month_picker_dialog import MonthPickerDialog
from ui.new_project_dialog import NewProjectDialog
from ui.quick_mode_settings_dialog import QuickModeSettingsDialog
from ui.time_input import TimeInputWidget
from ui.tutorial_overlay import TutorialOverlay, TutorialStep
from ui.loading_overlay import LoadingOverlay
from ui.demo_manager import DemoManager
from ui.license_manager import get_user_id, show_license_dialog
from version import APP_VERSION

class GeneratorWorker(QObject):
    finished = Signal(object)

    def __init__(self, controller, force=False):
        super().__init__()
        self.controller = controller
        self.force = force

    def run(self):
        result = self.controller.generate_schedule(force=self.force)
        self.finished.emit(result)


class UpdateCancelled(Exception):
    pass


class UpdateDownloadWorker(QObject):
    progress = Signal(int, int)
    finished = Signal(object, object)  # (path, error)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def _on_progress(self, downloaded, total):
        if QThread.currentThread().isInterruptionRequested():
            raise UpdateCancelled()
        self.progress.emit(downloaded, total)

    def run(self):
        from update_checker import download_installer

        try:
            path = download_installer(self.url, progress_callback=self._on_progress)
            self.finished.emit(path, None)
        except UpdateCancelled:
            self.finished.emit(None, None)
        except Exception as e:
            self.finished.emit(None, str(e))

class SettlementBalanceWorker(QObject):
    finished = Signal(object)

    def __init__(self, schedule, shop_config):
        super().__init__()
        self.schedule = schedule
        self.shop_config = shop_config

    def run(self):
        from logic.settlement_balancer import balance_settlement_period

        result = balance_settlement_period(self.schedule, self.shop_config)
        self.finished.emit(result)


class MainWindow(QMainWindow):
    def __init__(self, open_path=None):
        super().__init__()
        QTimer.singleShot(1000, self._check_updates)

        from ui.license_manager import load_license, validate_license

        self.user_id = get_user_id()
        self.demo = DemoManager()

        saved_key = load_license()
        if saved_key and validate_license(self.user_id, saved_key):
            self.demo.is_demo = False

        # Branch demonstracyjne (client-demo/enyo-ochrona) celowo nie
        # pokazuje marki "Dino" w tytule okna - patrz CLIENT_DEMO_README.md.
        self.setWindowTitle("Grafik pracy")
        self.user_id = get_user_id()
        today = date.today()
        self.year = today.year
        self.month = today.month

        self.schedule = None
        self.shop_config = None
        self.controller = None

        self._clipboard_day = None
        self._loading = False

        self.quick_mode_enabled = False
        self.quick_selected_shift = None

        self.settlement_mode_active = False

        # Aktualnie wybrana placówka (klucz w shop_config.locations) -
        # patrz przełącznik pod "Grafik na:" (_build_left_panel) i pasek
        # godzin nad tabelą (_update_grid_header_bar). Samonaprawia się do
        # pierwszej dostępnej lokalizacji w _update_location_switcher(), więc
        # None tu jest tylko stanem przejściowym przed pierwszym _sync_everything().
        self.selected_location_key = None

        self._build_quick_panel()
        self._build_ui()
        self._init_state()
        self._sync_everything()
        self._opened_existing_project = self._open_project_from_path(open_path)
        if not self._opened_existing_project:
            self._opened_existing_project = self._try_load_last_project()
        self.loading_overlay = LoadingOverlay(self)

        self.statusBar().showMessage("Gotowe")
        QTimer.singleShot(0, self._check_first_run)
        QTimer.singleShot(0, self.showMaximized)

    def _open_license_dialog(self):
        show_license_dialog(self)

    def _build_ui(self):
        self._build_menu()

        root = QWidget()
        self.setCentralWidget(root)

        outer = QHBoxLayout(root)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(16)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        outer.addWidget(splitter)

        self.left_panel = self._build_left_panel()
        splitter.addWidget(self.left_panel)

        self.right_panel = self._build_right_panel()
        splitter.addWidget(self.right_panel)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 1120])

        self._apply_card_shadow(self.left_panel)
        self._apply_card_shadow(self.right_panel)

    def _apply_card_shadow(self, widget):
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(28)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(15, 23, 42, 45))
        widget.setGraphicsEffect(shadow)

    def _add_section_header(self, layout, text):
        self._add_section_divider(layout)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        bar = QFrame()
        bar.setObjectName("sectionAccentBar")
        bar.setFixedSize(3, 14)
        row.addWidget(bar)

        header = QLabel(text)
        header.setObjectName("sectionHeader")
        row.addWidget(header)
        row.addStretch(1)

        layout.addLayout(row)

    def _add_section_divider(self, layout):
        divider = QFrame()
        divider.setObjectName("sectionDivider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

    def _build_left_panel(self):
        outer_panel = QFrame()
        outer_panel.setObjectName("panelCard")
        outer_panel.setMinimumWidth(300)
        outer_panel.setMaximumWidth(360)

        outer_layout = QVBoxLayout(outer_panel)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Sidebar bywa wyższy niż mały/niskorozdzielczy ekran ma miejsca —
        # bez przewijania dolne przyciski (okres rozliczeniowy, wersja itd.)
        # znikały wtedy poza widoczny obszar okna, bez możliwości dojechania
        # do nich. Karta zostaje wizualnie taka sama, tylko jej zawartość
        # jest teraz w scrollu.
        scroll = QScrollArea()
        scroll.setObjectName("sidebarScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer_layout.addWidget(scroll)

        panel = QWidget()
        panel.setObjectName("sidebarContent")
        scroll.setWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # Karta-nagłówek sidebaru: "Grafik na:" + data + edycja daty
        hero = QFrame()
        hero.setObjectName("sidebarHero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(14, 14, 14, 14)
        hero_layout.setSpacing(8)

        self.title_row_widget = QWidget()
        title_row_layout = QHBoxLayout(self.title_row_widget)
        title_row_layout.setContentsMargins(0, 0, 0, 0)
        title_row_layout.setSpacing(6)

        self.title_label = QLabel("Grafik na:")
        self.title_label.setObjectName("titleLabel")
        title_row_layout.addWidget(self.title_label)

        self.date_display_label = QLabel(f"{self.month:02d}.{self.year}")
        self.date_display_label.setObjectName("titleLabel")
        title_row_layout.addWidget(self.date_display_label)
        title_row_layout.addStretch(1)

        hero_layout.addWidget(self.title_row_widget)

        self.btn_change_date = QPushButton("🗓 Zmień datę")
        self.btn_change_date.setObjectName("linkButton")
        self.btn_change_date.setCursor(Qt.PointingHandCursor)
        self.btn_change_date.setFixedWidth(120)
        self.btn_change_date.clicked.connect(self._open_month_picker)

        hero_layout.addWidget(self.btn_change_date)

        layout.addWidget(hero)

        # Przełącznik placówek - celowo NA OSOBNYM tle od karty "hero"
        # powyżej (patrz QFrame#locationSwitcher w ui/theme.py), zawsze
        # widoczny (nawet z jedną lokalizacją - strzałki są wtedy tylko
        # wyszarzone), bo projekt ma zawsze co najmniej jedną lokalizację
        # (patrz model/shop_config.py). Kliknięcie nazwy otwiera pełną listę.
        self.location_switcher = QFrame()
        self.location_switcher.setObjectName("locationSwitcher")
        switcher_layout = QHBoxLayout(self.location_switcher)
        switcher_layout.setContentsMargins(6, 4, 6, 4)
        switcher_layout.setSpacing(4)

        self.btn_location_prev = QPushButton("◀")
        self.btn_location_prev.setObjectName("locationSwitcherArrow")
        self.btn_location_prev.setFixedWidth(30)
        self.btn_location_prev.setToolTip("Poprzednia placówka")
        self.btn_location_prev.clicked.connect(lambda: self._cycle_location(-1))
        switcher_layout.addWidget(self.btn_location_prev)

        # Zawija za długą nazwę na kilka linii (rosnąc w pionie) zamiast
        # przewijać ją w poziomie (marquee) - na życzenie użytkownika.
        # Minimalna wysokość rośnie monotonicznie w ramach sesji, więc
        # przełączenie na krótszą nazwę nie zmniejsza już wysokości tego
        # wiersza (i nie "rozjeżdża" reszty panelu) - patrz
        # WrappingLocationButton._rewrap().
        self.btn_location_name = WrappingLocationButton("")
        self.btn_location_name.setObjectName("locationNameButton")
        self.btn_location_name.setCursor(Qt.PointingHandCursor)
        self.btn_location_name.setToolTip("Wybierz placówkę")
        self.btn_location_name.clicked.connect(self._open_location_picker)
        switcher_layout.addWidget(self.btn_location_name, 1)

        self.btn_location_next = QPushButton("▶")
        self.btn_location_next.setObjectName("locationSwitcherArrow")
        self.btn_location_next.setFixedWidth(30)
        self.btn_location_next.setToolTip("Następna placówka")
        self.btn_location_next.clicked.connect(lambda: self._cycle_location(1))
        switcher_layout.addWidget(self.btn_location_next)

        layout.addWidget(self.location_switcher)

        metric_hint = QLabel("Nominalny etat")
        metric_hint.setObjectName("metricHint")
        layout.addWidget(metric_hint)

        self.nominal_hours_label = QLabel("-")
        self.nominal_hours_label.setObjectName("metricValue")
        layout.addWidget(self.nominal_hours_label)

        self.btn_generate = QPushButton("⚙ Generuj grafik")
        self.btn_generate.setObjectName("primaryButton")
        self.btn_generate.setMinimumHeight(44)
        self.btn_generate.clicked.connect(self._on_generate_clicked)
        self.btn_generate.setToolTip("Tworzy nowy grafik od zera. Nie nadpisuje ręcznie wprowadzonych zmian")

        self.btn_add_employee = QPushButton("＋ Dodaj pracownika")
        self.btn_add_employee.setObjectName("secondaryButton")
        self.btn_add_employee.setMinimumHeight(44)
        self.btn_add_employee.clicked.connect(self._open_add_employee)

        self.btn_undo = QPushButton("↶ Cofnij")
        self.btn_undo.setMinimumHeight(40)
        self.btn_undo.clicked.connect(self._undo)

        self.btn_redo = QPushButton("↷ Ponów")
        self.btn_redo.setMinimumHeight(40)
        self.btn_redo.clicked.connect(self._redo)

        self.btn_expand_view = QPushButton("⤢ Rozszerz widok")
        self.btn_expand_view.setObjectName("secondaryButton")
        self.btn_expand_view.setMinimumHeight(44)
        self.btn_expand_view.setCheckable(True)
        self.btn_expand_view.clicked.connect(self._toggle_expanded_view)

        self.btn_quick_mode = QPushButton("⚡ Tryb szybki")
        self.btn_quick_mode.setToolTip("Tryb szybkiego wprowadzania zmian ręcznie.")
        self.btn_quick_mode.setObjectName("secondaryButton")
        self.btn_quick_mode.setMinimumHeight(44)
        self.btn_quick_mode.setCheckable(True)
        self.btn_quick_mode.clicked.connect(self._toggle_quick_mode)

        layout.addWidget(self.btn_generate)
        self.generate_limit_label = QLabel("")
        self.generate_limit_label.setObjectName("mutedHint")
        layout.addWidget(self.generate_limit_label)

        self._add_section_header(layout, "WIDOK I TRYBY")
        layout.addWidget(self.btn_expand_view)
        layout.addWidget(self.btn_quick_mode)
        layout.addWidget(self.quick_panel)

        self._add_section_header(layout, "ZARZĄDZANIE")
        layout.addWidget(self.btn_add_employee)

        undo_redo_row = QHBoxLayout()
        undo_redo_row.addWidget(self.btn_undo)
        undo_redo_row.addWidget(self.btn_redo)
        layout.addLayout(undo_redo_row)

        self.settlement_section = QWidget()
        settlement_layout = QVBoxLayout(self.settlement_section)
        settlement_layout.setContentsMargins(0, 0, 0, 0)
        settlement_layout.setSpacing(8)

        self._add_section_header(settlement_layout, "OKRES ROZLICZENIOWY")

        self.btn_settlement_toggle = QPushButton("Włącz okres rozliczeniowy")
        self.btn_settlement_toggle.setObjectName("secondaryButton")
        self.btn_settlement_toggle.setMinimumHeight(40)
        self.btn_settlement_toggle.setCheckable(True)
        self.btn_settlement_toggle.clicked.connect(self._toggle_settlement_mode)
        settlement_layout.addWidget(self.btn_settlement_toggle)

        self.settlement_info_label = QLabel("Edytujesz teraz okres rozliczeniowy")
        self.settlement_info_label.setObjectName("warningHint")
        self.settlement_info_label.setWordWrap(True)
        self.settlement_info_label.hide()
        settlement_layout.addWidget(self.settlement_info_label)

        self.btn_settlement_balance = QPushButton("Wyrównaj godziny")
        self.btn_settlement_balance.setObjectName("primaryButton")
        self.btn_settlement_balance.setMinimumHeight(40)
        self.btn_settlement_balance.clicked.connect(self._on_balance_hours_clicked)
        self.btn_settlement_balance.hide()
        settlement_layout.addWidget(self.btn_settlement_balance)

        layout.addWidget(self.settlement_section)
        # Okres rozliczeniowy (sidebar + kolumna "Cel" w ui/grid_view.py, w
        # pełni sterowana przez settlement_mode) - schowany na prośbę klienta,
        # zostaje w pełni działający w kodzie (patrz też btn_work.hide() niżej
        # dla identycznego wzorca).
        self.settlement_section.hide()

        layout.addStretch(1)

        if self.demo.is_demo:
            self._add_section_divider(layout)
            self.demo_label = QLabel("Wersja demonstracyjna")
            self.demo_label.setObjectName("dangerHint")
            layout.addWidget(self.demo_label)

            self.btn_buy = QPushButton("Zakup pełną wersję")
            self.btn_buy.setObjectName("successButton")
            self.btn_buy.clicked.connect(self._open_buy_page)
            layout.addWidget(self.btn_buy)

        self.user_id_label = QLabel(f"ID użytkownika: {self.user_id}")
        self.user_id_label.setObjectName("mutedHint")
        layout.addWidget(self.user_id_label)

        self.version_label = QLabel(f"Wersja: {APP_VERSION}")
        self.version_label.setObjectName("mutedHint")
        layout.addWidget(self.version_label)

        return outer_panel

    def _open_buy_page(self):
        QDesktopServices.openUrl(QUrl("https://madebykewin.pl"))

    def _build_quick_panel(self):
        self.quick_panel = QWidget(self)
        self.quick_panel.setObjectName("quickPanel")

        layout = QVBoxLayout(self.quick_panel)
        layout.setContentsMargins(0, 5, 0, 0)
        layout.setSpacing(8)

        self.quick_info_label = QLabel("Tryb szybki włączony. Ustaw preferowany typ zmiany i nanieś na grafik jednym kliknięciem.")
        self.quick_info_label.setWordWrap(True)
        self.quick_info_label.setObjectName("quickInfoHint")
        layout.addWidget(self.quick_info_label)

        # --- przyciski: siatka 2x3 (Praca/Rano/Popo, Wolne/Urlop/L4) ---
        self.quick_btn_grid = QGridLayout()
        btn_grid = self.quick_btn_grid
        btn_grid.setSpacing(6)

        self.btn_work = QPushButton("Praca")
        self.btn_work.setCheckable(True)
        self.btn_work.setToolTip("Wprowadź dokładne godziny pracy dla wybranej komórki.")
        self.btn_work.clicked.connect(lambda: self._set_quick_shift("WORK"))

        self.btn_morning = QPushButton("Rano")
        self.btn_morning.setCheckable(True)
        self.btn_morning.setToolTip(
            "Blokuje zmianę na typ „rano” — dokładną godzinę dobierze później generator."
        )
        self.btn_morning.clicked.connect(lambda: self._set_quick_shift("MORNING_CLASS"))

        self.btn_afternoon = QPushButton("Popo")
        self.btn_afternoon.setCheckable(True)
        self.btn_afternoon.setToolTip(
            "Blokuje zmianę na typ „popołudnie” — dokładną godzinę dobierze później generator."
        )
        self.btn_afternoon.clicked.connect(lambda: self._set_quick_shift("AFTERNOON_CLASS"))

        self.btn_off = QPushButton("Wolne")
        self.btn_off.setCheckable(True)
        self.btn_off.clicked.connect(lambda: self._set_quick_shift("OFF"))

        self.btn_leave = QPushButton("Urlop")
        self.btn_leave.setCheckable(True)
        self.btn_leave.clicked.connect(lambda: self._set_quick_shift("LEAVE"))

        self.btn_sick = QPushButton("L4")
        self.btn_sick.setCheckable(True)
        self.btn_sick.clicked.connect(lambda: self._set_quick_shift("SICK"))

        for btn in (
            self.btn_work, self.btn_morning, self.btn_afternoon,
            self.btn_off, self.btn_leave, self.btn_sick,
        ):
            btn.setObjectName("secondaryButton")
            btn.setMinimumHeight(36)

        # "Praca" (ręczne wpisywanie godzin) - schowany na rzecz nazwanych
        # przedziałów z "Ustawień trybu szybkiego" (Konfiguracja), ale
        # zostaje w pełni działający w kodzie (_set_quick_shift("WORK"),
        # time_panel poniżej) na prośbę z 2026-09-17.
        self.btn_work.hide()

        # Pozycje w siatce są przeliczane dynamicznie w _relayout_quick_btn_grid()
        # (tak, żeby ukrycie Rano/Popo dla profili innych niż Dino/retail -
        # patrz _update_quick_panel_profile_visibility - nie zostawiało pustych
        # komórek), więc tu tylko budujemy layout, bez addWidget.
        self._relayout_quick_btn_grid()

        layout.addLayout(btn_grid)

        # --- przyciski dla ręcznie zdefiniowanych przedziałów (Konfiguracja
        # -> "Ustawienia trybu szybkiego") - dobudowywane dynamicznie,
        # patrz _rebuild_quick_preset_buttons(). ---
        self.quick_presets_label = QLabel("Własne przedziały:")
        self.quick_presets_label.setObjectName("mutedHint")
        self.quick_presets_label.hide()
        layout.addWidget(self.quick_presets_label)

        self.quick_presets_grid = QGridLayout()
        self.quick_presets_grid.setSpacing(6)
        layout.addLayout(self.quick_presets_grid)

        self.quick_preset_buttons: dict[str, QPushButton] = {}

        self.btn_add_quick_preset = QPushButton("+ Dodaj własne...")
        self.btn_add_quick_preset.setObjectName("secondaryButton")
        self.btn_add_quick_preset.clicked.connect(self._open_quick_mode_settings)
        layout.addWidget(self.btn_add_quick_preset)

        # --- panel godzin (tylko dla "Praca") ---
        self.time_panel = QWidget(self)
        time_layout = QHBoxLayout(self.time_panel)
        time_layout.setContentsMargins(0, 5, 0, 0)

        self.start_input = TimeInputWidget()
        self.start_input.set_time_str("06:00")

        self.end_input = TimeInputWidget()
        self.end_input.set_time_str("14:00")

        time_layout.addWidget(QLabel(" Od "))
        time_layout.addWidget(self.start_input)
        time_layout.addWidget(QLabel(" Do "))
        time_layout.addWidget(self.end_input)

        self.time_panel.setLayout(time_layout)
        self.time_panel.setEnabled(False)

        layout.addWidget(self.time_panel)

        self.quick_duration_label = QLabel("Czas pracy: 0:00")
        self.quick_duration_label.setObjectName("metricValue")
        self.quick_duration_label.setEnabled(False)
        layout.addWidget(self.quick_duration_label)

        # "Od"/"Do" (tylko dla "Praca", który jest schowany - patrz wyżej) oraz
        # licznik godzin pod nim - schowane z tego samego powodu, zostają w
        # pełni działające w kodzie (_set_quick_shift/_quick_update_duration
        # nadal ustawiają ich stan jak dziś).
        self.time_panel.hide()
        self.quick_duration_label.hide()

        self.quick_panel.setLayout(layout)
        self.quick_panel.hide()

        self._quick_manual_end = False

        self.start_input.input.textChanged.connect(self._quick_on_start_changed)
        self.end_input.input.textChanged.connect(self._quick_on_end_changed)

    def _build_right_panel(self):
        panel = QFrame()
        panel.setObjectName("contentCard")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 0, 12, 12)
        layout.setSpacing(10)

        # Pasek nad tabelą: nazwa aktualnie wybranej placówki (lewo) i jej
        # godziny pracy (prawo, patrz format_open_hours_summary) - odświeżany
        # w _update_grid_header_bar(), wywoływanym z _update_location_switcher().
        self.grid_header_bar = QWidget()
        grid_header_layout = QHBoxLayout(self.grid_header_bar)
        grid_header_layout.setContentsMargins(4, 4, 4, 4)

        self.grid_header_location_label = MarqueeLabel("")
        self.grid_header_location_label.setObjectName("sectionLabel")
        self.grid_header_location_label.setMaximumWidth(260)
        # Stretch=1 (nie 0): z 0 ta etykieta dostawała dokładnie swój
        # sizeHint() jako szerokość, bez dostępu do reszty wolnego miejsca w
        # tym wierszu mimo setMaximumWidth(260) - bug zgłoszony przez
        # użytkownika (nazwa ucinała się po ~2 znakach). addStretch(1) niżej
        # nadal spycha grid_header_hours_label w prawo, bo ta etykieta i tak
        # nie urośnie ponad swój maximumWidth.
        grid_header_layout.addWidget(self.grid_header_location_label, 1)
        grid_header_layout.addStretch(1)

        self.grid_header_hours_label = QLabel("")
        self.grid_header_hours_label.setObjectName("mutedHint")
        grid_header_layout.addWidget(self.grid_header_hours_label)

        layout.addWidget(self.grid_header_bar)

        self.grid = ScheduleGrid()
        self.grid.compact_mode = True
        layout.addWidget(self.grid, 1)

        # Legenda kolorów/zakreśleń komórek, zawsze pod siatką - stretch=0,
        # więc nigdy nie zabiera miejsca siatce (self.grid ma jedyny
        # stretch>0 w tym layoucie) - patrz _update_grid_legend() (stylizacja
        # zależna od liczby widocznych pracowników, wołane z _sync_everything).
        self.grid_legend = GridLegendWidget()
        layout.addWidget(self.grid_legend, 0)

        return panel

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("Plik")
        edit_menu = self.menuBar().addMenu("Edycja")
        config_menu = self.menuBar().addMenu("Konfiguracja")
        wyglad_menu = self.menuBar().addMenu("Wygląd")
        help_menu = self.menuBar().addMenu("Pomoc")

        help_menu.addAction("Samouczek", self._open_tutorial)

        file_menu.addAction("Nowy projekt...", self._open_new_project)
        file_menu.addAction("Usuń konfigurację", self._reset_configuration)
        file_menu.addSeparator()
        file_menu.addAction("Zapisz", self._save_project)
        file_menu.addAction("Wczytaj", self._load_project)

        export_menu = QMenu("Eksport", self)
        export_menu.addAction("Excel", self._export_excel)
        export_menu.addAction("JPG", self._export_image)
        export_menu.addAction("PDF", self._export_pdf)
        file_menu.addMenu(export_menu)

        cards_menu = QMenu("Karty pracy", self)
        cards_menu.addAction("Excel...", self._export_employee_cards_excel)
        cards_menu.addAction("JPG...", self._export_employee_cards_image)
        cards_menu.addAction("PDF...", self._export_employee_cards_pdf)
        file_menu.addMenu(cards_menu)

        file_menu.addSeparator()
        file_menu.addAction("Drukuj...", self._print_schedule)

        file_menu.addSeparator()
        file_menu.addAction("Zamknij", self.close)

        undo_action = edit_menu.addAction("Cofnij", self._undo)
        undo_action.setShortcut(QKeySequence.Undo)

        redo_action = edit_menu.addAction("Ponów", self._redo)
        redo_action.setShortcut(QKeySequence.Redo)

        edit_menu.addSeparator()
        edit_menu.addAction("Wyczyść grafik", self._clear_schedule)
        edit_menu.addAction("Wyczyść auto", self._clear_generated)

        # Ręczny edytor "Godziny zakończenia z poprzedniego miesiąca..."
        # (PreviousMonthShiftDialog) schowany na prośbę użytkownika - był
        # tylko testowym rozwiązaniem (i źródłem błędu: domyślna godzina
        # "22:00" w dialogu blokowała cały grafik bez wyjaśnienia, patrz
        # PreviousMonthBlocksDay1DiagnosticsTests). Sama pamięć
        # poprzedniego miesiąca zostaje w pełni aktywna - działa
        # automatycznie przy zmianie miesiąca (patrz
        # _carry_over_previous_month_end_shifts), tylko bez tej ręcznej
        # furtki do wpisania jej od zera.

        config_menu.addAction("Generator", self._open_config)
        config_menu.addAction("Lokalizacje", self._open_locations_dialog)
        config_menu.addAction("Ustawienia trybu szybkiego", self._open_quick_mode_settings)

        # Miejsce na ustawienia wyglądu GUI - na razie tylko jedna pozycja
        # (jak siatka grafiku pokazuje godziny zmiany), kolejne dojdą tu w
        # przyszłości. Wzorem "Eksport"/"Karty pracy" w menu Plik: osobny
        # QMenu zbudowany raz w _build_menu, nie odtwarzany przy każdym
        # kliknięciu (patrz self._update_hours_display_menu wywoływane z
        # _sync_everything, żeby stan zaznaczenia nadążał za wczytanym
        # projektem).
        hours_display_menu = QMenu("Widok trybu szybkiego", self)
        self.hours_display_standard_action = hours_display_menu.addAction(
            "Standardowy (obecny)", lambda: self._set_hours_display_mode("standard")
        )
        self.hours_display_standard_action.setCheckable(True)
        self.hours_display_fractions_action = hours_display_menu.addAction(
            "Ułamki", lambda: self._set_hours_display_mode("fractions")
        )
        self.hours_display_fractions_action.setCheckable(True)
        wyglad_menu.addMenu(hours_display_menu)

        # Pokaż/ukryj legendę kolorów pod siatką (ui/grid_legend.py) -
        # domyślnie ukryta (ShopConfig.show_grid_legend=False), patrz
        # _toggle_grid_legend/_update_grid_legend_menu.
        self.show_grid_legend_action = wyglad_menu.addAction(
            "Legenda kolorów", self._toggle_grid_legend
        )
        self.show_grid_legend_action.setCheckable(True)

        help_menu.addAction("Klucz produktu", self._open_license_dialog)
        help_menu.addAction("Sprawdź aktualizacje", lambda: self._check_updates(manual=True))
        help_menu.addAction("O programie", self._about)

    def _open_new_project(self):
        if self.schedule is not None:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Nowy projekt")
            msg_box.setText(
                "Utworzenie nowego projektu usunie bieżący grafik, listę "
                "pracowników i ustawienia konfiguracji. Kontynuować?"
            )
            btn_yes = msg_box.addButton("Tak", QMessageBox.YesRole)
            msg_box.addButton("Anuluj", QMessageBox.RejectRole)
            msg_box.exec()
            if msg_box.clickedButton() != btn_yes:
                return

        dialog = NewProjectDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        self.year = dialog.result_year
        self.month = dialog.result_month
        self._set_date_controls(self.year, self.month)

        # Świadomie nie dziedziczymy pracowników poprzedniego projektu -
        # _init_state() normalnie przenosi ich (sensowne przy zwykłej zmianie
        # miesiąca tej samej firmy), ale "Nowy projekt" może oznaczać inną
        # branżę z innymi rolami.
        self.schedule = None
        self._init_state()
        self.shop_config.business_type = dialog.result_business_type

        # Codex review finding on this PR: unlike _apply_first_run_wizard_result,
        # this path never applied a fresh custom profile's default policies -
        # apply_registry skips a spec whose policy key is absent from
        # shop.constraint_policies, so every rule of a custom profile
        # selected here (including ones configured as MANDATORY in the
        # wizard) stayed silently DISABLED until Config was opened and saved.
        from model.business_profile import get_custom_profile
        custom = get_custom_profile(dialog.result_business_type)
        if custom is not None:
            from logic.generator.custom_profile_wiring import default_policies
            self.shop_config.constraint_policies.update(default_policies(custom))

        self._update_nominal_hours_label()
        self._sync_everything()
        self.statusBar().showMessage("Utworzono nowy projekt.", 2500)

    def _reset_configuration(self):
        """"Usuń konfigurację" - przywraca WYŁĄCZNIE grafik/konfigurację
        (schedule, shop_config, last_project.json) do stanu sprzed
        pierwszego uruchomienia, tym samym mechanizmem co _open_new_project
        (self.schedule=None przed _init_state(), żeby nie przenieść starych
        pracowników) - tylko bez interaktywnego NewProjectDialog, od razu na
        gołe domyślne wartości, i z jawnym dopisaniem last_project.json na
        końcu (czego _open_new_project nie robi), żeby stan nie wrócił po
        restarcie. Świadomie NIE dotyka first_run.flag/*_tutorial_seen.flag/
        license.json/machine_id.json/demo.json/custom_profiles.json - to nie
        jest "grafik", tylko odrębny stan pierwszego uruchomienia/licencji/
        poradników, który użytkownik wprost poprosił zostawić w spokoju."""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Usuń konfigurację")
        msg_box.setText(
            "To przywróci program do stanu sprzed pierwszego uruchomienia: "
            "usunie bieżący grafik, listę pracowników, lokalizacje i całą "
            "konfigurację generatora.\n\n"
            "Klucz licencji, flaga pierwszego uruchomienia i zapamiętane "
            "poradniki NIE zostaną ruszone.\n\n"
            "Tej operacji nie da się cofnąć. Kontynuować?"
        )
        btn_yes = msg_box.addButton("Tak, usuń", QMessageBox.YesRole)
        msg_box.addButton("Anuluj", QMessageBox.RejectRole)
        msg_box.exec()
        if msg_box.clickedButton() != btn_yes:
            return

        today = date.today()
        self.year, self.month = today.year, today.month
        self._set_date_controls(self.year, self.month)

        self.schedule = None
        self._init_state()  # już ustawia domyślny widoczny profil - patrz _apply_default_visible_business_type

        self._update_nominal_hours_label()
        self._sync_everything()

        try:
            save_project_bundle("last_project.json", self.project, self.year, self.month)
        except OSError:
            pass

        self.statusBar().showMessage(
            "Usunięto konfigurację - program działa jak po pierwszym uruchomieniu.", 3000
        )

    def _init_state(self):
        old_employees = []

        if self.schedule:
            old_employees = self.schedule.employees

        self.schedule = MonthSchedule(self.year, self.month, employees=old_employees)
        self.shop_config = ShopConfig(self.year, self.month)
        self.controller = ScheduleController(self.schedule, self.shop_config)

        # Świeży/zerowany projekt = świeży kontener "pamięci wielu miesięcy"
        # (patrz model/monthly_project.py) - żaden inny miesiąc jeszcze nie
        # istnieje, tylko ten właśnie utworzony.
        self.project = MonthlyProject()
        self.project.put(self.year, self.month, self.schedule, self.shop_config)

        self._apply_default_visible_business_type()

    def _apply_default_visible_business_type(self):
        """Goły ShopConfig() domyślnie wraca do dino_retail (patrz
        model/business_profile.py::DEFAULT_BUSINESS_TYPE) - na tym branchu
        (Dino celowo wykluczone z visible_profiles(), patrz
        ENYO_ONLY_CHANGES.md) to nigdy nie jest poprawny wybór dla
        świeżo utworzonego projektu. Bez tego wiersze podsumowania
        Otwarcie/Zamknięcie/Mięso (dino_retail) pokazywały się przy każdym
        pierwszym uruchomieniu na chwilę (albo na stałe, gdyby ktoś zamknął
        kreator bez dokończenia go) - zanim kreator pierwszego uruchomienia
        (albo NewProjectDialog) zdążył nadpisać business_type poprawną
        wartością. Wywoływana z _init_state() - każdy z jego trzech
        wywołań, który faktycznie chce inny profil (kreator, "Nowy
        projekt..."), i tak nadpisuje business_type zaraz potem."""
        from model.business_profile import get_custom_profile, visible_profiles
        profiles = visible_profiles()
        if not profiles:
            return
        self.shop_config.business_type = profiles[0].key
        custom = get_custom_profile(self.shop_config.business_type)
        if custom is not None:
            from logic.generator.custom_profile_wiring import default_policies
            self.shop_config.constraint_policies.update(default_policies(custom))

    def _sync_everything(self):
        # Bezpiecznik: tabela grafiku filtruje pracowników po location_key
        # (patrz _sync_grid), więc ktoś bez poprawnego przypisania byłby
        # trwale niewidoczny w każdej placówce - dopina go do pierwszej
        # dostępnej. Tania, bezstanowa operacja (patrz assign_missing_location_keys),
        # bezpieczna do wołania przy każdej synchronizacji.
        if self.schedule and self.shop_config:
            assign_missing_location_keys(self.schedule, self.shop_config)

        # Musi wejść przed _sync_grid(): samonaprawia selected_location_key,
        # które ten drugi przekazuje jako filtr tabeli.
        self._update_location_switcher()
        self._sync_grid()
        self._update_grid_legend()
        self._update_window_title()
        self._update_state_label()
        self._update_generate_label()
        self._update_settlement_section_visibility()
        self._rebuild_quick_preset_buttons()
        self._update_quick_panel_profile_visibility()
        self._update_hours_display_menu()

    def _update_location_switcher(self):
        """Samonaprawia self.selected_location_key (patrz komentarz w
        __init__) i odświeża przełącznik pod "Grafik na:" oraz pasek godzin
        nad tabelą. Projekt ma zawsze >=1 lokalizację (model/shop_config.py),
        więc `location` poniżej jest None tylko przejściowo, zanim
        shop_config w ogóle istnieje."""
        locations = self.shop_config.locations if self.shop_config else {}
        if self.selected_location_key not in locations:
            self.selected_location_key = next(iter(locations), None)

        location = locations.get(self.selected_location_key)
        self.btn_location_name.setFullText(location.name if location else "—")

        multiple = len(locations) > 1
        self.btn_location_prev.setEnabled(multiple)
        self.btn_location_next.setEnabled(multiple)

        self._update_grid_header_bar()

    def _update_grid_header_bar(self):
        locations = self.shop_config.locations if self.shop_config else {}
        location = locations.get(self.selected_location_key)
        self.grid_header_location_label.setFullText(location.name if location else "")
        self.grid_header_hours_label.setText(
            format_open_hours_summary(location) if location else ""
        )

    def _cycle_location(self, direction: int):
        keys = list(self.shop_config.locations.keys())
        if len(keys) < 2 or self.selected_location_key not in keys:
            return
        idx = keys.index(self.selected_location_key)
        self._select_location(keys[(idx + direction) % len(keys)])

    def _select_location(self, key: str):
        if key == self.selected_location_key or key not in self.shop_config.locations:
            return
        self.selected_location_key = key
        self._update_location_switcher()
        self._sync_grid()

    def _open_location_picker(self):
        locations = self.shop_config.locations
        if not locations:
            return
        menu = QMenu(self)
        for key, loc in locations.items():
            action = menu.addAction(loc.name)
            action.setCheckable(True)
            action.setChecked(key == self.selected_location_key)
            action.triggered.connect(lambda checked=False, k=key: self._select_location(k))
        menu.exec(self.btn_location_name.mapToGlobal(self.btn_location_name.rect().bottomLeft()))

    def _relayout_quick_btn_grid(self):
        """Przelicza pozycje przycisków trybu szybkiego tak, żeby Rano/Popo,
        ukryte dla profili innych niż Dino/retail (patrz
        _update_quick_panel_profile_visibility), nie zostawiały pustych
        komórek w siatce. Celowo NIE opiera się na isHidden()/isVisible() -
        oba zależą od tego, czy cały widget jest już faktycznie pokazany w
        oknie (fałszywie widoczne jako "ukryte" zanim main_window.show() w
        ogóle się wykona), tylko bezpośrednio na profilu projektu."""
        while self.quick_btn_grid.count():
            self.quick_btn_grid.takeAt(0)

        is_retail = (
            self.shop_config.business_type == DEFAULT_BUSINESS_TYPE
            if self.shop_config else True
        )
        buttons = (
            [self.btn_morning, self.btn_afternoon] if is_retail else []
        ) + [self.btn_off, self.btn_leave, self.btn_sick]

        cols = 3
        for i, btn in enumerate(buttons):
            self.quick_btn_grid.addWidget(btn, i // cols, i % cols)

    def _update_quick_panel_profile_visibility(self):
        """Rano/Popo to skróty specyficzne dla profilu Dino/retail (klasy
        zmian sklepowych) - dla innych profili (np. Ochrona) są schowane, ale
        w pełni działające w kodzie, gdyby jednak okazały się potrzebne."""
        is_retail = self.shop_config.business_type == DEFAULT_BUSINESS_TYPE
        self.btn_morning.setVisible(is_retail)
        self.btn_afternoon.setVisible(is_retail)
        self._relayout_quick_btn_grid()

    def _update_settlement_section_visibility(self):
        is_generated = bool(self.schedule and getattr(self.schedule, "is_generated", False))
        self.btn_settlement_toggle.setEnabled(is_generated)
        self.btn_settlement_toggle.setToolTip(
            "" if is_generated else "Najpierw należy wygenerować grafik."
        )

        if not is_generated and self.settlement_mode_active:
            self.btn_settlement_toggle.setChecked(False)
            self._toggle_settlement_mode()


    def _sync_grid(self):
        self.grid.set_data(
            self.schedule,
            self.shop_config,
            self.controller,
            main_window=self,
            on_edit_day=self._edit_day,
            on_edit_employee=self._edit_employee,
            on_context_menu=self._open_day_context_menu,
            on_header_menu=self._open_header_menu,
            location_filter=self.selected_location_key,
        )
        self.grid.build()
        self.grid.refresh()

    def _update_grid_legend(self):
        """Widoczność legendy (menu Wygląd -> "Legenda kolorów", domyślnie
        ukryta - patrz ShopConfig.show_grid_legend) i jej wygląd pod siatką
        (patrz ui/grid_legend.py::GridLegendWidget) - "wyraźnie oddzielona
        sekcja" gdy widocznych (przefiltrowanych po lokalizacji, tak jak w
        samej siatce) pracowników jest więcej niż 10, bo przy dużej liczbie
        wierszy siatka i tak zajmuje większość ekranu. Wołane z
        _sync_everything() i _toggle_grid_legend()."""
        visible = bool(self.shop_config and self.shop_config.show_grid_legend)
        self.grid_legend.setVisible(visible)
        self.show_grid_legend_action.setChecked(visible)

        visible_count = len(self.grid.get_visible_employees()) if self.grid else 0
        self.grid_legend.set_compact_section(visible_count > 10)

    def _update_window_title(self):
        name = self.shop_config.name if self.shop_config else ""
        prefix = f"Grafik pracy — {name}" if name else "Grafik pracy"
        self.setWindowTitle(f"{prefix} — {self.month:02d}.{self.year}")

    def _update_nominal_hours_label(self):
        if not self.shop_config:
            self.nominal_hours_label.setText("-")
            return
        hours = self.shop_config.get_full_time_nominal_hours()
        self.nominal_hours_label.setText(f"{hours} h")

    def _update_state_label(self):
        # The month/year is shown in the left control panel; no duplicate grid header.
        pass

    def _set_date_controls(self, year, month):
        if hasattr(self, 'date_display_label'):
            self.date_display_label.setText(f"{month:02d}.{year}")

    def _open_month_picker(self):
        """Wpięte pod przycisk "🗓 Zmień datę" - okno-kalendarz
        (ui/month_picker_dialog.py) pokazujące wszystkie miesiące tego
        projektu razem z ich stanem (patrz
        model/monthly_project.py::describe_month_state), tak żeby przełączanie
        było świadomym wyborem, nie zgadywaniem "czy tu coś już jest"."""
        dialog = MonthPickerDialog(self.project, self.year, self.month, self)
        if dialog.exec() == QDialog.Accepted and dialog.result_year is not None:
            self._switch_to_month(dialog.result_year, dialog.result_month)

    def _switch_to_month(self, new_year: int, new_month: int) -> None:
        """Przełącza na (new_year, new_month) w ramach TEGO SAMEGO projektu -
        jedyna droga zmiany miesiąca (_open_month_picker). Od pamięci wielu
        miesięcy (model/monthly_project.py) nieodwracalnie NIC się już nie
        kasuje: miesiąc odwiedzony wcześniej wraca dokładnie taki, jaki
        został zostawiony; naprawdę nowy miesiąc startuje pusty (ale z tymi
        samymi pracownikami/lokalizacjami/regułami generatora), z pamięcią
        końca poprzedniego miesiąca doliczoną automatycznie, jeśli miesiąc
        bezpośrednio go poprzedzający już istnieje w projekcie - niezależnie
        od tego, który miesiąc był aktualnie otwarty przed przełączeniem."""
        if new_year == self.year and new_month == self.month:
            return

        self._loading = True

        # Bieżący stan zawsze z powrotem do kontenera, zanim przełączymy -
        # self.schedule/self.shop_config mogły być edytowane w miejscu od
        # czasu ostatniego project.put() (te same referencje, więc to tylko
        # zabezpieczenie, nie właściwa kopia).
        self.project.put(self.year, self.month, self.schedule, self.shop_config)

        existing = self.project.get(new_year, new_month)
        if existing is not None:
            self.schedule, self.shop_config = existing
        else:
            # Nowy miesiąc w tym projekcie - ten sam wzorzec co dawny
            # _save_date_clicked: NIE zupełnie świeży ShopConfig (to gubiłoby
            # profil działalności/lokalizacje/presety/reguły generatora),
            # tylko kopia bieżącego, zerowana z tego co miesiąc-specyficzne
            # (patrz ShopConfig.reset_for_new_month). Kopia (nie ten sam
            # obiekt) - inaczej edycja "nowego" miesiąca cofałaby się też do
            # miesięcy już zapisanych w kontenerze, które współdzieliłyby tę
            # samą instancję.
            new_shop_config = deepcopy(self.shop_config)
            new_shop_config.reset_for_new_month(new_year, new_month)
            self.shop_config = new_shop_config
            self.schedule = MonthSchedule(new_year, new_month, employees=self.schedule.employees)

            prev_year, prev_month = previous_calendar_month(new_year, new_month)
            predecessor = self.project.get(prev_year, prev_month)
            if PREVIOUS_MONTH_MEMORY_ENABLED and predecessor is not None:
                predecessor_schedule, _ = predecessor
                self._carry_over_previous_month_end_shifts(predecessor_schedule)

            self.project.put(new_year, new_month, self.schedule, self.shop_config)

        self.controller = ScheduleController(self.schedule, self.shop_config)
        self.year, self.month = new_year, new_month
        self._set_date_controls(self.year, self.month)

        self._update_nominal_hours_label()
        self._sync_everything()
        self.statusBar().showMessage(f"Przełączono na {new_month:02d}.{new_year}.", 2500)
        self._loading = False

    def _carry_over_previous_month_end_shifts(self, old_schedule: MonthSchedule) -> None:
        """"Pamięć poprzedniego miesiąca" (patrz PreviousMonthShiftEnd) -
        dla każdego pracownika przejmuje z KOŃCZĄCEGO SIĘ grafiku (przekazany
        jawnie - już niekoniecznie tożsamy z tym, co było aktualnie otwarte
        przed przełączeniem, patrz _switch_to_month) koniec jego ostatniej
        zmiany w ostatnim dniu tamtego miesiąca, żeby generator/rest-constraint
        w nowym miesiącu wiedziały, kiedy naprawdę mieli ostatni odpoczynek
        (patrz logic/generator/rest_constraint.py,
        logic/generator/duty_rotation_rest_constraint.py). Pomija dni puste
        (wolne/urlop/L4) - tam nie ma żadnego "końca" do przejęcia."""
        last_day = old_schedule.days_in_month
        for emp in old_schedule.employees:
            ds = old_schedule.get_day(emp, last_day)
            if ds.is_empty() or ds.end is None:
                continue
            self.schedule.set_previous_month_end_shift(emp, ds.end, ds.crosses_midnight())

    def _previous_month_memory_note(self) -> str | None:
        """Info do okna po udanej generacji, gdy pamięć poprzedniego
        miesiąca (patrz PREVIOUS_MONTH_MEMORY_ENABLED,
        _carry_over_previous_month_end_shifts) jest włączona, ale nie ma
        DANYCH dla ŻADNEGO pracownika tego miesiąca (pierwszy miesiąc
        projektu / skok przez miesiąc bezpośrednio poprzedzający) -
        generator po cichu pomija wtedy sprawdzenie przerwy 11h na
        początku miesiąca względem poprzedniego (patrz
        logic/generator/rest_constraint.py::_add_previous_month_rest_constraint,
        `if carry is None: continue`) - warto to zasygnalizować, zamiast
        zostawiać niezauważone."""
        if not PREVIOUS_MONTH_MEMORY_ENABLED or not self.schedule.employees:
            return None

        has_any_carryover = any(
            self.schedule.get_previous_month_end_shift(emp) is not None
            for emp in self.schedule.employees
        )
        if has_any_carryover:
            return None

        return (
            "Uwaga: brak zapamiętanych godzin zakończenia poprzedniego miesiąca - "
            "przerwa 11h na początku tego miesiąca nie została sprawdzona względem "
            "poprzedniego miesiąca."
        )

    def _open_previous_month_shift_dialog(self):
        dialog = PreviousMonthShiftDialog(self.schedule, self)
        if dialog.exec() == QDialog.Accepted:
            dialog.apply_to_schedule()
            self._sync_everything()

    def _on_generate_clicked(self):
        self._generate_schedule(force=True)

    def _generate_schedule(self, force=True):
        if not self.demo.can_generate(self):
            return

        if not self.schedule.employees:
            QMessageBox.information(self, "Generowanie", "Dodaj pracowników przed generowaniem grafiku.")
            return

        self._show_loading()

        self.thread = QThread()
        self.worker = GeneratorWorker(self.controller, force=force)

        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_generation_finished)

        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    def _on_generation_finished(self, result):
        self._hide_loading()

        self.schedule = self.controller.schedule
        self._sync_everything()

        if result and result.get("success"):
            self.demo.register_generation()
            self._update_generate_label()

            note = self._previous_month_memory_note()
            if self.demo.is_demo:
                self.demo.show_after_generate(self, extra_note=note)
            else:
                message = "Grafik został wygenerowany."
                if note:
                    message += f"\n\n{note}"
                QMessageBox.information(self, "Sukces", message)
        else:
            reasons = result.get("infeasibility_reasons", []) if result else []
            reason_text = "\n".join(f"• {reason}" for reason in reasons)
            QMessageBox.warning(
                self,
                "Nie udało się wygenerować grafiku",
                "Nie znaleziono grafiku spełniającego wszystkie wymagane zasady.\n\n"
                f"Wykryto:\n{reason_text}\n\n"
                "Grafik nie został zmieniony.",
            )

    def _open_add_employee(self):
        dialog = EmployeeDialog(self, shop_config=self.shop_config, default_location_key=self.selected_location_key)

        if dialog.exec() != QDialog.Accepted:
            return

        self.controller.add_employee(dialog.employee_result)
        self.schedule = self.controller.schedule
        self._sync_everything()
        self.statusBar().showMessage("Dodano pracownika.", 2500)

    def _edit_employee(self, emp):
        dialog = EmployeeDialog(self, employee=emp, shop_config=self.shop_config)
        if dialog.exec() != QDialog.Accepted:
            return

        if dialog.employee_result is None:
            self.controller.remove_employee(emp)
            self.schedule = self.controller.schedule
            self._sync_everything()
            self.statusBar().showMessage("Usunięto pracownika.", 2500)
            return

        self.controller.replace_employee(emp, dialog.employee_result)
        self.schedule = self.controller.schedule
        self._sync_everything()
        self.statusBar().showMessage("Zapisano pracownika.", 2500)

    def _edit_day(self, emp, day):
        # Codex review finding on this PR: this read project-wide hours even
        # for an employee assigned to a location with its own, different
        # hours, while night_hours just below was already resolved per
        # location - the dialog validated/bounded a manual entry against the
        # wrong open/close window for such an employee.
        location = self.shop_config.get_location(emp)
        hours = location.get_open_hours_for_day(day)
        if not hours:
            return

        ds = self.controller.get_day(emp, day)
        duty_rotation = location.get_duty_rotation()
        # Pracownik rotacji służby 24/7: dowolne godziny (także przez
        # północ) i zmiana 24h - generator liczy ręczny wpis jako pokrycie.
        # Automatycznie wykryte okno nocne 22:00-06:00 nie jest tu żadną
        # zmianą rotacji, więc nie jest podpowiadane.
        night_hours = None if duty_rotation else location.get_night_shift_hours()
        dialog = DayEditDialog(
            self,
            start=None if ds.is_leave else ds.start,
            end=None if ds.is_leave else ds.end,
            open_start=hours[0],
            open_end=hours[1],
            daily_hours=emp.daily_hours,
            night_hours=night_hours,
            duty_rotation=duty_rotation,
            full_day=bool(getattr(ds, "is_full_day", False)),
        )

        if dialog.exec() != QDialog.Accepted:
            return

        if dialog.result_mode == "free":
            self.controller.set_day_free(emp, day)
        elif dialog.result_mode == "leave":
            self.controller.set_day_leave(emp, day)
        elif dialog.result_mode == "sick":
            self.controller.set_day_sick(emp, day)
        elif dialog.result_mode == "full_day":
            self.controller.set_day_full_day_shift(emp, day, dialog.result_start)
        elif dialog.result_mode == "hours":
            from datetime import datetime

            fmt = "%H:%M"
            try:
                start_dt = datetime.strptime(dialog.result_start, fmt)
                end_dt = datetime.strptime(dialog.result_end, fmt)
            except:
                QMessageBox.warning(self, "Błąd", "Niepoprawny format godziny.")
                return

            is_configured_night_shift = (
                night_hours is not None and (dialog.result_start, dialog.result_end) == night_hours
            )
            if end_dt <= start_dt and not is_configured_night_shift and not duty_rotation:
                QMessageBox.warning(self, "Błąd", "Godzina zakończenia musi być późniejsza niż rozpoczęcia.")
                return

            # Generator już to wykrywa (add_no_night_constraint teraz zna
            # SHIFT_NIGHT) i zgłosi sprzeczność przy generowaniu, jeśli
            # polityka "Zakaz pracy nocnej" jest Wymagana - ale wtedy
            # użytkownik dostaje ogólny komunikat o niespełnialnych
            # regułach, bez wskazania które dnia/pracownika. Ostrzegamy
            # od razu przy zapisie, zamiast wyłącznie po fakcie.
            if is_configured_night_shift and getattr(emp, "no_night", False):
                reply = QMessageBox.question(
                    self,
                    "Zakaz pracy nocnej",
                    f"{emp.display_name()} ma zaznaczony zakaz pracy nocnej. "
                    "Ręczne przypisanie zmiany nocnej może uniemożliwić wygenerowanie "
                    "grafiku (jeśli ta reguła jest ustawiona jako Wymagana) albo zostać "
                    "ukarane jako naruszenie preferencji. Kontynuować mimo to?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    return

            self.controller.set_day_hours(emp, day, dialog.result_start, dialog.result_end)

        self.schedule = self.controller.schedule
        self._sync_everything()
        self.statusBar().showMessage("Zmieniono dzień.", 2500)

    def _open_day_context_menu(self, emp, day, global_pos):
        if not self.shop_config.is_trade_day(day):
            return

        menu = QMenu(self)
        menu.addAction("Rano", lambda: self._ctx_morning(emp, day))
        menu.addAction("Zamknięcie", lambda: self._ctx_close(emp, day))
        menu.addSeparator()
        menu.addAction("Zablokuj: rano (generator dobierze godzinę)", lambda: self._ctx_lock_morning_class(emp, day))
        menu.addAction("Zablokuj: popołudnie (generator dobierze godzinę)", lambda: self._ctx_lock_afternoon_class(emp, day))
        menu.addSeparator()
        menu.addAction("Kopiuj dzień", lambda: self._ctx_copy(emp, day))
        menu.addAction("Wklej dzień", lambda: self._ctx_paste(emp, day))
        menu.addSeparator()
        menu.addAction("Ustaw wolne", lambda: self._ctx_free(emp, day))
        menu.addAction("Ustaw urlop", lambda: self._ctx_leave(emp, day))
        menu.exec(global_pos)

    def _ctx_copy(self, emp, day):
        ds = self.controller.get_day(emp, day)
        if ds.is_empty():
            self._clipboard_day = None
            self.grid.set_clipboard(None)
            return

        self._clipboard_day = {
            "start": ds.start,
            "end": ds.end,
            "is_leave": ds.is_leave,
        }
        self.grid.set_clipboard(self._clipboard_day)
        self.statusBar().showMessage("Skopiowano dzień.", 1800)

    def _ctx_paste(self, emp, day):
        clip = self.grid.clipboard() or self._clipboard_day
        if not clip:
            return

        if clip.get("is_leave"):
            self.controller.set_day_leave(emp, day)
        else:
            self.controller.set_day_hours(emp, day, clip["start"], clip["end"])

        self.schedule = self.controller.schedule
        self._sync_everything()

    def _ctx_free(self, emp, day):
        self.controller.set_day_free(emp, day)
        self.schedule = self.controller.schedule
        self._sync_everything()

    def _ctx_leave(self, emp, day):
        self.controller.set_day_leave(emp, day)
        self.schedule = self.controller.schedule
        self._sync_everything()

    def _ctx_sick(self, emp, day):
        self.controller.set_day_sick(emp, day)
        self.schedule = self.controller.schedule
        self._sync_everything()

    def _ctx_morning(self, emp, day):
        hours = self.shop_config.get_open_hours_for_day(day)
        if not hours:
            return
        start = hours[0]
        end = self._calc_end_from_daily(start, emp.daily_hours)
        self.controller.set_day_hours(emp, day, start, end)
        self.schedule = self.controller.schedule
        self._sync_everything()

    def _ctx_close(self, emp, day):
        hours = self.shop_config.get_open_hours_for_day(day)
        if not hours:
            return
        end = hours[1]
        start = self._calc_start_from_daily(end, emp.daily_hours)
        self.controller.set_day_hours(emp, day, start, end)
        self.schedule = self.controller.schedule
        self._sync_everything()

    def _ctx_lock_morning_class(self, emp, day):
        self.controller.set_shift_class(emp, day, "1")
        self.schedule = self.controller.schedule
        self._sync_everything()

    def _ctx_lock_afternoon_class(self, emp, day):
        self.controller.set_shift_class(emp, day, "2")
        self.schedule = self.controller.schedule
        self._sync_everything()

    def _open_header_menu(self, day, global_pos):
        # Ta kolumna nagłówka jest osadzona w kontekście aktualnie
        # przeglądanej lokalizacji (patrz _sync_grid location_filter) - dzień
        # nadpisany tu musi trafić do JEJ day_overrides/public_holidays, bo
        # to je czyta generator (shop.get_location(emp), patrz
        # model/location.py), a nie projektowe ShopConfig.day_overrides.
        from model.business_profile import get_profile

        location = self.shop_config.locations.get(self.selected_location_key)
        if location is not None:
            uses_trade_calendar = get_profile(self.shop_config.business_type).uses_trade_calendar
            hours = location.get_open_hours_for_day(self.schedule.year, self.schedule.month, day, uses_trade_calendar)
            weekday = location.weekday(self.schedule.year, self.schedule.month, day)
            fallback_hours = location.open_hours.get(weekday)
        else:
            hours = self.shop_config.get_open_hours_for_day(day)
            weekday = self.shop_config.weekday(day)
            fallback_hours = self.shop_config.get_open_hours_for_weekday(weekday)

        # `hours` (None gdy dzień jest faktycznie zamknięty - święto,
        # "Nieczynne" w tygodniu, niedziela niehandlowa) NIE MOŻE tu
        # dostawać fallbacku na zwykłe godziny tygodniowe - dialog musi
        # zobaczyć prawdziwy stan (i sam automatycznie zaznaczyć "Nieczynne
        # tego dnia"), inaczej użytkownik widzi zwykłe godziny, jakby dzień
        # był otwarty. `fallback_hours` to osobna wartość - tylko do
        # podpowiedzi pól czasu, gdyby użytkownik odznaczył "Nieczynne".
        dialog = DayOverrideDialog(self, day, hours or (None, None), self.shop_config, fallback_hours=fallback_hours)
        result = dialog.exec()

        if result != QDialog.Accepted:
            return

        target_overrides = location.day_overrides if location is not None else self.shop_config.day_overrides
        target_holidays = location.public_holidays if location is not None else self.shop_config.public_holidays

        # Undo must restore both the schedule and this day-specific shop setup.
        self.controller.snapshot()
        if dialog.result_mode == "reset":
            target_overrides.pop(day, None)
            target_holidays.discard(day)
        elif dialog.result_mode == "save":
            target_overrides[day] = (dialog.result_start, dialog.result_end)
            if dialog.result_holiday:
                target_holidays.add(day)
            else:
                target_holidays.discard(day)

        self._update_nominal_hours_label()
        self._sync_grid()
        # Nadpisanie godzin/święta to ustawienie (day_overrides/public_holidays),
        # nie dana grafiku - reszta okien ustawień (Konfiguracja, Lokalizacje,
        # tryb szybki) zapisuje się od razu po zamknięciu, więc to też powinno,
        # zamiast czekać na osobne "Zapisz" albo monit przy zamknięciu programu.
        try:
            save_project_bundle("last_project.json", self.project, self.year, self.month)
        except OSError:
            pass
        self.statusBar().showMessage("Zaktualizowano godziny dnia.", 2500)

    def _open_config(self):
        dialog = ConfigDialog(self, self.shop_config, location_key=self.selected_location_key)
        if dialog.exec() != QDialog.Accepted:
            return
        self._update_nominal_hours_label()
        self._sync_grid()
        self._update_quick_panel_profile_visibility()
        # Constraint policies are part of the local working project, so retain
        # the selected generator configuration for the next application start.
        try:
            save_project_bundle("last_project.json", self.project, self.year, self.month)
        except OSError:
            pass
        self.statusBar().showMessage("Zapisano konfigurację.", 2500)

    def _open_locations_dialog(self):
        dialog = LocationsDialog(self, self.shop_config)
        if dialog.exec() != QDialog.Accepted:
            return

        # Lokalizacja usunięta/przemianowana może osierocić pracowników
        # przypisanych do jej starego klucza - dopinamy ich do pierwszej
        # dostępnej, tak samo jak przy wczytywaniu starego pliku.
        assign_missing_location_keys(self.schedule, self.shop_config)
        self._sync_everything()
        try:
            save_project_bundle("last_project.json", self.project, self.year, self.month)
        except OSError:
            pass
        self.statusBar().showMessage("Zapisano lokalizacje.", 2500)

    def _set_hours_display_mode(self, mode: str):
        if self.shop_config is None or self.shop_config.hours_display_mode == mode:
            return
        self.shop_config.hours_display_mode = mode
        self._update_hours_display_menu()
        self.grid.refresh()
        try:
            save_project_bundle("last_project.json", self.project, self.year, self.month)
        except OSError:
            pass
        self.statusBar().showMessage("Zapisano widok trybu szybkiego.", 2500)

    def _update_hours_display_menu(self):
        """Zaznaczenie w menu Wygląd -> "Widok trybu szybkiego" ma zawsze
        odzwierciedlać aktualnie wczytany projekt - wołane z
        _sync_everything(), nie tylko z _set_hours_display_mode()."""
        mode = self.shop_config.hours_display_mode if self.shop_config else "standard"
        self.hours_display_standard_action.setChecked(mode == "standard")
        self.hours_display_fractions_action.setChecked(mode == "fractions")

    def _toggle_grid_legend(self):
        if self.shop_config is None:
            return
        self.shop_config.show_grid_legend = not self.shop_config.show_grid_legend
        self._update_grid_legend()
        try:
            save_project_bundle("last_project.json", self.project, self.year, self.month)
        except OSError:
            pass
        self.statusBar().showMessage(
            "Pokazano legendę kolorów." if self.shop_config.show_grid_legend else "Ukryto legendę kolorów.",
            2500,
        )

    def _open_quick_mode_settings(self):
        dialog = QuickModeSettingsDialog(self, self.shop_config.quick_mode_presets)
        if dialog.exec() != QDialog.Accepted:
            return

        self.shop_config.quick_mode_presets = dialog.result_presets
        self._rebuild_quick_preset_buttons()
        try:
            save_project_bundle("last_project.json", self.project, self.year, self.month)
        except OSError:
            pass
        self.statusBar().showMessage("Zapisano ustawienia trybu szybkiego.", 2500)

    def _save_project(self):

        if self.demo.block_save(self):
            return

        # .myp is the extension the installer registers as this app's file
        # type (see "dla inno.iss"), so double-clicking a saved project opens
        # it here. Older .json saves remain readable, just not the default.
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Zapisz projekt", "",
            "Projekt grafiku (*.myp);;Starszy format JSON (*.json)"
        )
        if not path:
            return

        if not path.lower().endswith((".myp", ".json")):
            path += ".json" if selected_filter.endswith("(*.json)") else ".myp"

        # Cały projekt (patrz model/monthly_project.py) - każdy miesiąc
        # odwiedzony w tej sesji, nie tylko aktualnie otwarty.
        save_project_bundle(path, self.project, self.year, self.month)
        save_project_bundle("last_project.json", self.project, self.year, self.month)
        self.statusBar().showMessage("Zapisano projekt.", 2500)

    def _load_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Wczytaj projekt", "", "Projekt grafiku (*.myp *.json)"
        )
        if not path:
            return

        self._apply_loaded_project(*load_project_bundle(path))
        self.statusBar().showMessage("Wczytano projekt.", 2500)

    def _apply_loaded_project(self, project: MonthlyProject, active_year: int, active_month: int):
        self.project = project
        self.year, self.month = active_year, active_month
        self.schedule, self.shop_config = self.project.get(self.year, self.month)
        self.controller = ScheduleController(self.schedule, self.shop_config)
        self._set_date_controls(self.year, self.month)
        self._update_nominal_hours_label()
        self._sync_everything()

    def _open_project_from_path(self, path) -> bool:
        """Load a project passed on the command line - e.g. Windows launching
        us with a .myp file's path after the user double-clicked it. Returns
        whether a project was actually opened this way."""
        if not path or not os.path.exists(path):
            return False
        try:
            self._apply_loaded_project(*load_project_bundle(path))
        except Exception:
            return False
        self.statusBar().showMessage("Wczytano projekt.", 2500)
        return True

    def _export_excel(self):
        if self.demo.block_export(self):
            return
        path, _ = QFileDialog.getSaveFileName(self, "Eksport Excel", "", "Excel (*.xlsx)")
        if not path:
            return

        export_schedule_to_excel(
            self.schedule, self.year, self.month, path, shop=self.shop_config,
            employees=self.grid.get_visible_employees(),
        )
        self.statusBar().showMessage("Wyeksportowano do Excela.", 2500)

    def _render_visible_schedule_image(self):
        return render_schedule_image(
            self.schedule, self.year, self.month, shop=self.shop_config,
            employees=self.grid.get_visible_employees(),
        )

    def _export_image(self):
        if self.demo.block_export(self):
            return

        image = self._render_visible_schedule_image()
        if not show_export_preview(image, "Podgląd grafiku — JPG", parent=self):
            return

        path, _ = QFileDialog.getSaveFileName(self, "Eksport JPG", "", "Obraz JPG (*.jpg)")
        if not path:
            return

        if not path.lower().endswith(".jpg"):
            path += ".jpg"

        image.save(path, "JPEG", quality=95)
        self.statusBar().showMessage("Wyeksportowano do JPG.", 2500)

    def _export_pdf(self):
        if self.demo.block_export(self):
            return

        image = self._render_visible_schedule_image()
        if not show_export_preview(image, "Podgląd grafiku — PDF", parent=self):
            return

        path, _ = QFileDialog.getSaveFileName(self, "Eksport PDF", "", "PDF (*.pdf)")
        if not path:
            return

        if not path.lower().endswith(".pdf"):
            path += ".pdf"

        image.save(path, "PDF", resolution=150.0)
        self.statusBar().showMessage("Wyeksportowano do PDF.", 2500)

    def _pick_single_employee(self, title):
        # Ograniczone do aktualnie wybranej placówki (patrz przełącznik pod
        # "Grafik na:"), spójnie z tym, co użytkownik widzi w tabeli.
        employees = self.grid.get_visible_employees()
        if not employees:
            QMessageBox.warning(self, title, "Brak pracowników w tej placówce.")
            return None
        names = [emp.display_name() for emp in employees]
        name, ok = QInputDialog.getItem(self, title, "Pracownik:", names, editable=False)
        if not ok:
            return None
        return employees[names.index(name)]

    def _pick_card_scope(self, title):
        """Wybór zakresu dla "Karty pracy": wszyscy pracownicy aktualnie
        wybranej lokalizacji, jeden konkretny pracownik, albo anulowanie
        (None)."""
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText("Czy wygenerować kartę dla całej lokalizacji, czy dla jednego pracownika?")
        btn_all = box.addButton("Cała lokalizacja", QMessageBox.AcceptRole)
        btn_single = box.addButton("Wybierz pracownika...", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()

        clicked = box.clickedButton()
        if clicked is btn_all:
            return "all"
        if clicked is btn_single:
            return "single"
        return None

    def _employee_cards_scope_list(self, title):
        """Zwraca listę pracowników do wygenerowania kart wg wyboru
        użytkownika (cała lokalizacja / jeden pracownik), albo None przy
        anulowaniu/braku pracowników."""
        scope = self._pick_card_scope(title)
        if scope is None:
            return None

        if scope == "all":
            employees = self.grid.get_visible_employees()
            if not employees:
                QMessageBox.warning(self, title, "Brak pracowników w tej placówce.")
                return None
            return employees

        emp = self._pick_single_employee(title)
        if emp is None:
            return None
        return [emp]

    def _export_employee_cards_excel(self):
        if self.demo.block_export(self):
            return
        employees = self._employee_cards_scope_list("Karty pracy — Excel")
        if not employees:
            return

        path, _ = QFileDialog.getSaveFileName(self, "Karty pracy — Excel", "", "Excel (*.xlsx)")
        if not path:
            return

        export_employee_cards_to_excel(self.schedule, self.year, self.month, path, shop=self.shop_config, employees=employees)
        self.statusBar().showMessage("Wyeksportowano karty pracy do Excela.", 2500)

    def _render_employee_card_images(self, employees):
        return [
            render_employee_card_image(self.schedule, self.year, self.month, self.shop_config, emp)
            for emp in employees
        ]

    def _export_employee_cards_image(self):
        if self.demo.block_export(self):
            return
        employees = self._employee_cards_scope_list("Karty pracy — JPG")
        if not employees:
            return

        images = self._render_employee_card_images(employees)
        if not show_export_preview(images, "Podgląd kart pracy — JPG", parent=self):
            return

        if len(employees) == 1:
            emp = employees[0]
            path, _ = QFileDialog.getSaveFileName(self, "Karta pracy — JPG", "", "Obraz JPG (*.jpg)")
            if not path:
                return
            if not path.lower().endswith(".jpg"):
                path += ".jpg"

            images[0].save(path, "JPEG", quality=95)
            self.statusBar().showMessage(f"Wyeksportowano kartę pracy {emp.display_name()} do JPG.", 2500)
            return

        folder = QFileDialog.getExistingDirectory(self, "Karty pracy — folder docelowy")
        if not folder:
            return

        for emp, image in zip(employees, images):
            name_part = sanitize_filename_part(f"{emp.last_name}_{emp.first_name}")
            path = os.path.join(folder, f"Karta_pracy_{name_part}_{self.month:02d}_{self.year}.jpg")
            image.save(path, "JPEG", quality=95)

        self.statusBar().showMessage(f"Wyeksportowano {len(employees)} kart pracy do JPG.", 2500)

    def _export_employee_cards_pdf(self):
        if self.demo.block_export(self):
            return
        employees = self._employee_cards_scope_list("Karty pracy — PDF")
        if not employees:
            return

        images = self._render_employee_card_images(employees)
        if not show_export_preview(images, "Podgląd kart pracy — PDF", parent=self):
            return

        # Jeden dokument PDF niezależnie od liczby pracowników - jedna
        # strona na pracownika (patrz save_employee_card_pages_to_pdf), więc
        # w przeciwieństwie do JPG nie ma tu potrzeby wyboru folderu.
        path, _ = QFileDialog.getSaveFileName(self, "Karty pracy — PDF", "", "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"

        save_employee_card_pages_to_pdf(images, path)
        self.statusBar().showMessage(f"Wyeksportowano {len(employees)} kart(y) pracy do PDF.", 2500)

    def _update_generate_label(self):
        remaining = self.demo.get_remaining_generations()

        if remaining is None:
            self.generate_limit_label.setText("")
            return

        self.generate_limit_label.setText(f"Pozostało generacji: {remaining}")

    def _print_schedule(self):
        if self.demo.block_export(self):
            return

        if not self.schedule:
            QMessageBox.warning(self, "Drukowanie", "Brak grafiku do wydruku.")
            return

        try:
            import tempfile
            from PySide6.QtGui import QPageLayout

            # 1. generujemy obraz
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            temp_path = temp_file.name
            temp_file.close()

            self._render_visible_schedule_image().save(temp_path, "JPEG", quality=95)

            # 2. printer
            printer = QPrinter(QPrinter.HighResolution)
            printer.setPageOrientation(QPageLayout.Landscape)

            # 3. preview (czysty — bez styli)
            preview = QPrintPreviewDialog(printer, self)
            preview.setStyleSheet("")

            # 4. render
            def render(printer):
                painter = QPainter(printer)

                image = QImage(temp_path)
                if image.isNull():
                    painter.end()
                    return

                rect = painter.viewport()
                size = image.size()
                size.scale(rect.size(), Qt.KeepAspectRatio)

                painter.setViewport(rect.x(), rect.y(), size.width(), size.height())
                painter.setWindow(image.rect())

                painter.drawImage(0, 0, image)
                painter.end()

            preview.paintRequested.connect(render)

            # 5. odpal preview
            preview.exec()

        except Exception as e:
            QMessageBox.critical(self, "Błąd drukowania", str(e))

    def _undo(self):
        self.schedule = self.controller.undo()
        self.shop_config = self.controller.shop_config
        self._sync_everything()
        self.statusBar().showMessage("Cofnięto ostatnią zmianę.", 2500)

    def _redo(self):
        self.schedule = self.controller.redo()
        self.shop_config = self.controller.shop_config
        self._sync_everything()
        self.statusBar().showMessage("Ponowiono zmianę.", 2500)

    def _clear_schedule(self):
        if not self.schedule or not self.controller:
            return

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

        self.schedule.settlement_targets.clear()

        self._sync_everything()
        self.statusBar().showMessage("Wyczyszczono grafik.", 2500)

    def _about(self):
        from PySide6.QtWidgets import QMessageBox
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl, Qt

        msg = QMessageBox(self)
        msg.setWindowTitle("O programie")

        msg.setText(
            "<b>Grafik pracy</b><br><br>"
            "Nowoczesne narzędzie do tworzenia grafików pracy.<br><br>"
            f"<b>Wersja:</b> {APP_VERSION}<br><br>"
            "Strona: madebykewin.pl"
        )

        msg.setTextFormat(Qt.RichText)
        msg.setTextInteractionFlags(Qt.TextBrowserInteraction)

        btn_open = msg.addButton("Kontakt", QMessageBox.ActionRole)
        msg.addButton("Zamknij", QMessageBox.RejectRole)

        msg.exec()

        if msg.clickedButton() == btn_open:
            QDesktopServices.openUrl(QUrl("https://madebykewin.pl"))

    def _try_load_last_project(self) -> bool:
        """Returns whether a previously-saved project was actually loaded -
        used at startup to tell a genuinely fresh install (see
        _maybe_show_first_run_wizard) from a normal relaunch."""
        if not os.path.exists("last_project.json"):
            return False

        try:
            self._apply_loaded_project(*load_project_bundle("last_project.json"))
        except Exception:
            return False
        return True

    def _toggle_expanded_view(self, checked):
        self.grid.set_compact_mode(not checked)
        self.btn_expand_view.setText("Zwiń widok" if checked else "Rozszerz widok")
        self.statusBar().showMessage(
            "Widok rozszerzony włączony." if checked else "Widok kompaktowy włączony.",
            2000
        )


    def _toggle_settlement_mode(self):
        self.settlement_mode_active = self.btn_settlement_toggle.isChecked()
        self.btn_settlement_toggle.setText(
            "Wyłącz okres rozliczeniowy" if self.settlement_mode_active else "Włącz okres rozliczeniowy"
        )
        self.settlement_info_label.setVisible(self.settlement_mode_active)
        self.btn_settlement_balance.setVisible(self.settlement_mode_active)
        self.btn_generate.setEnabled(not self.settlement_mode_active)
        self.grid.set_settlement_mode(self.settlement_mode_active)

    def _on_balance_hours_clicked(self):
        if not self.schedule.settlement_targets:
            QMessageBox.information(
                self,
                "Okres rozliczeniowy",
                "Wpisz najpierw docelową liczbę godzin przynajmniej jednemu "
                "pracownikowi (dwuklik w kolumnie \"Cel\").",
            )
            return

        self.controller.snapshot()
        self._show_loading()

        self.settlement_thread = QThread()
        self.settlement_worker = SettlementBalanceWorker(self.schedule, self.shop_config)
        self.settlement_worker.moveToThread(self.settlement_thread)

        self.settlement_thread.started.connect(self.settlement_worker.run)
        self.settlement_worker.finished.connect(self._on_settlement_balance_finished)
        self.settlement_worker.finished.connect(self.settlement_thread.quit)
        self.settlement_worker.finished.connect(self.settlement_worker.deleteLater)
        self.settlement_thread.finished.connect(self.settlement_thread.deleteLater)

        self.settlement_thread.start()

    def _on_settlement_balance_finished(self, result):
        self._hide_loading()
        self._sync_everything()

        employees = result.get("employees", [])
        if not employees:
            return

        lines = []
        for entry in employees:
            if entry["reached_target"]:
                status = "cel osiągnięty"
            else:
                status = f"pozostało {entry['remaining_delta']} min do celu"
            lines.append(f"{entry['employee']}: {status}")

        QMessageBox.information(self, "Wyrównano godziny", "\n".join(lines))

    def _toggle_quick_mode(self):
        self.quick_mode_enabled = self.btn_quick_mode.isChecked()
        self._update_quick_mode_ui()

    def _update_quick_mode_ui(self):
        if self.quick_mode_enabled:
            self.quick_panel.show()
        else:
            self.quick_panel.hide()

    def _set_quick_shift(self, shift_type):
        self.quick_duration_label.setText("Czas pracy: 0:00")
        self._quick_manual_end = False
        self.quick_selected_shift = shift_type

        # reset
        self.btn_work.setChecked(False)
        self.btn_morning.setChecked(False)
        self.btn_afternoon.setChecked(False)
        self.btn_off.setChecked(False)
        self.btn_leave.setChecked(False)
        self.btn_sick.setChecked(False)
        for btn in self.quick_preset_buttons.values():
            btn.setChecked(False)

        # Wyszarzone zamiast ukryte, żeby reszta panelu bocznego nie
        # "przeskakiwała" przy każdej zmianie typu zmiany w trybie szybkim.
        is_work = shift_type == "WORK"
        self.time_panel.setEnabled(is_work)
        self.quick_duration_label.setEnabled(is_work)

        # aktywny
        if shift_type == "WORK":
            self.btn_work.setChecked(True)
        elif shift_type == "MORNING_CLASS":
            self.btn_morning.setChecked(True)
        elif shift_type == "AFTERNOON_CLASS":
            self.btn_afternoon.setChecked(True)
        elif shift_type == "OFF":
            self.btn_off.setChecked(True)
        elif shift_type == "LEAVE":
            self.btn_leave.setChecked(True)
        elif shift_type == "SICK":
            self.btn_sick.setChecked(True)
        elif shift_type.startswith("PRESET:"):
            btn = self.quick_preset_buttons.get(shift_type.split(":", 1)[1])
            if btn:
                btn.setChecked(True)

    def _rebuild_quick_preset_buttons(self):
        while self.quick_presets_grid.count():
            item = self.quick_presets_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        self.quick_preset_buttons = {}

        presets = self.shop_config.quick_mode_presets if self.shop_config else []
        # "visible" (patrz model/shop_config.py::normalize_quick_mode_presets)
        # pozwala trzymać przygotowane przedziały bez pokazywania ich jako
        # przycisk - odfiltrowane tu, więc nieaktywne nie zajmują miejsca
        # w gridzie ani nie liczą się do decyzji, czy pokazać cały panel.
        visible_presets = [p for p in presets if p.get("visible", True)]
        self.quick_presets_label.setVisible(bool(visible_presets))

        for index, preset in enumerate(visible_presets):
            name = preset["name"]
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setObjectName("secondaryButton")
            btn.setMinimumHeight(36)
            if preset.get("full_day"):
                btn.setToolTip(f"Cała doba (24h), start {preset['start']}.")
            else:
                btn.setToolTip(f"{preset['start']}–{preset['end']}")
            shift_type = f"PRESET:{name}"
            btn.clicked.connect(lambda _checked=False, st=shift_type: self._set_quick_shift(st))
            self.quick_preset_buttons[name] = btn
            row, col = divmod(index, 3)
            self.quick_presets_grid.addWidget(btn, row, col)

        # Wybrany wcześniej przedział mógł zostać usunięty/przemianowany w
        # "Ustawieniach trybu szybkiego" - nie zostawiamy generatora trybu
        # szybkiego wskazującego na już nieistniejący przycisk.
        if (
            isinstance(self.quick_selected_shift, str)
            and self.quick_selected_shift.startswith("PRESET:")
            and self.quick_selected_shift.split(":", 1)[1] not in self.quick_preset_buttons
        ):
            self.quick_selected_shift = None

    def _calc_end_from_daily(self, start_str, hours):
        from datetime import datetime, timedelta
        fmt = "%H:%M"
        start = datetime.strptime(start_str, fmt)
        end = start + timedelta(hours=hours)
        return end.strftime(fmt)

    def _calc_start_from_daily(self, end_str, hours):
        from datetime import datetime, timedelta
        fmt = "%H:%M"
        end = datetime.strptime(end_str, fmt)
        start = end - timedelta(hours=hours)
        return start.strftime(fmt)

    def _build_tutorial_steps(self):
        return [
            TutorialStep(
                "Witaj!",
                "Program służy do tworzenia grafików pracy.\n"
                "Możesz generować grafik automatycznie albo układać go ręcznie.",
            ),
            TutorialStep(
                "Dodaj pracowników",
                "Tutaj dodajesz pracowników i ustawiasz ich dane: wymiar etatu, "
                "godziny dzienne oraz role.",
                target=self.btn_add_employee,
            ),
            TutorialStep(
                "Generowanie grafiku",
                "Program ułoży grafik automatycznie, uwzględniając wszystkie "
                "ograniczenia. Nigdy nie nadpisuje zmian wprowadzonych ręcznie.",
                target=self.btn_generate,
            ),
            TutorialStep(
                "Edycja ręczna",
                "Kliknij dwukrotnie komórkę w siatce, żeby ręcznie ustawić "
                "godziny pracy, dzień wolny albo urlop.",
                target=self.grid,
            ),
            TutorialStep(
                "Kopiuj / wklej dzień",
                "Zaznacz dzień pracownika, wciśnij Ctrl+C, a potem Ctrl+V na "
                "innym dniu, żeby skopiować cały jego stan - działa też dla "
                "urlopu, L4, zmiany nocnej i zmiany 24h.",
                target=self.grid,
            ),
            TutorialStep(
                "Ikony przy pracowniku",
                "Ikony obok nazwiska pracownika pokazują jego role: dokument - "
                "priorytet „Umowa” w rozliczaniu godzin, przekreślone „24h” - "
                "pracownik nie chce pojedynczych zmian 24h przy rotacji służby.",
                target=self.grid,
            ),
            TutorialStep(
                "Tryb szybki",
                "Najszybszy sposób na ręczne zmiany: wybierz typ zmiany, ustaw "
                "godziny i klikaj kolejne komórki w siatce. Przyciskiem "
                "„+ Dodaj własne...” zdefiniujesz własne, nazwane przedziały "
                "czasowe.",
                target=self.btn_quick_mode,
            ),
            TutorialStep(
                "Rozszerz widok",
                "Przełącza między pełnym widokiem grafiku a kompaktowym, "
                "czytelnym jak kartka papieru.",
                target=self.btn_expand_view,
            ),
            TutorialStep(
                "Gotowe!",
                "Dodaj pracowników, wygeneruj grafik, popraw ręcznie jeśli trzeba.\n"
                "W każdej chwili wrócisz tu przez Pomoc → Samouczek.",
            ),
        ]

    def _start_tutorial(self, on_finished=None):
        existing = getattr(self, "_tutorial_overlay", None)
        if existing is not None:
            existing.deleteLater()
        self._tutorial_overlay = TutorialOverlay(self, self._build_tutorial_steps(), on_finished=on_finished)
        self._tutorial_overlay.start()

    def _open_tutorial(self):
        self._start_tutorial()

    def _show_loading(self):
        self.loading_overlay.show_overlay()
        QApplication.processEvents()

    def _hide_loading(self):
        self.loading_overlay.hide_overlay()


    def _ctx_sick(self, emp, day):
        self.controller.set_day_sick(emp, day)
        self.schedule = self.controller.schedule
        self._sync_everything()

    def _quick_on_start_changed(self, _):
        if not self._quick_manual_end:
            self._quick_suggest_end()
        self._quick_update_duration()


    def _quick_on_end_changed(self, _):
        self._quick_manual_end = True
        self._quick_update_duration()


    def _quick_suggest_end(self):
        from datetime import datetime, timedelta

        fmt = "%H:%M"

        try:
            start = datetime.strptime(self.start_input.get_time_str(), fmt)
        except:
            return

        hours = 8  # możesz potem podpiąć pod pracownika

        end = start + timedelta(hours=hours)

        self.end_input.input.blockSignals(True)
        self.end_input.set_time_str(end.strftime(fmt))
        self.end_input.input.blockSignals(False)


    def _quick_update_duration(self):
        from datetime import datetime

        fmt = "%H:%M"

        try:
            start = datetime.strptime(self.start_input.get_time_str(), fmt)
            end = datetime.strptime(self.end_input.get_time_str(), fmt)
        except:
            self.quick_duration_label.setText(f"Czas pracy: {h}:{m:02d}")
            return

        minutes = int((end - start).total_seconds() / 60)
        if minutes < 0:
            minutes = 0

        h = minutes // 60
        m = minutes % 60

        self.quick_duration_label.setText(f"Czas pracy: {h}:{m:02d}")

    def closeEvent(self, event):
        msg = QMessageBox(self)
        msg.setWindowTitle("Zamknij program")
        msg.setText("Czy chcesz zapisać projekt przed wyjściem?")

        btn_yes = msg.addButton("Zapisz", QMessageBox.AcceptRole)
        btn_no = msg.addButton("Nie zapisuj", QMessageBox.DestructiveRole)
        btn_cancel = msg.addButton("Anuluj", QMessageBox.RejectRole)

        msg.setDefaultButton(btn_yes)

        msg.exec()

        clicked = msg.clickedButton()

        if clicked == btn_yes:
            if self.demo.block_save(self):
                event.ignore()
                return

            try:
                save_project_bundle("last_project.json", self.project, self.year, self.month)
            except:
                pass

            event.accept()

        elif clicked == btn_no:
            event.accept()

        else:
            event.ignore()

    def _check_first_run(self):
        flag_path = "first_run.flag"

        if os.path.exists(flag_path):
            return

        def mark_seen():
            try:
                with open(flag_path, "w") as f:
                    f.write("seen")
            except OSError:
                pass

        # Placówkę konfigurujemy tylko gdy naprawdę nie ma jeszcze żadnego
        # zapisanego projektu (świeży instal) - _init_state() w __init__
        # zawsze tworzy w pamięci pusty, domyślny dino_retail, więc
        # self.schedule tu nigdy nie jest None; prawdziwy sygnał "świeży
        # instal" to _opened_existing_project ustawione w __init__. Poradnik
        # zawsze zamyka tę sekwencję, po kreatorze albo od razu, jeśli
        # kreatora nie było czego pokazywać.
        if not self._opened_existing_project:
            self._maybe_show_first_run_wizard(
                on_finished=lambda: self._start_tutorial(on_finished=mark_seen)
            )
        else:
            self._start_tutorial(on_finished=mark_seen)

    def _maybe_show_first_run_wizard(self, on_finished):
        from ui.first_run_wizard import FirstRunWizardDialog

        wizard = FirstRunWizardDialog(self)
        wizard.exec()
        if wizard.completed:
            self._apply_first_run_wizard_result(wizard)
        on_finished()

    def _apply_first_run_wizard_result(self, wizard):
        self.year = wizard.result_year
        self.month = wizard.result_month
        self._set_date_controls(self.year, self.month)

        self.schedule = None
        self._init_state()
        self.shop_config.name = wizard.result_name
        self.shop_config.business_type = wizard.result_business_type

        from model.business_profile import get_custom_profile
        custom = get_custom_profile(wizard.result_business_type)
        if custom is not None:
            from logic.generator.custom_profile_wiring import default_policies
            self.shop_config.constraint_policies.update(default_policies(custom))
        self.shop_config.constraint_policies.update(wizard.result_policy_overrides)

        self._update_nominal_hours_label()
        self._sync_everything()
        save_project_bundle("last_project.json", self.project, self.year, self.month)
        self.statusBar().showMessage("Utworzono placówkę.", 2500)

    def _clear_generated(self):
        if not self.schedule or not self.controller:
            return

        reply = QMessageBox.question(
            self,
            "Potwierdzenie",
            "Usunąć tylko zmiany wygenerowane automatycznie?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        self.controller.snapshot()

        for emp in self.schedule.employees:
            for day in range(1, self.schedule.days_in_month + 1):
                ds = self.schedule.get_day(emp, day)

                if ds.is_locked:
                    continue

                ds.start = None
                ds.end = None
                ds.is_leave = False
                ds.is_sick = False

                if hasattr(ds, "is_day_off"):
                    ds.is_day_off = False

        self._sync_everything()
        self.statusBar().showMessage("Usunięto wygenerowane zmiany.", 2500)

    def _check_updates(self, manual=False):
        from update_checker import check_for_updates

        result = check_for_updates()

        if not result.get("available"):
            if manual:
                if result.get("error"):
                    QMessageBox.warning(
                        self,
                        "Sprawdzanie aktualizacji",
                        f"Nie udało się sprawdzić dostępności aktualizacji.\n\n{result['error']}",
                    )
                else:
                    QMessageBox.information(
                        self,
                        "Sprawdzanie aktualizacji",
                        "Masz już najnowszą wersję programu.",
                    )
            return

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Question)
        msg.setWindowTitle("Dostępna aktualizacja")
        msg.setText(
            f"Dostępna jest nowa wersja programu ({result['version']}).\n\nPobrać i zainstalować?"
        )
        # Opis wydania z GitHub Releases (jeśli autor go wypełnił) pokazuje się
        # od razu pod treścią pytania. setDetailedText() dawałby rozwijany
        # przycisk, ale Qt sam zarządza jego stanem/tekstem i przy próbie
        # spolszczenia go w locie potrafi zostawić na przycisku wizualnie
        # uszkodzony tekst (nakładka starego i nowego renderu) — nie warto
        # tego obchodzić dla czegoś, co i tak zwykle ma kilka linijek.
        notes = result.get("notes")
        if notes:
            msg.setInformativeText(notes)

        btn_yes = msg.addButton("Tak", QMessageBox.YesRole)
        msg.addButton("Nie", QMessageBox.NoRole)
        msg.setDefaultButton(btn_yes)

        msg.exec()

        if msg.clickedButton() == btn_yes:
            self._start_update_download(result["url"])

    def _start_update_download(self, url):
        self.update_progress_dialog = QProgressDialog("Łączenie z serwerem aktualizacji...", "Anuluj", 0, 100, self)
        self.update_progress_dialog.setWindowTitle("Aktualizacja programu")
        self.update_progress_dialog.setWindowModality(Qt.WindowModal)
        self.update_progress_dialog.setMinimumDuration(0)
        self.update_progress_dialog.setAutoClose(False)
        self.update_progress_dialog.setAutoReset(False)
        self.update_progress_dialog.setMinimum(0)
        self.update_progress_dialog.setMaximum(0)  # tryb nieokreślony, dopóki nie znamy rozmiaru pliku
        self.update_progress_dialog.setValue(0)

        self.update_thread = QThread()
        self.update_worker = UpdateDownloadWorker(url)
        self.update_worker.moveToThread(self.update_thread)

        # Uwaga: sygnały MUSZĄ być podpięte do metod związanych z self (QObject
        # żyjącym w wątku głównym), nie do lokalnych domknięć — inaczej Qt
        # wywołuje je bezpośrednio w wątku roboczym (brak automatycznego
        # queued connection dla zwykłych funkcji), co dotyka widgetów spoza
        # wątku GUI i zawiesza aplikację.
        self.update_thread.started.connect(self.update_worker.run)
        self.update_worker.progress.connect(self._on_update_progress)
        self.update_worker.finished.connect(self._on_update_download_finished)
        self.update_worker.finished.connect(self.update_thread.quit)
        self.update_worker.finished.connect(self.update_worker.deleteLater)
        self.update_thread.finished.connect(self.update_thread.deleteLater)
        self.update_progress_dialog.canceled.connect(self.update_thread.requestInterruption)

        self.update_thread.start()
        self.update_progress_dialog.exec()

    def _on_update_progress(self, downloaded, total):
        downloaded_mb = downloaded / (1024 * 1024)

        if total > 0:
            total_mb = total / (1024 * 1024)
            percent = int(downloaded * 100 / total)
            self.update_progress_dialog.setMaximum(100)
            self.update_progress_dialog.setValue(percent)
            self.update_progress_dialog.setLabelText(
                f"Pobieranie aktualizacji... {percent}%\n"
                f"{downloaded_mb:.1f} MB z {total_mb:.1f} MB"
            )
        else:
            # serwer nie podał rozmiaru pliku — pokaż sam postęp w MB
            self.update_progress_dialog.setMaximum(0)
            self.update_progress_dialog.setLabelText(
                f"Pobieranie aktualizacji...\n{downloaded_mb:.1f} MB pobrane"
            )

    def _on_update_download_finished(self, path, error):
        self.update_thread.quit()

        if error:
            self.update_progress_dialog.close()
            QMessageBox.warning(
                self,
                "Aktualizacja",
                f"Nie udało się pobrać aktualizacji.\n\n{error}",
            )
            return

        if not path:
            self.update_progress_dialog.close()
            return  # anulowane przez użytkownika

        # Krótka, czytelna informacja przed zamknięciem programu, żeby
        # użytkownik wiedział co się dzieje zamiast nagle widzieć zniknięcie okna.
        self.update_progress_dialog.setCancelButton(None)
        self.update_progress_dialog.setLabelText(
            "Pobrano aktualizację.\nUruchamiam instalator, program zaraz się zamknie..."
        )
        self.update_progress_dialog.setMaximum(1)
        self.update_progress_dialog.setValue(1)

        QTimer.singleShot(1200, lambda: self._finish_update_install(path))

    def _finish_update_install(self, path):
        self.update_progress_dialog.close()
        self._launch_installer_and_quit(path)

    def _launch_installer_and_quit(self, installer_path):
        try:
            # Instalator (Inno Setup) wymaga uprawnień administratora
            # (domyślne PrivilegesRequired=admin), więc trzeba go uruchomić
            # przez ShellExecute (os.startfile), żeby Windows pokazał prompt
            # UAC. subprocess.Popen woła CreateProcess bezpośrednio, które
            # nie potrafi podnieść uprawnień i kończy się błędem/brakiem
            # efektu — dla użytkownika wyglądało to jak zawieszenie programu.
            os.startfile(installer_path)
        except OSError as e:
            QMessageBox.warning(
                self,
                "Aktualizacja",
                f"Nie udało się uruchomić instalatora.\n\n{e}",
            )
            return

        self.close()
