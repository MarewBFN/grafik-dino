from datetime import datetime, timedelta

from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from model.location import normalize_duty_rotation
from ui.time_input import TimeInputWidget

_FMT = "%H:%M"


def _plus_12h(time_str: str) -> str:
    return (datetime.strptime(time_str, _FMT) + timedelta(hours=12)).strftime(_FMT)


def rotation_start_and_split(duty_rotation: dict | None) -> tuple[str, str]:
    """(godzina rozpoczęcia doby, godzina podziału doby) odczytane z
    zapisanej LocationConfig.duty_rotation. Początek doby to start zmiany
    24h (weekend_full), a gdy go brak - wcześniejszy ze startów dwóch
    połówek (obie zaczynają się w tym samym dniu kalendarzowym, więc doba
    połówek zaczyna się o wcześniejszej z tych godzin). Podział to start tej
    połówki, która NIE zaczyna się o początku doby. Starsze projekty z
    osobnym schematem tygodnia (weekday_long/short) - odczytywany jest tylko
    schemat weekendowy, jedyny, który ten edytor dziś zapisuje."""
    duty_rotation = duty_rotation or {}
    half_a = duty_rotation.get("weekend_half_a") or {}
    half_b = duty_rotation.get("weekend_half_b") or {}
    half_starts = [h["start"] for h in (half_a, half_b) if h.get("start")]

    full = duty_rotation.get("weekend_full") or {}
    start = full.get("start") or (min(half_starts) if half_starts else "08:00")

    split = next((s for s in half_starts if s != start), None) or _plus_12h(start)
    return start, split


class DutyRotationEditor(QFrame):
    """Edytor "Rotacja służby 24/7" (LocationConfig.duty_rotation).

    Świadomie BEZ własnego checkboxa włączającego - podpięty wprost pod
    checkbox "Działalność całodobowa (24/7)" (LocationConfig.is_24_7) w
    ui/locations_dialog.py::_LocationRow i ui/config_dialog.py (decyzja z
    użytkownikiem, 2026-09-21). Widoczność i to, czy get_duty_rotation() w
    ogóle jest wołane, kontroluje wywołujący.

    Uproszczony na życzenie użytkownika (2026-09-25, patrz
    ENYO_ONLY_CHANGES.md): zamiast osobnych podziałów doby dla tygodnia i
    weekendu (dwie pary pól "od-do", które przy różnych godzinach dawały
    lukę w poniedziałek rano i podwójną obsadę w sobotę, a zmiana 24h
    startowała od pierwszej wpisanej godziny zamiast od początku doby)
    użytkownik podaje tylko:

    - godzinę rozpoczęcia doby S - każdego dnia albo jedna zmiana 24h od S,
      albo dwie zmiany S -> P i P -> S,
    - godzinę podziału doby P (domyślnie S + 12h, np. GZUK: 07:00 i 15:00),
    - "Preferuj zmiany 24h" - kierunek miękkiej preferencji generatora.

    Zapisywane zawsze jako only_12_24h=True - ten sam schemat każdego dnia
    tygodnia. Osobny schemat tygodnia (weekday_long/short) nadal rozumie
    generator (starsze projekty), ale ten edytor już go nie tworzy."""

    def __init__(self, duty_rotation: dict | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("configCard")
        outer = QVBoxLayout(self)

        hint = QLabel(
            "Rotacja służby 24/7: każdego dnia generator przydziela jedną "
            "zmianę 24h od godziny rozpoczęcia albo dwie zmiany podzielone o "
            "godzinie podziału - zawsze dokładnie jedna osoba w pracy."
        )
        hint.setObjectName("mutedHint")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        start_row = QWidget()
        start_layout = QHBoxLayout(start_row)
        start_layout.setContentsMargins(0, 0, 0, 0)
        start_layout.addWidget(QLabel("Godzina rozpoczęcia doby:"))
        self.start_input = TimeInputWidget()
        start_layout.addWidget(self.start_input)
        start_layout.addStretch()
        outer.addWidget(start_row)

        split_row = QWidget()
        split_layout = QHBoxLayout(split_row)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.addWidget(QLabel("Podział doby (2 osoby) o:"))
        self.split_input = TimeInputWidget()
        split_layout.addWidget(self.split_input)
        split_layout.addStretch()
        outer.addWidget(split_row)

        self.summary_label = QLabel()
        self.summary_label.setObjectName("quickInfoHint")
        self.summary_label.setWordWrap(True)
        outer.addWidget(self.summary_label)

        self.prefer_24h_check = QCheckBox("Preferuj zmiany 24h")
        self.prefer_24h_check.setToolTip(
            "Zaznaczone: generator woli jedną osobę na 24h, a podział na dwie "
            "zmiany stosuje tylko wtedy, gdy musi (np. \"Nie chce zmian 24h\", "
            "urlopy). Odznaczone: woli dwie zmiany zamiast 24h. Pełne "
            "pokrycie doby jest zawsze ważniejsze."
        )
        outer.addWidget(self.prefer_24h_check)

        self._last_start = None
        self.set_duty_rotation(duty_rotation)
        self.start_input.input.textChanged.connect(self._on_inputs_changed)
        self.split_input.input.textChanged.connect(self._on_inputs_changed)

    def _on_inputs_changed(self, *_args) -> None:
        if len(self.start_input.input.text()) != 5:
            return  # w trakcie wpisywania - jeszcze nie pełna godzina
        start = self.start_input.get_time_str()
        # Podział "idzie za" początkiem doby, dopóki użytkownik go nie
        # zmienił ręcznie (był dokładnie +12h od poprzedniego początku).
        if self._last_start and start != self._last_start:
            if self.split_input.get_time_str() == _plus_12h(self._last_start):
                self.split_input.set_time_str(_plus_12h(start))
        self._last_start = start
        self._update_summary()

    def _update_summary(self) -> None:
        start = self.start_input.get_time_str()
        split = self.split_input.get_time_str()
        if start == split:
            self.summary_label.setText("Godzina podziału musi być inna niż godzina rozpoczęcia doby.")
            return
        self.summary_label.setText(
            f"Zmiany: 24h od {start} albo {start}–{split} + {split}–{start}."
        )

    def set_duty_rotation(self, duty_rotation: dict | None) -> None:
        start, split = rotation_start_and_split(duty_rotation)
        self.start_input.set_time_str(start)
        self.split_input.set_time_str(split)
        self.prefer_24h_check.setChecked(bool((duty_rotation or {}).get("prefer_24h", False)))
        self._last_start = start
        self._update_summary()

    def get_duty_rotation(self) -> dict:
        """Może rzucić ValueError (patrz normalize_duty_rotation) gdy godzina
        podziału == godzina rozpoczęcia - wywołujący (LocationsDialog._save(),
        ConfigDialog._save()) łapie i pokazuje użytkownikowi."""
        start = self.start_input.get_time_str()
        split = self.split_input.get_time_str()
        raw = {
            "weekend_half_a": {"start": start, "end": split},
            "weekend_half_b": {"start": split, "end": start},
            "weekend_full": {"start": start},
            "only_12_24h": True,
            "prefer_24h": self.prefer_24h_check.isChecked(),
        }
        return normalize_duty_rotation(raw)
