"""Dane firmy (model/company.py, Plik -> "Dane firmy") - zapis w projekcie,
walidacja i blok firmy we wniosku urlopowym."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from export.leave_request_exporter import _company_lines
from model.company import Company
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.monthly_project import MonthlyProject
from model.shop_config import ShopConfig
from persistence.project_io import load_project_bundle, save_project_bundle


def _company(**overrides):
    values = dict(
        name="Enyo Sp. z o.o.", nip="779-000-00-00", street="ul. Długa 5",
        postal_code="60-100", city="Poznań", phone="61 123 45 67", email="kadry@enyo.pl",
    )
    values.update(overrides)
    return Company(**values)


class CompanyValidationTests(unittest.TestCase):
    def test_valid_company_passes(self):
        _company().validate()

    def test_name_required(self):
        with self.assertRaises(ValueError):
            _company(name=" ").validate()

    def test_nip_must_have_ten_digits(self):
        with self.assertRaises(ValueError):
            _company(nip="123").validate()
        _company(nip="7790000000").validate()
        _company(nip="").validate()


class CompanyPersistenceTests(unittest.TestCase):
    def test_companies_and_employee_assignment_survive_save_load(self):
        company = _company()
        schedule = MonthSchedule(2026, 10)
        schedule.add_employee(Employee(last_name="Kowalski", first_name="Jan", company_key=company.key))
        project = MonthlyProject()
        project.companies = {company.key: company}
        project.put(2026, 10, schedule, ShopConfig(2026, 10))

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.myp")
            save_project_bundle(path, project, 2026, 10)
            loaded, _, _ = load_project_bundle(path)

        self.assertEqual(loaded.companies, {company.key: company})
        self.assertEqual(loaded.get(2026, 10)[0].employees[0].company_key, company.key)

    def test_old_files_without_companies_load_empty(self):
        project = MonthlyProject()
        project.put(2026, 10, MonthSchedule(2026, 10), ShopConfig(2026, 10))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.myp")
            save_project_bundle(path, project, 2026, 10)
            loaded, _, _ = load_project_bundle(path)
        self.assertEqual(loaded.companies, {})


class LeaveRequestCompanyBlockTests(unittest.TestCase):
    def test_no_company_gives_dotted_lines(self):
        self.assertEqual(_company_lines(None), [None, None, None])

    def test_company_lines(self):
        self.assertEqual(
            _company_lines(_company()),
            ["Enyo Sp. z o.o.", "ul. Długa 5", "60-100 Poznań", "NIP: 779-000-00-00",
             "tel. 61 123 45 67", "kadry@enyo.pl"],
        )

    def test_optional_fields_are_skipped(self):
        lines = _company_lines(replace(_company(), nip="", phone="", email=""))
        self.assertEqual(lines, ["Enyo Sp. z o.o.", "ul. Długa 5", "60-100 Poznań"])


if __name__ == "__main__":
    unittest.main()
