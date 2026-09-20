import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from logic.schedule_presenter import SchedulePresenter
from ui import theme


def _build_two_location_schedule():
    shop = ShopConfig(2026, 3)
    shop.locations = {
        "loc_a": LocationConfig(key="loc_a", name="Obiekt A", open_hours={i: ("06:00", "14:00") for i in range(7)}),
        "loc_b": LocationConfig(key="loc_b", name="Obiekt B", open_hours={i: ("14:00", "22:00") for i in range(7)}),
    }

    schedule = MonthSchedule(2026, 3)
    emp_a = Employee(last_name="A", first_name="A", location_key="loc_a", daily_hours=8)
    emp_b = Employee(last_name="B", first_name="B", location_key="loc_b", daily_hours=8)
    schedule.add_employee(emp_a)
    schedule.add_employee(emp_b)

    # 2026-03-02 is a Monday.
    schedule.set_day_hours(emp_a, 2, "06:00", "14:00")  # matches loc_a's open
    schedule.set_day_hours(emp_b, 2, "18:00", "22:00")  # matches loc_b's close only

    return shop, schedule, emp_a, emp_b


def test_schedule_presenter_resolves_open_close_labels_per_employee_location():
    shop, schedule, emp_a, emp_b = _build_two_location_schedule()
    presenter = SchedulePresenter(schedule, shop)

    view_a = presenter.get_cell_view(emp_a, 2)
    assert view_a.text_start == "OTW", view_a

    view_b = presenter.get_cell_view(emp_b, 2)
    assert view_b.text_start == "ZAM", view_b


def test_schedule_presenter_does_not_mix_up_locations():
    shop, schedule, emp_a, emp_b = _build_two_location_schedule()
    presenter = SchedulePresenter(schedule, shop)

    # emp_a's shift (06:00-14:00) matches loc_a's open time, not loc_b's -
    # if the presenter used the wrong (global/loc_b) hours this would show
    # neither OTW nor ZAM.
    view_a = presenter.get_cell_view(emp_a, 2)
    assert view_a.text_start != "ZAM"

    view_b = presenter.get_cell_view(emp_b, 2)
    assert view_b.text_start != "OTW"


def test_closed_weekday_greys_out_the_cell_for_that_locations_employees():
    """A day marked "Nieczynne" (open_hours[wd] == (None, None), see
    ui/weekly_hours_editor.py) must grey out the same way a non-trade day
    (holiday/non-trade Sunday) already did - get_open_hours_for_day()
    returns None for both, and get_cell_view() must check that per the
    employee's own location, not project-wide is_trade_day()."""
    shop = ShopConfig(2026, 3)
    loc = LocationConfig(key="loc_a", name="Obiekt A", open_hours={i: ("06:00", "14:00") for i in range(7)})
    loc.open_hours[0] = (None, None)  # Monday marked "Nieczynne"
    shop.locations["loc_a"] = loc

    schedule = MonthSchedule(2026, 3)
    emp = Employee(last_name="A", first_name="A", location_key="loc_a", daily_hours=8)
    schedule.add_employee(emp)

    presenter = SchedulePresenter(schedule, shop)
    # 2026-03-02 is a Monday.
    view = presenter.get_cell_view(emp, 2)

    assert view.bg == theme.BG_DISABLED


def test_closed_day_override_greys_out_the_cell():
    shop = ShopConfig(2026, 3)
    loc = LocationConfig(key="loc_a", name="Obiekt A", open_hours={i: ("06:00", "14:00") for i in range(7)})
    loc.day_overrides[2] = (None, None)
    shop.locations["loc_a"] = loc

    schedule = MonthSchedule(2026, 3)
    emp = Employee(last_name="A", first_name="A", location_key="loc_a", daily_hours=8)
    schedule.add_employee(emp)

    presenter = SchedulePresenter(schedule, shop)
    view = presenter.get_cell_view(emp, 2)

    assert view.bg == theme.BG_DISABLED


def test_open_day_in_other_location_is_unaffected_by_a_closed_day_elsewhere():
    shop = ShopConfig(2026, 3)
    loc_a = LocationConfig(key="loc_a", name="Obiekt A", open_hours={i: ("06:00", "14:00") for i in range(7)})
    loc_a.open_hours[0] = (None, None)
    loc_b = LocationConfig(key="loc_b", name="Obiekt B", open_hours={i: ("06:00", "14:00") for i in range(7)})
    shop.locations["loc_a"] = loc_a
    shop.locations["loc_b"] = loc_b

    schedule = MonthSchedule(2026, 3)
    emp_b = Employee(last_name="B", first_name="B", location_key="loc_b", daily_hours=8)
    schedule.add_employee(emp_b)
    schedule.set_day_hours(emp_b, 2, "06:00", "14:00")

    presenter = SchedulePresenter(schedule, shop)
    view_b = presenter.get_cell_view(emp_b, 2)

    assert view_b.bg != theme.BG_DISABLED


def test_sunday_is_not_greyed_out_for_a_profile_without_a_trade_calendar():
    """Dino-era leftover: LocationConfig.is_trade_day() closed every Sunday
    by default (trade_sundays starts empty) regardless of business profile -
    ShopConfig.is_trade_day() already guarded against this
    (uses_trade_calendar), but shop.get_location(emp) (used by grid_view.py/
    schedule_presenter.py for the per-cell/per-location view) did not."""
    from model.business_profile import register_custom_profile
    from model.custom_profile import CustomBusinessProfile

    profile = CustomBusinessProfile(
        key="custom_test_sunday_presentation", display_name="Test", roles=[], rules=[],
    )
    register_custom_profile(profile)

    shop = ShopConfig(2026, 3)
    shop.business_type = profile.key
    loc = LocationConfig(key="loc_a", name="Obiekt A", open_hours={i: ("06:00", "14:00") for i in range(7)})
    shop.locations["loc_a"] = loc

    schedule = MonthSchedule(2026, 3)
    emp = Employee(last_name="A", first_name="A", location_key="loc_a", daily_hours=8)
    schedule.add_employee(emp)
    schedule.set_day_hours(emp, 1, "06:00", "14:00")  # 2026-03-01 is a Sunday

    presenter = SchedulePresenter(schedule, shop)
    view = presenter.get_cell_view(emp, 1)

    assert view.bg != theme.BG_DISABLED


def test_schedule_presenter_without_locations_behaves_as_before():
    shop = ShopConfig(2026, 3)  # no locations defined
    schedule = MonthSchedule(2026, 3)
    emp = Employee(last_name="Kowalski", first_name="Jan", daily_hours=8)
    schedule.add_employee(emp)
    schedule.set_day_hours(emp, 2, *shop.get_open_hours_for_day(2))

    presenter = SchedulePresenter(schedule, shop)
    view = presenter.get_cell_view(emp, 2)
    assert view.text_start == "OTW"
