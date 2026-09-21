from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from model.location import normalize_duty_rotation
from ui.time_input import TimeInputWidget


class DutyRotationEditor(QFrame):
    """Edytor "Rotacja służby 24/7" (LocationConfig.duty_rotation).

    Świadomie BEZ własnego checkboxa włączającego - ta funkcjonalność jest
    podpięta wprost pod istniejący checkbox "Działalność całodobowa (24/7)"
    (LocationConfig.is_24_7) w ui/locations_dialog.py::_LocationRow, żeby nie
    dublować tego samego pytania do użytkownika dwoma osobnymi przełącznikami
    (decyzja z użytkownikiem, 2026-09-21). Widoczność całego widgetu
    (setVisible) i to, czy get_duty_rotation() w ogóle jest wołane, kontroluje
    wywołujący na podstawie TEGO checkboxa - patrz _LocationRow._update_hours_visibility()/_save().

    Schemat modelu (patrz model/location.py::normalize_duty_rotation) ma
    5 okien czasowych (weekday_long/short, weekend_full, weekend_half_a/b) +
    flagę only_12_24h. We wszystkich dotychczasowych lokalizacjach klienta
    każda para okien dokładnie dopełnia się do 24h (koniec pierwszego =
    start drugiego), a start zmiany 24h w weekend = start pierwszej
    połówki - to UI wykorzystuje wprost: użytkownik wpisuje TYLKO start/
    koniec jednej zmiany na kontekst (tydzień, weekend), drugą (i start
    zmiany 24h) dolicza się automatycznie jako dopełnienie do 24h. Patrz
    "ENYO_ONLY_CHANGES.md" - decyzja ustalona z użytkownikiem 2026-09-20,
    świadomie NIE pełna, niezależna kontrola nad wszystkich 5 okien (to by
    pozwalało wpisać sprzeczne/nietykające się godziny, których model dziś
    nie waliduje krzyżowo)."""

    def __init__(self, duty_rotation: dict | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("configCard")
        outer = QVBoxLayout(self)

        hint = QLabel(
            "Rotacja służby 24/7: generator przydzieli wyłącznie te zmiany, "
            "dokładnie pokrywające całą dobę, każdego dnia (zamiast zwykłych "
            "godzin otwarcia/zamknięcia)."
        )
        hint.setObjectName("mutedHint")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        self.only_12_24h_check = QCheckBox(
            "Używaj tylko zmian 12h/24h (każdy dzień tygodnia, nie tylko weekend)"
        )
        self.only_12_24h_check.toggled.connect(self._update_visibility)
        outer.addWidget(self.only_12_24h_check)

        self.weekday_container = QWidget()
        weekday_layout = QHBoxLayout(self.weekday_container)
        weekday_layout.setContentsMargins(0, 0, 0, 0)
        weekday_layout.addWidget(QLabel("Podział doby w tygodniu (pon-pt):"))
        self.weekday_start = TimeInputWidget()
        self.weekday_end = TimeInputWidget()
        weekday_layout.addWidget(self.weekday_start)
        weekday_layout.addWidget(QLabel("—"))
        weekday_layout.addWidget(self.weekday_end)
        weekday_layout.addStretch()
        outer.addWidget(self.weekday_container)

        self.weekend_container = QWidget()
        weekend_layout = QHBoxLayout(self.weekend_container)
        weekend_layout.setContentsMargins(0, 0, 0, 0)
        weekend_layout.addWidget(QLabel("Podział doby w weekend (sob-nd):"))
        self.weekend_start = TimeInputWidget()
        self.weekend_end = TimeInputWidget()
        weekend_layout.addWidget(self.weekend_start)
        weekend_layout.addWidget(QLabel("—"))
        weekend_layout.addWidget(self.weekend_end)
        weekend_layout.addStretch()
        outer.addWidget(self.weekend_container)

        self.set_duty_rotation(duty_rotation)

    def _update_visibility(self) -> None:
        self.weekday_container.setVisible(not self.only_12_24h_check.isChecked())

    def set_duty_rotation(self, duty_rotation: dict | None) -> None:
        duty_rotation = duty_rotation or {}
        self.only_12_24h_check.setChecked(bool(duty_rotation.get("only_12_24h", False)))

        weekend_a = duty_rotation.get("weekend_half_a") or {"start": "08:00", "end": "20:00"}
        self.weekend_start.set_time_str(weekend_a.get("start") or "08:00")
        self.weekend_end.set_time_str(weekend_a.get("end") or "20:00")

        weekday_long = duty_rotation.get("weekday_long") or {"start": "09:00", "end": "17:00"}
        self.weekday_start.set_time_str(weekday_long.get("start") or "09:00")
        self.weekday_end.set_time_str(weekday_long.get("end") or "17:00")

        self._update_visibility()

    def get_duty_rotation(self) -> dict:
        """Może rzucić ValueError (patrz normalize_duty_rotation) przy
        sprzecznych godzinach (start == koniec którejś pary) - wywołujący
        (LocationsDialog._save()) ma to złapać i pokazać użytkownikowi, tym
        samym wzorcem co reszta walidacji w tym oknie. Wywołujący decyduje,
        czy w ogóle wołać tę metodę (patrz docstring klasy) - nie ma tu
        "wyłączonego" stanu do sprawdzenia."""
        only_12_24h = self.only_12_24h_check.isChecked()
        weekend_start = self.weekend_start.get_time_str()
        weekend_end = self.weekend_end.get_time_str()

        raw = {
            "weekend_half_a": {"start": weekend_start, "end": weekend_end},
            "weekend_half_b": {"start": weekend_end, "end": weekend_start},
            "weekend_full": {"start": weekend_start},
            "only_12_24h": only_12_24h,
        }
        if not only_12_24h:
            weekday_start = self.weekday_start.get_time_str()
            weekday_end = self.weekday_end.get_time_str()
            raw["weekday_long"] = {"start": weekday_start, "end": weekday_end}
            raw["weekday_short"] = {"start": weekday_end, "end": weekday_start}

        return normalize_duty_rotation(raw)
