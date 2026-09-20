"""ScheduleController.copy_day_snapshot()/paste_day_snapshot() - the shared
copy/paste implementation used by ui/grid_view.py's Ctrl+C/Ctrl+V and its
right-click "Kopiuj dzień"/"Wklej dzień". Before this, paste only ever
carried start/end through controller.set_day_hours(), silently losing
urlop/L4/wolne/zmiana pełnodobowa (24h)/zablokowany typ zmiany on paste, and
rejecting night shifts unless they matched the destination's exact
configured window."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.schedule_controller import ScheduleController
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig

NIGHT_HOURS = ("22:00", "06:00")


def _controller_with_night_location():
    shop = ShopConfig(2026, 8)
    # Default open_hours already overlap 22:00-06:00 (see LocationConfig.get_night_shift_hours).
    loc = LocationConfig(key="site1", name="Site 1")
    shop.locations["site1"] = loc
    schedule = MonthSchedule(2026, 8)
    emp = Employee(last_name="Kowalski", first_name="Jan", location_key="site1")
    schedule.add_employee(emp)
    return ScheduleController(schedule, shop), emp


class CopyPasteDayTests(unittest.TestCase):
    def test_plain_hours_round_trip(self):
        controller, emp = _controller_with_night_location()
        controller.set_day_hours(emp, 3, "08:00", "16:00")

        snapshot = controller.copy_day_snapshot(emp, 3)
        controller.paste_day_snapshot(emp, 5, snapshot)

        pasted = controller.get_day(emp, 5)
        self.assertEqual((pasted.start, pasted.end), ("08:00", "16:00"))

    def test_night_shift_round_trip_within_same_location(self):
        controller, emp = _controller_with_night_location()
        controller.set_day_hours(emp, 3, *NIGHT_HOURS)

        snapshot = controller.copy_day_snapshot(emp, 3)
        controller.paste_day_snapshot(emp, 5, snapshot)

        pasted = controller.get_day(emp, 5)
        self.assertEqual((pasted.start, pasted.end), NIGHT_HOURS)

    def test_leave_day_round_trip(self):
        controller, emp = _controller_with_night_location()
        controller.set_day_leave(emp, 3)

        snapshot = controller.copy_day_snapshot(emp, 3)
        controller.set_day_hours(emp, 5, "08:00", "16:00")  # target starts non-empty
        controller.paste_day_snapshot(emp, 5, snapshot)

        pasted = controller.get_day(emp, 5)
        self.assertTrue(pasted.is_leave)
        self.assertIsNone(pasted.start)

    def test_sick_day_round_trip(self):
        controller, emp = _controller_with_night_location()
        controller.set_day_sick(emp, 3)

        snapshot = controller.copy_day_snapshot(emp, 3)
        controller.paste_day_snapshot(emp, 5, snapshot)

        self.assertTrue(controller.get_day(emp, 5).is_sick)

    def test_free_day_round_trip(self):
        controller, emp = _controller_with_night_location()
        controller.set_day_hours(emp, 3, "08:00", "16:00")
        controller.set_day_free(emp, 3)

        snapshot = controller.copy_day_snapshot(emp, 3)
        controller.set_day_hours(emp, 5, "08:00", "16:00")  # target starts non-empty
        controller.paste_day_snapshot(emp, 5, snapshot)

        pasted = controller.get_day(emp, 5)
        self.assertTrue(pasted.is_empty())
        self.assertFalse(pasted.is_leave)
        self.assertFalse(pasted.is_sick)

    def test_full_day_shift_round_trip(self):
        controller, emp = _controller_with_night_location()
        controller.set_day_full_day_shift(emp, 3, "08:00")

        snapshot = controller.copy_day_snapshot(emp, 3)
        controller.paste_day_snapshot(emp, 5, snapshot)

        pasted = controller.get_day(emp, 5)
        self.assertTrue(pasted.is_full_day)
        self.assertEqual(pasted.start, "08:00")
        self.assertEqual(pasted.end, "08:00")

    def test_locked_shift_class_round_trip(self):
        controller, emp = _controller_with_night_location()
        controller.set_shift_class(emp, 3, "1")

        snapshot = controller.copy_day_snapshot(emp, 3)
        controller.paste_day_snapshot(emp, 5, snapshot)

        pasted = controller.get_day(emp, 5)
        self.assertEqual(pasted.shift_class, "1")
        self.assertTrue(pasted.is_empty())

    def test_night_shift_paste_is_rejected_for_a_location_without_a_night_window(self):
        """Not a bug: pasting a night shift onto a location that never opens
        at night would create data the generator can't interpret (same rule
        as typing it in manually) - paste_day_snapshot must not bypass that."""
        controller, emp = _controller_with_night_location()
        controller.set_day_hours(emp, 3, *NIGHT_HOURS)
        snapshot = controller.copy_day_snapshot(emp, 3)

        shop = ShopConfig(2026, 8)
        loc = LocationConfig(key="day_only", name="Day only")
        for wd in range(7):
            loc.open_hours[wd] = ("08:00", "20:00")  # never touches night
        shop.locations["day_only"] = loc
        schedule = MonthSchedule(2026, 8)
        day_emp = Employee(last_name="Nowak", first_name="Anna", location_key="day_only")
        schedule.add_employee(day_emp)
        controller2 = ScheduleController(schedule, shop)

        controller2.paste_day_snapshot(day_emp, 5, snapshot)

        self.assertIsNone(controller2.get_day(day_emp, 5).start)

    def test_locked_flag_set_after_paste(self):
        controller, emp = _controller_with_night_location()
        controller.set_day_hours(emp, 3, "08:00", "16:00")
        snapshot = controller.copy_day_snapshot(emp, 3)

        controller.paste_day_snapshot(emp, 5, snapshot)

        self.assertTrue(controller.get_day(emp, 5).is_locked)

    def test_paste_supports_undo(self):
        controller, emp = _controller_with_night_location()
        controller.set_day_hours(emp, 3, "08:00", "16:00")
        snapshot = controller.copy_day_snapshot(emp, 3)

        controller.paste_day_snapshot(emp, 5, snapshot)
        self.assertEqual(controller.get_day(emp, 5).start, "08:00")

        controller.undo()
        self.assertIsNone(controller.get_day(emp, 5).start)


if __name__ == "__main__":
    unittest.main()
