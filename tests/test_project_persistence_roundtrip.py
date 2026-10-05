"""Pełny zapis/odczyt projektu (persistence/project_io.py): każde pole
pracownika, każdy stan dnia, urlopy, firmy - plus regresja "zapis po Cofnij"
(ui/main_window.py::_commit_current_month)."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import dataclasses
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from logic.schedule_controller import ScheduleController
from model.company import Company
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.monthly_project import MonthlyProject
from model.shop_config import ShopConfig
from persistence.project_io import load_project_bundle, save_project_bundle
from ui.main_window import MainWindow


def _roundtrip(project, year, month):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "p.myp")
        save_project_bundle(path, project, year, month)
        return load_project_bundle(path)[0]


class FullRoundtripTests(unittest.TestCase):
    def setUp(self):
        self.company = Company(name="Enyo", nip="7790000000", city="Poznań")
        self.shop = ShopConfig(2026, 10)
        self.emp = Employee(
            last_name="Kowalski", first_name="Jan", is_opener=True, is_manager=True,
            no_night=True, monthly_target_hours=120, daily_hours=12, employment_fraction=0.5,
            availability={1: {"start": "08:00", "end": "16:00", "mode": "hard"}},
            custom_roles={"kierowca": True}, location_key=next(iter(self.shop.locations)),
            company_key=self.company.key, phone="600 123 456", email="jan@x.pl",
            street="Krótka 1", postal_code="61-001", city="Poznań", vacation_days_left=12.5,
        )
        self.schedule = MonthSchedule(2026, 10, employees=[self.emp])
        s, e = self.schedule, self.emp
        s.get_day(e, 1).set_hours("22:00", "06:00")
        s.get_day(e, 2).set_leave()
        s.get_day(e, 3).is_sick = True
        s.get_day(e, 4).set_free()
        s.get_day(e, 5).set_free()
        s.get_day(e, 5).is_locked = True
        s.get_day(e, 6).shift_class = "W"
        s.get_day(e, 7).set_full_day_shift("08:00")
        s.set_settlement_target(e, 9600)
        s.set_previous_month_end_shift(e, "06:00", True)
        s.leave_days_charged[e] = 1.0
        s.printed_leave_requests[e] = {(2, 2)}

        self.project = MonthlyProject()
        self.project.companies = {self.company.key: self.company}
        self.project.put(2026, 10, self.schedule, self.shop)
        self.loaded = _roundtrip(self.project, 2026, 10)
        self.loaded_schedule = self.loaded.get(2026, 10)[0]
        self.loaded_emp = self.loaded_schedule.employees[0]

    def test_every_employee_field(self):
        for f in dataclasses.fields(Employee):
            if f.name == "id":
                continue
            with self.subTest(field=f.name):
                self.assertEqual(getattr(self.loaded_emp, f.name), getattr(self.emp, f.name))

    def test_every_day_state(self):
        for day in range(1, self.schedule.days_in_month + 1):
            with self.subTest(day=day):
                self.assertEqual(
                    self.loaded_schedule.get_day(self.loaded_emp, day),
                    self.schedule.get_day(self.emp, day),
                )

    def test_per_employee_month_data(self):
        s, e = self.loaded_schedule, self.loaded_emp
        self.assertEqual(s.settlement_targets.get(e), 9600)
        self.assertEqual(s.previous_month_end_shifts.get(e), self.schedule.previous_month_end_shifts[self.emp])
        self.assertEqual(s.leave_days_charged.get(e), 1.0)
        self.assertEqual(s.printed_leave_requests.get(e), {(2, 2)})

    def test_companies(self):
        self.assertEqual(self.loaded.companies, self.project.companies)


class SaveAfterUndoTests(unittest.TestCase):
    """Cofnij podmienia self.schedule na nowy obiekt - zapis musi brać ten
    bieżący, a nie stary trzymany wcześniej w MonthlyProject."""

    def test_undone_change_is_not_saved_and_later_edits_are(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        window = MainWindow.__new__(MainWindow)
        window.year, window.month = 2026, 10
        window.schedule = MonthSchedule(2026, 10, employees=[emp])
        window.shop_config = ShopConfig(2026, 10)
        window.controller = ScheduleController(window.schedule, window.shop_config)
        window.project = MonthlyProject()
        window.project.put(2026, 10, window.schedule, window.shop_config)
        window.statusBar = MagicMock(return_value=MagicMock())
        window._sync_everything = window._commit_current_month

        window.controller.set_day_hours(emp, 5, "08:00", "16:00")
        window._undo()
        window.controller.set_day_hours(emp, 6, "10:00", "18:00")

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.myp")
            window._save_bundle(path)
            schedule = load_project_bundle(path)[0].get(2026, 10)[0]

        loaded_emp = schedule.employees[0]
        self.assertIsNone(schedule.get_day(loaded_emp, 5).start)
        self.assertEqual(schedule.get_day(loaded_emp, 6).start, "10:00")


if __name__ == "__main__":
    unittest.main()
