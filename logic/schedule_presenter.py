from dataclasses import dataclass

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

        if not self.shop_config.is_trade_day(day):
            return CellView(bg=theme.BG_DISABLED)

        if not s or not e:
            return CellView(bg=theme.BG_MAIN)

        hours = self.shop_config.get_open_hours_for_day(day)
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

        tooltip = f"{s} - {e}\nSuma: {t}"
        return CellView(
            text_start=text_start,
            text_end=text_end,
            text_total=t,
            bg=bg,
            tooltip=tooltip,
        )
