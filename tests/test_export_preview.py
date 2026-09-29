"""Podgląd wygenerowanego grafiku/kart pracy przed eksportem
(ui/export_preview_dialog.py) - dialog dostaje gotowe obrazy PIL z
`export/export_style.py::render_schedule_image` i
`export/employee_card_exporter.py::render_employee_card_image`, żeby
podgląd był dokładnie tym, co trafia do JPG/PDF."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image
from PySide6.QtWidgets import QApplication, QDialog

_app = QApplication.instance() or QApplication([])

from export.employee_card_exporter import render_employee_card_image
from export.export_style import render_schedule_image
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from ui.export_preview_dialog import ExportPreviewDialog, show_export_preview


def _schedule_with_employee():
    schedule = MonthSchedule(2026, 8)
    emp = Employee(last_name="Kowalski", first_name="Adam")
    schedule.add_employee(emp)
    schedule.get_day(emp, 3).set_hours("08:00", "16:00")
    return schedule, emp


class RenderHelpersTests(unittest.TestCase):
    def test_render_schedule_image_returns_a_pil_image(self):
        schedule, emp = _schedule_with_employee()
        image = render_schedule_image(schedule, 2026, 8, employees=[emp])
        self.assertIsInstance(image, Image.Image)
        self.assertGreater(image.width, 0)
        self.assertGreater(image.height, 0)

    def test_render_schedule_image_respects_security_profile(self):
        schedule, emp = _schedule_with_employee()
        shop = ShopConfig(2026, 8)
        shop.business_type = "ochrona_enyo"
        image = render_schedule_image(schedule, 2026, 8, shop=shop, employees=[emp])
        self.assertIsInstance(image, Image.Image)

    def test_render_employee_card_image_returns_a4_portrait_page(self):
        schedule, emp = _schedule_with_employee()
        image = render_employee_card_image(schedule, 2026, 8, None, emp)
        self.assertIsInstance(image, Image.Image)
        self.assertEqual(image.size, (1240, 1754))


class ExportPreviewDialogTests(unittest.TestCase):
    def test_single_page_has_no_navigation_and_shows_pixmap(self):
        image = Image.new("RGB", (100, 100), "white")
        dialog = ExportPreviewDialog([image], title="Test")
        self.assertFalse(hasattr(dialog, "page_label"))
        self.assertFalse(dialog.image_label.pixmap().isNull())

    def test_multi_page_navigation_updates_label_and_buttons(self):
        pages = [Image.new("RGB", (50, 50), "white") for _ in range(3)]
        dialog = ExportPreviewDialog(pages, title="Test")

        self.assertEqual(dialog.page_label.text(), "Strona 1 / 3")
        self.assertFalse(dialog.prev_btn.isEnabled())
        self.assertTrue(dialog.next_btn.isEnabled())

        dialog._show_next()
        self.assertEqual(dialog.page_label.text(), "Strona 2 / 3")
        self.assertTrue(dialog.prev_btn.isEnabled())
        self.assertTrue(dialog.next_btn.isEnabled())

        dialog._show_next()
        self.assertEqual(dialog.page_label.text(), "Strona 3 / 3")
        self.assertTrue(dialog.prev_btn.isEnabled())
        self.assertFalse(dialog.next_btn.isEnabled())

        dialog._show_prev()
        self.assertEqual(dialog.page_label.text(), "Strona 2 / 3")

    def test_export_button_accepts_dialog(self):
        image = Image.new("RGB", (10, 10), "white")
        dialog = ExportPreviewDialog([image])
        dialog.export_btn.click()
        self.assertEqual(dialog.result(), QDialog.Accepted)

    def test_requires_at_least_one_page(self):
        with self.assertRaises(ValueError):
            ExportPreviewDialog([])


class ShowExportPreviewTests(unittest.TestCase):
    def test_wraps_single_image_and_reports_acceptance(self):
        image = Image.new("RGB", (10, 10), "white")
        with patch.object(ExportPreviewDialog, "exec", return_value=QDialog.Accepted):
            result = show_export_preview(image, title="Test")
        self.assertTrue(result)

    def test_reports_cancellation(self):
        image = Image.new("RGB", (10, 10), "white")
        with patch.object(ExportPreviewDialog, "exec", return_value=QDialog.Rejected):
            result = show_export_preview(image, title="Test")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
