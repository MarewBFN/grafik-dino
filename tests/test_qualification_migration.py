"""Model kwalifikacji (model/qualification.py) i migracja starych plików
projektów: pola is_opener/is_meat/is_meat_light/is_manager/custom_roles ->
Employee.qualifications, katalog MonthlyProject.qualifications, kopia .bak
przed pierwszym zapisem w nowym formacie."""

import copy
import dataclasses
import json
import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from model.employee import Employee
from model.qualification import (
    MEAT_LEVEL_FULL,
    MEAT_LEVEL_LIGHT,
    QUAL_MANAGER,
    QUAL_MEAT,
    QUAL_OPENER,
    EmployeeQualification,
    Qualification,
    QualificationLevel,
    qualifications_from_legacy,
    qualifications_of,
)
from persistence.project_io import (
    BACKUP_SUFFIX,
    FORMAT_VERSION,
    load_project,
    load_project_bundle,
    save_project,
    save_project_bundle,
)

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PROJECTS = sorted((ROOT / "tests" / "golden" / "projects").glob("*.json"))
LEGACY_EMPLOYEE_KEYS = ("is_opener", "is_meat", "is_meat_light", "is_manager", "custom_roles")


class QualificationModelTests(unittest.TestCase):
    def test_validity_dates_are_inclusive(self):
        q = EmployeeQualification("wozki", valid_from=date(2026, 10, 1), valid_to=date(2026, 10, 31))
        self.assertFalse(q.is_valid_on(date(2026, 9, 30)))
        self.assertTrue(q.is_valid_on(date(2026, 10, 1)))
        self.assertTrue(q.is_valid_on(date(2026, 10, 31)))
        self.assertFalse(q.is_valid_on(date(2026, 11, 1)))
        self.assertTrue(q.is_valid_on(None))

    def test_location_restriction_empty_means_everywhere(self):
        self.assertTrue(EmployeeQualification("x").applies_to_location("a"))
        restricted = EmployeeQualification("x", location_ids=("a",))
        self.assertTrue(restricted.applies_to_location("a"))
        self.assertFalse(restricted.applies_to_location("b"))

    def test_employee_level_respects_date_and_location(self):
        emp = Employee(
            "Nowak", "Anna",
            qualifications=(
                EmployeeQualification(QUAL_MEAT, MEAT_LEVEL_FULL, valid_to=date(2026, 10, 15)),
                EmployeeQualification("wozki", location_ids=("magazyn",)),
            ),
        )
        self.assertEqual(emp.qualification_level(QUAL_MEAT), MEAT_LEVEL_FULL)
        self.assertEqual(emp.qualification_level(QUAL_MEAT, on=date(2026, 10, 16)), 0)
        self.assertTrue(emp.has_qualification("wozki", location_key="magazyn"))
        self.assertFalse(emp.has_qualification("wozki", location_key="sklep"))
        self.assertFalse(emp.has_qualification(QUAL_MEAT, min_level=3))

    def test_duplicate_qualification_is_rejected(self):
        emp = Employee("A", "B", qualifications=qualifications_of(QUAL_OPENER, QUAL_OPENER))
        with self.assertRaises(ValueError):
            emp.validate()

    def test_qualification_and_assignment_dict_roundtrip(self):
        q = Qualification(
            id="wozki", name="Wózki widłowe", code="UDT", icon="🚜", kind="certificate",
            levels=(QualificationLevel(1, "I"), QualificationLevel(2, "II")), requires_validity=True,
        )
        self.assertEqual(Qualification.from_dict(json.loads(json.dumps(q.to_dict()))), q)
        eq = EmployeeQualification("wozki", 2, date(2026, 1, 1), date(2027, 1, 1), ("a", "b"))
        self.assertEqual(EmployeeQualification.from_dict(json.loads(json.dumps(eq.to_dict()))), eq)


class LegacyMappingTests(unittest.TestCase):
    def test_dino_fields(self):
        self.assertEqual(qualifications_from_legacy({"is_opener": True}), qualifications_of(QUAL_OPENER))
        self.assertEqual(
            qualifications_from_legacy({"is_meat": True}), qualifications_of((QUAL_MEAT, MEAT_LEVEL_FULL))
        )
        self.assertEqual(
            qualifications_from_legacy({"is_meat_light": True}), qualifications_of((QUAL_MEAT, MEAT_LEVEL_LIGHT))
        )
        self.assertEqual(qualifications_from_legacy({"is_manager": True}), qualifications_of(QUAL_MANAGER))
        self.assertEqual(qualifications_from_legacy({"is_opener": False, "is_meat": False}), ())

    def test_custom_roles_true_only(self):
        quals = qualifications_from_legacy({"custom_roles": {"umowa": True, "nie_chce_24h": False, "guard": True}})
        self.assertEqual(quals, qualifications_of("umowa", "guard"))

    def test_legacy_views_match_original_flags(self):
        for flags in (
            {"is_opener": True, "is_meat": True},
            {"is_meat_light": True, "is_manager": True},
            {"custom_roles": {"umowa": True}},
            {},
        ):
            emp = Employee("A", "B", qualifications=qualifications_from_legacy(flags))
            with self.subTest(flags=flags):
                for key in ("is_opener", "is_meat", "is_meat_light", "is_manager"):
                    self.assertEqual(getattr(emp, key), bool(flags.get(key, False)))
                self.assertEqual(emp.custom_roles, {k: True for k, v in flags.get("custom_roles", {}).items() if v})


