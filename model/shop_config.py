import calendar
from model.constraint_policy import ConstraintPolicy

class ShopConfig:
    """
    Konfiguracja sklepu:
    - niedziele handlowe
    - godziny otwarcia per dzień tygodnia
    - constrainty
    - opcje UI
    """

    def __init__(self, year: int, month: int):
        self.year = year
        self.month = month

        # Toggle dla constraintów z model.constraint_policy
        self.constraint_policies = {
            "rest_11h": ConstraintPolicy.MANDATORY,
            "meat": ConstraintPolicy.PREFERRED,
            "balance": ConstraintPolicy.PREFERRED,
            "max_consecutive": ConstraintPolicy.PREFERRED,
            "open": ConstraintPolicy.MANDATORY,
            "close": ConstraintPolicy.MANDATORY,
            "monthly_hours": ConstraintPolicy.PREFERRED,
            "meat_coverage": ConstraintPolicy.PREFERRED,
            "availability": ConstraintPolicy.PREFERRED,
        }
        # -----------------------------
        # Override godzin dla konkretnego dnia
        # -----------------------------
        self.day_overrides: dict[int, tuple[str, str]] = {}

        # -----------------------------
        # CONSTRAINTS CONFIG
        # -----------------------------
        self.constraints = {
            "max_consecutive_days": 4,
            "min_open_staff": 3,
            "min_close_staff": 3,
        }

        # -----------------------------
        # UI OPTIONS
        # -----------------------------
        # "compact" | "detailed"
        self.cell_display_mode = "compact"

        # -----------------------------
        # Niedziele handlowe
        # -----------------------------
        self.trade_sundays: set[int] = set()

        # dni ustawowo wolne
        self.public_holidays: set[int] = set()

        # -----------------------------
        # Godziny otwarcia per weekday
        # (0=Pn ... 6=Nd)
        # -----------------------------
        self.open_hours: dict[int, tuple[str, str]] = {
            0: ("05:30", "22:45"),
            1: ("05:30", "22:45"),
            2: ("05:30", "22:45"),
            3: ("05:30", "22:45"),
            4: ("05:30", "22:45"),
            5: ("05:30", "22:45"),
            6: ("05:30", "22:45"),  # Nd (jeśli handlowa)
        }

    # ==========================================================
    # PODSTAWOWE METODY
    # ==========================================================

    def weekday(self, day: int) -> int:
        return calendar.weekday(self.year, self.month, day)

    def is_sunday(self, day: int) -> bool:
        return self.weekday(day) == 6

    def is_trade_day(self, day: int) -> bool:

        if day in self.public_holidays:
            return False

        if self.is_sunday(day):
            return day in self.trade_sundays

        return True

    # ==========================================================
    # GODZINY OTWARCIA
    # ==========================================================

    def get_open_hours_for_day(self, day: int) -> tuple[str, str] | None:
        """
        Zwraca (open, close) albo None jeśli sklep zamknięty
        lub brak poprawnych godzin.
        """
        if not self.is_trade_day(day):
            return None

        # override ma najwyższy priorytet
        if day in self.day_overrides:
            start, end = self.day_overrides[day]
            if start and end:
                return start, end
            return None

        wd = self.weekday(day)
        hours = self.open_hours.get(wd)

        if not hours:
            return None

        start, end = hours
        if not start or not end:
            return None

        return start, end

    def get_open_hours_for_weekday(self, weekday: int) -> tuple[str, str]:
        return self.open_hours[weekday]

    def set_open_hours_for_weekday(self, weekday: int, start: str, end: str):
        self.open_hours[weekday] = (start, end)

    # ==========================================================
    # SERIALIZACJA
    # ==========================================================

    def to_dict(self):
        return {
            "year": self.year,
            "month": self.month,
            "open_hours": self.open_hours,
            "trade_sundays": list(self.trade_sundays),
            "day_overrides": self.day_overrides,
            "constraints": self.constraints,
            "cell_display_mode": self.cell_display_mode,
            "public_holidays": list(self.public_holidays),
        }

    @classmethod
    def from_dict(cls, data):
        cfg = cls(data["year"], data["month"])

        # open_hours
        cfg.open_hours = {
            int(k): tuple(v)
            for k, v in data.get("open_hours", {}).items()
        }

        # niedziele handlowe
        cfg.trade_sundays = set(data.get("trade_sundays", []))

        #święta ustawowo wolne
        cfg.public_holidays = set(data.get("public_holidays", []))


        # override dni
        cfg.day_overrides = {
            int(day): tuple(hours)
            for day, hours in data.get("day_overrides", {}).items()
        }

        # constraints
        saved_constraints = data.get("constraints", {})
        cfg.constraints.update(saved_constraints)

        # UI
        cfg.cell_display_mode = data.get("cell_display_mode", "compact")

        return cfg

    def get_full_time_nominal_hours(self) -> int:
        """
        Zwraca nominalny wymiar czasu pracy (pełny etat)
        dla danego miesiąca zgodnie z kodeksem pracy.
        """

        import calendar
        from datetime import date

        workdays = 0

        days_in_month = calendar.monthrange(self.year, self.month)[1]

        for d in range(1, days_in_month + 1):
            wd = calendar.weekday(self.year, self.month, d)

            # pon–pt
            if wd < 5:
                # jeśli to święto ustawowe → nie liczymy
                if d in self.public_holidays:
                    continue
                workdays += 1

        return workdays * 8
