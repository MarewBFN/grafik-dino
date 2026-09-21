import os

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from model.shop_config import normalize_quick_mode_presets
from ui.time_input import TimeInputWidget
from ui.tutorial_overlay import TutorialOverlay, TutorialStep

QUICK_MODE_TUTORIAL_FLAG = "quick_mode_tutorial_seen.flag"


class _PresetRow(QFrame):
    """Jeden edytowalny przedział: nazwa + start/koniec (albo "cała doba"),
    wzorem _LocationRow w ui/config_dialog.py."""

    def __init__(self, on_remove, name="", start="08:00", end="16:00", full_day=False):
        super().__init__()
        self.setObjectName("configCard")
        layout = QHBoxLayout(self)

        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("np. Zmiana 16h")
        layout.addWidget(self.name_edit, 1)

        layout.addWidget(QLabel("Start:"))
        self.start_input = TimeInputWidget()
        self.start_input.set_time_str(start)
        layout.addWidget(self.start_input)

        layout.addWidget(QLabel("Koniec:"))
        self.end_input = TimeInputWidget()
        self.end_input.set_time_str(end or start)
        layout.addWidget(self.end_input)

        self.full_day_check = QCheckBox("Cała doba (24h)")
        self.full_day_check.setChecked(full_day)
        self.full_day_check.toggled.connect(lambda checked: self.end_input.setEnabled(not checked))
        self.end_input.setEnabled(not full_day)
        layout.addWidget(self.full_day_check)

        remove_btn = QPushButton("Usuń")
        remove_btn.setObjectName("dangerButton")
        remove_btn.clicked.connect(lambda: on_remove(self))
        layout.addWidget(remove_btn)

    def name(self) -> str:
        return self.name_edit.text().strip()

    def start_time(self) -> str:
        return self.start_input.get_time_str()

    def end_time(self) -> str:
        return self.end_input.get_time_str()

    def is_full_day(self) -> bool:
        return self.full_day_check.isChecked()


class QuickModeSettingsDialog(QDialog):
    """Konfiguracja nazwanych, ręcznie zdefiniowanych przedziałów czasowych
    dla trybu szybkiego (ui/main_window.py::_build_quick_panel) - menu
    Konfiguracja -> "Ustawienia trybu szybkiego", obok "Generator".
    Każdy zapisany tu przedział pojawia się jako osobny przycisk w trybie
    szybkim, zastępując ręczne wpisywanie godzin (przycisk "Praca")."""

    def __init__(self, parent, presets):
        super().__init__(parent)
        self.setWindowTitle("Ustawienia trybu szybkiego")
        self.setModal(True)
        self.resize(560, 420)
        self.result_presets = None
        self._rows: list[_PresetRow] = []
        self._build_ui(presets or [])
        QTimer.singleShot(0, self._maybe_show_tutorial)

    def _build_ui(self, presets):
        root = QVBoxLayout(self)

        hint = QLabel(
            "Zdefiniuj własne, nazwane przedziały czasowe (np. \"Zmiana 16h\", "
            "\"Nocka 22–06\", \"Doba 24h\") - każdy pojawi się jako osobny "
            "przycisk w trybie szybkim zamiast ręcznego wpisywania godzin. "
            "Koniec wcześniejszy niż start oznacza przejście przez północ."
        )
        hint.setObjectName("mutedHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(scroll, 1)

        host = QWidget()
        scroll.setWidget(host)
        self._rows_layout = QVBoxLayout(host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(8)

        for preset in presets:
            self._add_row(
                preset.get("name", ""),
                preset.get("start", "08:00"),
                preset.get("end") or preset.get("start", "08:00"),
                bool(preset.get("full_day")),
            )

        self._rows_layout.addStretch()

        self.add_btn = QPushButton("Dodaj przedział")
        self.add_btn.setObjectName("secondaryButton")
        self.add_btn.clicked.connect(lambda: self._add_row())
        root.addWidget(self.add_btn)

        buttons = QDialogButtonBox()
        help_btn = QPushButton("Pomoc")
        help_btn.setObjectName("secondaryButton")
        cancel_btn = QPushButton("Anuluj")
        self.save_btn = QPushButton("Zapisz")
        self.save_btn.setObjectName("primaryButton")
        buttons.addButton(help_btn, QDialogButtonBox.HelpRole)
        buttons.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        buttons.addButton(self.save_btn, QDialogButtonBox.AcceptRole)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._save)
        help_btn.clicked.connect(self._open_tutorial)
        root.addWidget(buttons)

    def _add_row(self, name="", start="08:00", end="16:00", full_day=False):
        row = _PresetRow(self._remove_row, name, start, end, full_day)
        self._rows.append(row)
        # -1: trzymamy addStretch() na samym końcu listy przedziałów.
        self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)

    def _remove_row(self, row):
        self._rows.remove(row)
        row.setParent(None)
        row.deleteLater()

    def _build_tutorial_steps(self):
        steps = [
            TutorialStep(
                "Ustawienia trybu szybkiego",
                "Zdefiniuj własne, nazwane przedziały czasowe - każdy pojawi się "
                "jako osobny przycisk w trybie szybkim, zamiast ręcznego "
                "wpisywania godzin.",
            ),
            TutorialStep(
                "Dodaj przedział",
                "Kliknij, żeby dodać nowy przedział czasowy.",
                target=self.add_btn,
            ),
        ]
        if self._rows:
            steps.append(TutorialStep(
                "Nazwa i godziny",
                "Nadaj przedziałowi nazwę (np. „Zmiana 16h”) i ustaw godziny "
                "start/koniec. Zaznacz „Cała doba (24h)”, jeśli przedział ma "
                "trwać całą dobę.",
                target=self._rows[0],
            ))
        steps.append(TutorialStep(
            "Zapisz",
            "Zapisz przedziały - od razu pojawią się jako przyciski w trybie "
            "szybkim.",
            target=self.save_btn,
        ))
        return steps

    def _start_tutorial(self, on_finished=None):
        existing = getattr(self, "_tutorial_overlay", None)
        if existing is not None:
            existing.deleteLater()
        self._tutorial_overlay = TutorialOverlay(self, self._build_tutorial_steps(), on_finished=on_finished)
        self._tutorial_overlay.start()

    def _open_tutorial(self):
        self._start_tutorial()

    def _maybe_show_tutorial(self):
        if os.path.exists(QUICK_MODE_TUTORIAL_FLAG):
            return

        def mark_seen():
            try:
                with open(QUICK_MODE_TUTORIAL_FLAG, "w") as f:
                    f.write("seen")
            except OSError:
                pass

        self._start_tutorial(on_finished=mark_seen)

    def _save(self):
        raw = []
        for row in self._rows:
            name = row.name()
            if not name:
                continue
            full_day = row.is_full_day()
            raw.append({
                "name": name,
                "start": row.start_time(),
                "end": None if full_day else row.end_time(),
                "full_day": full_day,
            })

        try:
            presets = normalize_quick_mode_presets(raw)
        except ValueError as exc:
            QMessageBox.critical(self, "Błąd", str(exc))
            return

        self.result_presets = presets
        self.accept()
