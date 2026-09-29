import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.utils.time_utils import (
    classify_shift_as_morning_or_afternoon,
    daily_windows_overlap,
    get_effective_daily_hours,
    hour_window_overlaps_time_range,
)
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


# --- daily_windows_overlap / hour_window_overlaps_time_range -----------
#
# Shared overlap math (Etap C/D/F+ regression, Codex review on PR #3) used
# to compare an hour-based restriction window (no_night, role_time_restriction)
# against a location's night_shift window - both are recurring-daily
# windows in minutes-of-day, not events anchored to a calendar date.


def test_identical_windows_overlap():
    assert daily_windows_overlap(22 * 60, 6 * 60, 22 * 60, 6 * 60)


def test_disjoint_windows_do_not_overlap():
    # 22:00-06:00 vs 08:00-16:00 - nowhere near each other.
    assert not daily_windows_overlap(22 * 60, 6 * 60, 8 * 60, 16 * 60)


def test_partial_overlap_at_the_edge():
    # 22:00-06:00 window vs a 05:00-13:00 window - 1h overlap (05:00-06:00).
    assert daily_windows_overlap(22 * 60, 6 * 60, 5 * 60, 13 * 60)


def test_touching_but_not_overlapping_windows_do_not_overlap():
    # 22:00-06:00 vs 06:00-14:00 - back-to-back, zero actual overlap.
    assert not daily_windows_overlap(22 * 60, 6 * 60, 6 * 60, 14 * 60)


def test_non_wrapping_window_overlaps_wrapping_window():
    # 20:00-23:00 (same-day) vs 22:00-06:00 (crosses midnight).
    assert daily_windows_overlap(20 * 60, 23 * 60, 22 * 60, 6 * 60)


def test_hour_window_matches_identical_hhmm_range():
    assert hour_window_overlaps_time_range(22, 6, ("22:00", "06:00"))


def test_hour_window_does_not_match_unrelated_hhmm_range():
    # A location could configure "night_shift" as an arbitrary fixed
    # midday block (normalize_night_shift only requires start != end) -
    # that must not count as "night" for a 22-6 restriction.
    assert not hour_window_overlaps_time_range(22, 6, ("13:00", "21:00"))
