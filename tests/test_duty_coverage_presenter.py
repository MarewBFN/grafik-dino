from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.duty_coverage_presenter import is_day_fully_covered, project_uses_duty_rotation
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig

ROTATION = {
    "weekday_long": {"start": "06:00", "end": "22:00"},
    "weekday_short": {"start": "22:00", "end": "06:00"},
    "weekend_full": {"start": "06:00"},
    "weekend_half_a": {"start": "06:00", "end": "18:00"},
    "weekend_half_b": {"start": "18:00", "end": "06:00"},
}

# August 2026: 3=Monday (weekday), 1=Saturday (weekend).
MONDAY = 3
SATURDAY = 1


ROTATION_ONLY_12_24H = {
    "only_12_24h": True,
    "weekend_full": {"start": "06:00"},
    "weekend_half_a": {"start": "06:00", "end": "18:00"},
    "weekend_half_b": {"start": "18:00", "end": "06:00"},
}


def _shop_with_rotation(rotation=ROTATION):
    shop = ShopConfig(2026, 8)
    loc = LocationConfig(key="site1", name="Site 1")
    loc.set_duty_rotation(rotation)
    shop.locations["site1"] = loc
    return shop


def _schedule_with(shop, *employees):
    schedule = MonthSchedule(2026, 8)
    for emp in employees:
        schedule.add_employee(emp)
    return schedule


def test_project_uses_duty_rotation_false_without_any_location():
    shop = ShopConfig(2026, 8)
    emp = Employee(last_name="A", first_name="A")
    assert project_uses_duty_rotation(shop, [emp]) is False


def test_project_uses_duty_rotation_true_when_a_location_has_it():
    shop = _shop_with_rotation()
    emp = Employee(last_name="A", first_name="A", location_key="site1")
    assert project_uses_duty_rotation(shop, [emp]) is True


def test_weekday_fully_covered_with_both_shifts_assigned():
    shop = _shop_with_rotation()
    long_emp = Employee(last_name="Long", first_name="A", location_key="site1")
    short_emp = Employee(last_name="Short", first_name="B", location_key="site1")
    schedule = _schedule_with(shop, long_emp, short_emp)
    schedule.get_day(long_emp, MONDAY).set_hours("06:00", "22:00")
    schedule.get_day(short_emp, MONDAY).set_hours("22:00", "06:00")

    assert is_day_fully_covered(schedule, shop, [long_emp, short_emp], MONDAY) is True


def test_weekday_not_covered_when_short_shift_is_missing():
    shop = _shop_with_rotation()
    long_emp = Employee(last_name="Long", first_name="A", location_key="site1")
    other_emp = Employee(last_name="Idle", first_name="B", location_key="site1")
    schedule = _schedule_with(shop, long_emp, other_emp)
    schedule.get_day(long_emp, MONDAY).set_hours("06:00", "22:00")
    # other_emp stays empty that day.

    assert is_day_fully_covered(schedule, shop, [long_emp, other_emp], MONDAY) is False


def test_weekend_fully_covered_by_a_single_24h_shift():
    shop = _shop_with_rotation()
    emp = Employee(last_name="A", first_name="A", location_key="site1")
    schedule = _schedule_with(shop, emp)
    schedule.get_day(emp, SATURDAY).set_full_day_shift("06:00")

    assert is_day_fully_covered(schedule, shop, [emp], SATURDAY) is True


def test_weekend_fully_covered_by_both_halves():
    shop = _shop_with_rotation()
    half_a_emp = Employee(last_name="A", first_name="A", location_key="site1")
    half_b_emp = Employee(last_name="B", first_name="B", location_key="site1")
    schedule = _schedule_with(shop, half_a_emp, half_b_emp)
    schedule.get_day(half_a_emp, SATURDAY).set_hours("06:00", "18:00")
    schedule.get_day(half_b_emp, SATURDAY).set_hours("18:00", "06:00")

    assert is_day_fully_covered(schedule, shop, [half_a_emp, half_b_emp], SATURDAY) is True


def test_weekend_not_covered_with_only_one_half_assigned():
    shop = _shop_with_rotation()
    half_a_emp = Employee(last_name="A", first_name="A", location_key="site1")
    idle_emp = Employee(last_name="B", first_name="B", location_key="site1")
    schedule = _schedule_with(shop, half_a_emp, idle_emp)
    schedule.get_day(half_a_emp, SATURDAY).set_hours("06:00", "18:00")

    assert is_day_fully_covered(schedule, shop, [half_a_emp, idle_emp], SATURDAY) is False


