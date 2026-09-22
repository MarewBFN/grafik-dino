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
        fractions = getattr(self.shop_config, "hours_display_mode", "standard") == "fractions"

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
            return CellView(bg=theme.BG_DISABLED)

        if not s or not e:
            return CellView(bg=theme.BG_MAIN)

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
            if s == open_t and emp.daily_hours == 8:
                text_start = "OTW"
                text_end = ""
            elif e == close_t and emp.daily_hours == 8:
                text_start = "ZAM"
                text_end = ""
            if s == open_t:
                bg = theme.SHIFT_MORNING
            elif e == close_t:
                bg = theme.SHIFT_CLOSE

        # "OTW"/"ZAM" wyżej to już zwarte etykiety, nie surowe godziny - nie
        # ma ich co dodatkowo skracać do ułamka (patrz warunek niżej: tylko
        # gdy text_start/text_end wciąż są surowymi s/e).
        if fractions and text_start == s and text_end == e:
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
