import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from ui.time_input import TimeInputWidget


def test_typing_24_00_is_normalized_to_00_00():
    widget = TimeInputWidget()
    widget.input.setText("2400")
    assert widget.get_time_str() == "00:00"


def test_typing_2400_partway_normalizes_the_hour_immediately():
    widget = TimeInputWidget()
    widget.input.setText("24")
    assert widget.input.text() == "00"


def test_typing_240_normalizes_hour_while_minute_is_incomplete():
    widget = TimeInputWidget()
    widget.input.setText("240")
    assert widget.input.text() == "00:0"


def test_set_time_str_24_00_is_normalized_to_00_00():
    widget = TimeInputWidget()
    widget.set_time_str("24:00")
    assert widget.get_time_str() == "00:00"


def test_normal_hours_are_unaffected():
    widget = TimeInputWidget()
    widget.set_time_str("22:30")
    assert widget.get_time_str() == "22:30"

    widget.input.setText("1345")
    assert widget.get_time_str() == "13:45"
