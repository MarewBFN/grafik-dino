"""Pracownicy (pasek menu) - lista pracowników, dane osobowe
(„Zaawansowane”), dodawanie/usuwanie - patrz ui/employees_dialog.py."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

_app = QApplication.instance() or QApplication([])

from logic.schedule_controller import ScheduleController
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from ui import employees_dialog as module
from ui.employees_dialog import EmployeesDialog, PersonalDataDialog, employee_flag_labels


def _setup(*employees):
    shop = ShopConfig(2026, 10)
    schedule = MonthSchedule(2026, 10, employees=list(employees))
    return shop, ScheduleController(schedule, shop)


def test_personal_data_round_trips_through_project_file():
    emp = Employee(
        last_name="Kowalski", first_name="Jan", phone="600 123 456", email="jan@firma.pl",
        street="Polna 1/2", postal_code="00-950", city="Warszawa",
    )
    schedule = MonthSchedule(2026, 10, employees=[emp])

    loaded = MonthSchedule.from_dict(schedule.to_dict()).employees[0]

    assert loaded.personal_data() == emp.personal_data()
    assert loaded.address() == "Polna 1/2, 00-950 Warszawa"


def test_old_project_file_without_personal_data_loads_empty():
    data = MonthSchedule(2026, 10, employees=[Employee(last_name="Nowak", first_name="Anna")]).to_dict()
    for field in ("phone", "email", "street", "postal_code", "city"):
        data["employees"][0].pop(field)

    loaded = MonthSchedule.from_dict(data).employees[0]

    assert loaded.phone == "" and loaded.email == "" and loaded.address() == ""


@pytest.mark.parametrize("kwargs", [
    {"email": "jan.firma.pl"},
    {"phone": "abc"},
    {"postal_code": "00950"},
])
def test_invalid_personal_data_is_rejected(kwargs):
    with pytest.raises(ValueError):
        Employee(last_name="Kowalski", first_name="Jan", **kwargs).validate()


def test_list_shows_all_employees_with_contact_data():
    shop, controller = _setup(
        Employee(last_name="Nowak", first_name="Anna", email="anna@firma.pl"),
        Employee(last_name="Kowalski", first_name="Jan", phone="600123456"),
    )
    dialog = EmployeesDialog(None, controller, shop)

    assert dialog.table.rowCount() == 2
    assert dialog.table.item(0, 0).text() == "Kowalski Jan"
    assert dialog.table.item(0, 4).text() == "600123456"
    assert dialog.table.item(1, 5).text() == "anna@firma.pl"
    assert "(2)" in dialog.title_label.text()


def test_search_filters_the_list():
    shop, controller = _setup(
        Employee(last_name="Nowak", first_name="Anna"),
        Employee(last_name="Kowalski", first_name="Jan"),
    )
    dialog = EmployeesDialog(None, controller, shop)

    dialog.search_edit.setText("nowa")

    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 0).text() == "Nowak Anna"


def test_flags_column_lists_set_roles():
    shop, _ = _setup()
    emp = Employee(last_name="Nowak", first_name="Anna", no_night=True)

    labels = employee_flag_labels(emp, shop)

    assert len(labels) == 1 and "nocn" in labels[0]


def test_advanced_saves_personal_data_and_keeps_schedule(monkeypatch):
    emp = Employee(last_name="Kowalski", first_name="Jan", custom_roles={"x": True})
    shop, controller = _setup(emp)
    controller.schedule.set_day_hours(emp, 3, "08:00", "16:00")
    changes = []
    dialog = EmployeesDialog(None, controller, shop, on_changed=changes.append)

    def fake_exec(self):
        self.phone.setText("600 123 456")
        self.email.setText("jan@firma.pl")
        self.city.setText("Gdańsk")
        self._save()
        return QDialog.Accepted

    monkeypatch.setattr(PersonalDataDialog, "exec", fake_exec)
    dialog._edit_personal_data(emp)

    saved = controller.schedule.employees[0]
    assert (saved.phone, saved.email, saved.city) == ("600 123 456", "jan@firma.pl", "Gdańsk")
    assert saved.custom_roles == {"x": True}
    assert controller.schedule.get_day(saved, 3).start == "08:00"
    assert changes == ["Zapisano dane osobowe."]
    assert dialog.table.item(0, 6).text() == "Gdańsk"


def test_advanced_rename_to_existing_employee_is_refused(monkeypatch):
    jan = Employee(last_name="Kowalski", first_name="Jan")
    anna = Employee(last_name="Nowak", first_name="Anna")
    shop, controller = _setup(jan, anna)
    dialog = EmployeesDialog(None, controller, shop)
    errors = []
    monkeypatch.setattr(module.QMessageBox, "critical", lambda *a, **k: errors.append(a))

    dialog._replace(jan, Employee(last_name="Nowak", first_name="Anna"), "x")

    assert errors
    assert len(controller.schedule.employees) == 2


def test_delete_asks_and_removes(monkeypatch):
    emp = Employee(last_name="Kowalski", first_name="Jan")
    shop, controller = _setup(emp)
    dialog = EmployeesDialog(None, controller, shop)
    monkeypatch.setattr(module.QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)

    dialog._delete_employee(emp)

    assert controller.schedule.employees == []
    assert dialog.table.rowCount() == 0


def test_delete_cancelled_keeps_employee(monkeypatch):
    emp = Employee(last_name="Kowalski", first_name="Jan")
    shop, controller = _setup(emp)
    dialog = EmployeesDialog(None, controller, shop)
    monkeypatch.setattr(module.QMessageBox, "question", lambda *a, **k: QMessageBox.No)

    dialog._delete_employee(emp)

    assert controller.schedule.employees == [emp]


def test_add_employee_adds_to_list(monkeypatch):
    shop, controller = _setup()
    dialog = EmployeesDialog(None, controller, shop)

    def fake_exec(self):
        self.employee_result = Employee(last_name="Wiśniewska", first_name="Ewa")
        return QDialog.Accepted

    monkeypatch.setattr(module.EmployeeDialog, "exec", fake_exec)
    dialog._add_employee()

    assert [e.display_name() for e in controller.schedule.employees] == ["Wiśniewska Ewa"]
    assert dialog.table.rowCount() == 1


def test_employee_dialog_edit_keeps_personal_data():
    from ui.employee_dialog import EmployeeDialog

    shop = ShopConfig(2026, 10)
    emp = Employee(last_name="Kowalski", first_name="Jan", phone="600123456", city="Gdańsk")
    dialog = EmployeeDialog(None, employee=emp, shop_config=shop)

    dialog._save()

    assert dialog.employee_result.phone == "600123456"
    assert dialog.employee_result.city == "Gdańsk"
