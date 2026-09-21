"""Interactive tutorial for ui/quick_mode_settings_dialog.py::
QuickModeSettingsDialog - same pattern as ConfigDialog (ui/config_dialog.py):
auto-shows on first open of this window (flag file, see
QUICK_MODE_TUTORIAL_FLAG) and can be reopened any time through the "Pomoc"
button."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QWidget

_app = QApplication.instance() or QApplication([])

from ui.quick_mode_settings_dialog import (
    QUICK_MODE_TUTORIAL_FLAG,
    QuickModeSettingsDialog,
)

FORBIDDEN_PHRASES = [
    "Progi obsady",
    "Nazwa i Profil placówki",
    "Okres rozliczeniowy",
    "poprzedniego miesiąca",
    "Rotacja służby 24/7",
]


def _known_widgets(dialog):
    widgets = {dialog.add_btn, dialog.save_btn}
    widgets.update(dialog._rows)
    return widgets


def test_build_tutorial_steps_has_well_formed_steps_with_no_presets():
    dialog = QuickModeSettingsDialog(None, [])

    steps = dialog._build_tutorial_steps()

    assert len(steps) > 0
    known = _known_widgets(dialog)
    for step in steps:
        assert step.title.strip()
        assert step.text.strip()
        if step.target is not None:
            assert isinstance(step.target, QWidget)
            assert step.target in known
        for phrase in FORBIDDEN_PHRASES:
            assert phrase not in step.title
            assert phrase not in step.text


def test_build_tutorial_steps_includes_row_step_when_a_preset_exists():
    presets = [{"name": "Zmiana 16h", "start": "06:00", "end": "22:00", "full_day": False}]
    dialog = QuickModeSettingsDialog(None, presets)

    steps = dialog._build_tutorial_steps()

    assert any(step.target is dialog._rows[0] for step in steps)


def test_tutorial_shows_automatically_on_first_open_and_sets_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    flag_path = tmp_path / QUICK_MODE_TUTORIAL_FLAG
    assert not flag_path.exists()

    dialog = QuickModeSettingsDialog(None, [])

    dialog._maybe_show_tutorial()

    assert not dialog._tutorial_overlay.isHidden()
    dialog._tutorial_overlay._finish()
    assert flag_path.exists()


def test_tutorial_does_not_auto_show_on_second_open(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    flag_path = tmp_path / QUICK_MODE_TUTORIAL_FLAG
    flag_path.write_text("seen")

    dialog = QuickModeSettingsDialog(None, [])
    dialog._maybe_show_tutorial()

    assert getattr(dialog, "_tutorial_overlay", None) is None


def test_help_button_reopens_tutorial_without_touching_the_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    flag_path = tmp_path / QUICK_MODE_TUTORIAL_FLAG
    flag_path.write_text("seen")

    dialog = QuickModeSettingsDialog(None, [])

    dialog._open_tutorial()

    assert not dialog._tutorial_overlay.isHidden()
    assert flag_path.read_text() == "seen"
