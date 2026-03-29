import os
from datetime import date

from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer
from PySide6.QtGui import QAction, QPainter, QColor
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QDialog,
    QToolBar,
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

class GeneratorWorker(QObject):
    finished = Signal(object)

    def __init__(self, controller, force=False):
        super().__init__()
        self.controller = controller
        self.force = force

    def run(self):
        result = self.controller.generate_schedule(force=self.force)
        self.finished.emit(result)

class LoadingSpinner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.start(16)  # ~60 FPS

        self.setFixedSize(80, 80)

    def _rotate(self):
        self._angle = (self._angle + 5) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(10, 10, -10, -10)

        # tło (szare kółko)
        painter.setPen(QColor(255, 255, 255, 40))
        painter.drawEllipse(rect)

        # aktywny łuk
        pen = painter.pen()
        pen.setWidth(4)
        pen.setColor(QColor(255, 255, 255))
        painter.setPen(pen)

        painter.drawArc(rect, int(self._angle * 16), int(120 * 16))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Grafik Dino v2")
        self.resize(1540, 920)

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
        self._build_loading_overlay()

        self.statusBar().showMessage("Gotowe")
        QTimer.singleShot(0, self._check_first_run)

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

    def _build_left_panel(self):
        panel = QFrame()
        panel.setObjectName("panelCard")
        panel.setMinimumWidth(300)
        panel.setMaximumWidth(360)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # Widget dla "Grafik na:" i Daty
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
        
        layout.addWidget(self.title_row_widget)

        self.btn_change_date = QPushButton("Zmień datę")
        self.btn_change_date.setStyleSheet("color: #0078d4; text-align: left; background: transparent; border: none; text-decoration: underline;")
        self.btn_change_date.setCursor(Qt.PointingHandCursor)
        self.btn_change_date.setFixedWidth(120)
        self.btn_change_date.clicked.connect(self._enter_edit_date_mode)
        
        layout.addWidget(self.btn_change_date)

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
        layout.addWidget(self.date_edit_widget)

        metric_hint = QLabel("Nominalny etat")
        metric_hint.setObjectName("metricHint")
        layout.addWidget(metric_hint)

        self.nominal_hours_label = QLabel("-")
        self.nominal_hours_label.setObjectName("metricValue")
        layout.addWidget(self.nominal_hours_label)

        self.btn_generate = QPushButton("Generuj grafik")
        self.btn_generate.setObjectName("primaryButton")
        self.btn_generate.setMinimumHeight(44)
        self.btn_generate.clicked.connect(self._on_generate_clicked)
        self.btn_generate.setToolTip("Tworzy nowy grafik od zera. Nie nadpisuje ręcznie wprowadzonych zmian")
        
        self.btn_regenerate = QPushButton("Generuj ponownie")
        self.btn_regenerate.setObjectName("secondaryButton")
        self.btn_regenerate.setMinimumHeight(44)
        self.btn_regenerate.clicked.connect(self._on_force_generate_clicked)
        self.btn_generate.setToolTip("Tworzy nowy grafik od zera. Nie nadpisuje ręcznie wprowadzonych zmian")
        self.btn_regenerate.hide()

        self.btn_add_employee = QPushButton("Dodaj pracownika")
        self.btn_add_employee.setObjectName("secondaryButton")
        self.btn_add_employee.setMinimumHeight(44)
        self.btn_add_employee.clicked.connect(self._open_add_employee)

        self.btn_undo = QPushButton("Cofnij")
        self.btn_undo.setMinimumHeight(40)
        self.btn_undo.clicked.connect(self._undo)

        self.btn_redo = QPushButton("Ponów")
        self.btn_redo.setMinimumHeight(40)
        self.btn_redo.clicked.connect(self._redo)

        self.btn_quick_mode = QPushButton("Tryb szybki")
        self.btn_quick_mode.setToolTip("Tryb szybkiego wprowadzania zmian ręcznie.")
        self.btn_quick_mode.setObjectName("secondaryButton")
        self.btn_quick_mode.setMinimumHeight(44)
        self.btn_quick_mode.setCheckable(True)
        self.btn_quick_mode.setStyleSheet("""
            QPushButton:checked {
                background-color: #0078d4;
                color: white;
                font-weight: bold;
                border: none;
            }
        """)
        self.btn_quick_mode.clicked.connect(self._toggle_quick_mode)

        layout.addWidget(self.btn_generate)
        layout.addWidget(self.btn_regenerate)
        layout.addWidget(self.btn_add_employee)
        layout.addWidget(self.btn_undo)
        layout.addWidget(self.btn_redo)
        layout.addWidget(self.btn_quick_mode)
        layout.addWidget(self.quick_panel)

        layout.addStretch(1)
        return panel

    def _build_quick_panel(self):
        self.quick_panel = QWidget(self)

        layout = QVBoxLayout(self.quick_panel)
        layout.setContentsMargins(0, 5, 0, 0)

        self.quick_info_label = QLabel("Tryb szybki włączony. Ustaw preferowany typ zmiany i nanieś na grafik jednym kliknięciem.")
        self.quick_info_label.setWordWrap(True)
        self.quick_info_label.setStyleSheet("color: #555; font-size: 11px; margin-bottom: 5px; font-style: italic;")
        layout.addWidget(self.quick_info_label)

        # --- przyciski ---
        btn_row = QHBoxLayout()

        button_style = """
            QPushButton:checked {
                background-color: #0078d4;
                color: white;
                font-weight: bold;
                border: 1px solid #005a9e;
            }
        """

        self.btn_work = QPushButton("Praca")
        self.btn_work.setCheckable(True)
        self.btn_work.setStyleSheet(button_style)
        self.btn_work.clicked.connect(lambda: self._set_quick_shift("WORK"))

        self.btn_off = QPushButton("Wolne")
        self.btn_off.setCheckable(True)
        self.btn_off.setStyleSheet(button_style)
        self.btn_off.clicked.connect(lambda: self._set_quick_shift("OFF"))

        self.btn_leave = QPushButton("Urlop")
        self.btn_leave.setCheckable(True)
        self.btn_leave.setStyleSheet(button_style)
        self.btn_leave.clicked.connect(lambda: self._set_quick_shift("LEAVE"))

        self.btn_sick = QPushButton("L4")
        self.btn_sick.setCheckable(True)
        self.btn_sick.setStyleSheet(button_style)
        self.btn_sick.clicked.connect(lambda: self._set_quick_shift("SICK"))

        btn_row.addWidget(self.btn_work)
        btn_row.addWidget(self.btn_off)
        btn_row.addWidget(self.btn_leave)
        btn_row.addWidget(self.btn_sick)

        layout.addLayout(btn_row)

        # --- panel godzin ---
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

        self.quick_duration_label = QLabel("0:00")
        self.quick_duration_label.setStyleSheet("color: #555; font-size: 11px;")

        self.time_panel.setLayout(time_layout)
        self.time_panel.hide()

        layout.addWidget(self.time_panel)

        self.quick_duration_label = QLabel("Czas pracy: 0:00")
        self.quick_duration_label.setObjectName("metricValue")
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
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        top = QHBoxLayout()
        self.grid_title = QLabel("Widok grafiku")
        self.grid_title.setObjectName("sectionLabel")
        top.addWidget(self.grid_title)

        top.addStretch(1)
        self.state_label = QLabel("")
        self.state_label.setObjectName("subtitleLabel")
        top.addWidget(self.state_label)
        layout.addLayout(top)

        self.grid = ScheduleGrid()
        layout.addWidget(self.grid, 1)

        return panel

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("Plik")
        edit_menu = self.menuBar().addMenu("Edycja")
        config_menu = self.menuBar().addMenu("Konfiguracja")
        help_menu = self.menuBar().addMenu("Pomoc")

        self.act_compact = QAction("Tryb kompaktowy", self)
        self.act_compact.setCheckable(True)
        self.act_compact.triggered.connect(self._toggle_compact_mode)
        config_menu.addAction(self.act_compact)

        help_menu.addAction("Samouczek", self._open_tutorial)

        file_menu.addAction("Zapisz", self._save_project)
        file_menu.addAction("Wczytaj", self._load_project)

        export_menu = QMenu("Eksport", self)
        export_menu.addAction("Excel", self._export_excel)
        export_menu.addAction("JPG", self._export_image)
        file_menu.addMenu(export_menu)

        file_menu.addSeparator()
        file_menu.addAction("Zamknij", self.close)

        edit_menu.addAction("Cofnij", self._undo)
        edit_menu.addAction("Ponów", self._redo)

        config_menu.addAction("Generator", self._open_config)

        help_menu.addAction("O programie", self._about)

    def _build_toolbar(self):
        toolbar = QToolBar("Szybkie akcje", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(toolbar)

        act_save = QAction("Zapisz", self)
        act_save.triggered.connect(self._save_project)
        toolbar.addAction(act_save)

        act_load = QAction("Wczytaj", self)
        act_load.triggered.connect(self._load_project)
        toolbar.addAction(act_load)

        act_excel = QAction("Excel", self)
        act_excel.triggered.connect(self._export_excel)
        toolbar.addAction(act_excel)

        toolbar.addSeparator()

        act_config = QAction("Konfiguracja", self)
        act_config.triggered.connect(self._open_config)
        toolbar.addAction(act_config)

        act_undo = QAction("Cofnij", self)
        act_undo.triggered.connect(self._undo)
        toolbar.addAction(act_undo)

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

        if hasattr(self, "btn_generate") and hasattr(self, "btn_regenerate"):
            if getattr(self.schedule, "is_generated", False):
                self.btn_generate.setText("Napraw grafik")
                self.btn_regenerate.show()
                self.btn_regenerate.setToolTip("Szybka naprawa po ręcznych zmianach. Może popełniać błędy w odrębie tygodnia")
            else:
                self.btn_generate.setText("Generuj grafik")
                self.btn_regenerate.hide()

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
        if not self.schedule:
            self.state_label.setText("")
            return
        self.state_label.setText(f"{self.month:02d}.{self.year}")

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
        self._generate_schedule(force=False)
        
    def _on_force_generate_clicked(self):
        self._generate_schedule(force=True)

    def _generate_schedule(self, force=False):
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
            self.statusBar().showMessage("Grafik wygenerowany.", 3000)
            QMessageBox.information(self, "Sukces", "Grafik został wygenerowany.")
        else:
            QMessageBox.warning(self, "Brak rozwiązania", "Nie udało się znaleźć poprawnego grafiku.")

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

    def _open_header_menu(self, day, global_pos):
        hours = self.shop_config.get_open_hours_for_day(day)
        if not hours:
            weekday = self.shop_config.weekday(day)
            hours = self.shop_config.get_open_hours_for_weekday(weekday)

        dialog = DayOverrideDialog(self, day, hours, self.shop_config)
        result = dialog.exec()

        if result != QDialog.Accepted:
            return

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
        self.statusBar().showMessage("Zapisano konfigurację.", 2500)

    def _save_project(self):
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
        path, _ = QFileDialog.getSaveFileName(self, "Eksport Excel", "", "Excel (*.xlsx)")
        if not path:
            return

        export_schedule_to_excel(self.schedule, self.year, self.month, path)
        self.statusBar().showMessage("Wyeksportowano do Excela.", 2500)

    def _export_image(self):
        path, _ = QFileDialog.getSaveFileName(self, "Eksport JPG", "", "Obraz JPG (*.jpg)")
        if not path:
            return

        if not path.lower().endswith(".jpg"):
            path += ".jpg"

        export_schedule_to_image(self.schedule, self.year, self.month, path)
        self.statusBar().showMessage("Wyeksportowano do JPG.", 2500)

    def _undo(self):
        self.schedule = self.controller.undo()
        self._sync_everything()
        self.statusBar().showMessage("Cofnięto ostatnią zmianę.", 2500)

    def _redo(self):
        self.schedule = self.controller.redo()
        self._sync_everything()
        self.statusBar().showMessage("Ponowiono zmianę.", 2500)

    def _about(self):
        QMessageBox.information(self, "O programie", "Grafik Dino v2\nNowe UI w PySide6.")

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

    def _toggle_compact_mode(self, checked):
        self.grid.set_compact_mode(checked)
        self.statusBar().showMessage(
            "Tryb kompaktowy włączony." if checked else "Tryb kompaktowy wyłączony.",
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
        self.btn_off.setChecked(False)
        self.btn_leave.setChecked(False)
        self.btn_sick.setChecked(False)

        # aktywny
        if shift_type == "WORK":
            self.btn_work.setChecked(True)
            self.time_panel.show()
        elif shift_type == "OFF":
            self.btn_off.setChecked(True)
            self.time_panel.hide()
        elif shift_type == "LEAVE":
            self.btn_leave.setChecked(True)
            self.time_panel.hide()
        elif shift_type == "SICK":
            self.btn_sick.setChecked(True)
            self.time_panel.hide()

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

    def _build_loading_overlay(self):
        self.loading_overlay = QWidget(self)
        self.loading_overlay.setStyleSheet("background-color: rgba(0, 0, 0, 120);")
        self.loading_overlay.hide()

        layout = QVBoxLayout(self.loading_overlay)
        layout.setAlignment(Qt.AlignCenter)

        self.spinner = LoadingSpinner(self)
        layout.addWidget(self.spinner, alignment=Qt.AlignCenter)

        self.loading_label = QLabel("Generowanie grafiku...")
        self._loading_messages = [
            "Analizowanie dostępności pracowników...",
            "Układanie zmian porannych i popołudniowych...",
            "Sprawdzanie ograniczeń...",
            "Balansowanie godzin pracy...",
            "Dopasowywanie otwarcia i zamknięcia...",
        ]

        self._loading_msg_index = 0

        self._loading_timer = QTimer(self)
        self._loading_timer.timeout.connect(self._update_loading_text)
        self.loading_label.setStyleSheet("color: white; font-size: 20px;")
        self.loading_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.loading_label)

    def _update_loading_text(self):
        if not self._loading_messages:
            return

        self.loading_label.setText(self._loading_messages[self._loading_msg_index])
        self._loading_msg_index = (self._loading_msg_index + 1) % len(self._loading_messages)

    def _show_loading(self):
        self.loading_overlay.setGeometry(self.rect())
        self.loading_overlay.show()
        self._loading_msg_index = 0
        self._loading_timer.start(3000)
        QApplication.processEvents()

    def _hide_loading(self):
        self._loading_timer.stop()
        self.loading_overlay.hide()

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
            from ui.tutorial_dialog import TutorialDialog

            dialog = TutorialDialog(self)
            dialog.setWindowModality(Qt.ApplicationModal)

            if dialog.exec() == QDialog.Accepted:
                try:
                    with open(flag_path, "w") as f:
                        f.write("seen")
                except:
                    pass

from PySide6.QtCore import QTimer

class LoadingSpinner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.start(16)  # ~60 FPS

        self.setFixedSize(80, 80)

    def _rotate(self):
        self._angle = (self._angle + 5) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(10, 10, -10, -10)

        # tło (szare kółko)
        painter.setPen(QColor(255, 255, 255, 40))
        painter.drawEllipse(rect)

        # aktywny łuk
        pen = painter.pen()
        pen.setWidth(4)
        pen.setColor(QColor(255, 255, 255))
        painter.setPen(pen)

        painter.drawArc(rect, int(self._angle * 16), int(120 * 16))