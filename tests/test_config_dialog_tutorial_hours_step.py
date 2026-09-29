"""ConfigDialog's "Godziny otwarcia" tutorial step (ui/config_dialog.py::
ConfigDialog._build_tutorial_steps) went stale after this session's UI/UX
round: that tab now edits the CURRENTLY SELECTED location's hours directly
(see tests/test_location_hours_editing_ui.py) instead of a separate,
project-wide set - the step text must explain that, not the old behavior."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from model.location import LocationConfig
from model.shop_config import ShopConfig
from ui.config_dialog import ConfigDialog


def _hours_step(dialog):
    steps = dialog._build_tutorial_steps()
    return next(s for s in steps if s.title == "Godziny otwarcia")


def test_hours_step_mentions_the_selected_location_when_one_is_given():
    shop = ShopConfig(2026, 8)
    loc = LocationConfig(key="site1", name="Site 1")
    shop.locations["site1"] = loc

    dialog = ConfigDialog(None, shop, location_key="site1")

    step = _hours_step(dialog)
    assert "lokalizacj" in step.text.lower()
    assert "Lokalizacje" in step.text


def test_hours_step_falls_back_to_generic_text_without_a_location():
    shop = ShopConfig(2026, 8)

    dialog = ConfigDialog(None, shop)

    step = _hours_step(dialog)
    assert step.text.strip()
