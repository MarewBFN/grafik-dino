import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model.location import LocationConfig
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
