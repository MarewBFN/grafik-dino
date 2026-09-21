"""ui/duty_rotation_editor.py::DutyRotationEditor - the only UI (Lokalizacje
i Konfiguracja -> Godziny otwarcia) that can configure LocationConfig.
duty_rotation. Covers get/set round-trip, automatic complementary-window
fill (only one time range is entered per week-type, the other half and
weekend_full's start are derived), only_12_24h hiding the weekday split,
and validation errors surfacing from normalize_duty_rotation()."""

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


class DutyRotationEditorDisabledByDefaultTests(unittest.TestCase):
    def test_no_duty_rotation_means_disabled_and_returns_none(self):
        editor = DutyRotationEditor(None)
        self.assertFalse(editor.enabled_check.isChecked())
        self.assertIsNone(editor.get_duty_rotation())

    def test_weekday_and_weekend_fields_hidden_when_disabled(self):
        editor = DutyRotationEditor(None)
        self.assertTrue(editor.weekday_container.isHidden())
        self.assertTrue(editor.weekend_container.isHidden())
        self.assertTrue(editor.only_12_24h_check.isHidden())


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
        self.assertTrue(editor.enabled_check.isChecked())
        self.assertEqual(editor.get_duty_rotation(), self.ROTATION)

    def test_weekend_full_start_always_mirrors_weekend_half_a_start(self):
        editor = DutyRotationEditor(None)
        editor.enabled_check.setChecked(True)
        editor.weekend_start.set_time_str("06:00")
        editor.weekend_end.set_time_str("18:00")
        editor.weekday_start.set_time_str("07:00")
        editor.weekday_end.set_time_str("15:00")

        rotation = editor.get_duty_rotation()

        self.assertEqual(rotation["weekend_full"]["start"], "06:00")
        self.assertEqual(rotation["weekend_half_a"], {"start": "06:00", "end": "18:00"})

    def test_second_shift_of_each_pair_is_derived_as_the_complement(self):
        editor = DutyRotationEditor(None)
        editor.enabled_check.setChecked(True)
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
        self.assertFalse(editor.weekend_container.isHidden())

        rotation = editor.get_duty_rotation()
        self.assertNotIn("weekday_long", rotation)
        self.assertNotIn("weekday_short", rotation)
        self.assertTrue(rotation["only_12_24h"])

    def test_toggling_enabled_off_hides_everything_and_returns_none(self):
        editor = DutyRotationEditor(self.ROTATION)
        editor.enabled_check.setChecked(False)

        self.assertIsNone(editor.get_duty_rotation())
        self.assertTrue(editor.weekday_container.isHidden())
        self.assertTrue(editor.weekend_container.isHidden())
        self.assertTrue(editor.only_12_24h_check.isHidden())


class DutyRotationEditorValidationTests(unittest.TestCase):
    def test_identical_weekend_start_and_end_raises(self):
        editor = DutyRotationEditor(None)
        editor.enabled_check.setChecked(True)
        editor.weekend_start.set_time_str("08:00")
        editor.weekend_end.set_time_str("08:00")

        with self.assertRaises(ValueError):
            editor.get_duty_rotation()

    def test_identical_weekday_start_and_end_raises(self):
        editor = DutyRotationEditor(None)
        editor.enabled_check.setChecked(True)
        editor.weekday_start.set_time_str("09:00")
        editor.weekday_end.set_time_str("09:00")

        with self.assertRaises(ValueError):
            editor.get_duty_rotation()


if __name__ == "__main__":
    unittest.main()
