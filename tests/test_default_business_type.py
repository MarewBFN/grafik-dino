"""ui/main_window.py::MainWindow._apply_default_visible_business_type - a
freshly constructed MainWindow (no last_project.json, wizard not yet
completed/cancelled) must never sit on the bare ShopConfig() default
(dino_retail) - on the "enyo" release channel that profile is excluded from
visible_profiles() and would show Otwarcie/Zamknięcie/Mięso summary rows
that make no sense for this client (see ENYO_ONLY_CHANGES.md). On every
other channel (default: "dino") dino_retail IS the correct default, so
these tests specifically exercise the enyo-channel behavior."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

import model.business_profile as bp
from model.business_profile import DEFAULT_BUSINESS_TYPE


def _window_in_tmp_dir(tmp_dir):
    from ui.main_window import MainWindow

    cwd = os.getcwd()
    os.chdir(tmp_dir)
    try:
        with patch.object(bp, "RELEASE_CHANNEL", "enyo"):
            return MainWindow()
    finally:
        os.chdir(cwd)


class DefaultBusinessTypeTests(unittest.TestCase):
    def test_fresh_window_never_defaults_to_dino_retail(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            window = _window_in_tmp_dir(tmp_dir)

            self.assertNotEqual(window.shop_config.business_type, DEFAULT_BUSINESS_TYPE)
            with patch.object(bp, "RELEASE_CHANNEL", "enyo"):
                self.assertEqual(window.shop_config.business_type, bp.visible_profiles()[0].key)

    def test_fresh_window_grid_hides_dino_only_summary_rows(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            window = _window_in_tmp_dir(tmp_dir)

            keys = [key for _, key in window.grid._summary_rows()]
            self.assertNotIn("open", keys)
            self.assertNotIn("close", keys)
            self.assertNotIn("meat", keys)
            self.assertIn("coverage", keys)


if __name__ == "__main__":
    unittest.main()
