"""ui/demo_manager.py::DemoManager.show_after_generate - dostał opcjonalny
extra_note (patrz ui/main_window.py::_previous_month_memory_note), żeby
wersja demo też informowała o pominiętej pamięci poprzedniego miesiąca,
tak samo jak pełna wersja."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from ui.demo_manager import DemoManager


class ShowAfterGenerateTests(unittest.TestCase):
    def _manager(self):
        manager = DemoManager.__new__(DemoManager)
        manager.is_demo = True
        return manager

    def test_plain_message_without_a_note(self):
        manager = self._manager()
        with patch("ui.demo_manager.QMessageBox") as mock_box:
            manager.show_after_generate(None)

        message = mock_box.information.call_args.args[2]
        self.assertNotIn("poprzedniego miesiąca", message)

    def test_note_is_appended_when_present(self):
        manager = self._manager()
        with patch("ui.demo_manager.QMessageBox") as mock_box:
            manager.show_after_generate(None, extra_note="Uwaga: brak pamięci poprzedniego miesiąca.")

        message = mock_box.information.call_args.args[2]
        self.assertIn("Uwaga: brak pamięci poprzedniego miesiąca.", message)

    def test_no_dialog_outside_demo_mode(self):
        manager = self._manager()
        manager.is_demo = False
        with patch("ui.demo_manager.QMessageBox") as mock_box:
            manager.show_after_generate(None, extra_note="cokolwiek")

        mock_box.information.assert_not_called()


if __name__ == "__main__":
    unittest.main()
