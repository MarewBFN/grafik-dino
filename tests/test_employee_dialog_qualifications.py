"""Okno pracownika zbudowane z katalogu kwalifikacji projektu (Krok 1.4a):
wiersz na kwalifikację (zaznaczenie, poziom, ważność i placówki), zapis bez
utraty danych, wymagana data ważności, "Nie chce 24h" przy rotacji 24/7."""

import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from model.employee import Employee
from model.location import LocationConfig
from model.qualification import (
    MEAT_LEVEL_FULL,
    MEAT_LEVEL_LIGHT,
    QUAL_MANAGER,
    QUAL_MEAT,
    QUAL_NO_24H,
    QUAL_OPENER,
    EmployeeQualification,
    Qualification,
    QualificationLevel,
)
from model.shop_config import ShopConfig
from ui.employee_dialog import EmployeeDialog, QualificationScopeDialog, scope_summary

_app = QApplication.instance() or QApplication([])


def _dino_shop():
    return ShopConfig(2026, 10)


def _save(dialog):
    dialog._save()
    return dialog.employee_result


def test_dino_dialog_lists_catalog_qualifications_with_short_names():
    dialog = EmployeeDialog(None, shop_config=_dino_shop())
    rows = dialog.qualification_rows
    assert list(rows) == [QUAL_OPENER, QUAL_MEAT, QUAL_MANAGER]
    assert [row.checkbox.text() for row in rows.values()] == ["Otwarcie", "Mięso", "Kierowniczka"]
    assert rows[QUAL_MEAT].level_combo is not None
    assert rows[QUAL_OPENER].level_combo is None


def test_new_meat_defaults_to_full_service_level():
    dialog = EmployeeDialog(None, shop_config=_dino_shop())
    dialog.last_name.setText("Nowak")
    dialog.qualification_rows[QUAL_MEAT].checkbox.setChecked(True)
    assert _save(dialog).qualifications == (EmployeeQualification(QUAL_MEAT, MEAT_LEVEL_FULL),)


def test_edit_keeps_dates_and_qualifications_outside_the_dialog():
    old = Employee("A", "B", qualifications=(
        EmployeeQualification(QUAL_MEAT, MEAT_LEVEL_FULL, valid_to=date(2027, 1, 1)),
        EmployeeQualification("spoza_katalogu", 3),
    ))
    dialog = EmployeeDialog(None, employee=old, shop_config=_dino_shop())
    meat = dialog.qualification_rows[QUAL_MEAT]
    assert meat.checkbox.isChecked()
    assert meat.scope_btn.text() == "do 01.01.2027"

    dialog.qualification_rows[QUAL_OPENER].checkbox.setChecked(True)
    assert _save(dialog).qualifications == (
        EmployeeQualification(QUAL_MEAT, MEAT_LEVEL_FULL, valid_to=date(2027, 1, 1)),
        EmployeeQualification("spoza_katalogu", 3),
        EmployeeQualification(QUAL_OPENER),
    )


def test_changing_meat_level_keeps_dates():
    old = Employee("A", "B", qualifications=(
        EmployeeQualification(QUAL_MEAT, MEAT_LEVEL_FULL, valid_to=date(2027, 1, 1)),
    ))
    dialog = EmployeeDialog(None, employee=old, shop_config=_dino_shop())
    combo = dialog.qualification_rows[QUAL_MEAT].level_combo
    combo.setCurrentIndex(combo.findData(MEAT_LEVEL_LIGHT))
    assert _save(dialog).qualifications == (
        EmployeeQualification(QUAL_MEAT, MEAT_LEVEL_LIGHT, valid_to=date(2027, 1, 1)),
    )


def test_unchecking_removes_assignment():
    old = Employee("A", "B", qualifications=(EmployeeQualification(QUAL_OPENER), EmployeeQualification(QUAL_MANAGER)))
    dialog = EmployeeDialog(None, employee=old, shop_config=_dino_shop())
    dialog.qualification_rows[QUAL_OPENER].checkbox.setChecked(False)
    assert _save(dialog).qualifications == (EmployeeQualification(QUAL_MANAGER),)


def test_manager_forces_eight_hour_fulltime():
    dialog = EmployeeDialog(None, shop_config=_dino_shop())
    dialog.qualification_rows[QUAL_MANAGER].checkbox.setChecked(True)
    assert dialog.employment_fraction.currentData() == 1.01


def test_untouched_employee_round_trips_unchanged():
    old = Employee("A", "B", location_key="", no_night=True, qualifications=(
        EmployeeQualification(QUAL_OPENER, valid_from=date(2026, 9, 1)),
        EmployeeQualification(QUAL_MEAT, MEAT_LEVEL_LIGHT),
    ))
    saved = _save(EmployeeDialog(None, employee=old, shop_config=_dino_shop()))
    assert saved.qualifications == old.qualifications
    assert saved.no_night is True


# ---------------------------------------------------------------------------
# Katalog projektu
# ---------------------------------------------------------------------------

FORKLIFT = Qualification(
    id="wozek", name="Wózek widłowy", kind="certificate", requires_validity=True,
    levels=(QualificationLevel(1, "Podstawowy"), QualificationLevel(2, "Zaawansowany")),
)


