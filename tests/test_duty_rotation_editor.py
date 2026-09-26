"""ui/duty_rotation_editor.py::DutyRotationEditor - the only UI (Lokalizacje,
podpięta wprost pod checkbox "Działalność całodobowa (24/7)" - decyzja z
użytkownikiem 2026-09-21, żadnego osobnego przełącznika) that can configure
LocationConfig.duty_rotation. Uproszczony edytor (2026-09-25): godzina
rozpoczęcia doby + godzina podziału + "Preferuj zmiany 24h" - zawsze
only_12_24h, ten sam schemat każdego dnia. Covers defaults, round-trip,
reading older rotation dicts, the split following the start hour, and
validation errors surfacing from normalize_duty_rotation().

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

from ui.duty_rotation_editor import DutyRotationEditor, rotation_start_and_split


class DutyRotationEditorDefaultsTests(unittest.TestCase):
    def test_no_duty_rotation_falls_back_to_08_and_20(self):
        editor = DutyRotationEditor(None)
        self.assertEqual(editor.start_input.get_time_str(), "08:00")
        self.assertEqual(editor.split_input.get_time_str(), "20:00")
        self.assertFalse(editor.prefer_24h_check.isChecked())

    def test_default_rotation_is_one_consistent_day_pattern(self):
        rotation = DutyRotationEditor(None).get_duty_rotation()
        self.assertEqual(rotation, {
            "weekend_half_a": {"start": "08:00", "end": "20:00"},
            "weekend_half_b": {"start": "20:00", "end": "08:00"},
            "weekend_full": {"start": "08:00"},
            "only_12_24h": True,
        })


class DutyRotationEditorRoundTripTests(unittest.TestCase):
    def test_start_split_and_prefer_24h_round_trip(self):
        editor = DutyRotationEditor(None)
        editor.start_input.set_time_str("07:00")
        editor.split_input.set_time_str("15:00")
        editor.prefer_24h_check.setChecked(True)

        rotation = editor.get_duty_rotation()

        self.assertEqual(rotation["weekend_full"], {"start": "07:00"})
        self.assertEqual(rotation["weekend_half_a"], {"start": "07:00", "end": "15:00"})
        self.assertEqual(rotation["weekend_half_b"], {"start": "15:00", "end": "07:00"})
        self.assertTrue(rotation["only_12_24h"])
        self.assertTrue(rotation["prefer_24h"])

        reopened = DutyRotationEditor(rotation)
        self.assertEqual(reopened.get_duty_rotation(), rotation)

    def test_24h_shift_always_starts_at_the_start_of_the_day(self):
        """Dawny błąd: podział wpisany "20:00 - 08:00" dawał zmianę 24h od
        20:00, a połówki - dobę od 08:00 (12h luki + 12h podwójnie)."""
        editor = DutyRotationEditor(None)
        editor.start_input.set_time_str("08:00")
        editor.split_input.set_time_str("20:00")
        rotation = editor.get_duty_rotation()
        self.assertEqual(rotation["weekend_full"]["start"], "08:00")
        starts = {rotation["weekend_half_a"]["start"], rotation["weekend_half_b"]["start"]}
        self.assertEqual(min(starts), rotation["weekend_full"]["start"])

    def test_split_follows_start_until_changed_by_hand(self):
        editor = DutyRotationEditor(None)
        editor.start_input.input.setText("0700")
        self.assertEqual(editor.split_input.get_time_str(), "19:00")

        editor.split_input.input.setText("1500")
        editor.start_input.input.setText("0600")
        self.assertEqual(editor.split_input.get_time_str(), "15:00")


class RotationStartAndSplitTests(unittest.TestCase):
    def test_client_gzuk_rotation_with_16h_and_8h_halves(self):
        rotation = {
            "weekend_full": {"start": "07:00"},
            "weekend_half_a": {"start": "15:00", "end": "07:00"},
            "weekend_half_b": {"start": "07:00", "end": "15:00"},
            "only_12_24h": True,
        }
        self.assertEqual(rotation_start_and_split(rotation), ("07:00", "15:00"))

    def test_older_weekday_pattern_reads_the_weekend_part(self):
        rotation = {
            "weekday_long": {"start": "09:00", "end": "17:00"},
            "weekday_short": {"start": "17:00", "end": "09:00"},
            "weekend_half_a": {"start": "08:00", "end": "20:00"},
            "weekend_half_b": {"start": "20:00", "end": "08:00"},
            "weekend_full": {"start": "08:00"},
            "only_12_24h": False,
        }
        self.assertEqual(rotation_start_and_split(rotation), ("08:00", "20:00"))

    def test_none(self):
        self.assertEqual(rotation_start_and_split(None), ("08:00", "20:00"))


class DutyRotationEditorValidationTests(unittest.TestCase):
    def test_split_equal_to_start_raises(self):
        editor = DutyRotationEditor(None)
        editor.start_input.set_time_str("08:00")
        editor.split_input.set_time_str("08:00")

        with self.assertRaises(ValueError):
            editor.get_duty_rotation()


if __name__ == "__main__":
    unittest.main()
