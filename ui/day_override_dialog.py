from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from ui.time_input import TimeInputWidget
from model.business_profile import get_profile


def _parse_time(value: str) -> QTime:
    if not value:
        return QTime(0, 0)
    hour, minute = value.split(":")
    return QTime(int(hour), int(minute))


class DayOverrideDialog(QDialog):
    def __init__(self, parent, day, current_hours, shop_config, fallback_hours=None):
        super().__init__(parent)
        self.day = day
        self.shop_config = shop_config
        self.current_hours = current_hours
        # Godziny "zwykłego" wzorca tygodniowego dla tego dnia tygodnia -
        # WYŁĄCZNIE podpowiedź pól czasu po odznaczeniu "Nieczynne tego
        # dnia" (current_hours samo w sobie jest już None/None, gdy dzień
        # jest faktycznie zamknięty - patrz ui/main_window.py::_open_header_menu),
        # żeby pola nie zostawały puste/"00:00" bez sensownego punktu startu.
        self.fallback_hours = fallback_hours or ("08:00", "16:00")

        self.setWindowTitle(f"Godziny dla dnia {day}")
        self.setModal(True)
        self.setMinimumWidth(360)

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        label = QLabel("Ustaw godziny dla wybranego dnia")
        label.setObjectName("sectionLabel")
        root.addWidget(label)

        # Toggle otwarta/zamknięta NAD godzinami otwarcia (czytelność UI -
        # decyzja/wygenerowana na życzenie użytkownika) - automatycznie
        # zaznaczony, gdy placówka jest tego dnia faktycznie zamknięta
        # (święto, "Nieczynne" w tygodniowym wzorcu, niedziela niehandlowa -
        # patrz current_hours przekazane z _open_header_menu), żeby UI od
        # razu odzwierciedlał prawdziwy stan zamiast pokazywać godziny
        # zwykłego wzorca, jakby dzień był otwarty.
        self.closed_check = QCheckBox("Nieczynne tego dnia")
        self.closed_check.toggled.connect(self._on_closed_toggled)
        root.addWidget(self.closed_check)

        self.hours_form_widget = QWidget()
        form = QFormLayout(self.hours_form_widget)
        form.setContentsMargins(0, 0, 0, 0)

        self.start_edit = TimeInputWidget()
        self.end_edit = TimeInputWidget()

        form.addRow("Otwarcie", self.start_edit)
        form.addRow("Zamknięcie", self.end_edit)

        root.addWidget(self.hours_form_widget)

        is_closed = not self.current_hours[0] or not self.current_hours[1]
        start_for_fields = self.current_hours[0] if not is_closed else self.fallback_hours[0]
        end_for_fields = self.current_hours[1] if not is_closed else self.fallback_hours[1]
        self.start_edit.set_time_str(start_for_fields)
        self.end_edit.set_time_str(end_for_fields)
        # setChecked() woła _on_closed_toggled(), które chowa/pokazuje
        # hours_form_widget - musi więc nastąpić PO wypełnieniu pól wyżej.
        self.closed_check.setChecked(is_closed)

        # "Dzień wolny ustawowo" ma sens tylko dla profili z kalendarzem
        # handlowym (patrz BusinessProfile.uses_trade_calendar) - inaczej
        # ten checkbox konfigurowałby coś, co i tak nic nie robi.
        self.holiday_box = None
        if get_profile(self.shop_config.business_type).uses_trade_calendar:
            self.holiday_box = QCheckBox("Dzień wolny ustawowo")
            self.holiday_box.setChecked(self.day in self.shop_config.public_holidays)
            root.addWidget(self.holiday_box)

        row = QHBoxLayout()
        reset_btn = QPushButton("Przywróć domyślne")
        reset_btn.clicked.connect(self._reset_to_default)
        row.addWidget(reset_btn)
        row.addStretch()
        root.addLayout(row)

        buttons = QDialogButtonBox()
        cancel_btn = QPushButton("Anuluj")
        save_btn = QPushButton("Zapisz")
        save_btn.setObjectName("primaryButton")
        buttons.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        buttons.addButton(save_btn, QDialogButtonBox.AcceptRole)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._save)
        root.addWidget(buttons)

    def _on_closed_toggled(self, checked):
        # Chowa (nie tylko wyszarza) edytor godzin, gdy dzień jest
        # oznaczony jako nieczynny - na życzenie użytkownika, dla
        # czytelności (pola i tak nie mają wtedy żadnego znaczenia).
        self.hours_form_widget.setVisible(not checked)
        if not checked and self.start_edit.get_time_str() == "00:00" and self.end_edit.get_time_str() == "00:00":
            # Odznaczenie "Nieczynne" z pustymi/zerowymi polami (dzień był
            # faktycznie zamknięty przy otwarciu okna) - podpowiedz zwykłe
            # godziny tego dnia tygodnia zamiast zostawiać 00:00-00:00.
            self.start_edit.set_time_str(self.fallback_hours[0])
            self.end_edit.set_time_str(self.fallback_hours[1])

    def _reset_to_default(self):
        self.result_mode = "reset"
        self.accept()

    def _save(self):
        if self.closed_check.isChecked():
            self.result_mode = "save"
            self.result_start = None
            self.result_end = None
            self.result_holiday = self.holiday_box.isChecked() if self.holiday_box else False
            self.accept()
            return

        start_str = self.start_edit.get_time_str()
        end_str = self.end_edit.get_time_str()

        if not start_str or not end_str:
            QMessageBox.critical(self, "Błąd", "Godziny nie mogą być puste.")
            return

        start_qt = _parse_time(start_str)
        end_qt = _parse_time(end_str)

        if end_qt <= start_qt:
            QMessageBox.critical(self, "Błąd", "Zamknięcie musi być później niż otwarcie.")
            return

        self.result_mode = "save"
        self.result_start = start_str
        self.result_end = end_str
        self.result_holiday = self.holiday_box.isChecked() if self.holiday_box else False
        self.accept()