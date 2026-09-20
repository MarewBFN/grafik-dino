from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openpyxl import load_workbook

from export.employee_card_exporter import (
    _day_night_hours,
    _location_name,
    _night_minutes,
    export_employee_card_to_image,
    export_employee_cards_to_excel,
)
from model.day_schedule import DaySchedule
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig, DEFAULT_LOCATION_KEY


class NightMinutesTests(unittest.TestCase):
    def test_plain_day_shift_has_no_night_minutes(self):
        ds = DaySchedule()
        ds.set_hours("08:00", "16:00")
        self.assertEqual(_night_minutes(ds), 0)
        self.assertEqual(_day_night_hours(ds), ("8:00", "0:00"))

    def test_classic_night_shift_is_fully_night(self):
        ds = DaySchedule()
        ds.set_hours("22:00", "06:00")
        self.assertEqual(_night_minutes(ds), 480)
        self.assertEqual(_day_night_hours(ds), ("0:00", "8:00"))

    def test_partial_night_overlap(self):
        ds = DaySchedule()
        ds.set_hours("20:00", "23:00")
        self.assertEqual(_night_minutes(ds), 60)
        self.assertEqual(_day_night_hours(ds), ("2:00", "1:00"))

    def test_full_day_shift_counts_as_night(self):
        ds = DaySchedule()
        ds.set_full_day_shift("06:00")
        self.assertEqual(_night_minutes(ds), 480)
        self.assertEqual(_day_night_hours(ds), ("16:00", "8:00"))

    def test_empty_leave_and_sick_days_have_no_hours(self):
        empty = DaySchedule()
        self.assertEqual(_day_night_hours(empty), ("", ""))

        leave = DaySchedule()
        leave.set_leave()
        self.assertEqual(_day_night_hours(leave), ("", ""))

        sick = DaySchedule()
        sick.set_sick()
        self.assertEqual(_day_night_hours(sick), ("", ""))


class LocationNameTests(unittest.TestCase):
    def test_default_single_location_project(self):
        shop = ShopConfig(2026, 8)
        emp = Employee(last_name="Testowy", first_name="Jan", location_key=DEFAULT_LOCATION_KEY)
        self.assertEqual(_location_name(shop, emp), "Placówka główna")

    def test_unassigned_location_falls_back_to_shop_name(self):
        shop = ShopConfig(2026, 8)
        shop.name = "Firma X"
        emp = Employee(last_name="Testowy", first_name="Jan", location_key="brak")
        self.assertEqual(_location_name(shop, emp), "Firma X")

    def test_none_shop_returns_empty_string(self):
        emp = Employee(last_name="Testowy", first_name="Jan")
        self.assertEqual(_location_name(None, emp), "")


def _sample_schedule():
    schedule = MonthSchedule(2026, 8)
    emp = Employee(last_name="Kowalski", first_name="Adam", location_key=DEFAULT_LOCATION_KEY)
    schedule.add_employee(emp)
    schedule.get_day(emp, 1).set_hours("08:00", "16:00")
    schedule.get_day(emp, 2).set_leave()
    return schedule, emp


class ExcelCardExportTests(unittest.TestCase):
    def test_single_employee_creates_one_sheet_with_expected_header(self):
        schedule, emp = _sample_schedule()
        shop = ShopConfig(2026, 8)

        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/karta.xlsx"
            export_employee_cards_to_excel(schedule, 2026, 8, path, shop=shop, employees=[emp])

            wb = load_workbook(path)
            self.assertEqual(len(wb.sheetnames), 1)
            ws = wb.active

            self.assertEqual(ws.cell(row=1, column=1).value, "Lista obecności miesięczna pracownika")
            self.assertEqual(ws.cell(row=3, column=2).value, 2026)
            self.assertEqual(ws.cell(row=4, column=2).value, "08")
            self.assertIsNone(ws.cell(row=5, column=2).value)
            self.assertEqual(ws.cell(row=3, column=4).value, emp.display_name())
            self.assertEqual(ws.cell(row=4, column=4).value, "Placówka główna")

    def test_leave_day_has_blank_columns_2_to_5(self):
        schedule, emp = _sample_schedule()

        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/karta.xlsx"
            export_employee_cards_to_excel(schedule, 2026, 8, path, employees=[emp])

            wb = load_workbook(path)
            ws = wb.active
            # Wiersz nagłówka tabeli to 7, dzień 1 to wiersz 8, dzień 2 (urlop) to wiersz 9.
            leave_row = 9
            self.assertEqual(ws.cell(row=leave_row, column=1).value, 2)
            for col in range(2, 7):
                self.assertIsNone(ws.cell(row=leave_row, column=col).value)

    def test_footer_sum_matches_total_hours(self):
        schedule, emp = _sample_schedule()

        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/karta.xlsx"
            export_employee_cards_to_excel(schedule, 2026, 8, path, employees=[emp])

            wb = load_workbook(path)
            ws = wb.active
            days_in_month = 31
            header_row = 7
            footer_row = header_row + days_in_month + 1
            self.assertEqual(ws.cell(row=footer_row, column=1).value, "Razem ilość godzin:")
            self.assertEqual(ws.cell(row=footer_row, column=4).value, schedule.total_hours_for_employee(emp))

    def test_multiple_employees_get_one_sheet_each(self):
        schedule = MonthSchedule(2026, 8)
        emp1 = Employee(last_name="Kowalski", first_name="Adam")
        emp2 = Employee(last_name="Nowak", first_name="Ewa")
        schedule.add_employee(emp1)
        schedule.add_employee(emp2)

        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/karty.xlsx"
            export_employee_cards_to_excel(schedule, 2026, 8, path, employees=[emp1, emp2])

            wb = load_workbook(path)
            self.assertEqual(len(wb.sheetnames), 2)


class ImageCardExportTests(unittest.TestCase):
    def test_export_produces_non_empty_file(self):
        schedule, emp = _sample_schedule()
        shop = ShopConfig(2026, 8)

        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/karta.jpg"
            result = export_employee_card_to_image(schedule, 2026, 8, path, shop=shop, employee=emp)

            self.assertTrue(result)
            self.assertGreater(Path(path).stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
