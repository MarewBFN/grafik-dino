import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.utils.time_utils import classify_shift_as_morning_or_afternoon


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
