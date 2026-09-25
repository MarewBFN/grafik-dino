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
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QDialog

_app = QApplication.instance() or QApplication([])

from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from ui.day_override_dialog import DayOverrideDialog
from ui.weekly_hours_editor import WeeklyHoursEditor
from model.shop_config import ShopConfig
from ui.main_window import MainWindow


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

    def test_closed_check_sits_above_the_hours_form_in_the_layout(self):
        shop = ShopConfig(2026, 8)
        dialog = DayOverrideDialog(None, 3, ("08:00", "20:00"), shop)

        root = dialog.layout()
        checkbox_index = next(
            i for i in range(root.count()) if root.itemAt(i).widget() is dialog.closed_check
        )
        form_index = next(
            i for i in range(root.count()) if root.itemAt(i).widget() is dialog.hours_form_widget
        )
        self.assertLess(checkbox_index, form_index)

    def test_hours_form_hidden_when_closed_is_checked(self):
        shop = ShopConfig(2026, 8)
        dialog = DayOverrideDialog(None, 3, (None, None), shop)
        self.assertTrue(dialog.hours_form_widget.isHidden())

        dialog.closed_check.setChecked(False)
        self.assertFalse(dialog.hours_form_widget.isHidden())

        dialog.closed_check.setChecked(True)
        self.assertTrue(dialog.hours_form_widget.isHidden())

    def test_closed_day_prefills_fallback_hours_instead_of_zeros_when_reopened(self):
        shop = ShopConfig(2026, 8)
        dialog = DayOverrideDialog(None, 3, (None, None), shop, fallback_hours=("09:00", "18:00"))

        self.assertEqual(dialog.start_edit.get_time_str(), "09:00")
        self.assertEqual(dialog.end_edit.get_time_str(), "18:00")

        dialog.closed_check.setChecked(False)

        self.assertEqual(dialog.start_edit.get_time_str(), "09:00")
        self.assertEqual(dialog.end_edit.get_time_str(), "18:00")


class HeaderMenuDoesNotMaskAClosedDayTests(unittest.TestCase):
    """ui/main_window.py::_open_header_menu used to fall back to the
    weekday's regular open_hours whenever get_open_hours_for_day() returned
    None (holiday, "Nieczynne" in the weekly pattern, non-trade Sunday) -
    silently masking the real closed status, so DayOverrideDialog showed
    normal hours instead of auto-checking "Nieczynne tego dnia" - reported
    by the user (2026-09-25)."""

    def _make_window(self, shop, schedule, location_key):
        window = MainWindow.__new__(MainWindow)
        window.shop_config = shop
        window.schedule = schedule
        window.selected_location_key = location_key
        window.controller = MagicMock()
        window._update_nominal_hours_label = MagicMock()
        window._sync_grid = MagicMock()
        window.statusBar = MagicMock(return_value=MagicMock())
        return window

    def test_closed_weekday_passes_none_hours_not_the_weekly_pattern(self):
        shop = ShopConfig(2026, 8)
        loc = LocationConfig(key="site1", name="Site 1")
        loc.open_hours[0] = (None, None)  # 2026-08-03 (Monday) marked "Nieczynne"
        shop.locations["site1"] = loc
        schedule = MonthSchedule(2026, 8)
        window = self._make_window(shop, schedule, "site1")

        fake_dialog = MagicMock()
        fake_dialog.exec.return_value = QDialog.Rejected
        with patch("ui.main_window.DayOverrideDialog", return_value=fake_dialog) as mock_dialog:
            window._open_header_menu(3, None)

        args, kwargs = mock_dialog.call_args
        self.assertEqual(args[2], (None, None))

    def test_open_weekday_still_passes_its_real_hours(self):
        shop = ShopConfig(2026, 8)
        loc = LocationConfig(key="site1", name="Site 1")
        loc.open_hours[0] = ("08:00", "20:00")
        shop.locations["site1"] = loc
        schedule = MonthSchedule(2026, 8)
        window = self._make_window(shop, schedule, "site1")

        fake_dialog = MagicMock()
        fake_dialog.exec.return_value = QDialog.Rejected
        with patch("ui.main_window.DayOverrideDialog", return_value=fake_dialog) as mock_dialog:
            window._open_header_menu(3, None)

        args, kwargs = mock_dialog.call_args
        self.assertEqual(args[2], ("08:00", "20:00"))

    def test_fallback_hours_kwarg_carries_the_weekly_pattern_even_when_the_day_is_closed(self):
        """np. dzień zamknięty przez konkretne nadpisanie (day_override) na
        lokalizacji, której zwykły wzorzec tygodniowy tego dnia tygodnia
        jest normalnie otwarty - current_hours (przekazane pozycyjnie) musi
        pokazać prawdziwe zamknięcie, ale fallback_hours ma zostać
        podpowiedzią do odznaczenia "Nieczynne", nie też None/None."""
        shop = ShopConfig(2026, 8)
        loc = LocationConfig(key="site1", name="Site 1")
        loc.open_hours[0] = ("09:00", "17:00")  # zwykły wzorzec poniedziałku
        loc.day_overrides[3] = (None, None)  # ale 2026-08-03 jawnie zamknięte
        shop.locations["site1"] = loc
        schedule = MonthSchedule(2026, 8)
        window = self._make_window(shop, schedule, "site1")

        fake_dialog = MagicMock()
        fake_dialog.exec.return_value = QDialog.Rejected
        with patch("ui.main_window.DayOverrideDialog", return_value=fake_dialog) as mock_dialog:
            window._open_header_menu(3, None)

        args, kwargs = mock_dialog.call_args
        self.assertEqual(args[2], (None, None))
        self.assertEqual(kwargs.get("fallback_hours"), ("09:00", "17:00"))


if __name__ == "__main__":
    unittest.main()
