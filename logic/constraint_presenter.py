from dataclasses import dataclass
from ui import theme
from model.constraints import ConstraintEngine


@dataclass
class ValidationCellView:
    bg: str = theme.BG_MAIN
    text: str = ""
    tooltip: str | None = None


class ConstraintPresenter:

    def __init__(self, schedule, shop_config):
        self.schedule = schedule
        self.shop_config = shop_config

        self.violations = ConstraintEngine.evaluate(
            schedule,
            shop_config
        )

    def get_cell_error(self, emp, day):
        """
        Zwraca True jeśli komórka pracownika ma być czerwona.
        """
        for v in self.violations:
            if v.employee == emp and v.day == day:
                return True
        return False

    def get_validation_cell_view(self, key, day):
        """
        key: "open" | "close" | "meat"
        """
        view = ValidationCellView()

        for v in self.violations:
            if v.day != day:
                continue

            if key == "open" and v.type == "min_open_staff":
                view.bg = theme.ERR_RED
                view.tooltip = v.message

            elif key == "close" and v.type == "min_close_staff":
                view.bg = theme.ERR_RED
                view.tooltip = v.message

            elif key == "meat" and v.type == "meat_coverage":
                view.bg = theme.ERR_RED
                view.tooltip = v.message

        return view
