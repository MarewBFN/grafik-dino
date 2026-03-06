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

        if not self.shop_config.is_trade_day(day):
            return CellView(bg=theme.BG_DISABLED)

        base_bg = theme.BG_MAIN

        if not s or not e:
            return CellView(bg=base_bg)

        hours = self.shop_config.get_open_hours_for_day(day)

        text_start = ""
        text_end = ""
        text_total = ""
        bg = base_bg

        if hours:
            open_t, close_t = hours

            # STANDARD OTW
            if s == open_t and emp.daily_hours == 8:
                text_start = "OTW"

            # STANDARD ZAM
            elif e == close_t and emp.daily_hours == 8:
                text_start = "ZAM"

            else:
                text_start = s
                text_end = e
        else:
            text_start = s
            text_end = e

        # Kolor zmiany
        if hours:
            open_t, close_t = hours
            if s == open_t:
                bg = theme.SHIFT_MORNING
            elif e == close_t:
                bg = theme.SHIFT_CLOSE

        tooltip = f"{s} - {e}\nSuma: {t}"

        return CellView(
            text_start=text_start,
            text_end=text_end,
            text_total=text_total,
            bg=bg,
            tooltip=tooltip
        )
