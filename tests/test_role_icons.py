import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from model.business_profile import get_profile, register_custom_profile
from model.custom_profile import CustomBusinessProfile, RoleDefinition
from model.employee import Employee


def test_custom_profile_role_icon_is_registered_and_visible_on_the_business_profile():
    profile = CustomBusinessProfile(
        key="custom_test_icons",
        display_name="Test Icons",
        roles=[
            RoleDefinition(key="uzbrojony", label="Uzbrojony", icon="🔫"),
            RoleDefinition(key="kierownik", label="Kierownik", icon=""),
        ],
        rules=[],
    )
    register_custom_profile(profile)

    resolved = get_profile("custom_test_icons")
    icons = {role.key: role.icon for role in resolved.roles}
    assert icons["uzbrojony"] == "🔫"
    assert icons["kierownik"] == ""


def test_grid_view_badges_include_emoji_icon_for_employee_with_role():
    from ui.grid_view import _employee_badges

    profile = CustomBusinessProfile(
        key="custom_test_icons2",
        display_name="Test Icons 2",
        roles=[RoleDefinition(key="uzbrojony", label="Uzbrojony", icon="🔫")],
        rules=[],
    )
    register_custom_profile(profile)

    class _FakeShop:
        business_type = "custom_test_icons2"
        constraint_policies = {}

    class _FakeTable:
        shop_config = _FakeShop()
        icon_open = icon_meat = icon_meat_light = icon_manager = None

    armed_emp = Employee(last_name="A", first_name="A", custom_roles={"uzbrojony": True})
    plain_emp = Employee(last_name="B", first_name="B", custom_roles={"uzbrojony": False})

    table = _FakeTable()
    assert len(_employee_badges(table, armed_emp)) == 1
    assert len(_employee_badges(table, plain_emp)) == 0


def test_dino_employees_get_no_emoji_badges():
    from ui.grid_view import _employee_badges

    class _FakeShop:
        business_type = "dino_retail"
        constraint_policies = {}

    class _FakeTable:
        shop_config = _FakeShop()
        icon_open = icon_meat = icon_meat_light = icon_manager = None

    emp = Employee(last_name="A", first_name="A")  # no legacy flags set
    assert _employee_badges(_FakeTable(), emp) == []
