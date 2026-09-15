import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from model.location import LocationConfig, normalize_night_shift
from model.shop_config import ShopConfig
from model.employee import Employee
from model.month_schedule import MonthSchedule


def test_location_config_round_trips_through_dict():
    loc = LocationConfig(
        key="galeria_pn",
        name="Galeria Płn",
        open_hours={0: ("08:00", "20:00")},
        trade_sundays={7, 21},
        public_holidays={1},
        day_overrides={15: ("10:00", "18:00")},
        constraints={"min_open_staff": 2, "min_close_staff": 2, "max_consecutive_days": 5},
    )

    restored = LocationConfig.from_dict(loc.to_dict())

    assert restored.key == "galeria_pn"
    assert restored.name == "Galeria Płn"
    assert restored.open_hours == {0: ("08:00", "20:00")}
    assert restored.trade_sundays == {7, 21}
    assert restored.public_holidays == {1}
    assert restored.day_overrides == {15: ("10:00", "18:00")}
    assert restored.constraints == {"min_open_staff": 2, "min_close_staff": 2, "max_consecutive_days": 5}
    assert restored.night_shift is None


# --- Etap B (plan zmiany nocne): night_shift na lokalizacji i na ShopConfig ---


def test_normalize_night_shift_accepts_empty_pair_as_no_window():
    assert normalize_night_shift(None, None) is None
    assert normalize_night_shift("", "") is None


def test_normalize_night_shift_rejects_a_single_missing_side():
    with pytest.raises(ValueError):
        normalize_night_shift("22:00", None)
    with pytest.raises(ValueError):
        normalize_night_shift(None, "06:00")


def test_normalize_night_shift_rejects_equal_start_and_end():
    with pytest.raises(ValueError):
        normalize_night_shift("22:00", "22:00")


def test_normalize_night_shift_allows_crossing_midnight():
    assert normalize_night_shift("22:00", "06:00") == {"start": "22:00", "end": "06:00"}


def test_location_config_night_shift_set_get_and_round_trip():
    loc = LocationConfig(key="obiekt_1", name="Obiekt 1")
    assert loc.get_night_shift_hours() is None

    loc.set_night_shift("22:00", "06:00")
    assert loc.get_night_shift_hours() == ("22:00", "06:00")

    restored = LocationConfig.from_dict(loc.to_dict())
    assert restored.get_night_shift_hours() == ("22:00", "06:00")

    loc.set_night_shift(None, None)
    assert loc.get_night_shift_hours() is None


def test_location_config_night_shift_defaults_none_for_old_data():
    loc = LocationConfig(key="obiekt_1", name="Obiekt 1")
    data = loc.to_dict()
    del data["night_shift"]  # simulate a project saved before this field existed

    restored = LocationConfig.from_dict(data)
    assert restored.night_shift is None
    assert restored.get_night_shift_hours() is None


def test_shop_config_night_shift_set_get_and_round_trip():
    shop = ShopConfig(2026, 8)
    assert shop.get_night_shift_hours() is None

    shop.set_night_shift("22:00", "06:00")
    assert shop.get_night_shift_hours() == ("22:00", "06:00")

    restored = ShopConfig.from_dict(shop.to_dict())
    assert restored.get_night_shift_hours() == ("22:00", "06:00")


def test_shop_config_night_shift_defaults_none_for_old_data():
    shop = ShopConfig(2026, 8)
    data = shop.to_dict()
    del data["night_shift"]  # simulate a project saved before this field existed

    restored = ShopConfig.from_dict(data)
    assert restored.get_night_shift_hours() is None


def test_get_location_exposes_night_shift_hours_for_assigned_employee():
    shop = ShopConfig(2026, 8)
    shop.set_night_shift("21:00", "05:00")  # project-level default, unused once a location applies

    loc = LocationConfig(key="obiekt_1", name="Obiekt 1")
    loc.set_night_shift("22:00", "06:00")
    shop.locations["obiekt_1"] = loc

    emp = Employee(last_name="Kowalski", first_name="Jan", location_key="obiekt_1")
    assert shop.get_location(emp).get_night_shift_hours() == ("22:00", "06:00")

    emp_no_location = Employee(last_name="Nowak", first_name="Anna")
    assert shop.get_location(emp_no_location).get_night_shift_hours() == ("21:00", "05:00")


def test_location_config_open_hours_use_explicit_year_month_day():
    loc = LocationConfig(key="a", name="A", open_hours={0: ("08:00", "20:00")})
    # 2026-03-02 is a Monday.
    assert loc.get_open_hours_for_day(2026, 3, 2) == ("08:00", "20:00")


def test_shop_config_locations_default_empty_and_round_trip():
    shop = ShopConfig(2026, 3)
    assert shop.locations == {}

    shop.locations["main"] = LocationConfig(key="main", name="Główna")
    data = shop.to_dict()
    restored = ShopConfig.from_dict(data)

    assert set(restored.locations.keys()) == {"main"}
    assert restored.locations["main"].name == "Główna"


def test_old_project_without_locations_field_loads_with_empty_locations():
    shop = ShopConfig(2026, 3)
    data = shop.to_dict()
    del data["locations"]  # simulate a project file saved before this field existed

    restored = ShopConfig.from_dict(data)
    assert restored.locations == {}


def test_employee_location_key_defaults_empty_and_round_trips():
    emp = Employee(last_name="Kowalski", first_name="Jan")
    assert emp.location_key == ""

    schedule = MonthSchedule(2026, 3)
    emp2 = Employee(last_name="Nowak", first_name="Anna", location_key="galeria_pn")
    schedule.add_employee(emp2)

    restored = MonthSchedule.from_dict(schedule.to_dict())
    assert restored.employees[0].location_key == "galeria_pn"
