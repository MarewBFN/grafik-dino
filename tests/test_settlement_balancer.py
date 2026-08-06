from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model.day_schedule import calc_end, calc_start
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from logic.settlement_balancer import (
    balance_employee_hours,
    balance_settlement_period,
    classify_editable_side,
    compute_safe_adjustment_bounds,
)

# 2026-08-03 is a Monday — a plain trade day with no Sunday/holiday edge cases.
WORK_DAYS = (3, 4, 5, 6, 7)


def _make_schedule(fraction=1.0):
    shop = ShopConfig(2026, 8)
    schedule = MonthSchedule(2026, 8)
    emp = Employee("Testowy", "Pracownik", daily_hours=8, employment_fraction=fraction)
    schedule.add_employee(emp)
    return schedule, shop, emp


class ComputeSafeAdjustmentBoundsTests(unittest.TestCase):
    def test_regular_employee_can_extend_by_15_minutes(self):
        _, shop, emp = _make_schedule(fraction=1.0)
        self.assertEqual(compute_safe_adjustment_bounds(emp, shop), (-60, 15))

    def test_seven_eighths_employee_cannot_extend(self):
        _, shop, emp = _make_schedule(fraction=0.875)
        self.assertEqual(compute_safe_adjustment_bounds(emp, shop), (-60, 0))

    def test_full_time_max_8h_employee_cannot_extend(self):
        _, shop, emp = _make_schedule(fraction=1.01)
        self.assertEqual(compute_safe_adjustment_bounds(emp, shop), (-60, 0))


class ClassifyEditableSideTests(unittest.TestCase):
    def test_opening_shift_keeps_start_fixed(self):
        schedule, shop, emp = _make_schedule()
        open_t, close_t = shop.get_open_hours_for_day(WORK_DAYS[0])
        ds = schedule.get_day(emp, WORK_DAYS[0])
        ds.set_hours(open_t, calc_end(open_t, 8.5))

        self.assertEqual(classify_editable_side(ds, shop, WORK_DAYS[0]), "end")

    def test_closing_shift_keeps_end_fixed(self):
        schedule, shop, emp = _make_schedule()
        open_t, close_t = shop.get_open_hours_for_day(WORK_DAYS[0])
        ds = schedule.get_day(emp, WORK_DAYS[0])
        ds.set_hours(calc_start(close_t, 8.5), close_t)

        self.assertEqual(classify_editable_side(ds, shop, WORK_DAYS[0]), "start")

    def test_empty_day_is_not_editable(self):
        schedule, shop, emp = _make_schedule()
        ds = schedule.get_day(emp, WORK_DAYS[0])

        self.assertIsNone(classify_editable_side(ds, shop, WORK_DAYS[0]))

    def test_leave_day_is_not_editable(self):
        schedule, shop, emp = _make_schedule()
        ds = schedule.get_day(emp, WORK_DAYS[0])
        ds.set_leave()

        self.assertIsNone(classify_editable_side(ds, shop, WORK_DAYS[0]))


