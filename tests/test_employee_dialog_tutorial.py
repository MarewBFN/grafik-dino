"""Interactive tutorial for ui/employee_dialog.py::EmployeeDialog - same
pattern as ConfigDialog (ui/config_dialog.py): auto-shows on first open of
this window (flag file, see EMPLOYEE_TUTORIAL_FLAG) and can be reopened any
time through the "Pomoc" button."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QWidget

_app = QApplication.instance() or QApplication([])

from model.location import LocationConfig, normalize_duty_rotation
from model.shop_config import ShopConfig
from ui.employee_dialog import EMPLOYEE_TUTORIAL_FLAG, EmployeeDialog

FORBIDDEN_PHRASES = [
    "Progi obsady",
    "Nazwa i Profil placówki",
    "Okres rozliczeniowy",
    "poprzedniego miesiąca",
    "Rotacja służby 24/7",
]


def _known_widgets(dialog):
    widgets = {dialog.employment_fraction, dialog.flags_card, dialog.save_btn}
    if dialog.location_combo is not None:
        widgets.add(dialog.location_combo)
    if dialog.no_24h_check is not None:
        widgets.add(dialog.no_24h_check)
    return widgets


def _shop_with_duty_rotation():
    shop = ShopConfig(2026, 8)
    loc = LocationConfig(key="site1", name="Site 1")
    loc.duty_rotation = normalize_duty_rotation({
        "weekday_long": {"start": "06:00", "end": "22:00"},
        "weekday_short": {"start": "22:00", "end": "06:00"},
        "weekend_full": {"start": "06:00"},
        "weekend_half_a": {"start": "06:00", "end": "18:00"},
        "weekend_half_b": {"start": "18:00", "end": "06:00"},
    })
    shop.locations["site1"] = loc
    return shop


def test_build_tutorial_steps_has_well_formed_steps():
    shop = ShopConfig(2026, 8)
    dialog = EmployeeDialog(None, shop_config=shop)

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


def test_tutorial_includes_no24h_step_only_when_duty_rotation_is_used():
    shop = ShopConfig(2026, 8)
    dialog = EmployeeDialog(None, shop_config=shop)
    steps = dialog._build_tutorial_steps()
    assert not any("24h" in step.title for step in steps)

    shop_duty = _shop_with_duty_rotation()
    dialog_duty = EmployeeDialog(None, shop_config=shop_duty)
    steps_duty = dialog_duty._build_tutorial_steps()
    assert any(step.target is dialog_duty.no_24h_check for step in steps_duty)


def test_tutorial_shows_automatically_on_first_open_and_sets_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    flag_path = tmp_path / EMPLOYEE_TUTORIAL_FLAG
    assert not flag_path.exists()

    shop = ShopConfig(2026, 8)
    dialog = EmployeeDialog(None, shop_config=shop)

    dialog._maybe_show_tutorial()

    assert not dialog._tutorial_overlay.isHidden()
    dialog._tutorial_overlay._finish()
    assert flag_path.exists()


def test_tutorial_does_not_auto_show_on_second_open(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    flag_path = tmp_path / EMPLOYEE_TUTORIAL_FLAG
    flag_path.write_text("seen")

    shop = ShopConfig(2026, 8)
    dialog = EmployeeDialog(None, shop_config=shop)
    dialog._maybe_show_tutorial()

    assert getattr(dialog, "_tutorial_overlay", None) is None


def test_help_button_reopens_tutorial_without_touching_the_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    flag_path = tmp_path / EMPLOYEE_TUTORIAL_FLAG
    flag_path.write_text("seen")

    shop = ShopConfig(2026, 8)
    dialog = EmployeeDialog(None, shop_config=shop)

    dialog._open_tutorial()

    assert not dialog._tutorial_overlay.isHidden()
    assert flag_path.read_text() == "seen"
