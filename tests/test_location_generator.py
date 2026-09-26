import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model.business_profile import register_custom_profile
from model.constraint_policy import ConstraintPolicy
from model.custom_profile import (
    RULE_TYPE_MIN_STAFF_WITH_ROLE,
    CustomBusinessProfile,
    RoleDefinition,
    RuleInstance,
)
from logic.generator.custom_profile_wiring import default_policies
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from logic.auto_generator import AutoScheduleGenerator


def test_multi_location_generator_resolves_each_employees_own_location_hours():
    profile = CustomBusinessProfile(
        key="custom_test_multiloc",
        display_name="Test MultiLoc",
        roles=[RoleDefinition(key="worker", label="Pracownik")],
        rules=[],
    )
    register_custom_profile(profile)

    shop = ShopConfig(2026, 3)
    shop.business_type = profile.key
    shop.constraint_policies.update(default_policies(profile))

    # Generous, non-overlapping windows (>= 8h shift + 90min offset on each
    # side) so every shift variant comfortably fits inside its own location's
    # hours - the point of this test is whether the right location's hours
    # get used at all, not exercising every offset edge case.
    loc_a = LocationConfig(key="loc_a", name="Obiekt A", open_hours={i: ("00:00", "11:00") for i in range(7)})
    loc_b = LocationConfig(key="loc_b", name="Obiekt B", open_hours={i: ("12:00", "23:00") for i in range(7)})
    shop.locations = {"loc_a": loc_a, "loc_b": loc_b}

    schedule = MonthSchedule(2026, 3)
    employees = [
        Employee(last_name="Alfa1", first_name="A", location_key="loc_a", custom_roles={"worker": True}),
        Employee(last_name="Alfa2", first_name="A", location_key="loc_a", custom_roles={"worker": True}),
        Employee(last_name="Beta1", first_name="B", location_key="loc_b", custom_roles={"worker": True}),
        Employee(last_name="Beta2", first_name="B", location_key="loc_b", custom_roles={"worker": True}),
    ]
    for emp in employees:
        schedule.add_employee(emp)

    with redirect_stdout(io.StringIO()):
        result = AutoScheduleGenerator(schedule, shop).generate(
            solver_time_limit_seconds=10, solver_workers=2
        )

    assert result["success"], result["infeasibility_reasons"]

    checked_any = False
    for emp in employees:
        expected_start, expected_end = ("00:00", "11:00") if emp.location_key == "loc_a" else ("12:00", "23:00")
        for day in range(1, schedule.days_in_month + 1):
            ds = schedule.get_day(emp, day)
            if not ds.start or ds.is_leave:
                continue
            checked_any = True
            assert expected_start <= ds.start, (emp.location_key, day, ds.start, ds.end)
            assert ds.end <= expected_end, (emp.location_key, day, ds.start, ds.end)

    assert checked_any, "generator produced no assigned shifts to check"


def test_max_consecutive_days_is_resolved_per_employee_location():
    profile = CustomBusinessProfile(
        key="custom_test_maxconsec",
        display_name="Test MaxConsec",
        roles=[RoleDefinition(key="worker", label="Pracownik")],
        rules=[],
    )
    register_custom_profile(profile)

    def build(location_max_consecutive):
        shop = ShopConfig(2026, 3)
        shop.business_type = profile.key
        shop.constraint_policies.update(default_policies(profile))
        from model.constraint_policy import ConstraintPolicy
        shop.constraint_policies["max_consecutive"] = ConstraintPolicy.MANDATORY

        loc = LocationConfig(
            key="loc", name="Obiekt",
            open_hours={i: ("08:00", "16:00") for i in range(7)},
            constraints={"max_consecutive_days": location_max_consecutive},
        )
        shop.locations = {"loc": loc}

        schedule = MonthSchedule(2026, 3)
        emp = Employee(last_name="A", first_name="A", location_key="loc", custom_roles={"worker": True})
        schedule.add_employee(emp)

        # Lock 3 consecutive worked days - satisfiable only if the location's
        # max_consecutive_days allows 3+ in a row.
        for day in (2, 3, 4):
            ds = schedule.get_day(emp, day)
            ds.start, ds.end = "08:00", "16:00"
            ds.is_locked = True

        with redirect_stdout(io.StringIO()):
            result = AutoScheduleGenerator(schedule, shop).generate(
                is_fix=True, solver_time_limit_seconds=10, solver_workers=1
            )
        return result["success"]

    assert build(2) is False, "3 locked consecutive days should conflict with a 2-day location limit"
    assert build(6) is True, "3 locked consecutive days should be fine under a 6-day location limit"


