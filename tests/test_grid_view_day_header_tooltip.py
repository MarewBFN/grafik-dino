"""ui/grid_view.py::ScheduleGrid._day_header_tooltip() and the header's
overridden-day marker - both must read the CURRENTLY VIEWED location's own
day_overrides/open_hours (see ui/main_window.py::_open_header_menu, which
now writes day overrides there too), not the project-wide ShopConfig
fields, which silently diverge from what the generator actually uses."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from logic.schedule_controller import ScheduleController
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from ui.grid_view import ScheduleGrid, DayHeaderView


def _grid_for_location(shop, schedule, location_key):
    controller = ScheduleController(schedule, shop)
    grid = ScheduleGrid()
    grid.set_data(schedule, shop, controller, location_filter=location_key)
    grid.build()
    return grid


def test_tooltip_shows_the_selected_locations_own_hours_not_the_project_default():
    shop = ShopConfig(2026, 8)  # project default hours: 05:30-22:45/23:00
    loc = LocationConfig(key="site1", name="Site 1")
    for wd in range(7):
        loc.open_hours[wd] = ("08:00", "20:00")
    shop.locations["site1"] = loc
    schedule = MonthSchedule(2026, 8)

    grid = _grid_for_location(shop, schedule, "site1")

    tooltip = grid._day_header_tooltip(3)  # 2026-08-03 is a Monday, a plain trade day

    assert "08:00" in tooltip
    assert "20:00" in tooltip
    assert "05:30" not in tooltip


def test_override_marker_only_shows_for_the_locations_own_override():
    shop = ShopConfig(2026, 8)
    loc_a = LocationConfig(key="site_a", name="Site A")
    loc_b = LocationConfig(key="site_b", name="Site B")
    loc_a.day_overrides[3] = ("09:00", "15:00")
    shop.locations["site_a"] = loc_a
    shop.locations["site_b"] = loc_b
    schedule = MonthSchedule(2026, 8)

    grid_a = _grid_for_location(shop, schedule, "site_a")
    grid_b = _grid_for_location(shop, schedule, "site_b")

    assert "zmienione ręcznie" in grid_a._day_header_tooltip(3)
    assert "zmienione ręcznie" not in grid_b._day_header_tooltip(3)


def test_header_overridden_days_marker_is_per_location():
    shop = ShopConfig(2026, 8)
    loc_a = LocationConfig(key="site_a", name="Site A")
    loc_b = LocationConfig(key="site_b", name="Site B")
    loc_a.day_overrides[3] = ("09:00", "15:00")
    shop.locations["site_a"] = loc_a
    shop.locations["site_b"] = loc_b
    schedule = MonthSchedule(2026, 8)

    grid_a = _grid_for_location(shop, schedule, "site_a")
    grid_b = _grid_for_location(shop, schedule, "site_b")

    header_a = grid_a.horizontalHeader()
    header_b = grid_b.horizontalHeader()
    assert isinstance(header_a, DayHeaderView) and isinstance(header_b, DayHeaderView)
    assert 3 in header_a.overridden_days
    assert 3 not in header_b.overridden_days
