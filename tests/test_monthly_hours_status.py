import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from logic.monthly_hours_status import monthly_hours_status


def _make_schedule(fraction=1.0):
    shop = ShopConfig(2026, 8)
    # Dino's "force 8:30 for full-timers" convention would otherwise make
    # get_effective_daily_hours() return 8.5h instead of 8h for fraction=1.0,
    # which these tests assume for the leave/sick daily-minutes calculation.
    shop.constraints["force_fulltime_845"] = False
    schedule = MonthSchedule(2026, 8)
    emp = Employee("Testowy", "Pracownik", daily_hours=8, employment_fraction=fraction)
    schedule.add_employee(emp)
    return schedule, shop, emp


def test_no_shifts_worked_is_not_over():
    schedule, shop, emp = _make_schedule()
    status = monthly_hours_status(schedule, shop, emp)
    assert status["worked_minutes"] == 0
    assert status["is_over"] is False
    assert status["over_minutes"] == 0


def test_exactly_at_target_is_not_over():
    schedule, shop, emp = _make_schedule()
    nominal_hours = shop.get_full_time_nominal_hours()
    full_days = nominal_hours // 8

    for day in range(1, full_days + 1):
        schedule.get_day(emp, day).set_hours("08:00", "16:00")

    status = monthly_hours_status(schedule, shop, emp)
    assert status["worked_minutes"] == full_days * 8 * 60
    assert status["target_minutes"] == nominal_hours * 60
    assert status["is_over"] is False


def test_working_more_than_nominal_is_over():
    schedule, shop, emp = _make_schedule()
    nominal_hours = shop.get_full_time_nominal_hours()
    days_needed = math.ceil(nominal_hours / 8) + 1

    for day in range(1, days_needed + 1):
        schedule.get_day(emp, day).set_hours("08:00", "16:00")

    status = monthly_hours_status(schedule, shop, emp)
    expected_worked = days_needed * 8 * 60
    expected_target = nominal_hours * 60
    assert status["worked_minutes"] == expected_worked
    assert status["target_minutes"] == expected_target
    assert status["is_over"] is True
    assert status["over_minutes"] == expected_worked - expected_target


def test_leave_days_lower_the_target_so_the_same_hours_can_tip_over():
    schedule, shop, emp = _make_schedule()
    nominal_hours = shop.get_full_time_nominal_hours()
    full_days = nominal_hours // 8

    # Two days of urlop lower the target by 2 * 8h, but the employee still
    # works the same number of days as in test_exactly_at_target_is_not_over.
    schedule.get_day(emp, 1).set_leave()
    schedule.get_day(emp, 2).set_leave()

    for day in range(3, full_days + 3):
        schedule.get_day(emp, day).set_hours("08:00", "16:00")

    status = monthly_hours_status(schedule, shop, emp)
    assert status["target_minutes"] == (nominal_hours - 16) * 60
    assert status["is_over"] is True
    assert status["over_minutes"] == 2 * 8 * 60


def test_half_time_employee_has_a_proportionally_lower_target():
    schedule, shop, emp = _make_schedule(fraction=0.5)
    nominal_hours = shop.get_full_time_nominal_hours()

    status = monthly_hours_status(schedule, shop, emp)
    assert status["target_minutes"] == int(nominal_hours * 60 * 0.5)
