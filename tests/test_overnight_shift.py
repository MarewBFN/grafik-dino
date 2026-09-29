from pathlib import Path
import sys
import unittest
from datetime import timedelta

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model.day_schedule import DaySchedule
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from persistence.project_io import save_project, load_project


class DayScheduleOvernightTests(unittest.TestCase):
    """Etap A: fundament pod zmiany nocne (przechodzące przez północ)."""

    def test_set_hours_accepts_overnight_range(self):
        ds = DaySchedule()
        ds.set_hours("22:00", "06:00")

        self.assertEqual(ds.start, "22:00")
        self.assertEqual(ds.end, "06:00")

    def test_overnight_duration_is_eight_hours(self):
        ds = DaySchedule()
        ds.set_hours("22:00", "06:00")

        self.assertEqual(ds.total_duration(), timedelta(hours=8))
        self.assertEqual(ds.total_as_str(), "8:00")
        self.assertEqual(ds.total_minutes(), 480)

    def test_crosses_midnight_flag(self):
        overnight = DaySchedule()
        overnight.set_hours("22:00", "06:00")
        self.assertTrue(overnight.crosses_midnight())

        same_day = DaySchedule()
        same_day.set_hours("08:00", "16:00")
        self.assertFalse(same_day.crosses_midnight())

        empty = DaySchedule()
        self.assertFalse(empty.crosses_midnight())

    def test_equal_start_end_still_rejected(self):
        ds = DaySchedule()
        with self.assertRaises(ValueError):
            ds.set_hours("22:00", "22:00")

    def test_same_day_shift_behavior_unchanged(self):
        ds = DaySchedule()
        ds.set_hours("08:00", "16:00")

        self.assertEqual(ds.total_duration(), timedelta(hours=8))
        self.assertEqual(ds.as_rows(), ("08:00", "16:00", "8:00"))

    def test_project_round_trip_preserves_overnight_hours(self, tmp_path=None):
        import tempfile
        import os

        shop = ShopConfig(2026, 8)
        schedule = MonthSchedule(2026, 8)
        emp = Employee("Kowalski", "Jan")
        schedule.add_employee(emp)
        schedule.get_day(emp, 1).set_hours("22:00", "06:00")

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "project.json")
            save_project(path, schedule, shop)
            loaded_schedule, _ = load_project(path)

        loaded_emp = loaded_schedule.employees[0]
        loaded_day = loaded_schedule.get_day(loaded_emp, 1)

        self.assertEqual(loaded_day.start, "22:00")
        self.assertEqual(loaded_day.end, "06:00")
        self.assertEqual(loaded_day.total_duration(), timedelta(hours=8))


if __name__ == "__main__":
    unittest.main()
