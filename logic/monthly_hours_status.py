"""Per-employee porównanie już przepracowanych godzin z tym samym
miesięcznym limitem pełnego etatu, którego pilnuje generator
(logic/generator/hours_constraint.py::add_monthly_hours_constraint) -
używane do podświetlania przekroczenia w gridzie i obu eksporterach
(patrz "plan profil ochrona (analiza specyfikacji klienta).md", sekcje
2.3/9 punkt 5). Celowo bez zależności od ui/theme - to warstwa liczb,
kolor dobiera każdy widok osobno.
"""

from logic.utils.time_utils import get_effective_daily_hours


def monthly_hours_status(schedule, shop, employee) -> dict:
    """{"worked_minutes", "target_minutes", "over_minutes", "is_over"} dla
    jednego pracownika w całym miesiącu `schedule`. `target_minutes` to
    dokładnie ten sam próg co `target_minutes` w add_monthly_hours_constraint
    (nominał pełnego etatu razy wymiar etatu, pomniejszony o urlop/L4)."""
    nominal_minutes = shop.get_full_time_nominal_hours() * 60
    daily_minutes = int(get_effective_daily_hours(employee, shop) * 60)

    leave_days = 0
    sick_days = 0
    for day in range(1, schedule.days_in_month + 1):
        ds = schedule.get_day(employee, day)
        if ds.is_leave:
            leave_days += 1
        if getattr(ds, "is_sick", False):
            sick_days += 1

    leave_minutes = leave_days * daily_minutes
    sick_minutes = sick_days * daily_minutes
    target_minutes = int(nominal_minutes * employee.employment_fraction - leave_minutes - sick_minutes)

    worked_minutes = schedule.total_minutes_for_employee(employee)
    over_minutes = max(0, worked_minutes - target_minutes)

    return {
        "worked_minutes": worked_minutes,
        "target_minutes": target_minutes,
        "over_minutes": over_minutes,
        "is_over": over_minutes > 0,
    }
