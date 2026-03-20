from dataclasses import dataclass

from model.constraints import ConstraintEngine
from ui import theme


@dataclass
class ValidationCellView:
    bg: str = theme.BG_MAIN
    text: str = ""
    tooltip: str | None = None


class ConstraintPresenter:
    def __init__(self, schedule, shop_config):
        self.schedule = schedule
        self.shop_config = shop_config
        self.violations = ConstraintEngine.evaluate(schedule, shop_config)

    def get_cell_error(self, emp, day):
        for v in self.violations:
            if v.employee == emp and v.day == day:
                return True
        return False

    def get_validation_cell_view(self, key, day):
        view = ValidationCellView()

        if not self.shop_config.is_trade_day(day):
            view.bg = theme.BG_DISABLED
            return view

        messages = []
        for v in self.violations:
            if v.day != day:
                continue
            if key == "open" and v.type == "min_open_staff":
                messages.append(v.message)
            elif key == "close" and v.type == "min_close_staff":
                messages.append(v.message)
            elif key == "meat" and v.type == "meat_coverage":
                messages.append(v.message)

        if messages:
            view.bg = theme.ERR_RED
            view.tooltip = "\n".join(messages)
        else:
            view.bg = theme.BG_MAIN

        return view
