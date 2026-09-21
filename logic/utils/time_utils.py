from datetime import timedelta

# Przeniesione do model/location.py (żeby model/ nie zaczęło importować z
# logic/) - re-eksportowane tutaj, żeby istniejące importy w logic/generator/*
# i testach zostały bez zmian.
from model.location import (  # noqa: F401
    daily_subintervals,
    daily_windows_overlap,
    hour_window_overlaps_time_range,
)


def get_effective_daily_hours(emp, shop):
    # 🔴 specjalny fulltime max 8h
    if emp.employment_fraction == 1.01:
        hours = 8.0

    # 🔴 normalny fulltime z wymuszeniem 8:30
    elif shop.constraints.get("force_fulltime_845", False) and emp.employment_fraction == 1.0:
        hours = 8.50

    else:
        hours = shop.standard_daily_hours * emp.employment_fraction

    minutes = int(hours * 60)
    minutes = (minutes // 15) * 15

    return minutes / 60


def is_next_calendar_month(old_year: int, old_month: int, new_year: int, new_month: int) -> bool:
    """Czy (new_year, new_month) to dokładnie jeden miesiąc kalendarzowy po
    (old_year, old_month) - używane przy przejmowaniu "pamięci poprzedniego
    miesiąca" (patrz ui/main_window.py::_save_date_clicked): skok o więcej
    niż jeden miesiąc (albo wstecz) czyni koniec ostatniej zmiany starego
    grafiku nieaktualnym (między miesiącami był z pewnością pełny
    odpoczynek), więc nie ma sensu go przejmować."""
    return old_year * 12 + old_month + 1 == new_year * 12 + new_month


def classify_shift_as_morning_or_afternoon(shift_start, shift_end, shop_open_dt, shop_close_dt):
    """Classify a shift based on the actual shop opening/closing window.

    The previous logic used a fixed noon-like assumption and misclassified
    special days such as 10:00-18:00 or 05:30-22:45. We now compare the
    midpoint of the assigned shift to the midpoint of the shop's operating
    window so that the split is based on real opening/closing hours.
    """

    if not shop_open_dt or not shop_close_dt:
        return None

    if shift_start is None or shift_end is None:
        return None

    if shift_end <= shift_start:
        return "morning"

    window = shop_close_dt - shop_open_dt
    if window <= timedelta(0):
        return "morning"

    shop_midpoint = shop_open_dt + (window / 2)
    shift_midpoint = shift_start + ((shift_end - shift_start) / 2)

    return "morning" if shift_midpoint <= shop_midpoint else "afternoon"