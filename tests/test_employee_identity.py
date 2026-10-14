"""Stałe ID pracownika (F1.1): tożsamością pracownika jest Employee.id
zapisywane w pliku, nie imię i nazwisko - dwie osoby o tym samym imieniu i
nazwisku, zmiana nazwiska bez utraty ciągłości, stałe ID dla starych plików."""

import dataclasses
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from model.employee import Employee, legacy_employee_id
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig

_app = QApplication.instance() or QApplication([])


def test_same_name_people_are_distinct_and_survive_save():
    first = Employee("Kowalska", "Anna")
    second = Employee("Kowalska", "Anna")
    assert first != second and len({first, second}) == 2

    schedule = MonthSchedule(2026, 10, employees=[first, second])
    schedule.get_day(first, 5).set_hours("06:00", "14:00")
    schedule.get_day(second, 5).set_hours("14:00", "22:00")

    reloaded = MonthSchedule.from_dict(schedule.to_dict())
    assert {e.id for e in reloaded.employees} == {first.id, second.id}
    assert reloaded.get_day(first, 5).start == "06:00"
    assert reloaded.get_day(second, 5).start == "14:00"


def test_rename_keeps_identity_across_months():
    anna = Employee("Kowalska", "Anna")
    october = MonthSchedule(2026, 10, employees=[anna])
    october.get_day(anna, 31).set_hours("14:00", "22:00")

    renamed = dataclasses.replace(anna, last_name="Nowak")
    november = MonthSchedule(2026, 11, employees=[renamed])

    # Ta sama osoba - po zmianie nazwiska nadal odnajduje swój październik
    # (np. pamięć poprzedniego miesiąca).
    assert october.get_day(renamed, 31).start == "14:00"
    assert november.employees[0] == anna


def test_legacy_file_gets_stable_id_from_name():
    data = MonthSchedule(2026, 10, employees=[Employee("Kowalska", "Anna")]).to_dict()
    for employee in data["employees"]:
        del employee["id"]  # plik sprzed zapisywania ID

    first_load = MonthSchedule.from_dict(data)
    second_load = MonthSchedule.from_dict(data)
    expected = legacy_employee_id("Kowalska", "Anna")
    assert first_load.employees[0].id == second_load.employees[0].id == expected
    assert legacy_employee_id("Kowalska", "Anna") != legacy_employee_id("Kowalska", "Ania")


def test_employees_still_sort_by_name():
    people = [Employee("Nowak", "Ewa"), Employee("Adamska", "Ola"), Employee("Nowak", "Adam")]
    assert [e.display_name() for e in sorted(people)] == ["Adamska Ola", "Nowak Adam", "Nowak Ewa"]


# ---------------------------------------------------------------------------
# Okno pracownika
# ---------------------------------------------------------------------------

def _dialog(**kwargs):
    from ui.employee_dialog import EmployeeDialog

    return EmployeeDialog(None, shop_config=ShopConfig(2026, 10), **kwargs)


def test_edit_keeps_id_and_fields_the_dialog_does_not_show():
    original = Employee(
        "Kowalska", "Anna", daily_hours=7,
        availability={0: [{"start": "06:00", "end": "14:00", "mode": "hard"}]},
    )
    dialog = _dialog(employee=original)
    dialog.last_name.setText("Nowak")
    dialog._save()

    saved = dialog.employee_result
    assert saved.id == original.id
    assert saved.last_name == "Nowak"
    assert saved.availability == original.availability  # dawniej gubione przy każdej edycji
    assert saved.daily_hours == 7


def test_duplicate_name_asks_and_respects_answer(monkeypatch):
    existing = Employee("Kowalska", "Anna")
    answers = []

    def question(*args, **kwargs):
        answers.append(args[2])
        return answer

    monkeypatch.setattr("ui.employee_dialog.QMessageBox.question", question)

    answer = QMessageBox.No
    dialog = _dialog(existing_employees=[existing])
    dialog.last_name.setText("kowalska")
    dialog.first_name.setText("Anna")
    dialog._save()
    assert answers and not hasattr(dialog, "employee_result")

    answer = QMessageBox.Yes
    dialog._save()
    assert dialog.employee_result.id != existing.id


def test_editing_without_name_change_does_not_ask(monkeypatch):
    anna = Employee("Kowalska", "Anna")
    monkeypatch.setattr("ui.employee_dialog.QMessageBox.question", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    dialog = _dialog(employee=anna, existing_employees=[anna])
    dialog._save()
    assert dialog.employee_result.id == anna.id
