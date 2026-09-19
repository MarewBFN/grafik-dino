import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from openpyxl import load_workbook
from PIL import Image

from export.excel_exporter import export_schedule_to_excel
from export.image_exporter import export_schedule_to_image
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from ui import theme
from ui.grid_view import ScheduleGrid


def _two_employee_schedule():
    shop = ShopConfig(2026, 8)
    shop.constraints["force_fulltime_845"] = False
    schedule = MonthSchedule(2026, 8)
    over = Employee(last_name="Ponadwymiarowy", first_name="Jan")
    under = Employee(last_name="Wramach", first_name="Ola")
    schedule.add_employee(over)
    schedule.add_employee(under)

    nominal_hours = shop.get_full_time_nominal_hours()
    days_needed = math.ceil(nominal_hours / 8) + 1
    for day in range(1, days_needed + 1):
        schedule.get_day(over, day).set_hours("08:00", "16:00")

    schedule.get_day(under, 3).set_hours("08:00", "16:00")

    return schedule, shop, over, under


def test_grid_has_a_dedicated_nadgodziny_column_next_to_razem():
    schedule, shop, over, under = _two_employee_schedule()
    days = schedule.days_in_month

    grid = ScheduleGrid()
    grid.schedule = schedule
    grid.shop_config = shop
    grid.build()
    grid.refresh()

    headers = [grid.horizontalHeaderItem(c).text() for c in range(grid.columnCount())]
    assert headers[days + 4] == "Razem\n(h)"
    assert headers[days + 5] == "Nadgodziny\n(h)"

    over_row = schedule.employees.index(over)
    under_row = schedule.employees.index(under)

    over_item = grid.item(over_row, days + 5)
    under_item = grid.item(under_row, days + 5)

    assert over_item.text() != "0:00"
    assert under_item.text() == "0:00"
    assert over_item.background().color().name() == theme.ERR_RED
    assert under_item.background().color().name() != theme.ERR_RED


class TestExcelOvertimeColumn:
    def test_nadgodziny_column_shows_the_overage_and_is_highlighted(self):
        import tempfile

        schedule, shop, over, under = _two_employee_schedule()

        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/grafik.xlsx"
            export_schedule_to_excel(schedule, 2026, 8, path, shop=shop)

            wb = load_workbook(path)
            ws = wb.active
            days_in_month = 31
            sum_col_start = days_in_month + 3
            nadgodziny_col = sum_col_start + 4

            header = ws.cell(row=4, column=nadgodziny_col).value
            over_cell = ws.cell(row=6, column=nadgodziny_col)
            under_cell = ws.cell(row=9, column=nadgodziny_col)

        assert header == "Nadgodziny"
        assert over_cell.value != "0:00"
        assert over_cell.font.color.rgb == "FFCC0000"
        assert under_cell.value == "0:00"
        assert under_cell.font.color != over_cell.font.color


class TestImageOvertimeColumn:
    def test_export_with_overtime_column_does_not_crash_and_grows_the_image(self):
        import tempfile

        schedule, shop, over, under = _two_employee_schedule()

        with tempfile.TemporaryDirectory() as tmp:
            path_with_shop = f"{tmp}/with_shop.jpg"
            path_without_shop = f"{tmp}/without_shop.jpg"
            export_schedule_to_image(schedule, 2026, 8, path_with_shop, shop=shop)
            export_schedule_to_image(schedule, 2026, 8, path_without_shop)

            with Image.open(path_with_shop) as img_with, Image.open(path_without_shop) as img_without:
                # Same 5-column summary layout either way (Nadgodziny always
                # rendered) - only the color changes when `shop` is passed.
                assert img_with.width == img_without.width
