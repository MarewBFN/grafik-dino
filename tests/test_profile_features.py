import calendar
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from model.business_profile import register_custom_profile
from model.constraint_policy import ConstraintPolicy
from model.custom_profile import CustomBusinessProfile, RoleDefinition
from model.employee import Employee
from model.shop_config import ShopConfig
from ui.employee_dialog import EmployeeDialog
from ui.grid_view import _employee_badges, ScheduleGrid


def _first_sunday(year, month):
    for day in range(1, 32):
        try:
            if calendar.weekday(year, month, day) == 6:
                return day
        except ValueError:
            break
    raise AssertionError("no Sunday found")


def test_dino_retail_keeps_trade_calendar_behavior():
    shop = ShopConfig(2026, 3)  # business_type defaults to dino_retail
    sunday = _first_sunday(2026, 3)

    assert shop.is_trade_day(sunday) is False  # trade_sundays empty by default
    shop.trade_sundays.add(sunday)
    assert shop.is_trade_day(sunday) is True


def test_custom_profile_ignores_trade_calendar_by_default():
    profile = CustomBusinessProfile(
        key="custom_test_trade_calendar",
        display_name="Test Trade Calendar",
        roles=[RoleDefinition(key="worker", label="Pracownik")],
        rules=[],
    )
    register_custom_profile(profile)

    shop = ShopConfig(2026, 3)
    shop.business_type = profile.key
    sunday = _first_sunday(2026, 3)

    # No trade_sundays/public_holidays set, and none should matter - every
    # day is a normal working day for a profile without uses_trade_calendar.
    assert shop.is_trade_day(sunday) is True
    shop.public_holidays.add(sunday)
    assert shop.is_trade_day(sunday) is True


def test_employee_dialog_hides_meat_roles_when_meat_policy_disabled():
    shop = ShopConfig(2026, 3)  # dino_retail
    shop.constraint_policies["meat"] = ConstraintPolicy.DISABLED

    dialog = EmployeeDialog(None, shop_config=shop)
    assert "is_meat" not in dialog.role_checkboxes
    assert "is_meat_light" not in dialog.role_checkboxes
    assert "is_opener" in dialog.role_checkboxes  # unrelated role stays


def test_employee_dialog_shows_meat_roles_when_meat_policy_enabled():
    shop = ShopConfig(2026, 3)  # meat defaults to PREFERRED
    dialog = EmployeeDialog(None, shop_config=shop)
    assert "is_meat" in dialog.role_checkboxes
    assert "is_meat_light" in dialog.role_checkboxes


def test_editing_employee_with_meat_disabled_preserves_is_meat_flag():
    shop = ShopConfig(2026, 3)
    shop.constraint_policies["meat"] = ConstraintPolicy.DISABLED

    existing = Employee(last_name="A", first_name="A", is_meat=True, is_opener=True)
    dialog = EmployeeDialog(None, employee=existing, shop_config=shop)

    # No checkbox to toggle is_opener off through, but flip it to prove the
    # save path still works normally for a visible role...
    dialog.role_checkboxes["is_opener"].setChecked(False)
    dialog._save()

    saved = dialog.employee_result
    assert saved.is_opener is False  # visible role: honors the UI change
    assert saved.is_meat is True  # hidden role: preserved, not wiped to False


def test_grid_view_hides_meat_summary_row_and_badge_when_disabled():
    shop = ShopConfig(2026, 3)
    shop.constraint_policies["meat"] = ConstraintPolicy.DISABLED

    grid = ScheduleGrid()
    grid.shop_config = shop
    rows = grid._summary_rows()
    assert not any(key == "meat" for _, key in rows)

    class _FakeTable:
        shop_config = shop
        icon_open = icon_meat = icon_meat_light = icon_manager = None

    emp = Employee(last_name="A", first_name="A", is_meat=True)
    assert _employee_badges(_FakeTable(), emp) == []


def test_grid_view_hides_open_and_close_summary_rows_independently_when_disabled():
    shop = ShopConfig(2026, 3)  # dino_retail; open/close default to MANDATORY

    grid = ScheduleGrid()
    grid.shop_config = shop
    rows = grid._summary_rows()
    assert any(key == "open" for _, key in rows)
    assert any(key == "close" for _, key in rows)

    shop.constraint_policies["close"] = ConstraintPolicy.DISABLED
    rows = grid._summary_rows()
    assert any(key == "open" for _, key in rows)  # untouched policy stays
    assert not any(key == "close" for _, key in rows)

    shop.constraint_policies["open"] = ConstraintPolicy.DISABLED
    rows = grid._summary_rows()
    assert not any(key == "open" for _, key in rows)
    assert not any(key == "close" for _, key in rows)
