from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QFrame, QGridLayout, QLabel, QWidget

from ui.time_input import TimeInputWidget

DAY_NAMES = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]


class WeeklyHoursEditor(QFrame):
    """Edytor godzin otwarcia osobno na każdy dzień tygodnia (0=Pon...6=Nd).
    Wydzielony z dawnej, budowanej inline zawartości
    ConfigDialog._build_hours_tab(), żeby to samo UI dało się użyć zarówno w
    zakładce projektowej "Godziny otwarcia", jak i w oknie "Lokalizacje"
    (patrz ui/locations_dialog.py) - jedno źródło prawdy dla tego widgetu.
    Dzień oznaczony "Nieczynne" zwraca (None, None) z get_hours() - dokładnie
    ta sama konwencja "zamknięty dzień", którą get_open_hours_for_day() w
    model/location.py i model/shop_config.py już rozumiały wcześniej (brak
    wpisu / puste godziny), tylko bez sposobu, żeby ją wyrazić w UI."""

    def __init__(self, initial_hours: dict[int, tuple[str, str]] | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("configCard")

        layout = QGridLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(10)

        self._edits: dict[int, tuple[TimeInputWidget, TimeInputWidget]] = {}
        self._closed_checks: dict[int, QCheckBox] = {}
        for wd, name in enumerate(DAY_NAMES):
            label = QLabel(name)
            label.setStyleSheet("font-weight: 600;")
            layout.addWidget(label, wd, 0)

            start_edit = TimeInputWidget()
            end_edit = TimeInputWidget()
            layout.addWidget(start_edit, wd, 1)
            layout.addWidget(QLabel("—"), wd, 2, Qt.AlignCenter)
            layout.addWidget(end_edit, wd, 3)

            closed_check = QCheckBox("Nieczynne")
            closed_check.toggled.connect(
                lambda checked, wd=wd: self._on_closed_toggled(wd, checked)
            )
            layout.addWidget(closed_check, wd, 4)

            self._edits[wd] = (start_edit, end_edit)
            self._closed_checks[wd] = closed_check

        self.set_hours(initial_hours or {})

    def _on_closed_toggled(self, wd: int, checked: bool) -> None:
        start_edit, end_edit = self._edits[wd]
        start_edit.setEnabled(not checked)
        end_edit.setEnabled(not checked)

    def get_hours(self) -> dict[int, tuple[str, str] | tuple[None, None]]:
        result = {}
        for wd, (start_edit, end_edit) in self._edits.items():
            if self._closed_checks[wd].isChecked():
                result[wd] = (None, None)
            else:
                result[wd] = (start_edit.get_time_str(), end_edit.get_time_str())
        return result

    def set_hours(self, hours: dict[int, tuple[str, str]]) -> None:
        for wd, (start_edit, end_edit) in self._edits.items():
            start, end = hours.get(wd, ("08:00", "20:00"))
            is_closed = not start or not end
            self._closed_checks[wd].setChecked(is_closed)
            start_edit.set_time_str(start or "08:00")
            end_edit.set_time_str(end or "20:00")
            start_edit.setEnabled(not is_closed)
            end_edit.setEnabled(not is_closed)
