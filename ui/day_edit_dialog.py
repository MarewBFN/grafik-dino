from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
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


class DayEditDialog(QDialog):
    def __init__(self, parent=None, start=None, end=None, open_start="05:30", open_end="22:45", daily_hours=8):
        super().__init__(parent)
        self.setWindowTitle("Edycja dnia")
        self.setModal(True)
        self.setMinimumWidth(420)

        self.daily_hours = daily_hours
        self._manual_end = False
        self._updating = False
        self._open_start_qt = _parse_time(open_start)
        self._open_end_qt = _parse_time(open_end)

        self._build_ui()
        self._fill_values(start, end)

        if start is None:
            self.start_edit.set_time_str(open_start)

        self._update_duration()
        if end is None:
            self._suggest_end()

    def _build_ui(self):
        root = QVBoxLayout(self)

        title = QLabel("Wybierz godziny albo ustaw wolne / urlop")
        title.setObjectName("sectionLabel")
        root.addWidget(title)

        form = QFormLayout()

        self.start_edit = TimeInputWidget()
        self.start_edit.hour_box.valueChanged.connect(self._on_start_changed)
        self.start_edit.minute_box.valueChanged.connect(self._on_start_changed)

        self.end_edit = TimeInputWidget()
        self.end_edit.hour_box.valueChanged.connect(self._on_end_changed)
        self.end_edit.minute_box.valueChanged.connect(self._on_end_changed)

        form.addRow("Start", self.start_edit)
        form.addRow("Koniec", self.end_edit)

        root.addLayout(form)

        self.duration_label = QLabel("Czas pracy: 0:00")
        self.duration_label.setObjectName("metricValue")
        root.addWidget(self.duration_label)

        row = QHBoxLayout()
        self.free_btn = QPushButton("Wolne")
        self.leave_btn = QPushButton("Urlop")
        self.sick_btn = QPushButton("Chorobowe")

        self.free_btn.clicked.connect(self._set_free)
        self.leave_btn.clicked.connect(self._set_leave)
        self.sick_btn.clicked.connect(self._set_sick)

        row.addWidget(self.free_btn)
        row.addWidget(self.leave_btn)
        row.addWidget(self.sick_btn)
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

    def _fill_values(self, start, end):
        if start:
            self.start_edit.set_time_str(start)
        if end:
            self._manual_end = True
            self.end_edit.set_time_str(end)

    def _suggest_end(self):
        if self._manual_end:
            self._update_duration()
            return

        start_qt = _parse_time(self.start_edit.get_time_str())
        suggested = start_qt.addSecs(self.daily_hours * 3600)
        
        if suggested > self._open_end_qt:
            suggested = self._open_end_qt

        self._updating = True
        self.end_edit.set_time_str(suggested.toString("HH:mm"))
        self._updating = False
        self._update_duration()

    def _on_start_changed(self, _):
        if self._updating:
            return
        if not self._manual_end:
            self._suggest_end()
        else:
            self._update_duration()

    def _on_end_changed(self, _):
        if self._updating:
            return
        self._manual_end = True
        self._update_duration()

    def _update_duration(self):
        start_qt = _parse_time(self.start_edit.get_time_str())
        end_qt = _parse_time(self.end_edit.get_time_str())
        
        minutes = start_qt.secsTo(end_qt) // 60
        if minutes < 0:
            minutes = 0
        hours = minutes // 60
        mins = minutes % 60
        self.duration_label.setText(f"Czas pracy: {hours}:{mins:02d}")

    def _set_free(self):
        self.result_mode = "free"
        self.accept()

    def _set_leave(self):
        self.result_mode = "leave"
        self.accept()

    def _set_sick(self):
        self.result_mode = "sick"
        self.accept()

    def _save(self):
        start_str = self.start_edit.get_time_str()
        end_str = self.end_edit.get_time_str()
        
        start_qt = _parse_time(start_str)
        end_qt = _parse_time(end_str)

        if end_qt <= start_qt:
            QMessageBox.critical(self, "Błąd", "Koniec musi być później niż start.")
            return

        if start_qt < self._open_start_qt or end_qt > self._open_end_qt:
            QMessageBox.critical(self, "Błąd", "Godziny muszą mieścić się w czasie otwarcia sklepu.")
            return

        self.result_mode = "hours"
        self.result_start = start_str
        self.result_end = end_str
        self.accept()