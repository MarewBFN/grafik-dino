from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTimeEdit,
    QVBoxLayout,
)


def _parse_time(value: str) -> QTime:
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
        self._open_start = _parse_time(open_start)
        self._open_end = _parse_time(open_end)

        self._build_ui()
        self._fill_values(start, end)

        if start is None:
            self.start_edit.setTime(self._open_start)

        self._update_duration()
        if end is None:
            self._suggest_end()

    def _build_ui(self):
        root = QVBoxLayout(self)

        title = QLabel("Wybierz godziny albo ustaw wolne / urlop")
        title.setObjectName("sectionLabel")
        root.addWidget(title)

        form = QFormLayout()

        self.start_edit = QTimeEdit()
        self.start_edit.setDisplayFormat("HH:mm")
        self.start_edit.setMinimumTime(self._open_start)
        self.start_edit.setMaximumTime(self._open_end)
        self.start_edit.timeChanged.connect(self._on_start_changed)

        self.end_edit = QTimeEdit()
        self.end_edit.setDisplayFormat("HH:mm")
        self.end_edit.setMinimumTime(self._open_start)
        self.end_edit.setMaximumTime(self._open_end)
        self.end_edit.timeChanged.connect(self._on_end_changed)

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
            self.start_edit.setTime(_parse_time(start))
        if end:
            self._manual_end = True
            self.end_edit.setTime(_parse_time(end))

    def _suggest_end(self):
        if self._manual_end:
            self._update_duration()
            return

        start = self.start_edit.time()
        suggested = start.addSecs(self.daily_hours * 3600)
        if suggested > self._open_end:
            suggested = self._open_end

        self._updating = True
        self.end_edit.setTime(suggested)
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
        start = self.start_edit.time()
        end = self.end_edit.time()
        minutes = start.secsTo(end) // 60
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
        start = self.start_edit.time()
        end = self.end_edit.time()

        if end <= start:
            QMessageBox.critical(self, "Błąd", "Koniec musi być później niż start.")
            return

        if start < self._open_start or end > self._open_end:
            QMessageBox.critical(self, "Błąd", "Godziny muszą mieścić się w czasie otwarcia sklepu.")
            return

        self.result_mode = "hours"
        self.result_start = start.toString("HH:mm")
        self.result_end = end.toString("HH:mm")
        self.accept()