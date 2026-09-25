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
from ui.duty_rotation_editor import rotation_start_and_split
from ui.time_input import TimeInputWidget


def _parse_time(value: str) -> QTime:
    if not value:
        return QTime(0, 0)
    hour, minute = value.split(":")
    return QTime(int(hour), int(minute))


class DayEditDialog(QDialog):
    def __init__(
        self, parent=None, start=None, end=None, open_start="05:30", open_end="22:45",
        daily_hours=8, night_hours=None, duty_rotation=None, full_day=False,
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
        # Pracownik placówki z rotacją służby 24/7: dowolne godziny, także
        # przez północ, i zmiana 24h - generator liczy każdy ręczny wpis
        # jako pokrycie i dopasowuje resztę doby (patrz
        # logic/generator/duty_rotation_manual_coverage.py). Szybkie
        # przyciski wpisują zmiany rotacji tej placówki.
        self.duty_rotation = duty_rotation
        self._initial_full_day = full_day
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

        self.full_day_check = QCheckBox("Cała doba (24h)")
        self.full_day_check.toggled.connect(self._on_full_day_toggled)
        self.full_day_check.setVisible(self.duty_rotation is not None)
        root.addWidget(self.full_day_check)

        if self.duty_rotation is not None:
            day_start, split = rotation_start_and_split(self.duty_rotation)
            hint = QLabel(
                f"Rotacja służby: 24h od {day_start} albo {day_start}–{split} + {split}–{day_start}. "
                "Możesz też wpisać inne godziny - generator dopasuje resztę doby."
            )
            hint.setObjectName("mutedHint")
            hint.setWordWrap(True)
            root.addWidget(hint)

            quick_row = QHBoxLayout()
            for label, start, end in (
                (f"{day_start}–{split}", day_start, split),
                (f"{split}–{day_start}", split, day_start),
                (f"24h od {day_start}", day_start, None),
            ):
                btn = QPushButton(label)
                btn.setObjectName("secondaryButton")
                btn.clicked.connect(lambda _checked=False, s=start, e=end: self._apply_quick_shift(s, e))
                quick_row.addWidget(btn)
            quick_row.addStretch()
            root.addLayout(quick_row)
        elif self.night_hours:
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
        if self._initial_full_day and self.duty_rotation is not None:
            self.full_day_check.setChecked(True)

    def _apply_quick_shift(self, start, end):
        self._updating = True
        self.start_edit.set_time_str(start)
        if end is not None:
            self.end_edit.set_time_str(end)
        self._updating = False
        self._manual_end = end is not None
        self.full_day_check.setChecked(end is None)
        self._update_duration()

    def _on_full_day_toggled(self, checked):
        self.end_edit.setEnabled(not checked)
        self._update_duration()

    def _is_full_day(self) -> bool:
        return self.duty_rotation is not None and self.full_day_check.isChecked()

    def _is_configured_night_shift(self, start_str, end_str) -> bool:
        return bool(self.night_hours) and (start_str, end_str) == self.night_hours

    def _suggest_end(self):
        if self._manual_end:
            self._update_duration()
            return

        start_qt = _parse_time(self.start_edit.get_time_str())
        if self.duty_rotation is not None:
            suggested = start_qt.addSecs(12 * 3600)
        else:
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
        if self._is_full_day():
            secs = 24 * 3600
        elif secs < 0 and self.duty_rotation is not None:
            secs += 24 * 3600
        elif secs < 0:
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

        if self._is_full_day():
            self.result_mode = "full_day"
            self.result_start = start_str
            self.result_end = start_str
            self.accept()
            return

        if self.duty_rotation is not None:
            if end_qt == start_qt:
                QMessageBox.critical(
                    self, "Błąd",
                    "Start i koniec nie mogą być takie same - dla zmiany 24h zaznacz „Cała doba (24h)”.",
                )
                return
            # Dowolne godziny, także przez północ - bez ostrzeżenia o
            # godzinach otwarcia (placówka 24/7).
            self.result_mode = "hours"
            self.result_start = start_str
            self.result_end = end_str
            self.accept()
            return

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