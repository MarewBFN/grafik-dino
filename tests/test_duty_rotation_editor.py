"""ui/duty_rotation_editor.py::DutyRotationEditor - the only UI (Lokalizacje,
podpięta wprost pod checkbox "Działalność całodobowa (24/7)" - decyzja z
użytkownikiem 2026-09-21, żadnego osobnego przełącznika) that can configure
LocationConfig.duty_rotation. Covers get/set round-trip, automatic
complementary-window fill (only one time range is entered per week-type, the
other half and weekend_full's start are derived), only_12_24h hiding the
weekday split, and validation errors surfacing from normalize_duty_rotation().

The widget itself has no "enabled" concept anymore - visibility and whether
get_duty_rotation() is even called is entirely up to the embedding dialog
(see ui/locations_dialog.py::_LocationRow._update_hours_visibility/_save)."""

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

from ui.duty_rotation_editor import DutyRotationEditor


class DutyRotationEditorDefaultsTests(unittest.TestCase):
    def test_no_duty_rotation_falls_back_to_sensible_defaults(self):
        editor = DutyRotationEditor(None)
        self.assertEqual(editor.weekday_start.get_time_str(), "09:00")
        self.assertEqual(editor.weekday_end.get_time_str(), "17:00")
        self.assertEqual(editor.weekend_start.get_time_str(), "08:00")
        self.assertEqual(editor.weekend_end.get_time_str(), "20:00")
        self.assertFalse(editor.only_12_24h_check.isChecked())

    def test_weekday_fields_visible_by_default(self):
        editor = DutyRotationEditor(None)
        self.assertFalse(editor.weekday_container.isHidden())


class DutyRotationEditorRoundTripTests(unittest.TestCase):
    ROTATION = {
        "weekday_long": {"start": "09:00", "end": "17:00"},
        "weekday_short": {"start": "17:00", "end": "09:00"},
        "weekend_half_a": {"start": "08:00", "end": "20:00"},
        "weekend_half_b": {"start": "20:00", "end": "08:00"},
        "weekend_full": {"start": "08:00"},
        "only_12_24h": False,
    }

    def test_get_duty_rotation_matches_what_was_set(self):
        editor = DutyRotationEditor(self.ROTATION)
        self.assertEqual(editor.get_duty_rotation(), self.ROTATION)

    def test_weekend_full_start_always_mirrors_weekend_half_a_start(self):
        editor = DutyRotationEditor(None)
        editor.weekend_start.set_time_str("06:00")
        editor.weekend_end.set_time_str("18:00")
        editor.weekday_start.set_time_str("07:00")
        editor.weekday_end.set_time_str("15:00")

        rotation = editor.get_duty_rotation()

        self.assertEqual(rotation["weekend_full"]["start"], "06:00")
        self.assertEqual(rotation["weekend_half_a"], {"start": "06:00", "end": "18:00"})

    def test_second_shift_of_each_pair_is_derived_as_the_complement(self):
        editor = DutyRotationEditor(None)
        editor.weekday_start.set_time_str("08:00")
        editor.weekday_end.set_time_str("16:00")
        editor.weekend_start.set_time_str("06:00")
        editor.weekend_end.set_time_str("18:00")

        rotation = editor.get_duty_rotation()

        self.assertEqual(rotation["weekday_short"], {"start": "16:00", "end": "08:00"})
        self.assertEqual(rotation["weekend_half_b"], {"start": "18:00", "end": "06:00"})

    def test_only_12_24h_hides_weekday_fields_and_omits_weekday_keys(self):
        editor = DutyRotationEditor(dict(self.ROTATION, only_12_24h=True))
        self.assertTrue(editor.only_12_24h_check.isChecked())
        self.assertTrue(editor.weekday_container.isHidden())

        rotation = editor.get_duty_rotation()
        self.assertNotIn("weekday_long", rotation)
        self.assertNotIn("weekday_short", rotation)
        self.assertTrue(rotation["only_12_24h"])

    def test_toggling_only_12_24h_live_hides_and_reveals_weekday_fields(self):
        editor = DutyRotationEditor(self.ROTATION)
        self.assertFalse(editor.weekday_container.isHidden())

        editor.only_12_24h_check.setChecked(True)
        self.assertTrue(editor.weekday_container.isHidden())

        editor.only_12_24h_check.setChecked(False)
        self.assertFalse(editor.weekday_container.isHidden())


class DutyRotationEditorValidationTests(unittest.TestCase):
    def test_identical_weekend_start_and_end_raises(self):
        editor = DutyRotationEditor(None)
        editor.weekend_start.set_time_str("08:00")
        editor.weekend_end.set_time_str("08:00")

        with self.assertRaises(ValueError):
            editor.get_duty_rotation()

    def test_identical_weekday_start_and_end_raises(self):
        editor = DutyRotationEditor(None)
        editor.weekday_start.set_time_str("09:00")
        editor.weekday_end.set_time_str("09:00")

        with self.assertRaises(ValueError):
            editor.get_duty_rotation()


if __name__ == "__main__":
    unittest.main()
