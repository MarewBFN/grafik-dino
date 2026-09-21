"""Interactive tutorial for ui/locations_dialog.py::LocationsDialog - same
pattern as ConfigDialog (ui/config_dialog.py): auto-shows on first open of
this window (flag file, see LOCATIONS_TUTORIAL_FLAG) and can be reopened any
time through the "Pomoc" button."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QWidget

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from model.shop_config import ShopConfig
from ui.locations_dialog import LOCATIONS_TUTORIAL_FLAG, LocationsDialog

# Features hidden from the client (see ENYO_ONLY_CHANGES.md) that a tutorial
# must never reference, because they'd point at something invisible/unclickable.
# "Rotacja służby 24/7" was hidden (no UI existed) when this test was first
# written - ui/duty_rotation_editor.py now gives it a real, working editor
# here, so it's no longer forbidden; see ENYO_ONLY_CHANGES.md.
FORBIDDEN_PHRASES = [
    "Progi obsady",
    "Nazwa i Profil placówki",
    "Okres rozliczeniowy",
    "poprzedniego miesiąca",
]


def _known_widgets(dialog):
    widgets = {dialog.add_btn, dialog.save_btn}
    for row in dialog._location_rows:
        widgets.add(row.is_24_7_check)
        widgets.add(row.toggle_hours_btn)
    return widgets


def test_build_tutorial_steps_has_well_formed_steps():
    shop = ShopConfig(2026, 8)
    dialog = LocationsDialog(None, shop)

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


def test_tutorial_shows_automatically_on_first_open_and_sets_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    flag_path = tmp_path / LOCATIONS_TUTORIAL_FLAG
    assert not flag_path.exists()

    shop = ShopConfig(2026, 8)
    dialog = LocationsDialog(None, shop)

    dialog._maybe_show_tutorial()

    assert not dialog._tutorial_overlay.isHidden()
    dialog._tutorial_overlay._finish()
    assert flag_path.exists()


def test_tutorial_does_not_auto_show_on_second_open(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    flag_path = tmp_path / LOCATIONS_TUTORIAL_FLAG
    flag_path.write_text("seen")

    shop = ShopConfig(2026, 8)
    dialog = LocationsDialog(None, shop)
    dialog._maybe_show_tutorial()

    assert getattr(dialog, "_tutorial_overlay", None) is None


def test_help_button_reopens_tutorial_without_touching_the_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    flag_path = tmp_path / LOCATIONS_TUTORIAL_FLAG
    flag_path.write_text("seen")

    shop = ShopConfig(2026, 8)
    dialog = LocationsDialog(None, shop)

    dialog._open_tutorial()

    assert not dialog._tutorial_overlay.isHidden()
    assert flag_path.read_text() == "seen"
