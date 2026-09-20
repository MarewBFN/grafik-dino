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
    def __init__(
        self, parent=None, start=None, end=None, open_start="05:30", open_end="22:45",
        daily_hours=8, night_hours=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Edycja dnia")
        self.setModal(True)
        self.setMinimumWidth(420)

        self.daily_hours = daily_hours
        # Skonfigurowane okno zmiany nocnej tej lokalizacji, o ile istnieje
        # (patrz LocationConfig.get_night_shift_hours()) - jedyny wariant
        # "koniec wcześniej niż start" (przejście przez północ), jaki
        # ręczne wpisanie godzin tutaj może zaakceptować bez błędu (patrz
        # _save()/_update_duration()). Bez osobnego checkboxa "Zmiana nocna"
        # (usunięty - był starą funkcjonalnością sprzed automatycznego
        # wykrywania nocy z godzin otwarcia, patrz LocationConfig): po prostu
        # wpisz 22:00/06:00 (albo jaki tam jest night_hours) normalnie w pola
        # Start/Koniec.
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

        if self.night_hours:
            night_start, night_end = self.night_hours
            hint = QLabel(f"Zmiana nocna tej lokalizacji: {night_start}–{night_end}.")
            hint.setObjectName("mutedHint")
            root.addWidget(hint)

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

    def _is_configured_night_shift(self, start_str, end_str) -> bool:
        return bool(self.night_hours) and (start_str, end_str) == self.night_hours

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
        start_str = self.start_edit.get_time_str()
        end_str = self.end_edit.get_time_str()
        start_qt = _parse_time(start_str)
        end_qt = _parse_time(end_str)

        secs = start_qt.secsTo(end_qt)
        if secs < 0:
            # Tylko dokładnie skonfigurowana zmiana nocna tej lokalizacji
            # legalnie kończy się "wcześniej" niż zaczyna - w tym jednym
            # przypadku to przejście przez północ, nie błąd.
            if self._is_configured_night_shift(start_str, end_str):
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
        start_str = self.start_edit.get_time_str()
        end_str = self.end_edit.get_time_str()

        start_qt = _parse_time(start_str)
        end_qt = _parse_time(end_str)

        is_night = self._is_configured_night_shift(start_str, end_str)
        if end_qt <= start_qt and not is_night:
            QMessageBox.critical(self, "Błąd", "Koniec musi być później niż start.")
            return

        # Ominięcie ostrzeżenia o wyjściu poza godziny otwarcia dla
        # skonfigurowanej zmiany nocnej: start/end nie są tu porównywalne
        # wprost jako godziny w obrębie jednej doby (przejście przez
        # północ), a i tak jest to rozpoznane, poprawne okno tej lokalizacji
        # (patrz LocationConfig.get_night_shift_hours()).
        if not is_night and (start_qt < self._open_start_qt or end_qt > self._open_end_qt):
            reply = QMessageBox.question(
                self,
                "Godziny poza godzinami otwarcia",
                "Wprowadzone godziny wykraczają poza godziny otwarcia tej lokalizacji "
                f"({self._open_start_qt.toString('HH:mm')}–{self._open_end_qt.toString('HH:mm')}). "
                "Kontynuować mimo to?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self.result_mode = "hours"
        self.result_start = start_str
        self.result_end = end_str
        self.accept()