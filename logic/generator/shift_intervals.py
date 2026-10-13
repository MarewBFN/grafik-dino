"""Przedziały czasu zmian pracownika w danym dniu - wspólne dla reguł, które
liczą obsadę w konkretnych godzinach (np. "min. 2 osoby z kwalifikacją X w
oknie 10:00-14:00", generic_rules.py::build_min_staff_with_role,
scope="window").

Dla każdego "świata zmian" generatora (patrz logic/auto_generator.py)
zwraca {id zmiany: (start, koniec)} w minutach od północy dnia, w którym
zmiana się zaczyna (koniec > start, także przez północ i dla 24 h):

- model godzin otwarcia (Ochrona, placówki bez rotacji) - kształty okien z
  opening_hours_coverage.OpeningHoursModel,
- rotacja służby 24/7 - zmiany doby i zmiany resztkowe
  (duty_rotation_rest_constraint._day_windows),
- rotacja całodobowa "ogólna" - kafelki doby (round_clock_constraint),
- pozostali (Dino i profile custom bez tych mechanizmów) - zmiany
  zakotwiczone przy otwarciu/zamknięciu (rest_constraint._build_shift_windows)
  i sztywna nocka (SHIFT_NIGHT), gdy placówka ją ma.

Ręcznie zablokowany dzień z godzinami (ds.is_locked + start/end) to stały
przedział - ręczny wpis wygrywa, a jego zmienne x są i tak ustalone przez
ograniczenia ręcznych wpisów, więc nie liczy się ich drugi raz
(locked_interval). Przedział wpisanej zmiany i podział okna na odcinki są
wspólne z walidacją siatki (model/staffing_rules.py)."""

from logic.utils.time_utils import get_effective_daily_hours
from model.staffing_rules import DAY, cell_interval, minutes as _minutes, span as _span


def locked_interval(day_state) -> tuple[int, int] | None:
    """Stały przedział ręcznie zablokowanego dnia z godzinami (minuty od
    północy jego dnia) albo None."""
    return cell_interval(day_state) if day_state.is_locked else None


def shift_intervals(ctx, e: int, d: int) -> dict:
    """{id zmiany: (start, koniec)} kandydatów zmian pracownika `e` w dniu
    `d` (minuty od północy dnia `d`)."""
    from logic.generator.opening_hours_coverage import get_model

    emp = ctx.employees[e]
    shop = ctx.shop
    location = shop.get_location(emp)

    opening = get_model(ctx)
    if opening is not None and e in opening.index_set:
        base = (d - 1) * DAY
        return {sid: (start - base, end - base) for sid, (start, end) in opening.windows[(e, d)].items()}

    rotation = location.get_duty_rotation()
    if rotation and ctx.duty_shifts is not None:
        from logic.generator.duty_rotation_manual_coverage import get_plan
        from logic.generator.duty_rotation_rest_constraint import _day_windows

        return {
            sid: (start, end)
            for sid, _is_full, start, end in _day_windows(
                rotation, shop.weekday(d), ctx.duty_shifts, get_plan(ctx.duty_shifts), emp.location_key or "", d,
            )
        }

    eff_minutes = int(get_effective_daily_hours(emp, shop) * 60)

    start_hour = location.get_round_clock_start_hour()
    if start_hour and ctx.round_clock_shifts is not None:
        from logic.generator.round_clock_constraint import round_clock_tile_count, round_clock_tile_start_hour

        tiles = round_clock_tile_count(shop.standard_daily_hours)
        result = {}
        for index in range(tiles):
            start = _minutes(round_clock_tile_start_hour(start_hour, index, shop.standard_daily_hours))
            result[ctx.round_clock_shifts[index]] = (start, start + eff_minutes)
        return result

    result = {}
    hours = location.get_open_hours_for_day(d)
    if hours:
        open_t, close_t = hours
        open_m = _minutes(open_t)
        close_m = _minutes(close_t)
        if close_m <= open_m:
            close_m += DAY
        result[ctx.shift_open] = (open_m, open_m + eff_minutes)
        result[ctx.shift_close] = (close_m - eff_minutes, close_m)
        for sid, offset in ctx.start_shift_map.items():
            result[sid] = (open_m + offset, open_m + offset + eff_minutes)
        for sid, offset in ctx.end_shift_map.items():
            result[sid] = (close_m - offset - eff_minutes, close_m - offset)
    if ctx.shift_night is not None:
        night = location.get_night_shift_hours()
        if night:
            result[ctx.shift_night] = _span(*night)
    return result
