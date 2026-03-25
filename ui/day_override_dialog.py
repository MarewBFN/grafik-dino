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
)
from ui.time_input import TimeInputWidget


def _parse_time(value: str) -> QTime:
    if not value:
        return QTime(0, 0)
    hour, minute = value.split(":")
    return QTime(int(hour), int(minute))


class DayOverrideDialog(QDialog):
    def __init__(self, parent, day, current_hours, shop_config):
        super().__init__(parent)
        self.day = day
        self.shop_config = shop_config
        self.current_hours = current_hours

        self.setWindowTitle(f"Godziny dla dnia {day}")
        self.setModal(True)
        self.setMinimumWidth(360)

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        label = QLabel("Ustaw godziny dla wybranego dnia")
        label.setObjectName("sectionLabel")
        root.addWidget(label)

        form = QFormLayout()

        self.start_edit = TimeInputWidget()
        self.start_edit.set_time_str(self.current_hours[0])

        self.end_edit = TimeInputWidget()
        self.end_edit.set_time_str(self.current_hours[1])

        self.holiday_box = QCheckBox("Dzień wolny ustawowo")
        self.holiday_box.setChecked(self.day in self.shop_config.public_holidays)

        form.addRow("Otwarcie", self.start_edit)
        form.addRow("Zamknięcie", self.end_edit)

        root.addLayout(form)
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

    def _reset_to_default(self):
        self.result_mode = "reset"
        self.accept()

    def _save(self):
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
        self.result_holiday = self.holiday_box.isChecked()
        self.accept()