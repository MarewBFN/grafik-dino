import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from model.constraints import ConstraintEngine
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig


def test_clear_unlocked_days_keeps_manual_hours():
    schedule = MonthSchedule(2025, 2)
    emp = Employee("Kowalski", "Jan", True, True, 8)
    schedule.add_employee(emp)

    schedule.set_day_hours(emp, 3, "05:30", "13:30")
    schedule.clear_unlocked_days()

    ds = schedule.get_day(emp, 3)
    assert ds.start == "05:30"
    assert ds.end == "13:30"


def test_constraint_engine_reports_meat_coverage_by_default_policy():
    schedule = MonthSchedule(2025, 2)
    meat_emp = Employee("Meat", "Only", True, True, 8)
    non_meat_emp = Employee("No", "Meat", True, False, 8)
    schedule.add_employee(meat_emp)
    schedule.add_employee(non_meat_emp)

    shop = ShopConfig(2025, 2)
    # handlowy dzień roboczy
    schedule.set_day_hours(meat_emp, 3, "05:30", "09:30")
    schedule.set_day_hours(non_meat_emp, 3, "09:30", "17:30")

    violations = ConstraintEngine.evaluate(schedule, shop)

    assert any(v.type == "meat_coverage" and v.day == 3 for v in violations)