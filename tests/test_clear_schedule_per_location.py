"""Edycja -> "Wyczyść grafik" / "Wyczyść auto" (MainWindow._clear_schedule /
_clear_generated) czyszczą tylko obecnie wybraną placówkę - pozostałe
placówki projektu zostają nietknięte (tak samo jak "Generuj grafik")."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QMessageBox

_app = QApplication.instance() or QApplication([])

from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from ui.main_window import MainWindow


class ClearSchedulePerLocationTests(unittest.TestCase):
    def setUp(self):
        self.shop = ShopConfig(2026, 8)
        self.shop.locations["a"] = LocationConfig(key="a", name="Placówka A")
        self.shop.locations["b"] = LocationConfig(key="b", name="Placówka B")
        self.schedule = MonthSchedule(2026, 8)
        self.emp_a = Employee(last_name="Nowak", first_name="Anna", location_key="a")
        self.emp_b = Employee(last_name="Kowal", first_name="Jan", location_key="b")
        for emp in (self.emp_a, self.emp_b):
            self.schedule.add_employee(emp)
            for day, locked in ((1, False), (2, True)):
                ds = self.schedule.get_day(emp, day)
                ds.start, ds.end, ds.is_locked = "08:00", "16:00", locked
            self.schedule.set_settlement_target(emp, 600)

    def _make_window(self, location_key):
        window = MainWindow.__new__(MainWindow)
        window.shop_config = self.shop
        window.schedule = self.schedule
        window.selected_location_key = location_key
        window.controller = MagicMock()
        window._sync_everything = MagicMock()
        window.statusBar = MagicMock(return_value=MagicMock())
        return window

    def _run(self, method_name, location_key="a"):
        window = self._make_window(location_key)
        with patch("ui.main_window.QMessageBox.question", return_value=QMessageBox.Yes) as q:
            getattr(window, method_name)()
        return q

    def _assert_untouched(self, emp):
        for day in (1, 2):
            self.assertEqual(self.schedule.get_day(emp, day).start, "08:00")
        self.assertEqual(self.schedule.get_settlement_target(emp), 600)

    def test_clear_schedule_only_clears_selected_location(self):
        q = self._run("_clear_schedule")
        for day in (1, 2):
            ds = self.schedule.get_day(self.emp_a, day)
            self.assertIsNone(ds.start)
            self.assertFalse(ds.is_locked)
        self.assertIsNone(self.schedule.get_settlement_target(self.emp_a))
        self._assert_untouched(self.emp_b)
        self.assertIn("Placówka A", q.call_args[0][2])

    def test_clear_generated_only_clears_selected_location(self):
        q = self._run("_clear_generated")
        self.assertIsNone(self.schedule.get_day(self.emp_a, 1).start)
        self.assertEqual(self.schedule.get_day(self.emp_a, 2).start, "08:00")
        self._assert_untouched(self.emp_b)
        self.assertIn("Placówka A", q.call_args[0][2])

    def test_without_locations_clears_whole_project(self):
        self.shop.locations.clear()
        self._run("_clear_schedule", location_key=None)
        for emp in (self.emp_a, self.emp_b):
            self.assertIsNone(self.schedule.get_day(emp, 1).start)


if __name__ == "__main__":
    unittest.main()
