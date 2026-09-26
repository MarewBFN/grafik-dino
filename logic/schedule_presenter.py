from dataclasses import dataclass

from logic.utils.time_utils import format_hours_as_fraction
from ui import theme


@dataclass
class CellView:
    text_start: str = ""
    text_end: str = ""
    text_total: str = ""
    bg: str = theme.BG_MAIN
    tooltip: str | None = None


class SchedulePresenter:
    def __init__(self, schedule, shop_config):
        self.schedule = schedule
        self.shop_config = shop_config

    def get_cell_view(self, emp, day) -> CellView:
        ds = self.schedule.get_day(emp, day)
        s, e, t = ds.as_rows()

        if ds.is_leave:
            return CellView(
                text_start="🌴",
                text_end="",
                text_total="",
                bg=theme.OK_GREEN,
                tooltip="Urlop",
            )

        # Nieczynne = brak handlowej niedzieli/święta ALBO dzień jawnie
        # oznaczony "Nieczynne" (patrz WeeklyHoursEditor/DayOverrideDialog) -
        # get_open_hours_for_day() sprawdza oba, per lokalizacja pracownika.
        if not self.shop_config.get_location(emp).get_open_hours_for_day(day):
            if not s or not e:
                return CellView(bg=theme.BG_DISABLED)
            # Zmiana mimo to istnieje - np. kawałek doby rotacji służby z
            # dnia poprzedniego zaczynający się po północy
            # (logic/generator/duty_rotation_manual_coverage.py) albo ręczny
            # wpis sprzed zamknięcia dnia. Liczy się do godzin i eksportu,
            # więc nie może zniknąć z siatki - tło zostaje "nieczynne".
            view = self._shift_view(emp, day, s, e, t, ds)
            view.bg = theme.BG_DISABLED
            view.tooltip = f"Placówka nieczynna tego dnia\n{view.tooltip}"
            return view

        if not s or not e:
            return CellView(bg=theme.BG_MAIN)

        return self._shift_view(emp, day, s, e, t, ds)

    def _shift_view(self, emp, day, s, e, t, ds) -> CellView:
        fractions = getattr(self.shop_config, "hours_display_mode", "standard") == "fractions"

        if ds.crosses_midnight():
            # Zmiana nocna (Etap C/D planu zmian nocnych) - koniec leży w
            # kolejnej dobie kalendarzowej. Rozróżnia to wyłącznie tło
            # (SHIFT_NIGHT) i tooltip - na życzenie użytkownika bez znacznika
            # "(+1)" w samym tekście komórki (mylące/zbędne, usunięte
            # całkiem, nie tylko w widoku ułamkowym).
            tooltip = f"{s} → {e}\nSuma: {t}"
            if fractions:
                text_start = format_hours_as_fraction(s, e)
                text_end = ""
            else:
                text_start = s
                text_end = e
            return CellView(
                text_start=text_start,
                text_end=text_end,
                text_total=t,
                bg=theme.SHIFT_NIGHT,
                tooltip=tooltip,
            )

        hours = self.shop_config.get_location(emp).get_open_hours_for_day(day)
        text_start = s
        text_end = e
        bg = theme.BG_MAIN

        if hours:
            open_t, close_t = hours
            if s == open_t:
                bg = theme.SHIFT_MORNING
            elif e == close_t:
                bg = theme.SHIFT_CLOSE

        if fractions:
            text_start = format_hours_as_fraction(s, e)
            text_end = ""

        tooltip = f"{s} - {e}\nSuma: {t}"
        return CellView(
            text_start=text_start,
            text_end=text_end,
            text_total=t,
            bg=bg,
            tooltip=tooltip,
        )
