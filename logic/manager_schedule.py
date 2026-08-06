"""Sztywny, cotygodniowy grafik dla pracowników z flagą is_manager.

Zamiast wpisywać te same godziny co miesiąc ręcznie, dzień z tą flagą jest
automatycznie blokowany (is_locked) na stałe godziny:
  - poniedziałek: wolne
  - wtorek-piątek: 07:00-15:00
  - sobota: 06:00-14:00
  - niedziela: bez zmian - traktowana tak jak dla innych pracowników

Generator nadal bierze te dni pod uwagę przy liczeniu obsady, bo zablokowane
godziny są dopasowywane do istniejących szablonów zmian (logic/generator/
manual_constraint.py) - stąd wymóg dokładnie 8h dziennie (patrz
ui/employee_dialog.py, gdzie wybór "kierowniczki" ustawia wymiar etatu na
1.01 = dokładnie 8:00, żeby uniknąć rozjazdu z force_fulltime_845).
"""

# 0=poniedziałek ... 6=niedziela (zgodnie z ShopConfig.weekday())
MANAGER_WEEKDAY_HOURS = {
    1: ("07:00", "15:00"),  # wtorek
    2: ("07:00", "15:00"),  # środa
    3: ("07:00", "15:00"),  # czwartek
    4: ("07:00", "15:00"),  # piątek
    5: ("06:00", "14:00"),  # sobota
}
MANAGER_DAY_OFF_WEEKDAY = 0  # poniedziałek
MANAGER_UNMANAGED_WEEKDAY = 6  # niedziela - bez ingerencji


def _lock_day_off(ds) -> None:
    ds.set_free()
    ds.is_locked = True
    ds.shift_class = None


def _lock_work_hours(ds, start: str, end: str) -> None:
    ds.set_hours(start, end)
    ds.is_locked = True
    ds.shift_class = None


def apply_manager_schedule(schedule, shop, employee) -> None:
    """(Ponownie) nakłada sztywny grafik kierowniczki na cały miesiąc.

    Idempotentne - bezpiecznie wywoływać wielokrotnie. Nie rusza dni już
    oznaczonych jako urlop/L4 (te mają pierwszeństwo przed sztywnym wzorcem).
    """
    for day in range(1, schedule.days_in_month + 1):
        ds = schedule.get_day(employee, day)

        if ds.is_leave or getattr(ds, "is_sick", False):
            continue

        weekday = shop.weekday(day)

        if weekday == MANAGER_DAY_OFF_WEEKDAY:
            _lock_day_off(ds)
            continue

        if weekday == MANAGER_UNMANAGED_WEEKDAY:
            continue

        hours = MANAGER_WEEKDAY_HOURS.get(weekday)
        if hours is None:
            continue

        if not shop.is_trade_day(day):
            # Sklep zamknięty (np. święto) - nie ma czego przypisać.
            _lock_day_off(ds)
            continue

        start, end = hours
        _lock_work_hours(ds, start, end)


def apply_all_manager_schedules(schedule, shop) -> None:
    for employee in schedule.employees:
        if getattr(employee, "is_manager", False):
            apply_manager_schedule(schedule, shop, employee)