def test_min_staff_with_role_rule_is_resolved_per_employee_location():
    rule = RuleInstance(
        type=RULE_TYPE_MIN_STAFF_WITH_ROLE, role_key="guard",
        policy="MANDATORY", params={"min_count": 1, "scope": "open"},
    )
    profile = CustomBusinessProfile(
        key="custom_test_minstaff_loc",
        display_name="Test MinStaffLoc",
        roles=[RoleDefinition(key="guard", label="Ochroniarz")],
        rules=[rule],
    )
    register_custom_profile(profile)
    rule_key = profile.rule_policy_key(rule)

    def build(location_min_count):
        shop = ShopConfig(2026, 3)
        shop.business_type = profile.key
        shop.constraint_policies.update(default_policies(profile))
        shop.constraint_policies[rule_key] = ConstraintPolicy.MANDATORY

        loc = LocationConfig(
            key="loc", name="Obiekt",
            open_hours={i: ("08:00", "16:00") for i in range(7)},
            constraints={rule_key: location_min_count},
        )
        shop.locations = {"loc": loc}

        schedule = MonthSchedule(2026, 3)
        emp = Employee(last_name="A", first_name="A", location_key="loc", custom_roles={"guard": True})
        schedule.add_employee(emp)

        with redirect_stdout(io.StringIO()):
            result = AutoScheduleGenerator(schedule, shop).generate(
                solver_time_limit_seconds=10, solver_workers=1
            )
        return result["success"]

    assert build(1) is True, "one guard should satisfy a 1-guard location threshold"
    assert build(2) is False, "one guard can never satisfy a 2-guard location threshold"


def test_min_staff_with_role_rule_skips_days_when_every_role_holder_location_is_closed():
    """11.11.2026 (święto): placówka A (wszyscy z rolą) zamknięta
    (closed_on_public_holidays), placówka B czynna - dzień zostaje w
    trade_days. Od kiedy dzień zamknięty lokalizacji blokuje wszystkie
    zmiany (add_non_trade_day_constraints), reguła "min. 1 z rolą" była tego
    dnia niespełnialna i cały miesiąc wychodził bez rozwiązania (wcześniej
    solver "spełniał" ją niewidoczną zmianą w zamkniętej placówce)."""
    rule = RuleInstance(
        type=RULE_TYPE_MIN_STAFF_WITH_ROLE, role_key="kier",
        policy="MANDATORY", params={"min_count": 1, "scope": "any_shift"},
    )
    profile = CustomBusinessProfile(
        key="custom_test_minstaff_closed_loc",
        display_name="Test MinStaffClosedLoc",
        roles=[RoleDefinition(key="kier", label="Kierownik")],
        rules=[rule],
    )
    register_custom_profile(profile)

    shop = ShopConfig(2026, 11)
    shop.business_type = profile.key
    shop.constraint_policies.update(default_policies(profile))
    shop.constraint_policies["balance"] = ConstraintPolicy.DISABLED
    shop.constraint_policies["monthly_hours"] = ConstraintPolicy.DISABLED
    shop.locations = {
        "a": LocationConfig(key="a", name="A", open_hours={i: ("08:00", "16:00") for i in range(7)}),
        "b": LocationConfig(
            key="b", name="B", open_hours={i: ("08:00", "16:00") for i in range(7)},
            closed_on_public_holidays=False,
        ),
    }
    employees = [
        Employee(last_name=f"A{i}", first_name="X", location_key="a", custom_roles={"kier": True})
        for i in range(3)
    ] + [Employee(last_name=f"B{i}", first_name="X", location_key="b") for i in range(3)]
    schedule = MonthSchedule(2026, 11, employees=employees)

    with redirect_stdout(io.StringIO()):
        result = AutoScheduleGenerator(schedule, shop).generate(solver_time_limit_seconds=20, solver_workers=2)

    assert result["success"], result.get("infeasibility_reasons")
    assert all(schedule.get_day(emp, 11).is_empty() for emp in employees[:3])
    assert any(not schedule.get_day(emp, 12).is_empty() for emp in employees[:3])


def test_shop_config_get_location_falls_back_to_self_without_locations():
    shop = ShopConfig(2026, 3)
    emp = Employee(last_name="Kowalski", first_name="Jan")

    assert shop.get_location(emp) is shop


def test_shop_config_get_location_falls_back_when_employee_unassigned():
    shop = ShopConfig(2026, 3)
    shop.locations["loc_a"] = LocationConfig(key="loc_a", name="Obiekt A")
    emp = Employee(last_name="Kowalski", first_name="Jan")  # location_key == ""

    assert shop.get_location(emp) is shop
