import calendar

from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QFrame,
)
from ui.time_input import TimeInputWidget

def _parse_time(value: str) -> QTime:
    if not value:
        return QTime(0, 0)
    hour, minute = value.split(":")
    return QTime(int(hour), int(minute))


class ConfigDialog(QDialog):
    def __init__(self, parent, shop_config):
        super().__init__(parent)
        self.shop_config = shop_config
        self.setWindowTitle("Konfiguracja")
        self.setModal(True)
        self.resize(580, 500)

        # Wspólny styl dla wszystkich kart i elementów w dialogu
        self.setStyleSheet("""
            QFrame#configCard {
                background-color: #f9f9f9;
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 10px;
                margin-bottom: 2px;
            }
            QFrame#configCard:hover {
                background-color: #f0f7ff;
                border-color: #0078d4;
            }
            QCheckBox {
                font-size: 14px;
                font-weight: bold;
                spacing: 12px;
            }
            QCheckBox::indicator {
                width: 22px;
                height: 22px;
            }
            QLabel#groupLabel {
                font-weight: bold;
                color: #0078d4;
                font-size: 13px;
                margin-top: 10px;
                border-bottom: 1px solid #eee;
            }
        """)

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        title = QLabel("Konfiguracja sklepu")
        title.setObjectName("sectionLabel")
        root.addWidget(title)

        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        tabs.addTab(self._build_hours_tab(), "Godziny otwarcia")
        tabs.addTab(self._build_sundays_tab(), "Niedziele handlowe")
        tabs.addTab(self._build_constraints_tab(), "Limity")

        buttons = QDialogButtonBox()
        cancel_btn = QPushButton("Anuluj")
        save_btn = QPushButton("Zapisz")
        save_btn.setObjectName("primaryButton")
        buttons.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        buttons.addButton(save_btn, QDialogButtonBox.AcceptRole)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._save)
        root.addWidget(buttons)

    def _build_hours_tab(self):
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self.open_edits = {}
        days = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]

        for row, name in enumerate(days):
            label = QLabel(name)
            label.setStyleSheet("font-weight: bold;")
            layout.addWidget(label, row, 0)

            start, end = self.shop_config.open_hours[row]
            
            start_edit = TimeInputWidget()
            start_edit.set_time_str(start)

            end_edit = TimeInputWidget()
            end_edit.set_time_str(end)

            layout.addWidget(start_edit, row, 1)
            layout.addWidget(QLabel("—"), row, 2, Qt.AlignCenter)
            layout.addWidget(end_edit, row, 3)

            self.open_edits[row] = (start_edit, end_edit)

        return page

    def _build_sundays_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        info = QLabel("Zaznacz niedziele handlowe w tym miesiącu:")
        info.setStyleSheet("color: #666; margin-bottom: 5px;")
        layout.addWidget(info)

        self.sunday_checks = {}
        cal = calendar.Calendar()

        sundays = [
            d for d, wd in cal.itermonthdays2(self.shop_config.year, self.shop_config.month)
            if d and wd == 6
        ]

        if not sundays:
            layout.addWidget(QLabel("W tym miesiącu nie ma niedziel."))
            return page

        for day in sundays:
            card = QFrame()
            card.setObjectName("configCard")
            card_layout = QHBoxLayout(card)
            
            date_str = f"{day:02d}.{self.shop_config.month:02d}.{self.shop_config.year}"
            box = QCheckBox(f"Niedziela {date_str}")
            box.setCursor(Qt.PointingHandCursor)
            box.setChecked(day in self.shop_config.trade_sundays)
            
            self.sunday_checks[day] = box
            card_layout.addWidget(box)
            layout.addWidget(card)

        layout.addStretch()
        return page

    def _build_constraints_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # --- Sekcja: Ogólne ---
        gen_label = QLabel("LIMITY CZASU PRACY")
        gen_label.setObjectName("groupLabel")
        layout.addWidget(gen_label)

        form_gen = QFormLayout()
        self.max_consecutive = QSpinBox()
        self.max_consecutive.setRange(1, 14)
        self.max_consecutive.setFixedWidth(70)
        self.max_consecutive.setValue(self.shop_config.constraints.get("max_consecutive_days", 4))
        form_gen.addRow("Maksymalna liczba dni pod rząd:", self.max_consecutive)
        layout.addLayout(form_gen)

        # Karta Checkboxa (ten sam styl co niedziele)
        fulltime_card = QFrame()
        fulltime_card.setObjectName("configCard")
        fulltime_layout = QHBoxLayout(fulltime_card)
        self.force_fulltime_845 = QCheckBox("Wymuś 8h 30 min dla pracowników pełnoetatowych")
        self.force_fulltime_845.setCursor(Qt.PointingHandCursor)
        self.force_fulltime_845.setChecked(
            self.shop_config.constraints.get("force_fulltime_845", True)
        )
        self.shop_config.constraints["force_fulltime_845"] = self.force_fulltime_845.isChecked()
        fulltime_layout.addWidget(self.force_fulltime_845)
        layout.addWidget(fulltime_card)

        # Karta dla podświetlania limitu dni pod rząd
        hl_card = QFrame()
        hl_card.setObjectName("configCard")
        hl_layout = QHBoxLayout(hl_card)
        self.hl_consecutive = QCheckBox("Podświetlaj przekroczenie limitu dni pod rząd (Grid)")
        self.hl_consecutive.setCursor(Qt.PointingHandCursor)
        self.hl_consecutive.setChecked(
            self.shop_config.constraints.get("highlight_max_consecutive", False)
        )
        hl_layout.addWidget(self.hl_consecutive)
        layout.addWidget(hl_card)

        # --- Sekcja: Obsada ---
        staff_label = QLabel("MINIMALNA OBSADA PRACOWNIKÓW")
        staff_label.setObjectName("groupLabel")
        layout.addWidget(staff_label)

        form_staff = QFormLayout()
        self.min_open = QSpinBox()
        self.min_open.setRange(1, 10)
        self.min_open.setFixedWidth(70)
        self.min_open.setValue(self.shop_config.constraints.get("min_open_staff", 3))

        self.min_close = QSpinBox()
        self.min_close.setRange(1, 10)
        self.min_close.setFixedWidth(70)
        self.min_close.setValue(self.shop_config.constraints.get("min_close_staff", 3))

        form_staff.addRow("Pracowników na otwarciu (rano):", self.min_open)
        form_staff.addRow("Pracowników na zamknięciu (wieczór):", self.min_close)
        layout.addLayout(form_staff)

        layout.addStretch()
        return page

    def _save(self):
        try:
            for wd, (start_input, end_input) in self.open_edits.items():
                start_str = start_input.get_time_str()
                end_str = end_input.get_time_str()
                
                start_qt = _parse_time(start_str)
                end_qt = _parse_time(end_str)

                if end_qt <= start_qt:
                    day_names = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]
                    raise ValueError(f"Zamknięcie musi być później niż otwarcie w dniu: {day_names[wd]}.")
                
                self.shop_config.open_hours[wd] = (start_str, end_str)

            self.shop_config.trade_sundays = {
                day for day, box in self.sunday_checks.items() if box.isChecked()
            }

            self.shop_config.constraints["max_consecutive_days"] = self.max_consecutive.value()
            self.shop_config.constraints["min_open_staff"] = self.min_open.value()
            self.shop_config.constraints["min_close_staff"] = self.min_close.value()
            self.shop_config.constraints["enforce_11h_rest"] = True
            self.shop_config.constraints["enforce_meat_coverage"] = True
            self.shop_config.constraints["force_fulltime_845"] = self.force_fulltime_845.isChecked()

        except Exception as exc:
            QMessageBox.critical(self, "Błąd konfiguracji", str(exc))
            return

        self.accept()