def _catalog():
    return {FORKLIFT.id: FORKLIFT}


def test_dialog_uses_project_catalog():
    dialog = EmployeeDialog(None, shop_config=_dino_shop(), qualifications=_catalog())
    assert list(dialog.qualification_rows) == ["wozek"]
    combo = dialog.qualification_rows["wozek"].level_combo
    assert [combo.itemText(i) for i in range(combo.count())] == ["Podstawowy", "Zaawansowany"]


def test_qualification_requiring_validity_needs_end_date(monkeypatch):
    shown = []
    monkeypatch.setattr("ui.employee_dialog.QMessageBox.critical", lambda *args, **kwargs: shown.append(args))
    dialog = EmployeeDialog(None, shop_config=_dino_shop(), qualifications=_catalog())
    dialog.last_name.setText("Nowak")
    row = dialog.qualification_rows["wozek"]
    row.checkbox.setChecked(True)

    dialog._save()
    assert shown and not hasattr(dialog, "employee_result")

    row.valid_to = date(2027, 3, 31)
    assert _save(dialog).qualifications == (EmployeeQualification("wozek", 2, valid_to=date(2027, 3, 31)),)


def test_location_restriction_saved_on_assignment():
    shop = _dino_shop()
    shop.locations["a"] = LocationConfig(key="a", name="Sklep A")
    shop.locations["b"] = LocationConfig(key="b", name="Sklep B")
    dialog = EmployeeDialog(None, shop_config=shop)
    dialog.last_name.setText("Nowak")
    row = dialog.qualification_rows[QUAL_OPENER]
    row.checkbox.setChecked(True)
    row.location_ids = ("b",)
    row._update_scope_text()
    assert row.scope_btn.text() == "bezterminowo, tylko: Sklep B"
    assert _save(dialog).qualifications == (EmployeeQualification(QUAL_OPENER, location_ids=("b",)),)


def test_scope_dialog_round_trip_and_summary():
    locations = {"a": LocationConfig(key="a", name="A"), "b": LocationConfig(key="b", name="B")}
    dialog = QualificationScopeDialog(
        None, FORKLIFT, date(2026, 10, 5), None, ("b", "zniknieta"), locations, (2026, 10),
    )
    assert dialog.from_check.isChecked() and not dialog.to_check.isChecked()
    assert dialog.location_checks["b"].isChecked() and not dialog.location_checks["a"].isChecked()
    # Placówka spoza projektu zostaje w przypisaniu.
    assert dialog.values() == (date(2026, 10, 5), None, ("zniknieta", "b"))

    dialog.to_check.setChecked(True)  # domyślnie ostatni dzień miesiąca
    assert dialog.values()[1] == date(2026, 10, 31)

    assert scope_summary(date(2026, 10, 5), date(2026, 10, 31), (), locations) == "05.10.2026 – 31.10.2026"
    assert scope_summary(None, None, ("a",), locations) == "bezterminowo, tylko: A"


# ---------------------------------------------------------------------------
# "Nie chce 24h"
# ---------------------------------------------------------------------------

def _rotation_location():
    location = LocationConfig(key="duty", name="Duty 24/7")
    location.set_duty_rotation({
        "only_12_24h": True,
        "weekend_full": {"start": "08:00"},
        "weekend_half_a": {"start": "08:00", "end": "20:00"},
        "weekend_half_b": {"start": "20:00", "end": "08:00"},
    })
    return location


def test_no_24h_hidden_without_rotation_and_preserved_on_save():
    old = Employee("A", "B", qualifications=(EmployeeQualification(QUAL_NO_24H),))
    dialog = EmployeeDialog(None, employee=old, shop_config=_dino_shop())
    assert QUAL_NO_24H not in dialog.qualification_rows
    assert dialog.no_24h_check is None
    assert _save(dialog).qualifications == old.qualifications


def test_no_24h_shown_with_rotation_even_if_catalog_lacks_it():
    shop = _dino_shop()
    shop.locations["duty"] = _rotation_location()
    catalog = {}
    dialog = EmployeeDialog(None, shop_config=shop, qualifications=catalog)
    assert dialog.no_24h_check is dialog.qualification_rows[QUAL_NO_24H].checkbox

    dialog.last_name.setText("Nowak")
    dialog.no_24h_check.setChecked(True)
    assert _save(dialog).qualifications == (EmployeeQualification(QUAL_NO_24H),)
    # Zapis dokłada pozycję do katalogu projektu.
    assert catalog[QUAL_NO_24H].name == "Nie chce 24h"


def test_ochrona_catalog_rows():
    from model.business_profile import DEFAULT_OCHRONA_PROFILE_KEY

    shop = ShopConfig(2026, 10)
    shop.business_type = DEFAULT_OCHRONA_PROFILE_KEY
    dialog = EmployeeDialog(None, shop_config=shop)
    # Ochrona używa modelu godzin otwarcia - "Nie chce 24h" widoczne.
    assert list(dialog.qualification_rows) == ["umowa", QUAL_NO_24H]
    assert dialog.qualification_rows[QUAL_NO_24H].checkbox.toolTip()
