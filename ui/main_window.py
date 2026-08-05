import os
from datetime import date

from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer, QUrl
from PySide6.QtGui import QPainter, QColor, QImage, QDesktopServices
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
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QDialog,
)

from export.excel_exporter import export_schedule_to_excel
from export.image_exporter import export_schedule_to_image
from logic.schedule_controller import ScheduleController
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from persistence.project_io import load_project, save_project
from ui.config_dialog import ConfigDialog
from ui.day_edit_dialog import DayEditDialog
from ui.day_override_dialog import DayOverrideDialog
from ui.employee_dialog import EmployeeDialog
from ui.grid_view import ScheduleGrid
from ui.time_input import TimeInputWidget
from ui.tutorial_dialog import TutorialDialog
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

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        QTimer.singleShot(1000, self._check_updates)

        from ui.license_manager import load_license, validate_license

        self.user_id = get_user_id()
        self.demo = DemoManager()

        saved_key = load_license()
        if saved_key and validate_license(self.user_id, saved_key):
            self.demo.is_demo = False

        self.setWindowTitle("Grafik Dino v2")
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

        self._build_quick_panel()
        self._build_ui()
        self._init_state()
        self._sync_everything()
        self._try_load_last_project()
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
        panel = QFrame()
        panel.setObjectName("panelCard")
        panel.setMinimumWidth(300)
        panel.setMaximumWidth(360)

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
        self.btn_change_date.setStyleSheet("color: #0078d4; text-align: left; background: transparent; border: none; text-decoration: underline;")
        self.btn_change_date.setCursor(Qt.PointingHandCursor)
        self.btn_change_date.setFixedWidth(120)
        self.btn_change_date.clicked.connect(self._enter_edit_date_mode)

        hero_layout.addWidget(self.btn_change_date)

        # Widget dla trybu edycji daty
        self.date_edit_widget = QWidget()
        self.date_edit_widget.hide()
        date_edit_layout = QVBoxLayout(self.date_edit_widget)
        date_edit_layout.setContentsMargins(0, 0, 0, 0)

        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("Miesiąc"))
        self.month_spin = QSpinBox()
        self.month_spin.setRange(1, 12)
        self.month_spin.setValue(self.month)
        date_row.addWidget(self.month_spin)

        date_row.addWidget(QLabel("Rok"))
        self.year_spin = QSpinBox()
        self.year_spin.setRange(2024, 2035)
        self.year_spin.setValue(self.year)
        date_row.addWidget(self.year_spin)
        
        self.btn_save_date = QPushButton("Zapisz")
        self.btn_save_date.setObjectName("primaryButton")
        self.btn_save_date.clicked.connect(self._save_date_clicked)
        self.btn_save_date.setMinimumHeight(30)
        date_row.addWidget(self.btn_save_date)

        date_edit_layout.addLayout(date_row)
        hero_layout.addWidget(self.date_edit_widget)

        layout.addWidget(hero)

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
        self.generate_limit_label.setStyleSheet("color: #777; font-size: 11px;")
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

        layout.addStretch(1)

        if self.demo.is_demo:
            self._add_section_divider(layout)
            self.demo_label = QLabel("Wersja demonstracyjna")
            self.demo_label.setStyleSheet("color: #d9534f; font-size: 11px; font-weight: bold;")
            layout.addWidget(self.demo_label)

            self.btn_buy = QPushButton("Zakup pełną wersję")
            self.btn_buy.setStyleSheet("""
                QPushButton {
                    background-color: #28a745;
                    color: white;
                    font-weight: bold;
                    border: none;
                    padding: 6px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #218838;
                }
            """)
            self.btn_buy.clicked.connect(self._open_buy_page)
            layout.addWidget(self.btn_buy)

        self.user_id_label = QLabel(f"ID użytkownika: {self.user_id}")
        self.user_id_label.setStyleSheet("color: #777; font-size: 11px;")
        layout.addWidget(self.user_id_label)

        self.version_label = QLabel(f"Wersja: {APP_VERSION}")
        self.version_label.setStyleSheet("color: #777; font-size: 11px;")
        layout.addWidget(self.version_label)

        return panel

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
        self.quick_info_label.setStyleSheet("color: #555; font-size: 11px; font-style: italic;")
        layout.addWidget(self.quick_info_label)

        # --- przyciski: siatka 2x3 (Praca/Rano/Popo, Wolne/Urlop/L4) ---
        btn_grid = QGridLayout()
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

        btn_grid.addWidget(self.btn_work, 0, 0)
        btn_grid.addWidget(self.btn_morning, 0, 1)
        btn_grid.addWidget(self.btn_afternoon, 0, 2)
        btn_grid.addWidget(self.btn_off, 1, 0)
        btn_grid.addWidget(self.btn_leave, 1, 1)
        btn_grid.addWidget(self.btn_sick, 1, 2)

        layout.addLayout(btn_grid)

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
        self.time_panel.hide()

        layout.addWidget(self.time_panel)

        self.quick_duration_label = QLabel("Czas pracy: 0:00")
        self.quick_duration_label.setObjectName("metricValue")
        self.quick_duration_label.hide()
        layout.addWidget(self.quick_duration_label)

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

        self.grid = ScheduleGrid()
        self.grid.compact_mode = True
        layout.addWidget(self.grid, 1)

        return panel

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("Plik")
        edit_menu = self.menuBar().addMenu("Edycja")
        config_menu = self.menuBar().addMenu("Konfiguracja")
        help_menu = self.menuBar().addMenu("Pomoc")

        help_menu.addAction("Samouczek", self._open_tutorial)

        file_menu.addAction("Zapisz", self._save_project)
        file_menu.addAction("Wczytaj", self._load_project)

        export_menu = QMenu("Eksport", self)
        export_menu.addAction("Excel", self._export_excel)
        export_menu.addAction("JPG", self._export_image)
        file_menu.addMenu(export_menu)

        file_menu.addSeparator()
        file_menu.addAction("Drukuj...", self._print_schedule)

        file_menu.addSeparator()
        file_menu.addAction("Zamknij", self.close)

        edit_menu.addAction("Cofnij", self._undo)
        edit_menu.addAction("Ponów", self._redo)

        edit_menu.addSeparator()
        edit_menu.addAction("Wyczyść grafik", self._clear_schedule)
        edit_menu.addAction("Wyczyść auto", self._clear_generated)

        config_menu.addAction("Generator", self._open_config)

        help_menu.addAction("Klucz produktu", self._open_license_dialog)
        help_menu.addAction("Sprawdź aktualizacje", lambda: self._check_updates(manual=True))
        help_menu.addAction("O programie", self._about)

    def _init_state(self):
        old_employees = []

        if self.schedule:
            old_employees = self.schedule.employees

        self.schedule = MonthSchedule(self.year, self.month, employees=old_employees)
        self.shop_config = ShopConfig(self.year, self.month)
        self.controller = ScheduleController(self.schedule, self.shop_config)

    def _sync_everything(self):
        self._sync_grid()
        self._update_window_title()
        self._update_state_label()
        self._update_generate_label()


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
        )
        self.grid.build()
        self.grid.refresh()

    def _update_window_title(self):
        self.setWindowTitle(f"Grafik Dino — {self.month:02d}.{self.year}")

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
        self._loading = True
        self.year_spin.blockSignals(True)
        self.month_spin.blockSignals(True)
        self.year_spin.setValue(year)
        self.month_spin.setValue(month)
        if hasattr(self, 'date_display_label'):
            self.date_display_label.setText(f"{month:02d}.{year}")
        self.year_spin.blockSignals(False)
        self.month_spin.blockSignals(False)
        self._loading = False

    def _enter_edit_date_mode(self):
        self.date_display_label.hide()
        self.btn_change_date.hide()
        self.date_edit_widget.show()

    def _save_date_clicked(self):
        new_year = self.year_spin.value()
        new_month = self.month_spin.value()
        
        if new_year == self.year and new_month == self.month:
            self.date_edit_widget.hide()
            self.date_display_label.show()
            self.btn_change_date.show()
            return

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Zmiana miesiąca")
        msg_box.setText("Zmiana miesiąca spowoduje usunięcie wszystkich zmian wprowadzonych na grafiku. Kontynuować?")
        btn_yes = msg_box.addButton("Tak", QMessageBox.YesRole)
        btn_cancel = msg_box.addButton("Anuluj", QMessageBox.RejectRole)
        msg_box.exec()

        if msg_box.clickedButton() == btn_yes:
            self._loading = True
            self.year = new_year
            self.month = new_month
            self.date_display_label.setText(f"{self.month:02d}.{self.year}")
            
            self._init_state()
            self._update_nominal_hours_label()
            self._sync_everything()
            self.statusBar().showMessage("Utworzono nowy grafik dla wybranego miesiąca.", 2500)
            
            self.date_edit_widget.hide()
            self.date_display_label.show()
            self.btn_change_date.show()
            self._loading = False
        else:
            self._set_date_controls(self.year, self.month)
            self.date_edit_widget.hide()
            self.date_display_label.show()
            self.btn_change_date.show()

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

            if self.demo.is_demo:
                self.demo.show_after_generate(self)
            else:
                QMessageBox.information(self, "Sukces", "Grafik został wygenerowany.")
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
        dialog = EmployeeDialog(self)

        if dialog.exec() != QDialog.Accepted:
            return

        self.controller.add_employee(dialog.employee_result)
        self.schedule = self.controller.schedule
        self._sync_everything()
        self.statusBar().showMessage("Dodano pracownika.", 2500)

    def _edit_employee(self, emp):
        dialog = EmployeeDialog(self, employee=emp)
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
        hours = self.shop_config.get_open_hours_for_day(day)
        if not hours:
            return

        ds = self.controller.get_day(emp, day)
        dialog = DayEditDialog(
            self,
            start=None if ds.is_leave else ds.start,
            end=None if ds.is_leave else ds.end,
            open_start=hours[0],
            open_end=hours[1],
            daily_hours=emp.daily_hours,
        )

        if dialog.exec() != QDialog.Accepted:
            return

        if dialog.result_mode == "free":
            self.controller.set_day_free(emp, day)
        elif dialog.result_mode == "leave":
            self.controller.set_day_leave(emp, day)
        elif dialog.result_mode == "sick":
            self.controller.set_day_sick(emp, day)
        elif dialog.result_mode == "hours":
            from datetime import datetime

            fmt = "%H:%M"
            try:
                start_dt = datetime.strptime(dialog.result_start, fmt)
                end_dt = datetime.strptime(dialog.result_end, fmt)
            except:
                QMessageBox.warning(self, "Błąd", "Niepoprawny format godziny.")
                return

            if end_dt <= start_dt:
                QMessageBox.warning(self, "Błąd", "Godzina zakończenia musi być późniejsza niż rozpoczęcia.")
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
        hours = self.shop_config.get_open_hours_for_day(day)
        if not hours:
            weekday = self.shop_config.weekday(day)
            hours = self.shop_config.get_open_hours_for_weekday(weekday)

        dialog = DayOverrideDialog(self, day, hours, self.shop_config)
        result = dialog.exec()

        if result != QDialog.Accepted:
            return

        # Undo must restore both the schedule and this day-specific shop setup.
        self.controller.snapshot()
        if dialog.result_mode == "reset":
            self.shop_config.day_overrides.pop(day, None)
            self.shop_config.public_holidays.discard(day)
        elif dialog.result_mode == "save":
            self.shop_config.day_overrides[day] = (dialog.result_start, dialog.result_end)
            if dialog.result_holiday:
                self.shop_config.public_holidays.add(day)
            else:
                self.shop_config.public_holidays.discard(day)

        self._update_nominal_hours_label()
        self._sync_grid()
        self.statusBar().showMessage("Zaktualizowano godziny dnia.", 2500)

    def _open_config(self):
        dialog = ConfigDialog(self, self.shop_config)
        if dialog.exec() != QDialog.Accepted:
            return
        self._update_nominal_hours_label()
        self._sync_grid()
        # Constraint policies are part of the local working project, so retain
        # the selected generator configuration for the next application start.
        try:
            save_project("last_project.json", self.schedule, self.shop_config)
        except OSError:
            pass
        self.statusBar().showMessage("Zapisano konfigurację.", 2500)

    def _save_project(self):

        if self.demo.block_save(self):
            return
        
        path, _ = QFileDialog.getSaveFileName(self, "Zapisz projekt", "", "Projekt grafiku (*.json)")
        if not path:
            return

        save_project(path, self.schedule, self.shop_config)
        save_project("last_project.json", self.schedule, self.shop_config)
        self.statusBar().showMessage("Zapisano projekt.", 2500)

    def _load_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Wczytaj projekt", "", "Projekt grafiku (*.json)")
        if not path:
            return

        self.schedule, self.shop_config = load_project(path)
        self.controller = ScheduleController(self.schedule, self.shop_config)
        self.year = self.schedule.year
        self.month = self.schedule.month
        self._set_date_controls(self.year, self.month)
        self._update_nominal_hours_label()
        self._sync_everything()
        self.statusBar().showMessage("Wczytano projekt.", 2500)

    def _export_excel(self):
        if self.demo.block_export(self):
            return
        path, _ = QFileDialog.getSaveFileName(self, "Eksport Excel", "", "Excel (*.xlsx)")
        if not path:
            return

        export_schedule_to_excel(self.schedule, self.year, self.month, path)
        self.statusBar().showMessage("Wyeksportowano do Excela.", 2500)

    def _export_image(self):
        if self.demo.block_export(self):
            return
        path, _ = QFileDialog.getSaveFileName(self, "Eksport JPG", "", "Obraz JPG (*.jpg)")
        if not path:
            return

        if not path.lower().endswith(".jpg"):
            path += ".jpg"

        export_schedule_to_image(self.schedule, self.year, self.month, path)
        self.statusBar().showMessage("Wyeksportowano do JPG.", 2500)

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

            export_schedule_to_image(self.schedule, self.year, self.month, temp_path)

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

        self._sync_everything()
        self.statusBar().showMessage("Wyczyszczono grafik.", 2500)

    def _about(self):
        from PySide6.QtWidgets import QMessageBox
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl, Qt

        msg = QMessageBox(self)
        msg.setWindowTitle("O programie")

        msg.setText(
            "<b>Dingo!</b><br><br>"
            "Nowoczesne narzędzie do tworzenia grafików pracy.<br><br>"
            "Z dedykacją dla Mamy ❤️<br>"
            "Dzięki za wsparcie i motywację.<br><br>"
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

        def open_link():
            QDesktopServices.openUrl(QUrl("https://madebykewin.pl"))

        msg.exec()

    def _try_load_last_project(self):
        if not os.path.exists("last_project.json"):
            return

        try:
            self.schedule, self.shop_config = load_project("last_project.json")
            self.controller = ScheduleController(self.schedule, self.shop_config)
            self.year = self.schedule.year
            self.month = self.schedule.month
            self._set_date_controls(self.year, self.month)
            self._update_nominal_hours_label()
            self._sync_everything()
        except Exception:
            pass

    def _toggle_expanded_view(self, checked):
        self.grid.set_compact_mode(not checked)
        self.btn_expand_view.setText("Zwiń widok" if checked else "Rozszerz widok")
        self.statusBar().showMessage(
            "Widok rozszerzony włączony." if checked else "Widok kompaktowy włączony.",
            2000
        )


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

        is_work = shift_type == "WORK"
        self.time_panel.setVisible(is_work)
        self.quick_duration_label.setVisible(is_work)

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

    def _open_tutorial(self):
        from ui.tutorial_dialog import TutorialDialog
        dialog = TutorialDialog(self)
        dialog.exec()

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
                save_project("last_project.json", self.schedule, self.shop_config)
            except:
                pass

            event.accept()

        elif clicked == btn_no:
            event.accept()

        else:
            event.ignore()

    def _check_first_run(self):
        flag_path = "first_run.flag"

        if not os.path.exists(flag_path):

            dialog = TutorialDialog(self)
            dialog.setWindowModality(Qt.ApplicationModal)

            if dialog.exec() == QDialog.Accepted:
                try:
                    with open(flag_path, "w") as f:
                        f.write("seen")
                except:
                    pass

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

        reply = QMessageBox.question(
            self,
            "Dostępna aktualizacja",
            f"Dostępna jest nowa wersja programu ({result['version']}).\n\nPobrać i zainstalować?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self._start_update_download(result["url"])

    def _start_update_download(self, url):
        self.update_progress_dialog = QProgressDialog("Łączenie z serwerem aktualizacji...", "Anuluj", 0, 100, self)
        self.update_progress_dialog.setWindowTitle("Aktualizacja DinGO")
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
        import subprocess

        try:
            subprocess.Popen([installer_path])
        except OSError as e:
            QMessageBox.warning(
                self,
                "Aktualizacja",
                f"Nie udało się uruchomić instalatora.\n\n{e}",
            )
            return

        self.close()
