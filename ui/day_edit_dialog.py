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


class DayEditDialog(QDialog):
    def __init__(
        self, parent=None, start=None, end=None, open_start="05:30", open_end="22:45",
        daily_hours=8, night_hours=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Edycja dnia")
        self.setModal(True)
        self.setMinimumWidth(420)

        self.daily_hours = daily_hours
        # Sztywny blok zmiany nocnej tej lokalizacji, o ile skonfigurowany
        # (Etap B/D planu zmian nocnych) - jedyny wariant "przez północ",
        # jaki ten dialog w ogóle pozwala wybrać (patrz _on_night_toggled).
        self.night_hours = night_hours
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
        self.start_edit.input.textChanged.connect(self._on_start_changed)

        self.end_edit = TimeInputWidget()
        self.end_edit.input.textChanged.connect(self._on_end_changed)

        form.addRow("Start", self.start_edit)
        form.addRow("Koniec", self.end_edit)

        root.addLayout(form)

        self.night_check = None
        if self.night_hours:
            night_start, night_end = self.night_hours
            self.night_check = QCheckBox(f"Zmiana nocna ({night_start}–{night_end})")
            self.night_check.toggled.connect(self._on_night_toggled)
            root.addWidget(self.night_check)

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
        self.start_edit.input.setFocus()

    def _fill_values(self, start, end):
        if start:
            self.start_edit.set_time_str(start)
        if end:
            self._manual_end = True
            self.end_edit.set_time_str(end)

        if self.night_check is not None and self.night_hours and (start, end) == self.night_hours:
            self.night_check.setChecked(True)

    def _on_night_toggled(self, checked):
        if checked:
            night_start, night_end = self.night_hours
            self._updating = True
            self.start_edit.set_time_str(night_start)
            self.end_edit.set_time_str(night_end)
            self._updating = False
            self._manual_end = True
            self.start_edit.setEnabled(False)
            self.end_edit.setEnabled(False)
        else:
            self.start_edit.setEnabled(True)
            self.end_edit.setEnabled(True)
        self._update_duration()

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

        secs = start_qt.secsTo(end_qt)
        if secs < 0:
            # Tylko zmiana nocna (patrz _on_night_toggled) legalnie kończy
            # się "wcześniej" niż zaczyna - w tym jednym przypadku to
            # przejście przez północ, nie błąd.
            if self.night_check is not None and self.night_check.isChecked():
                secs += 24 * 3600
            else:
                secs = 0

        minutes = secs // 60
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
        if self.night_check is not None and self.night_check.isChecked():
            # Sztywny blok - zapisujemy dokładnie skonfigurowane okno,
            # niezależnie od tego, co zostało w polach start/end (są i tak
            # wyłączone w tym trybie, patrz _on_night_toggled).
            self.result_mode = "hours"
            self.result_start, self.result_end = self.night_hours
            self.accept()
            return

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