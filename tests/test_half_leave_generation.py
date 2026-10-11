"""Pół dnia urlopu ("0,5 urlopu", DaySchedule.is_half_leave) w pełnym
uruchomieniu generatora: dzień zablokowany dokładnie jak zwykły urlop (żadna
zmiana nie trafia do grafiku, komórka zostaje urlopem), a cel godzinowy
pomniejszony tylko o połowę dziennego wymiaru."""

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.auto_generator import AutoScheduleGenerator
from logic.generator.custom_profile_wiring import default_policies
from logic.generator.duty_rotation_constraint import NIE_CHCE_24H_ROLE_KEY
from logic.monthly_hours_status import monthly_hours_status
from model.business_profile import register_custom_profile
from model.constraint_policy import ConstraintPolicy
from model.custom_profile import CustomBusinessProfile
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig

YEAR, MONTH = 2026, 8

ROTATION = {
    "only_12_24h": True,
    "weekend_full": {"start": "08:00"},
    "weekend_half_a": {"start": "08:00", "end": "20:00"},
    "weekend_half_b": {"start": "20:00", "end": "08:00"},
}


def _setup():
    profile = CustomBusinessProfile(key="test_half_leave", display_name="Test Half Leave", roles=[], rules=[])
    register_custom_profile(profile)

    shop = ShopConfig(YEAR, MONTH)
    shop.business_type = profile.key
    loc = LocationConfig(key="site1", name="Site 1")
    loc.set_duty_rotation(ROTATION)
    loc.closed_on_public_holidays = False
    shop.locations = {"site1": loc}
    shop.constraint_policies.update(default_policies(profile))
    shop.constraint_policies["balance"] = ConstraintPolicy.PREFERRED
    shop.constraint_policies["monthly_hours"] = ConstraintPolicy.PREFERRED

    schedule = MonthSchedule(YEAR, MONTH)
    employees = [
        Employee(
            last_name=f"Guard{i}", first_name="Rotation", location_key="site1",
            custom_roles={NIE_CHCE_24H_ROLE_KEY: True},
        )
        for i in range(4)
    ]
    for emp in employees:
        schedule.add_employee(emp)
    return shop, schedule, employees


def test_half_leave_day_is_blocked_and_kept_after_generation():
    shop, schedule, employees = _setup()
    target = employees[0]
    for day in range(1, 6):
        schedule.get_day(target, day).set_leave(half=True)
        schedule.get_day(target, day).is_locked = True

    with redirect_stdout(io.StringIO()):
        result = AutoScheduleGenerator(shop=shop, schedule=schedule).generate(solver_time_limit_seconds=30)

    assert result["success"], result
    for day in range(1, 6):
        ds = schedule.get_day(target, day)
        assert ds.is_leave and ds.is_half_leave
        assert ds.total_duration() is None


def test_half_leave_lowers_target_by_half_of_full_leave():
    shop, schedule, employees = _setup()
    target = employees[0]
    base = monthly_hours_status(schedule, shop, target)["target_minutes"]

    schedule.get_day(target, 3).set_leave()
    full = monthly_hours_status(schedule, shop, target)["target_minutes"]
    schedule.get_day(target, 3).set_leave(half=True)
    half = monthly_hours_status(schedule, shop, target)["target_minutes"]

    assert base - half == (base - full) / 2