def test_empty_day_is_not_covered():
    shop = _shop_with_rotation()
    emp = Employee(last_name="A", first_name="A", location_key="site1")
    schedule = _schedule_with(shop, emp)

    assert is_day_fully_covered(schedule, shop, [emp], MONDAY) is False
    assert is_day_fully_covered(schedule, shop, [emp], SATURDAY) is False


def test_only_12_24h_weekday_covered_by_a_single_24h_shift():
    shop = _shop_with_rotation(rotation=ROTATION_ONLY_12_24H)
    emp = Employee(last_name="A", first_name="A", location_key="site1")
    schedule = _schedule_with(shop, emp)
    schedule.get_day(emp, MONDAY).set_full_day_shift("06:00")

    assert is_day_fully_covered(schedule, shop, [emp], MONDAY) is True


def test_only_12_24h_weekday_covered_by_both_halves():
    shop = _shop_with_rotation(rotation=ROTATION_ONLY_12_24H)
    half_a_emp = Employee(last_name="A", first_name="A", location_key="site1")
    half_b_emp = Employee(last_name="B", first_name="B", location_key="site1")
    schedule = _schedule_with(shop, half_a_emp, half_b_emp)
    schedule.get_day(half_a_emp, MONDAY).set_hours("06:00", "18:00")
    schedule.get_day(half_b_emp, MONDAY).set_hours("18:00", "06:00")

    assert is_day_fully_covered(schedule, shop, [half_a_emp, half_b_emp], MONDAY) is True


# --- LocationConfig.closed_on_public_holidays: dzień zamknięty w
# automatycznie wykryte polskie święto liczy się jako "pokryty" (nikt nie
# jest tam wymagany), nie jako błąd - patrz
# logic/generator/duty_rotation_public_holiday_constraint.py ---


def test_closed_public_holiday_counts_as_covered_even_with_nobody_assigned():
    # Styczeń 2026, dzień 1 = Nowy Rok (czwartek, dzień roboczy).
    shop = ShopConfig(2026, 1)
    loc = LocationConfig(key="site1", name="Site 1")
    loc.set_duty_rotation(ROTATION)
    shop.locations["site1"] = loc
    long_emp = Employee(last_name="Long", first_name="A", location_key="site1")
    short_emp = Employee(last_name="Short", first_name="B", location_key="site1")
    schedule = MonthSchedule(2026, 1)
    schedule.add_employee(long_emp)
    schedule.add_employee(short_emp)
    # Nikt nie ma przypisanej zmiany tego dnia.

    assert is_day_fully_covered(schedule, shop, [long_emp, short_emp], 1) is True


def test_regular_day_in_the_same_month_still_requires_full_coverage():
    # Styczeń 2026, dzień 2 (piątek) - zwykły dzień roboczy, bez święta.
    shop = ShopConfig(2026, 1)
    loc = LocationConfig(key="site1", name="Site 1")
    loc.set_duty_rotation(ROTATION)
    shop.locations["site1"] = loc
    long_emp = Employee(last_name="Long", first_name="A", location_key="site1")
    short_emp = Employee(last_name="Short", first_name="B", location_key="site1")
    schedule = MonthSchedule(2026, 1)
    schedule.add_employee(long_emp)
    schedule.add_employee(short_emp)

    assert is_day_fully_covered(schedule, shop, [long_emp, short_emp], 2) is False


def test_toggle_off_still_requires_coverage_on_a_public_holiday():
    shop = ShopConfig(2026, 1)
    loc = LocationConfig(key="site1", name="Site 1", closed_on_public_holidays=False)
    loc.set_duty_rotation(ROTATION)
    shop.locations["site1"] = loc
    long_emp = Employee(last_name="Long", first_name="A", location_key="site1")
    short_emp = Employee(last_name="Short", first_name="B", location_key="site1")
    schedule = MonthSchedule(2026, 1)
    schedule.add_employee(long_emp)
    schedule.add_employee(short_emp)

    assert is_day_fully_covered(schedule, shop, [long_emp, short_emp], 1) is False


def test_only_12_24h_weekday_not_covered_by_a_16h_shift():
    """Gdyby ktoś ręcznie ustawił 06:00-22:00 (stary wzorzec weekday_long)
    na lokalizacji z only_12_24h, to i tak nie liczy się jako pokrycie -
    ten typ zmiany nie należy już do repertuaru tej lokalizacji."""
    shop = _shop_with_rotation(rotation=ROTATION_ONLY_12_24H)
    emp = Employee(last_name="A", first_name="A", location_key="site1")
    schedule = _schedule_with(shop, emp)
    schedule.get_day(emp, MONDAY).set_hours("06:00", "22:00")

    assert is_day_fully_covered(schedule, shop, [emp], MONDAY) is False
