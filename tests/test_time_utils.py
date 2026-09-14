import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.utils.time_utils import classify_shift_as_morning_or_afternoon, get_effective_daily_hours
from model.day_schedule import calc_end
from model.employee import Employee
from model.shop_config import ShopConfig


FMT = "%H:%M"


def test_classify_shift_uses_actual_shop_window_for_special_hours():
    open_dt = datetime.strptime("10:00", FMT)
    close_dt = datetime.strptime("18:00", FMT)

    assert classify_shift_as_morning_or_afternoon(
        datetime.strptime("10:00", FMT),
        datetime.strptime("18:00", FMT),
        open_dt,
        close_dt,
    ) == "morning"

    assert classify_shift_as_morning_or_afternoon(
        datetime.strptime("10:00", FMT),
        datetime.strptime("14:00", FMT),
        open_dt,
        close_dt,
    ) == "morning"


def test_classify_shift_uses_actual_shop_window_for_standard_hours():
    open_dt = datetime.strptime("05:30", FMT)
    close_dt = datetime.strptime("22:45", FMT)

    assert classify_shift_as_morning_or_afternoon(
        datetime.strptime("08:00", FMT),
        datetime.strptime("16:30", FMT),
        open_dt,
        close_dt,
    ) == "morning"

    assert classify_shift_as_morning_or_afternoon(
        datetime.strptime("18:00", FMT),
        datetime.strptime("23:00", FMT),
        open_dt,
        close_dt,
    ) == "afternoon"


def test_get_effective_daily_hours_uses_shop_standard_daily_hours():
    shop = ShopConfig(2026, 3)
    shop.standard_daily_hours = 12.0
    # force_fulltime_845 (Dino's own convention) would otherwise override
    # fraction 1.0 to a fixed 8.5h before standard_daily_hours is even
    # consulted - disable it to exercise the general case.
    shop.constraints["force_fulltime_845"] = False
    emp = Employee(last_name="A", first_name="A", employment_fraction=1.0)

    assert get_effective_daily_hours(emp, shop) == 12.0
    assert get_effective_daily_hours(
        Employee(last_name="B", first_name="B", employment_fraction=0.5), shop
    ) == 6.0


def test_get_effective_daily_hours_default_matches_dino_today():
    shop = ShopConfig(2026, 3)  # standard_daily_hours defaults to 8.0
    emp = Employee(last_name="A", first_name="A", employment_fraction=0.75)

    assert get_effective_daily_hours(emp, shop) == 6.0  # 8.0 * 0.75, same as before


def test_get_effective_daily_hours_dino_special_cases_ignore_standard_daily_hours():
    shop = ShopConfig(2026, 3)
    shop.standard_daily_hours = 12.0

    # Kierowniczka convention (fraction 1.01 -> always exactly 8h) and the
    # force_fulltime_845 override (fraction 1.0 -> 8.5h) are Dino-specific
    # legal conventions, not scaled by standard_daily_hours.
    manager = Employee(last_name="M", first_name="M", employment_fraction=1.01)
    assert get_effective_daily_hours(manager, shop) == 8.0

    shop.constraints["force_fulltime_845"] = True
    fulltime = Employee(last_name="F", first_name="F", employment_fraction=1.0)
    assert get_effective_daily_hours(fulltime, shop) == 8.5


def test_calc_end_of_a_literal_24h_shift_is_indistinguishable_from_empty():
    # Documents why the UI caps standard_daily_hours below 24.0 (see
    # ConfigDialog._build_limits_tab): a same-day HH:MM shift model has no
    # way to represent "24 hours later" distinctly from "0 hours later".
    assert calc_end("00:00", 24.0) == calc_end("00:00", 0.0) == "00:00"
