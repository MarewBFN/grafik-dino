from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QWidget

from ui.time_input import TimeInputWidget

DAY_NAMES = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]


class WeeklyHoursEditor(QFrame):
    """Edytor godzin otwarcia osobno na każdy dzień tygodnia (0=Pon...6=Nd).
    Wydzielony z dawnej, budowanej inline zawartości
    ConfigDialog._build_hours_tab(), żeby to samo UI dało się użyć zarówno w
    zakładce projektowej "Godziny otwarcia", jak i w oknie "Lokalizacje"
    (patrz ui/locations_dialog.py) - jedno źródło prawdy dla tego widgetu."""

    def __init__(self, initial_hours: dict[int, tuple[str, str]] | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("configCard")

        layout = QGridLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(10)

        self._edits: dict[int, tuple[TimeInputWidget, TimeInputWidget]] = {}
        for wd, name in enumerate(DAY_NAMES):
            label = QLabel(name)
            label.setStyleSheet("font-weight: 600;")
            layout.addWidget(label, wd, 0)

            start_edit = TimeInputWidget()
            end_edit = TimeInputWidget()
            layout.addWidget(start_edit, wd, 1)
            layout.addWidget(QLabel("—"), wd, 2, Qt.AlignCenter)
            layout.addWidget(end_edit, wd, 3)

            self._edits[wd] = (start_edit, end_edit)

        self.set_hours(initial_hours or {})

    def get_hours(self) -> dict[int, tuple[str, str]]:
        return {
            wd: (start_edit.get_time_str(), end_edit.get_time_str())
            for wd, (start_edit, end_edit) in self._edits.items()
        }

    def set_hours(self, hours: dict[int, tuple[str, str]]) -> None:
        for wd, (start_edit, end_edit) in self._edits.items():
            start, end = hours.get(wd, ("08:00", "20:00"))
            start_edit.set_time_str(start or "08:00")
            end_edit.set_time_str(end or "20:00")
