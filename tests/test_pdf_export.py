from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from export.employee_card_exporter import export_employee_cards_to_pdf
from export.pdf_exporter import export_schedule_to_pdf
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig


def _page_object_count(pdf_bytes: bytes) -> int:
    # "/Type /Pages" (drzewo stron) zawiera "/Type /Page" jako podciąg,
    # więc trzeba je odjąć, żeby policzyć tylko faktyczne strony.
    return pdf_bytes.count(b"/Type /Page") - pdf_bytes.count(b"/Type /Pages")


def _two_employee_schedule():
    schedule = MonthSchedule(2026, 8)
    emp1 = Employee(last_name="Kowalski", first_name="Adam")
    emp2 = Employee(last_name="Nowak", first_name="Ewa")
    schedule.add_employee(emp1)
    schedule.add_employee(emp2)
    schedule.get_day(emp1, 3).set_hours("08:00", "16:00")
    return schedule, emp1, emp2


class ScheduleToPdfTests(unittest.TestCase):
    def test_dino_profile_produces_a_valid_single_page_pdf(self):
        schedule, emp1, emp2 = _two_employee_schedule()

        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/grafik.pdf"
            result = export_schedule_to_pdf(schedule, 2026, 8, path)

            self.assertTrue(result)
            data = Path(path).read_bytes()
            self.assertTrue(data.startswith(b"%PDF"))
            self.assertEqual(_page_object_count(data), 1)

    def test_non_dino_profile_also_produces_a_valid_pdf(self):
        schedule, emp1, emp2 = _two_employee_schedule()
        shop = ShopConfig(2026, 8)
        shop.business_type = "ochrona_enyo"

        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/grafik.pdf"
            result = export_schedule_to_pdf(schedule, 2026, 8, path, shop=shop)

            self.assertTrue(result)
            data = Path(path).read_bytes()
            self.assertTrue(data.startswith(b"%PDF"))
            self.assertEqual(_page_object_count(data), 1)


class EmployeeCardsToPdfTests(unittest.TestCase):
    def test_single_employee_is_a_single_page_document(self):
        schedule, emp1, emp2 = _two_employee_schedule()

        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/karta.pdf"
            result = export_employee_cards_to_pdf(schedule, 2026, 8, path, employees=[emp1])

            self.assertTrue(result)
            data = Path(path).read_bytes()
            self.assertTrue(data.startswith(b"%PDF"))
            self.assertEqual(_page_object_count(data), 1)

    def test_multiple_employees_produce_one_page_per_employee(self):
        schedule, emp1, emp2 = _two_employee_schedule()

        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/karty.pdf"
            result = export_employee_cards_to_pdf(schedule, 2026, 8, path, employees=[emp1, emp2])

            self.assertTrue(result)
            data = Path(path).read_bytes()
            self.assertEqual(_page_object_count(data), 2)


if __name__ == "__main__":
    unittest.main()
