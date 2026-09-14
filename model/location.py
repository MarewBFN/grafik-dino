"""One location/obiekt within a multi-location project.

This is the data model only (Etap 3a of the location roadmap). It mirrors
the single-location fields ShopConfig already has (open_hours, trade_sundays,
public_holidays, day_overrides, min/max staffing) so a future generator/UI
pass can reuse the same shape - but nothing in logic/generator or ui reads
ShopConfig.locations yet. A project with no locations defined behaves
exactly as before this module existed.
"""

import calendar
from dataclasses import dataclass, field

DEFAULT_OPEN_HOURS = {
    0: ("05:30", "23:00"),
    1: ("05:30", "22:45"),
    2: ("05:30", "22:45"),
    3: ("05:30", "22:45"),
    4: ("05:30", "22:45"),
    5: ("05:30", "22:45"),
    6: ("05:30", "22:45"),
}

DEFAULT_LOCATION_CONSTRAINTS = {
    "min_open_staff": 3,
    "min_close_staff": 3,
    "max_consecutive_days": 4,
}


@dataclass
class LocationConfig:
    key: str
    name: str
    open_hours: dict = field(default_factory=lambda: dict(DEFAULT_OPEN_HOURS))
    trade_sundays: set = field(default_factory=set)
    public_holidays: set = field(default_factory=set)
    day_overrides: dict = field(default_factory=dict)
    constraints: dict = field(default_factory=lambda: dict(DEFAULT_LOCATION_CONSTRAINTS))

    # Same logic as ShopConfig.weekday/is_trade_day/get_open_hours_for_day
    # (model/shop_config.py) - a location has no year/month of its own, so
    # these take them as arguments instead of reading self.year/self.month.

    def weekday(self, year: int, month: int, day: int) -> int:
        return calendar.weekday(year, month, day)

    def is_sunday(self, year: int, month: int, day: int) -> bool:
        return self.weekday(year, month, day) == 6

    def is_trade_day(self, year: int, month: int, day: int) -> bool:
        if day in self.public_holidays:
            return False
        if self.is_sunday(year, month, day):
            return day in self.trade_sundays
        return True

    def get_open_hours_for_day(self, year: int, month: int, day: int):
        if not self.is_trade_day(year, month, day):
            return None

        if day in self.day_overrides:
            start, end = self.day_overrides[day]
            if start and end:
                return start, end
            return None

        wd = self.weekday(year, month, day)
        hours = self.open_hours.get(wd)
        if not hours:
            return None

        start, end = hours
        if not start or not end:
            return None
        return start, end

    def to_dict(self):
        return {
            "key": self.key,
            "name": self.name,
            "open_hours": self.open_hours,
            "trade_sundays": list(self.trade_sundays),
            "public_holidays": list(self.public_holidays),
            "day_overrides": self.day_overrides,
            "constraints": self.constraints,
        }

    @classmethod
    def from_dict(cls, data):
        loc = cls(key=data["key"], name=data.get("name", data["key"]))
        loc.open_hours = {
            int(k): tuple(v) for k, v in data.get("open_hours", {}).items()
        } or dict(DEFAULT_OPEN_HOURS)
        loc.trade_sundays = set(data.get("trade_sundays", []))
        loc.public_holidays = set(data.get("public_holidays", []))
        loc.day_overrides = {
            int(day): tuple(hours) for day, hours in data.get("day_overrides", {}).items()
        }
        loc.constraints = dict(DEFAULT_LOCATION_CONSTRAINTS)
        loc.constraints.update(data.get("constraints", {}))
        return loc
