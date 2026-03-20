import calendar
from copy import deepcopy
from typing import Dict

from model.day_schedule import DaySchedule
from model.employee import Employee


class MonthSchedule:
    def __init__(self, year: int, month: int):
        self.year = year
        self.month = month
        self.days_in_month = calendar.monthrange(year, month)[1]
        self.employees: list[Employee] = []
        self._data: Dict[Employee, Dict[int, DaySchedule]] = {}
        self._clipboard: DaySchedule | None = None

    def add_employee(self, employee: Employee) -> None:
        employee.validate()
        if employee in self._data:
            raise ValueError("Ten pracownik już istnieje w grafiku")

        self.employees.append(employee)
        self.employees.sort()
        self._data[employee] = {
            day: DaySchedule()
            for day in range(1, self.days_in_month + 1)
        }

    def remove_employee(self, employee: Employee) -> None:
        if employee not in self._data:
            return
        self.employees.remove(employee)
        del self._data[employee]

    def get_day(self, employee: Employee, day: int) -> DaySchedule:
        self._validate_day(day)
        return self._data[employee][day]

    def set_day_hours(self, employee: Employee, day: int, start: str, end: str) -> None:
        self._validate_day(day)
        self._data[employee][day].set_hours(start, end)

    def set_day_free(self, employee: Employee, day: int) -> None:
        self._validate_day(day)
        self._data[employee][day].set_free()

    def copy_day(self, employee: Employee, day: int) -> None:
        self._validate_day(day)
        self._clipboard = deepcopy(self._data[employee][day])

    def paste_day(self, employee: Employee, day: int) -> None:
        if self._clipboard is None:
            return
        self._validate_day(day)
        self._data[employee][day] = deepcopy(self._clipboard)

    def total_hours_for_employee(self, employee: Employee) -> str:
        total_minutes = 0
        for day in range(1, self.days_in_month + 1):
            duration = self._data[employee][day].total_duration()
            if duration:
                total_minutes += int(duration.total_seconds() // 60)
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours}:{minutes:02d}"

    def leave_hours_for_employee(self, employee: Employee) -> str:
        total_minutes = 0
        for day in range(1, self.days_in_month + 1):
            ds = self._data[employee][day]
            if ds.is_leave:
                total_minutes += employee.daily_hours * 60
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours}:{minutes:02d}"

    def total_with_leave_for_employee(self, employee: Employee) -> str:
        total_minutes = 0
        for day in range(1, self.days_in_month + 1):
            ds = self._data[employee][day]
            duration = ds.total_duration()
            if duration:
                total_minutes += int(duration.total_seconds() // 60)
            if ds.is_leave:
                total_minutes += employee.daily_hours * 60
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours}:{minutes:02d}"

    def total_hours_for_day(self, day: int) -> int:
        self._validate_day(day)
        count = 0
        for emp in self.employees:
            if not self._data[emp][day].is_empty():
                count += 1
        return count

    def snapshot(self) -> "MonthSchedule":
        return deepcopy(self)

    def _validate_day(self, day: int) -> None:
        if day < 1 or day > self.days_in_month:
            raise ValueError("Nieprawidłowy dzień miesiąca")

    def to_dict(self):
        return {
            "year": self.year,
            "month": self.month,
            "employees": [
                {
                    "first_name": e.first_name,
                    "last_name": e.last_name,
                    "is_opener": e.is_opener,
                    "is_meat": e.is_meat,
                    "monthly_target_hours": e.monthly_target_hours,
                    "daily_hours": e.daily_hours,
                    "days": {
                        day: {
                            "start": self.get_day(e, day).start,
                            "end": self.get_day(e, day).end,
                            "is_leave": self.get_day(e, day).is_leave,
                            "is_locked": self.get_day(e, day).is_locked,
                        }
                        for day in range(1, self.days_in_month + 1)
                        if not self.get_day(e, day).is_empty()
                    },
                }
                for e in self.employees
            ],
        }

    @classmethod
    def from_dict(cls, data):
        sched = cls(data["year"], data["month"])

        for ed in data["employees"]:
            emp = Employee(
                last_name=ed["last_name"],
                first_name=ed["first_name"],
                is_opener=ed.get("is_opener", False),
                is_meat=ed.get("is_meat", False),
                monthly_target_hours=ed.get("monthly_target_hours", 160),
                daily_hours=ed.get("daily_hours", 8),
            )
            sched.add_employee(emp)

            for day in range(1, sched.days_in_month + 1):
                ds = sched.get_day(emp, day)
                ds.start = None
                ds.end = None
                ds.is_leave = False

            for day, dd in ed.get("days", {}).items():
                ds = sched.get_day(emp, int(day))
                ds.start = dd.get("start")
                ds.end = dd.get("end")
                ds.is_leave = dd.get("is_leave", False)
                ds.is_locked = dd.get("is_locked", False)

        sched.employees.sort(key=lambda e: e.last_name.lower())
        return sched

    def replace_employee(self, old, new):
        if old not in self._data:
            return
        days_data = self._data[old]
        self.remove_employee(old)
        self.add_employee(new)
        self._data[new] = days_data

    def clear_unlocked_days(self):
        for emp in self.employees:
            for d in range(1, self.days_in_month + 1):
                day_data = self.get_day(emp, d)

                if not day_data.is_locked:
                    day_data.start = None
                    day_data.end = None
                    if hasattr(day_data, "is_day_off"):
                        day_data.is_day_off = False