def _strip_legacy(employee_dict):
    return {k: v for k, v in employee_dict.items() if k not in LEGACY_EMPLOYEE_KEYS}


def _strip_new(document):
    document = copy.deepcopy(document)
    document.pop("format_version", None)
    for employee in document["schedule"]["employees"]:
        employee.pop("qualifications")
    return document


class GoldenProjectsRoundtripTests(unittest.TestCase):
    """Każdy zamrożony projekt golden (stary format) wczytuje się z
    poprawnymi kwalifikacjami, a zapis->odczyt nie gubi ani nie zmienia
    żadnej innej danej."""

    def setUp(self):
        from tests.golden.cases import register_golden_profiles

        register_golden_profiles()
        self.assertTrue(GOLDEN_PROJECTS, "brak plików tests/golden/projects/*.json")

    def test_old_files_load_with_qualifications_and_roundtrip_without_loss(self):
        for path in GOLDEN_PROJECTS:
            with self.subTest(project=path.name), tempfile.TemporaryDirectory() as tmp:
                original = json.loads(path.read_text(encoding="utf-8"))
                self.assertNotIn("format_version", original)
                schedule, shop = load_project(path)

                by_name = {(e["last_name"], e["first_name"]): e for e in original["schedule"]["employees"]}
                for emp in schedule.employees:
                    self.assertEqual(
                        emp.qualifications,
                        qualifications_from_legacy(by_name[(emp.last_name, emp.first_name)]),
                    )

                copy_path = Path(tmp) / path.name
                shutil.copy(path, copy_path)
                save_project(copy_path, schedule, shop)
                saved = json.loads(copy_path.read_text(encoding="utf-8"))

                self.assertEqual(saved["format_version"], FORMAT_VERSION)
                expected = copy.deepcopy(original)
                expected["schedule"]["employees"] = [_strip_legacy(e) for e in expected["schedule"]["employees"]]
                self.assertEqual(_strip_new(saved), expected)

                # Kopia zapasowa = dokładnie oryginalny plik.
                self.assertEqual((Path(str(copy_path) + BACKUP_SUFFIX)).read_bytes(), path.read_bytes())

                reloaded, _shop = load_project(copy_path)
                for before, after in zip(schedule.employees, reloaded.employees):
                    for field in dataclasses.fields(Employee):
                        if field.name != "id":
                            self.assertEqual(getattr(after, field.name), getattr(before, field.name), field.name)


LEGACY_BUNDLE = {
    "format": "multi_month_project",
    "format_version": 1,
    "active_month": "2026-10",
    "months": {},
    "companies": [],
}


def _legacy_month(year, month, employees, business_type="dino_retail"):
    from model.shop_config import ShopConfig

    shop = ShopConfig(year, month)
    shop.business_type = business_type
    return {
        "schedule": {"year": year, "month": month, "is_generated": False, "employees": employees},
        "shop_config": shop.to_dict(),
    }


def _legacy_employee(last_name, **fields):
    return {
        "first_name": "", "last_name": last_name,
        "is_opener": False, "is_meat": False, "is_meat_light": False, "is_manager": False,
        "no_night": False, "no_afternoon": False, "custom_roles": {},
        "monthly_target_hours": 160, "daily_hours": 8, "employment_fraction": 1.0,
        "availability": {}, "days": {"3": {"start": "06:00", "end": "14:30", "is_locked": True}},
        **fields,
    }


class BundleMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "projekt.myp")
        data = copy.deepcopy(LEGACY_BUNDLE)
        data["months"]["2026-10"] = _legacy_month(2026, 10, [
            _legacy_employee("Otwierająca", is_opener=True, is_meat=True),
            _legacy_employee("Lekka", is_meat_light=True, no_night=True),
            _legacy_employee("Kierowniczka", is_manager=True, employment_fraction=1.01),
            _legacy_employee("Tajna", custom_roles={"tajna_rola": True, "pusta": False}),
        ])
        data["months"]["2026-09"] = _legacy_month(2026, 9, [_legacy_employee("Otwierająca", is_opener=True)])
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        with open(self.path, "rb") as f:
            self.original_bytes = f.read()

    def tearDown(self):
        self.tmp.cleanup()

    def test_old_bundle_migrates_employees_and_builds_catalog(self):
        project, year, month = load_project_bundle(self.path)
        schedule = project.get(2026, 10)[0]
        by_name = {e.last_name: e for e in schedule.employees}

        self.assertEqual(by_name["Otwierająca"].qualifications,
                         qualifications_of(QUAL_OPENER, (QUAL_MEAT, MEAT_LEVEL_FULL)))
        self.assertEqual(by_name["Lekka"].qualifications, qualifications_of((QUAL_MEAT, MEAT_LEVEL_LIGHT)))
        self.assertTrue(by_name["Lekka"].no_night)
        self.assertEqual(by_name["Kierowniczka"].qualifications, qualifications_of(QUAL_MANAGER))
        self.assertEqual(by_name["Tajna"].qualifications, qualifications_of("tajna_rola"))

        self.assertEqual(list(project.qualifications)[:3], [QUAL_OPENER, QUAL_MEAT, QUAL_MANAGER])
        self.assertEqual(project.qualifications[QUAL_MEAT].level_values(), (MEAT_LEVEL_LIGHT, MEAT_LEVEL_FULL))
        # Klucz spoza katalogu profilu nie znika - dostaje pozycję zastępczą.
        self.assertEqual(project.qualifications["tajna_rola"].name, "tajna_rola")
        self.assertNotIn("pusta", project.qualifications)

    def test_first_save_makes_backup_and_writes_new_format(self):
        project, year, month = load_project_bundle(self.path)
        save_project_bundle(self.path, project, year, month)

        with open(self.path + BACKUP_SUFFIX, "rb") as f:
            self.assertEqual(f.read(), self.original_bytes)
        with open(self.path, encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["format_version"], FORMAT_VERSION)
        self.assertEqual([q["id"] for q in saved["qualifications"]][:3], [QUAL_OPENER, QUAL_MEAT, QUAL_MANAGER])
        for month_data in saved["months"].values():
            for employee in month_data["schedule"]["employees"]:
                self.assertIn("qualifications", employee)
                for key in LEGACY_EMPLOYEE_KEYS:
                    self.assertNotIn(key, employee)

        # Drugi zapis (plik już w nowym formacie) nie rusza kopii.
        project.get(2026, 10)[0].get_day(project.get(2026, 10)[0].employees[0], 5).set_free()
        save_project_bundle(self.path, project, year, month)
        with open(self.path + BACKUP_SUFFIX, "rb") as f:
            self.assertEqual(f.read(), self.original_bytes)

    def test_new_format_roundtrip_is_stable(self):
        project, year, month = load_project_bundle(self.path)
        save_project_bundle(self.path, project, year, month)
        with open(self.path, encoding="utf-8") as f:
            first = json.load(f)
        reloaded, year, month = load_project_bundle(self.path)
        save_project_bundle(self.path, reloaded, year, month)
        with open(self.path, encoding="utf-8") as f:
            second = json.load(f)
        self.assertEqual(first, second)

    def test_existing_backup_is_never_overwritten(self):
        with open(self.path + BACKUP_SUFFIX, "w", encoding="utf-8") as f:
            f.write("starsza kopia")
        project, year, month = load_project_bundle(self.path)
        save_project_bundle(self.path, project, year, month)
        with open(self.path + BACKUP_SUFFIX, encoding="utf-8") as f:
            self.assertEqual(f.read(), "starsza kopia")

    def test_saving_brand_new_file_makes_no_backup(self):
        project, year, month = load_project_bundle(self.path)
        new_path = os.path.join(self.tmp.name, "nowy.myp")
        save_project_bundle(new_path, project, year, month)
        self.assertFalse(os.path.exists(new_path + BACKUP_SUFFIX))

    def test_ochrona_bundle_catalog_has_contract_and_no24h(self):
        data = copy.deepcopy(LEGACY_BUNDLE)
        data["months"]["2026-10"] = _legacy_month(2026, 10, [
            _legacy_employee("Straż", custom_roles={"umowa": True, "nie_chce_24h": True}),
        ], business_type="custom_ochrona")
        path = os.path.join(self.tmp.name, "ochrona.myp")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        project, _year, _month = load_project_bundle(path)

        self.assertEqual(project.get(2026, 10)[0].employees[0].qualifications,
                         qualifications_of("umowa", "nie_chce_24h"))
        self.assertEqual(list(project.qualifications), ["umowa", "nie_chce_24h"])
        self.assertEqual(project.qualifications["umowa"].icon, "builtin:contract")


if __name__ == "__main__":
    unittest.main()
