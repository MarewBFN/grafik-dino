import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from logic.schedule_controller import ScheduleController
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from ui.grid_view import ScheduleGrid


def _grid_with_preset(preset):
    emp = Employee(last_name="Kowalski", first_name="Jan")
    schedule = MonthSchedule(2026, 9, employees=[emp])
    shop = ShopConfig(2026, 9)
    shop.set_quick_mode_presets([preset])
    controller = ScheduleController(schedule, shop)

    main_window = SimpleNamespace(
        shop_config=shop,
        quick_mode_enabled=True,
        quick_selected_shift=f"PRESET:{preset['name']}",
    )

    grid = ScheduleGrid()
    grid.set_data(schedule, shop, controller, main_window=main_window)
    return grid, schedule, emp


def test_clicking_a_cell_applies_the_selected_preset():
    preset = {"name": "Zmiana 16h", "start": "06:00", "end": "22:00", "full_day": False}
    grid, schedule, emp = _grid_with_preset(preset)

    grid._apply_quick_shift(0, 1)

    ds = schedule.get_day(emp, 1)
    assert (ds.start, ds.end) == ("06:00", "22:00")
    assert ds.is_locked is True


def test_clicking_a_cell_applies_a_full_day_preset():
    preset = {"name": "Doba 24h", "start": "06:00", "end": None, "full_day": True}
    grid, schedule, emp = _grid_with_preset(preset)

    grid._apply_quick_shift(0, 1)

    ds = schedule.get_day(emp, 1)
    assert ds.is_full_day is True
    assert ds.start == "06:00"


def test_stale_preset_name_is_a_noop():
    preset = {"name": "Zmiana 16h", "start": "06:00", "end": "22:00", "full_day": False}
    grid, schedule, emp = _grid_with_preset(preset)
    grid.main_window.quick_selected_shift = "PRESET:Nie istnieje"

    grid._apply_quick_shift(0, 1)

    ds = schedule.get_day(emp, 1)
    assert ds.is_empty()
