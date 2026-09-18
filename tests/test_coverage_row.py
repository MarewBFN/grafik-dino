import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from ui import theme
from ui.grid_view import ScheduleGrid

ROTATION = {
    "weekday_long": {"start": "06:00", "end": "22:00"},
    "weekday_short": {"start": "22:00", "end": "06:00"},
    "weekend_full": {"start": "06:00"},
    "weekend_half_a": {"start": "06:00", "end": "18:00"},
    "weekend_half_b": {"start": "18:00", "end": "06:00"},
}

# August 2026: 3 = Monday.
MONDAY = 3


def test_duty_rotation_project_shows_oblozenie_instead_of_open_close():
    shop = ShopConfig(2026, 8)
    loc = LocationConfig(key="site1", name="Site 1")
    loc.set_duty_rotation(ROTATION)
    shop.locations["site1"] = loc

    long_emp = Employee(last_name="Long", first_name="A", location_key="site1")
    short_emp = Employee(last_name="Short", first_name="B", location_key="site1")

    grid = ScheduleGrid()
    grid.schedule = MonthSchedule(2026, 8)
    grid.schedule.add_employee(long_emp)
    grid.schedule.add_employee(short_emp)
    grid.shop_config = shop

    rows = grid._summary_rows()
    keys = [key for _, key in rows]
    assert "coverage" in keys
    assert "open" not in keys
    assert "close" not in keys


def test_dino_project_keeps_open_close_rows():
    shop = ShopConfig(2026, 8)  # dino_retail, no locations at all
    grid = ScheduleGrid()
    grid.schedule = MonthSchedule(2026, 8)
    grid.shop_config = shop

    rows = grid._summary_rows()
    keys = [key for _, key in rows]
    assert "open" in keys
    assert "close" in keys
    assert "coverage" not in keys


def test_oblozenie_row_renders_check_and_cross():
    shop = ShopConfig(2026, 8)
    loc = LocationConfig(key="site1", name="Site 1")
    loc.set_duty_rotation(ROTATION)
    shop.locations["site1"] = loc

    long_emp = Employee(last_name="Long", first_name="A", location_key="site1")
    short_emp = Employee(last_name="Short", first_name="B", location_key="site1")

    schedule = MonthSchedule(2026, 8)
    schedule.add_employee(long_emp)
    schedule.add_employee(short_emp)
    # Monday: fully covered.
    schedule.get_day(long_emp, MONDAY).set_hours("06:00", "22:00")
    schedule.get_day(short_emp, MONDAY).set_hours("22:00", "06:00")
    # Tuesday (MONDAY + 1): only the long shift, gap left uncovered.
    schedule.get_day(long_emp, MONDAY + 1).set_hours("06:00", "22:00")

    grid = ScheduleGrid()
    grid.schedule = schedule
    grid.shop_config = shop
    grid.build()
    grid.refresh()

    coverage_row = next(row for row, (_, key) in enumerate(grid._summary_rows()) if key == "coverage")
    coverage_row += len(schedule.employees)

    covered_item = grid.item(coverage_row, MONDAY)
    uncovered_item = grid.item(coverage_row, MONDAY + 1)

    assert covered_item.text() == "✅"
    assert covered_item.background().color().name() == theme.OK_GREEN
    assert uncovered_item.text() == "❌"
    assert uncovered_item.background().color().name() == theme.ERR_RED