class BalanceEmployeeHoursTests(unittest.TestCase):
    def _fill_work_days(self, schedule, shop, emp, days, eff_hours=8.5, opening=True):
        for day in days:
            open_t, close_t = shop.get_open_hours_for_day(day)
            if opening:
                schedule.get_day(emp, day).set_hours(open_t, calc_end(open_t, eff_hours))
            else:
                schedule.get_day(emp, day).set_hours(calc_start(close_t, eff_hours), close_t)

    def test_no_change_when_already_at_target(self):
        schedule, shop, emp = _make_schedule()
        self._fill_work_days(schedule, shop, emp, WORK_DAYS)
        current = sum(schedule.get_day(emp, d).total_minutes(emp, shop) for d in range(1, 32))

        result = balance_employee_hours(schedule, shop, emp, current)

        self.assertTrue(result["reached_target"])
        self.assertEqual(result["days_trimmed"], [])
        self.assertEqual(result["days_freed"], [])

    def test_small_overage_trims_edges_without_touching_anchor(self):
        schedule, shop, emp = _make_schedule()
        self._fill_work_days(schedule, shop, emp, WORK_DAYS, opening=True)
        open_t, _ = shop.get_open_hours_for_day(WORK_DAYS[0])
        current = sum(schedule.get_day(emp, d).total_minutes(emp, shop) for d in range(1, 32))

        result = balance_employee_hours(schedule, shop, emp, current - 90)

        self.assertTrue(result["reached_target"])
        self.assertEqual(result["days_freed"], [])
        for day in WORK_DAYS:
            ds = schedule.get_day(emp, day)
            # Start (godzina otwarcia) nigdy się nie zmienia.
            self.assertEqual(ds.start, open_t)

    def test_closing_shift_start_moves_but_end_stays_anchored(self):
        schedule, shop, emp = _make_schedule()
        self._fill_work_days(schedule, shop, emp, WORK_DAYS, opening=False)
        current = sum(schedule.get_day(emp, d).total_minutes(emp, shop) for d in range(1, 32))

        balance_employee_hours(schedule, shop, emp, current - 45)

        for day in WORK_DAYS:
            ds = schedule.get_day(emp, day)
            _, close_t = shop.get_open_hours_for_day(day)
            self.assertEqual(ds.end, close_t)

    def test_large_overage_frees_whole_days_first(self):
        schedule, shop, emp = _make_schedule()
        self._fill_work_days(schedule, shop, emp, WORK_DAYS, opening=True)
        current = sum(schedule.get_day(emp, d).total_minutes(emp, shop) for d in range(1, 32))

        # Zetnij więcej niż jedną pełną zmianę (8:30 = 510 min).
        result = balance_employee_hours(schedule, shop, emp, current - 600)

        self.assertGreaterEqual(len(result["days_freed"]), 1)
        for day in result["days_freed"]:
            self.assertTrue(schedule.get_day(emp, day).is_empty())
        self.assertTrue(schedule.get_day(emp, result["days_freed"][0]).is_locked)

    def test_large_overage_never_overshoots_past_target_with_irregular_day(self):
        schedule, shop, emp = _make_schedule()
        for index, day in enumerate(WORK_DAYS):
            open_t, _ = shop.get_open_hours_for_day(day)
            # Jeden dzień wyraźnie dłuższy niż typowa zmiana (np. ręcznie
            # wydłużony) — nie wolno go zwolnić, jeśli to przestrzeliłoby cel.
            hours = 11.0 if index == 1 else 8.5
            schedule.get_day(emp, day).set_hours(open_t, calc_end(open_t, hours))
            if index == 1:
                schedule.get_day(emp, day).is_locked = True

        current = sum(schedule.get_day(emp, d).total_minutes(emp, shop) for d in range(1, 32))
        target = current - 600

        result = balance_employee_hours(schedule, shop, emp, target)
        final = sum(schedule.get_day(emp, d).total_minutes(emp, shop) for d in range(1, 32))

        self.assertEqual(final, target)
        self.assertNotIn(WORK_DAYS[1], result["days_freed"])

    def test_current_total_matches_razem_column_when_employee_has_leave(self):
        # force_fulltime_845 (domyślnie True) sprawia, że get_effective_daily_hours
        # zwraca 8:30 dla pełnego etatu, ale kolumna "Razem" liczy dni urlopu
        # inaczej (employee.daily_hours * fraction = 8:00) — balancer musi
        # celować w wartość zgodną z tym, co widać w siatce, nie z
        # DaySchedule.total_minutes().
        schedule, shop, emp = _make_schedule()
        self._fill_work_days(schedule, shop, emp, WORK_DAYS[:3], opening=True)
        for day in WORK_DAYS[3:]:
            schedule.get_day(emp, day).set_leave()

        razem_minutes = schedule.total_with_leave_and_sick_minutes_for_employee(emp)

        result = balance_employee_hours(schedule, shop, emp, razem_minutes)

        self.assertTrue(result["reached_target"])
        self.assertEqual(result["starting_minutes"], razem_minutes)

    def test_seven_eighths_employee_never_extends_past_base(self):
        schedule, shop, emp = _make_schedule(fraction=0.875)
        self._fill_work_days(schedule, shop, emp, WORK_DAYS, eff_hours=7.0, opening=True)
        current = sum(schedule.get_day(emp, d).total_minutes(emp, shop) for d in range(1, 32))

        result = balance_employee_hours(schedule, shop, emp, current + 60)

        self.assertFalse(result["reached_target"])
        for day in WORK_DAYS:
            self.assertEqual(schedule.get_day(emp, day).total_minutes(emp, shop), 420)

    def test_locked_days_are_still_adjustable(self):
        schedule, shop, emp = _make_schedule()
        self._fill_work_days(schedule, shop, emp, WORK_DAYS, opening=True)
        for day in WORK_DAYS:
            schedule.get_day(emp, day).is_locked = True
        current = sum(schedule.get_day(emp, d).total_minutes(emp, shop) for d in range(1, 32))

        result = balance_employee_hours(schedule, shop, emp, current - 30)

        self.assertTrue(result["reached_target"])


class BalanceSettlementPeriodTests(unittest.TestCase):
    def test_only_employees_with_targets_are_processed(self):
        schedule, shop, emp = _make_schedule()
        other = Employee("Inny", "Ktos", daily_hours=8, employment_fraction=1.0)
        schedule.add_employee(other)

        schedule.set_settlement_target(emp, 1000)

        result = balance_settlement_period(schedule, shop)

        names = [entry["employee"] for entry in result["employees"]]
        self.assertIn(emp.display_name(), names)
        self.assertNotIn(other.display_name(), names)


if __name__ == "__main__":
    unittest.main()
