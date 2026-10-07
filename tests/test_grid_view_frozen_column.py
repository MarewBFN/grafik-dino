"""ui/grid_view.py - kolumna z pracownikami to osobna nakładka
(frozen_name_column) nad kolumną 0 tabeli. Zmiana szerokości z obu
nagłówków musi zmieniać obie, inaczej między pracownikami a dniami
zostaje pusta przerwa."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from logic.schedule_controller import ScheduleController
from ui.grid_view import ScheduleGrid


def _grid():
    grid = ScheduleGrid()
    schedule = MonthSchedule(2026, 8, employees=[Employee(last_name="Kowalski", first_name="Jan")])
    shop = ShopConfig(2026, 8)
    grid.set_data(schedule, shop, ScheduleController(schedule, shop))
    grid.build()
    grid.resize(1200, 500)
    grid.show()
    _app.processEvents()
    return grid


def _assert_in_sync(grid, width):
    assert grid.columnWidth(0) == width
    assert grid.frozen_name_column.columnWidth(0) == width
    assert grid.frozen_name_column.width() == width


def test_resizing_from_overlay_header_resizes_table_column():
    grid = _grid()
    grid.frozen_name_column.horizontalHeader().resizeSection(0, 340)
    _app.processEvents()
    _assert_in_sync(grid, 340)


def test_resizing_from_table_header_resizes_overlay():
    grid = _grid()
    grid.horizontalHeader().resizeSection(0, 180)
    _app.processEvents()
    _assert_in_sync(grid, 180)
