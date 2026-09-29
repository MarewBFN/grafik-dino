from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.time_input import TimeInputWidget

DEFAULT_END_TIME = "22:00"


class PreviousMonthShiftDialog(QDialog):
    """Ręczny fallback "pamięci poprzedniego miesiąca" (patrz
    model/month_schedule.py::PreviousMonthShiftEnd) - gdy nie ma czego
    przejąć automatycznie (świeży projekt / "Nowy projekt..." / projekt bez
    tej pamięci zapisanej wcześniej przy zmianie miesiąca w TYM SAMYM
    projekcie - patrz ui/main_window.py::_save_date_clicked), pozwala
    ręcznie wpisać dla każdego pracownika godzinę zakończenia jego
    ostatniej zmiany w (nieistniejącym w tym projekcie) ostatnim dniu
    poprzedniego miesiąca.

    Sama godzina końca nie wystarcza, żeby jednoznacznie umieścić ją na osi
    czasu względem dnia 1 tego miesiąca - ten sam problem co
    DaySchedule.crosses_midnight (koniec < start = przejście przez północ):
    "22:00" mogłoby oznaczać zarówno "koniec tuż PRZED dniem 1", jak i
    "koniec JUŻ W dniu 1" (np. zmiana nocna 14:00→22:00 w kolejnym dniu
    zapisu). Stąd checkbox "Zmiana wchodzi w dzień 1" obok każdej godziny -
    generator (logic/generator/rest_constraint.py,
    logic/generator/duty_rotation_rest_constraint.py) potrzebuje obu
    wartości, nie samej godziny.

    Wywoływane z menu Edycja - to jedyne miejsce, z którego można wpisać tę
    pamięć od zera: kolumna w ScheduleGrid (patrz build()) pokazuje się
    dopiero, gdy dane już istnieją dla choć jednego pracownika."""

    def __init__(self, schedule, parent=None):
        super().__init__(parent)
        self.schedule = schedule
        self.setWindowTitle("Godziny zakończenia z poprzedniego miesiąca")

        outer = QVBoxLayout(self)

        info = QLabel(
            "Dla każdego pracownika: godzina zakończenia jego ostatniej zmiany w "
            "ostatnim dniu poprzedniego miesiąca (tego samego projektu). Generator "
            "użyje tego, żeby nie złamać minimalnej przerwy (11h) na początku tego "
            "miesiąca. Pozostaw odznaczone „Mam dane”, jeśli nie znasz tej godziny.\n"
            "Uwaga: to jest przerwa dla KAŻDEGO pracownika z osobna - podanie tej "
            "samej (albo zgadniętej) godziny dla wielu osób naraz może zablokować "
            "wszystkich od razu na początku miesiąca i zrobić grafik niewykonalnym. "
            "Wpisuj tylko wtedy, gdy naprawdę znasz tę godzinę dla danej osoby."
        )
        info.setWordWrap(True)
        outer.addWidget(info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        grid = QGridLayout(container)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)

        grid.addWidget(QLabel("Pracownik"), 0, 0)
        grid.addWidget(QLabel("Mam dane"), 0, 1)
        grid.addWidget(QLabel("Koniec zmiany"), 0, 2)
        grid.addWidget(QLabel("Zmiana wchodzi w dzień 1"), 0, 3)

        self._rows: dict = {}
        for row, emp in enumerate(schedule.employees, start=1):
            name_label = QLabel(emp.display_name())
            has_check = QCheckBox()
            end_edit = TimeInputWidget()
            crosses_check = QCheckBox()

            existing = schedule.get_previous_month_end_shift(emp)
            has_check.setChecked(existing is not None)
            end_edit.set_time_str(existing.end if existing else DEFAULT_END_TIME)
            crosses_check.setChecked(existing.crosses_midnight if existing else False)
            end_edit.setEnabled(existing is not None)
            crosses_check.setEnabled(existing is not None)

            has_check.toggled.connect(
                lambda checked, e=end_edit, c=crosses_check: (
                    e.setEnabled(checked), c.setEnabled(checked),
                )
            )

            grid.addWidget(name_label, row, 0)
            grid.addWidget(has_check, row, 1)
            grid.addWidget(end_edit, row, 2)
            grid.addWidget(crosses_check, row, 3)

            self._rows[emp] = (has_check, end_edit, crosses_check)

        scroll.setWidget(container)
        outer.addWidget(scroll)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.resize(560, 420)

    def apply_to_schedule(self) -> None:
        """Zapisuje stan formularza do self.schedule - wołane przez wywołującego
        PO dialog.exec() == QDialog.Accepted (patrz
        ui/main_window.py::_open_previous_month_shift_dialog)."""
        for emp, (has_check, end_edit, crosses_check) in self._rows.items():
            if has_check.isChecked():
                self.schedule.set_previous_month_end_shift(
                    emp, end_edit.get_time_str(), crosses_check.isChecked()
                )
            else:
                self.schedule.set_previous_month_end_shift(emp, None)
