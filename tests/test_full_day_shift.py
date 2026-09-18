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


class DayScheduleFullDayShiftTests(unittest.TestCase):
    """Etap A "plan profil ochrona": fundament pod zmianę 24h (służba
    ochrony) - end == start jest niejednoznaczne dla set_hours() (zero
    minut vs cała doba), więc potrzebuje własnego, jawnego setera."""

    def test_set_full_day_shift_sets_equal_start_and_end(self):
        ds = DaySchedule()
        ds.set_full_day_shift("06:00")

        self.assertEqual(ds.start, "06:00")
        self.assertEqual(ds.end, "06:00")
        self.assertTrue(ds.is_full_day)

    def test_full_day_duration_is_24_hours(self):
        ds = DaySchedule()
        ds.set_full_day_shift("06:00")

        self.assertEqual(ds.total_duration(), timedelta(hours=24))
        self.assertEqual(ds.total_as_str(), "24:00")
        self.assertEqual(ds.total_minutes(), 1440)

    def test_full_day_shift_crosses_midnight(self):
        ds = DaySchedule()
        ds.set_full_day_shift("06:00")
        self.assertTrue(ds.crosses_midnight())

    def test_plain_set_hours_with_equal_start_end_still_rejected(self):
        """set_full_day_shift() istnieje właśnie dlatego, że set_hours() z
        end == start pozostaje - i musi pozostać - błędem (niejednoznaczne
        bez tej jawnej flagi)."""
        ds = DaySchedule()
        with self.assertRaises(ValueError):
            ds.set_hours("06:00", "06:00")

    def test_switching_away_from_full_day_clears_the_flag(self):
        ds = DaySchedule()
        ds.set_full_day_shift("06:00")

        ds.set_hours("08:00", "16:00")
        self.assertFalse(ds.is_full_day)
        self.assertEqual(ds.total_duration(), timedelta(hours=8))

        ds.set_full_day_shift("06:00")
        ds.set_free()
        self.assertFalse(ds.is_full_day)
        self.assertTrue(ds.is_empty())

        ds.set_full_day_shift("06:00")
        ds.set_leave()
        self.assertFalse(ds.is_full_day)

        ds.set_full_day_shift("06:00")
        ds.set_sick()
        self.assertFalse(ds.is_full_day)

    def test_stale_flag_on_an_emptied_day_is_harmless(self):
        """Wiele miejsc w kodzie (poza DaySchedule) czyści start/end wprost
        (ds.start = None; ds.end = None) bez przechodzenia przez
        set_free()/set_leave() - is_full_day może zostać nietknięte, ale
        crosses_midnight()/total_duration() muszą i tak zwrócić "pusty
        dzień", nie zachowywać się tak, jakby to była zmiana 24h."""
        ds = DaySchedule()
        ds.set_full_day_shift("06:00")

        ds.start = None
        ds.end = None

        self.assertTrue(ds.is_empty())
        self.assertFalse(ds.crosses_midnight())
        self.assertIsNone(ds.total_duration())

    def test_same_day_shift_behavior_unchanged(self):
        ds = DaySchedule()
        ds.set_hours("08:00", "16:00")

        self.assertFalse(ds.is_full_day)
        self.assertEqual(ds.total_duration(), timedelta(hours=8))

    def test_project_round_trip_preserves_full_day_shift(self):
        import tempfile
        import os

        shop = ShopConfig(2026, 8)
        schedule = MonthSchedule(2026, 8)
        emp = Employee("Kowalski", "Jan")
        schedule.add_employee(emp)
        schedule.get_day(emp, 1).set_full_day_shift("06:00")

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "project.json")
            save_project(path, schedule, shop)
            loaded_schedule, _ = load_project(path)

        loaded_emp = loaded_schedule.employees[0]
        loaded_day = loaded_schedule.get_day(loaded_emp, 1)

        self.assertEqual(loaded_day.start, "06:00")
        self.assertEqual(loaded_day.end, "06:00")
        self.assertTrue(loaded_day.is_full_day)
        self.assertEqual(loaded_day.total_duration(), timedelta(hours=24))


if __name__ == "__main__":
    unittest.main()
