"""Siatka i lista pracowników z katalogu kwalifikacji projektu (Krok 1.4b):
ikony przy nazwisku i kolumna "Flagi" pokazują kwalifikacje ważne w
pokazywanym miesiącu, wiersze podsumowania liczą kwalifikację ważną w danym
dniu."""

import calendar
import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from model.business_profile import DEFAULT_OCHRONA_PROFILE_KEY
from model.constraint_policy import ConstraintPolicy
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.qualification import (
    MEAT_LEVEL_FULL,
    MEAT_LEVEL_LIGHT,
    QUAL_CONTRACT,
    QUAL_MANAGER,
    QUAL_MEAT,
    QUAL_NO_24H,
    QUAL_OPENER,
    EmployeeQualification,
    Qualification,
    level_in_month,
    level_on,
)
from model.shop_config import ShopConfig
from ui.employees_dialog import employee_flag_labels
from ui.grid_view import ScheduleGrid, _employee_badges, _employee_restriction_icons

_app = QApplication.instance() or QApplication([])

YEAR, MONTH = 2026, 10


def _emp(*qualifications, location_key=""):
    return Employee("A", "B", location_key=location_key, qualifications=tuple(qualifications))


def _grid(shop=None, catalog=None):
    grid = ScheduleGrid()
    grid.shop_config = shop or ShopConfig(YEAR, MONTH)
    grid.qualifications = catalog
    return grid


# ---------------------------------------------------------------------------
# level_in_month
# ---------------------------------------------------------------------------

def test_level_in_month_matches_day_by_day_check():
    cases = [
        EmployeeQualification(QUAL_MEAT, 2),
        EmployeeQualification(QUAL_MEAT, 2, valid_from=date(2026, 10, 31)),
        EmployeeQualification(QUAL_MEAT, 2, valid_to=date(2026, 10, 1)),
        EmployeeQualification(QUAL_MEAT, 2, valid_to=date(2026, 9, 30)),
        EmployeeQualification(QUAL_MEAT, 2, valid_from=date(2026, 11, 1)),
        EmployeeQualification(QUAL_MEAT, 2, location_ids=("sklep",)),
        EmployeeQualification(QUAL_MEAT, 2, location_ids=("inny",)),
    ]
    days = range(1, calendar.monthrange(YEAR, MONTH)[1] + 1)
    for qualification in cases:
        emp = _emp(qualification, location_key="sklep")
        expected = max(level_on(emp, QUAL_MEAT, YEAR, MONTH, day) for day in days)
        assert level_in_month(emp, QUAL_MEAT, YEAR, MONTH) == expected, qualification


# ---------------------------------------------------------------------------
# Ikony w siatce
# ---------------------------------------------------------------------------

def test_dino_badges_follow_catalog_order_and_meat_level():
    grid = _grid()
    emp = _emp(EmployeeQualification(QUAL_MANAGER), EmployeeQualification(QUAL_MEAT, MEAT_LEVEL_FULL),
               EmployeeQualification(QUAL_OPENER))
    assert _employee_badges(grid, emp) == [grid.icon_open, grid.icon_meat, grid.icon_manager]

    light = _emp(EmployeeQualification(QUAL_MEAT, MEAT_LEVEL_LIGHT))
    assert _employee_badges(grid, light) == [grid.icon_meat_light]


def test_badge_only_for_qualification_valid_in_shown_month():
    grid = _grid()
    expired = _emp(EmployeeQualification(QUAL_OPENER, valid_to=date(2026, 9, 30)))
    future = _emp(EmployeeQualification(QUAL_OPENER, valid_from=date(2026, 11, 1)))
    partial = _emp(EmployeeQualification(QUAL_OPENER, valid_to=date(2026, 10, 3)))
    assert _employee_badges(grid, expired) == []
    assert _employee_badges(grid, future) == []
    assert _employee_badges(grid, partial) == [grid.icon_open]


def test_meat_badge_hidden_when_meat_policy_disabled():
    shop = ShopConfig(YEAR, MONTH)
    shop.constraint_policies["meat"] = ConstraintPolicy.DISABLED
    grid = _grid(shop)
    assert _employee_badges(grid, _emp(EmployeeQualification(QUAL_MEAT, MEAT_LEVEL_FULL))) == []


