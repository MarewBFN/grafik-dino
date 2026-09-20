""""Nieczynne" (closed) per-day toggle - WeeklyHoursEditor (shared by
Konfiguracja -> "Godziny otwarcia" and the Lokalizacje dialog, see
ui/weekly_hours_editor.py) and DayOverrideDialog (grid_view's single-day
header edit, see ui/day_override_dialog.py). Both must be able to represent
a closed day as (None, None), the convention get_open_hours_for_day() in
model/shop_config.py and model/location.py already understood, but which
neither UI could previously produce."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from ui.day_override_dialog import DayOverrideDialog
from ui.weekly_hours_editor import WeeklyHoursEditor
from model.shop_config import ShopConfig


class WeeklyHoursEditorClosedDayTests(unittest.TestCase):
    def test_checking_closed_returns_none_hours_for_that_day(self):
        editor = WeeklyHoursEditor({0: ("08:00", "20:00")})
        editor._closed_checks[0].setChecked(True)

        hours = editor.get_hours()

        self.assertEqual(hours[0], (None, None))

    def test_unchecked_day_keeps_its_hours(self):
        editor = WeeklyHoursEditor({0: ("08:00", "20:00")})

        hours = editor.get_hours()

        self.assertEqual(hours[0], ("08:00", "20:00"))

    def test_closed_day_disables_time_inputs(self):
        editor = WeeklyHoursEditor({0: ("08:00", "20:00")})
        editor._closed_checks[0].setChecked(True)

        start_edit, end_edit = editor._edits[0]
        self.assertFalse(start_edit.isEnabled())
        self.assertFalse(end_edit.isEnabled())

    def test_set_hours_with_none_preselects_closed_checkbox(self):
        editor = WeeklyHoursEditor({0: (None, None)})

        self.assertTrue(editor._closed_checks[0].isChecked())
        self.assertEqual(editor.get_hours()[0], (None, None))

    def test_other_days_unaffected_by_one_closed_day(self):
        editor = WeeklyHoursEditor({0: (None, None), 1: ("08:00", "20:00")})

        hours = editor.get_hours()

        self.assertEqual(hours[0], (None, None))
        self.assertEqual(hours[1], ("08:00", "20:00"))


class DayOverrideDialogClosedDayTests(unittest.TestCase):
    def test_saving_closed_day_returns_none_hours(self):
        shop = ShopConfig(2026, 8)
        dialog = DayOverrideDialog(None, 3, ("08:00", "20:00"), shop)
        dialog.closed_check.setChecked(True)
        dialog.accept = lambda: None

        dialog._save()

        self.assertEqual(dialog.result_mode, "save")
        self.assertIsNone(dialog.result_start)
        self.assertIsNone(dialog.result_end)

    def test_already_closed_day_preselects_checkbox(self):
        shop = ShopConfig(2026, 8)
        dialog = DayOverrideDialog(None, 3, (None, None), shop)

        self.assertTrue(dialog.closed_check.isChecked())

    def test_normal_hours_day_does_not_preselect_checkbox(self):
        shop = ShopConfig(2026, 8)
        dialog = DayOverrideDialog(None, 3, ("08:00", "20:00"), shop)

        self.assertFalse(dialog.closed_check.isChecked())

    def test_unchecking_closed_reenables_time_inputs_and_saves_hours(self):
        shop = ShopConfig(2026, 8)
        dialog = DayOverrideDialog(None, 3, (None, None), shop)
        dialog.closed_check.setChecked(False)
        dialog.start_edit.set_time_str("09:00")
        dialog.end_edit.set_time_str("17:00")
        dialog.accept = lambda: None

        dialog._save()

        self.assertEqual((dialog.result_start, dialog.result_end), ("09:00", "17:00"))


if __name__ == "__main__":
    unittest.main()
