"""Polskie święta ustawowo wolne od pracy, liczone z biblioteki `holidays`
(pip) zamiast polegania wyłącznie na ręcznym zaznaczaniu ich przez
użytkownika (ShopConfig.public_holidays/LocationConfig.public_holidays -
dwuklik na nagłówku dnia, "Święto"). Cienka nakładka, żeby reszta kodu nie
importowała `holidays` bezpośrednio i nie musiała pamiętać kodu kraju "PL" -
patrz ShopConfig.get_full_time_nominal_hours()."""

from functools import lru_cache

import holidays as _holidays_lib


@lru_cache(maxsize=None)
def _year_calendar(year: int):
    return _holidays_lib.country_holidays("PL", years=year)


def polish_public_holiday_days(year: int, month: int) -> set[int]:
    """Numery dni (1-31) danego miesiąca będące polskimi świętami ustawowo
    wolnymi od pracy (np. {1, 6} dla stycznia - Nowy Rok, Trzech Króli)."""
    calendar = _year_calendar(year)
    return {day.day for day in calendar if day.year == year and day.month == month}