def test_catalog_emoji_icon_is_a_badge():
    catalog = {"gasnica": Qualification(id="gasnica", name="Ppoż.", icon="🧯")}
    grid = _grid(catalog=catalog)
    assert len(_employee_badges(grid, _emp(EmployeeQualification("gasnica")))) == 1


def test_contract_and_no_24h_are_small_icons():
    shop = ShopConfig(YEAR, MONTH)
    shop.business_type = DEFAULT_OCHRONA_PROFILE_KEY
    grid = _grid(shop)
    emp = Employee("A", "B", no_night=True, qualifications=(
        EmployeeQualification(QUAL_NO_24H), EmployeeQualification(QUAL_CONTRACT),
    ))
    assert _employee_badges(grid, emp) == []
    assert _employee_restriction_icons(grid, emp) == [grid.icon_no_night, grid.icon_contract, grid.icon_no_24h]


def test_set_data_passes_project_catalog():
    catalog = {"gasnica": Qualification(id="gasnica", name="Ppoż.", icon="🧯")}
    grid = ScheduleGrid()
    grid.set_data(MonthSchedule(YEAR, MONTH), ShopConfig(YEAR, MONTH), controller=None, qualifications=catalog)
    assert grid.qualifications is catalog


# ---------------------------------------------------------------------------
# Wiersz podsumowania kwalifikacji profilu custom ("role:<klucz>")
# ---------------------------------------------------------------------------

def test_role_summary_counts_qualification_valid_that_day():
    from model.business_profile import register_custom_profile
    from model.custom_profile import CustomBusinessProfile, RoleDefinition

    register_custom_profile(CustomBusinessProfile(
        key="custom_test_summary_validity", display_name="Test",
        roles=[RoleDefinition(key="kasa", label="Kasa", show_summary_row=True)], rules=[],
    ))
    shop = ShopConfig(YEAR, MONTH)
    shop.business_type = "custom_test_summary_validity"
    emp = Employee("Kasjerka", "A", qualifications=(EmployeeQualification("kasa", valid_to=date(2026, 10, 10)),))
    schedule = MonthSchedule(YEAR, MONTH, employees=[emp])
    for day in (9, 12):  # ważna / po dacie ważności
        schedule.get_day(emp, day).set_hours("08:00", "16:00")

    grid = ScheduleGrid()
    grid.schedule = schedule
    grid.shop_config = shop
    grid.build()
    grid.refresh()

    row = len(schedule.employees) + next(i for i, (_, key) in enumerate(grid._summary_rows()) if key == "role:kasa")
    assert grid.item(row, 9 + grid._prev_col_offset).text() == "1"
    assert grid.item(row, 12 + grid._prev_col_offset).text() == "0"


# ---------------------------------------------------------------------------
# Kolumna "Flagi" w oknie "Pracownicy"
# ---------------------------------------------------------------------------

def test_flag_labels_use_catalog_names_and_level():
    shop = ShopConfig(YEAR, MONTH)
    emp = Employee("A", "B", no_night=True, qualifications=(
        EmployeeQualification(QUAL_MEAT, MEAT_LEVEL_LIGHT), EmployeeQualification(QUAL_OPENER),
        EmployeeQualification(QUAL_MANAGER, valid_to=date(2026, 9, 30)),  # wygasła przed miesiącem
    ))
    assert employee_flag_labels(emp, shop) == [
        "Otwarcie",
        "Mięso (Pomocniczo – może stanąć na chwilę)",
        "Nie pracuje w godzinach nocnych (przed 6:00 i po 22:00)",
    ]


def test_flag_labels_from_project_catalog():
    shop = ShopConfig(YEAR, MONTH)
    catalog = {QUAL_OPENER: Qualification(id=QUAL_OPENER, name="Otwieranie sklepu")}
    assert employee_flag_labels(_emp(EmployeeQualification(QUAL_OPENER)), shop, catalog) == ["Otwieranie sklepu"]


def test_ochrona_flag_labels():
    shop = ShopConfig(YEAR, MONTH)
    shop.business_type = DEFAULT_OCHRONA_PROFILE_KEY
    emp = Employee("A", "B", no_afternoon=True, qualifications=(
        EmployeeQualification(QUAL_NO_24H), EmployeeQualification(QUAL_CONTRACT),
    ))
    assert employee_flag_labels(emp, shop) == ["Umowa", "Nie chce 24h", "Bez popołudni"]
