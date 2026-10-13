"""Katalog kwalifikacji projektu (Krok 1.4c): edytor Plik -> "Kwalifikacje",
uzupełnianie katalogu o nowe role profilu, ochrona kwalifikacji z profilu i
używanych przez pracowników."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from model.business_profile import register_custom_profile
from model.custom_profile import CustomBusinessProfile, RoleDefinition, RuleInstance
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.monthly_project import MonthlyProject
from model.qualification import (
    DINO_QUALIFICATIONS,
    QUAL_MANAGER,
    QUAL_MEAT,
    QUAL_OPENER,
    EmployeeQualification,
    Qualification,
)
from model.shop_config import ShopConfig
from ui.qualifications_dialog import QualificationsDialog, levels_from_text, levels_to_text, new_qualification_key

_app = QApplication.instance() or QApplication([])


def _project(*employees, business_type=None, month=10):
    project = MonthlyProject()
    shop = ShopConfig(2026, month)
    if business_type:
        shop.business_type = business_type
    project.put(2026, month, MonthSchedule(2026, month, employees=list(employees)), shop)
    project.ensure_qualification_catalog()
    return project


def _dialog(project, **kwargs):
    return QualificationsDialog(
        None, project.qualifications,
        usage=project.qualification_usage(), protected=project.protected_qualifications(), **kwargs,
    )


def _select(dialog, key):
    row = next(i for i, (k, _q) in enumerate(dialog._items) if k == key)
    dialog.list.setCurrentRow(row)


def _save(dialog, monkeypatch=None):
    errors = []
    if monkeypatch is not None:
        monkeypatch.setattr("ui.qualifications_dialog.QMessageBox.critical", lambda *a, **k: errors.append(a[2]))
    dialog._save()
    return errors


# ---------------------------------------------------------------------------
# MonthlyProject
# ---------------------------------------------------------------------------

def test_catalog_gets_new_profile_role_without_touching_edited_entries():
    key = "custom_test_catalog_merge"
    register_custom_profile(CustomBusinessProfile(
        key=key, display_name="T", roles=[RoleDefinition(key="kasa", label="Kasa")], rules=[],
    ))
    project = _project(business_type=key)
    project.qualifications["kasa"] = Qualification(id="kasa", name="Kasa fiskalna")  # edycja użytkownika

    register_custom_profile(CustomBusinessProfile(
        key=key, display_name="T",
        roles=[RoleDefinition(key="kasa", label="Kasa"), RoleDefinition(key="dostawa", label="Dostawa")], rules=[],
    ))
    project.ensure_qualification_catalog()

    assert list(project.qualifications) == ["kasa", "dostawa"]
    assert project.qualifications["kasa"].name == "Kasa fiskalna"


def test_protected_qualifications_cover_profile_defaults_and_rule_keys():
    key = "custom_test_catalog_protected"
    register_custom_profile(CustomBusinessProfile(
        key=key, display_name="T", roles=[RoleDefinition(key="kasa", label="Kasa")],
        rules=[RuleInstance(type="min_staff_with_role", qualification_key="spoza_rol", params={})],
    ))
    project = _project(business_type=key)
    project.put(2026, 11, MonthSchedule(2026, 11), ShopConfig(2026, 11))  # Dino
    assert project.protected_qualifications() == {"kasa", "spoza_rol", *(q.id for q in DINO_QUALIFICATIONS)}


def test_usage_counts_each_employee_once_and_top_level():
    emp = Employee("A", "B", qualifications=(EmployeeQualification(QUAL_MEAT, 1),))
    project = _project(emp)
    later = Employee("A", "B", qualifications=(EmployeeQualification(QUAL_MEAT, 2),))
    project.put(2026, 11, MonthSchedule(2026, 11, employees=[later]), ShopConfig(2026, 11))
    assert project.qualification_usage() == {QUAL_MEAT: (1, 2)}


# ---------------------------------------------------------------------------
# Okno
# ---------------------------------------------------------------------------

def test_levels_text_round_trip():
    levels = levels_from_text("Pomocniczo\n\n  Pełna obsługa  \n")
    assert [(level.value, level.name) for level in levels] == [(1, "Pomocniczo"), (2, "Pełna obsługa")]
    assert levels_to_text(levels) == "Pomocniczo\nPełna obsługa"
    assert levels_from_text("") == ()


def test_new_key_is_ascii_and_unique():
    assert new_qualification_key("Wózek widłowy", set()) == "wozek_widlowy"
    assert new_qualification_key("Wózek widłowy", {"wozek_widlowy"}) == "wozek_widlowy_2"


def test_rename_keeps_key_and_unchanged_catalog_round_trips():
    project = _project()
    dialog = _dialog(project)
    assert _save(dialog) == []
    assert dialog.qualifications == project.qualifications

    dialog = _dialog(project)
    _select(dialog, QUAL_OPENER)
    dialog.name_edit.setText("Otwieranie sklepu")
    dialog.name_edit.textEdited.emit("Otwieranie sklepu")
    _save(dialog)
    assert list(dialog.qualifications) == [q.id for q in DINO_QUALIFICATIONS]
    assert dialog.qualifications[QUAL_OPENER].name == "Otwieranie sklepu"
    assert dialog.qualifications[QUAL_OPENER].icon == "builtin:open"


def test_add_certificate_with_levels_and_validity():
    project = _project()
    dialog = _dialog(project)
    dialog._add()
    dialog.name_edit.setText("Wózek widłowy")
    dialog.name_edit.textEdited.emit("Wózek widłowy")
    dialog.kind_combo.setCurrentIndex(dialog.kind_combo.findData("certificate"))
    dialog.validity_check.setChecked(True)
    dialog.levels_edit.setPlainText("Podstawowy\nZaawansowany")
    dialog.icon_combo.setCurrentIndex(dialog.icon_combo.findData("📦"))
    assert _save(dialog) == []

    forklift = dialog.qualifications["wozek_widlowy"]
    assert forklift.kind == "certificate" and forklift.requires_validity and forklift.icon == "📦"
    assert [level.name for level in forklift.levels] == ["Podstawowy", "Zaawansowany"]


def test_remove_only_unused_qualifications_outside_profile():
    project = _project(Employee("A", "B", qualifications=(EmployeeQualification("gasnica"),)))
    project.qualifications["gasnica"] = Qualification(id="gasnica", name="Ppoż.")
    project.qualifications["stara"] = Qualification(id="stara", name="Nieużywana")
    dialog = _dialog(project)

    _select(dialog, QUAL_MANAGER)
    assert not dialog.remove_btn.isEnabled()  # z profilu Dino
    _select(dialog, "gasnica")
    assert not dialog.remove_btn.isEnabled()  # ma ją pracownik
    _select(dialog, "stara")
    assert dialog.remove_btn.isEnabled()


def test_save_rejects_duplicate_names(monkeypatch):
    project = _project()
    dialog = _dialog(project)
    dialog._add()
    dialog.name_edit.setText("otwarcie")
    dialog.name_edit.textEdited.emit("otwarcie")
    assert _save(dialog, monkeypatch)
    assert dialog.qualifications == {}


def test_meat_level_count_is_fixed(monkeypatch):
    project = _project()
    dialog = _dialog(project)
    _select(dialog, QUAL_MEAT)
    dialog.levels_edit.setPlainText("Jedyny poziom")
    assert _save(dialog, monkeypatch)

    dialog.levels_edit.setPlainText("Na chwilę\nCały dzień")
    assert _save(dialog, monkeypatch) == []
    assert [level.name for level in dialog.qualifications[QUAL_MEAT].levels] == ["Na chwilę", "Cały dzień"]


def test_cannot_drop_levels_employees_use(monkeypatch):
    project = _project(Employee("A", "B", qualifications=(EmployeeQualification("jezyk", 3),)))
    project.qualifications["jezyk"] = Qualification(id="jezyk", name="Angielski")
    dialog = _dialog(project)
    _select(dialog, "jezyk")
    dialog.levels_edit.setPlainText("A1\nA2")
    assert _save(dialog, monkeypatch)
    dialog.levels_edit.setPlainText("A1\nA2\nB1")
    assert _save(dialog, monkeypatch) == []


def test_unchanged_placeholder_with_levels_outside_scale_still_saves():
    # Pozycja zastępcza (profil usunięty z komputera) bez skali poziomów, a
    # pracownik ma poziom 3 - zapis okna bez zmian nie może być blokowany.
    project = _project(Employee("A", "B", qualifications=(EmployeeQualification("stara_rola", 3),)))
    assert project.qualifications["stara_rola"].levels == ()
    dialog = _dialog(project)
    assert _save(dialog) == []
    assert "stara_rola" in dialog.qualifications
