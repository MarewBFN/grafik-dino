import json
import random
from pathlib import Path
from typing import Any

from logic.utils.time_utils import get_effective_daily_hours
from model.day_schedule import calc_end
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from persistence.project_io import save_project


class ConstraintTraceLogger:
    """Rejestruje, które constrainty wpływały na jakie decyzje w modelu."""

    def __init__(self):
        self.events: list[dict[str, Any]] = []

    def log_constraint(self, name: str, detail: str, **extra: Any) -> None:
        self.events.append({"type": "constraint", "name": name, "detail": detail, **extra})

    def log_assignment(self, employee_idx: int, day: int, shift: int | None, reason: str) -> None:
        self.events.append({
            "type": "assignment",
            "employee_idx": employee_idx,
            "day": day,
            "shift": shift,
            "reason": reason,
        })

    def to_dict(self) -> dict[str, Any]:
        return {"events": self.events}

    def write_json(self, path: str | Path) -> None:
        path = Path(path)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def build_random_scenario(seed: int = 7, employee_count: int = 4, days: int = 7, output_path: str | Path | None = None) -> dict[str, Any]:
    rng = random.Random(seed)

    employees = []
    for idx in range(employee_count):
        employees.append({
            "first_name": f"Emp{idx}",
            "last_name": f"Worker{idx}",
            "is_opener": rng.choice([True, False]),
            "is_meat": rng.choice([True, False]),
            "no_night": rng.choice([True, False]),
            "monthly_target_hours": 160,
            "daily_hours": 8,
            "employment_fraction": 1.0,
        })

    blocked_days = [day for day in range(1, days + 1) if rng.random() < 0.25]

    payload = {
        "seed": seed,
        "employee_count": employee_count,
        "days": days,
        "employees": employees,
        "blocked_days": blocked_days,
        "schedule": {
            "year": 2026,
            "month": 8,
        },
        "shop": {
            "constraints": {
                "min_open_staff": 2,
                "min_close_staff": 2,
                "max_consecutive_days": 4,
            }
        },
    }

    if output_path is not None:
        Path(output_path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    return payload


def build_random_project(
    seed: int = 7,
    employee_count: int = 8,
    year: int = 2026,
    month: int = 8,
    leave_probability: float = 0.06,
    sick_probability: float = 0.03,
    locked_probability: float = 0.04,
    availability_probability: float = 0.15,
) -> tuple[MonthSchedule, ShopConfig, dict[str, Any]]:
    """Create a reproducible project in exactly the format used by save/load.

    The returned metadata records every randomized input, while the schedule and
    shop can be written with :func:`write_random_project` and opened in the UI.
    """
    rng = random.Random(seed)
    shop = ShopConfig(year, month)
    schedule = MonthSchedule(year, month)
    metadata: dict[str, Any] = {"seed": seed, "employees": [], "blocked_days": []}

    for index in range(employee_count):
        availability = {}
        for weekday in range(7):
            if rng.random() < availability_probability:
                # These windows deliberately include restrictive cases for stress tests.
                start, end = rng.choice([("05:30", "14:30"), ("13:00", "22:45"), ("08:00", "18:00")])
                availability[weekday] = [{"start": start, "end": end, "mode": "hard"}]
        employee = Employee(
            last_name=f"Worker{index:02d}",
            first_name=f"Emp{index:02d}",
            is_opener=rng.choice([True, False]),
            is_meat=rng.choice([True, False]),
            no_night=rng.choice([True, False]),
            employment_fraction=rng.choice([0.5, 0.75, 1.0, 1.0]),
            availability=availability,
        )
        schedule.add_employee(employee)
        metadata["employees"].append({
            "name": employee.display_name(),
            "is_opener": employee.is_opener,
            "is_meat": employee.is_meat,
            "no_night": employee.no_night,
            "employment_fraction": employee.employment_fraction,
            "availability": availability,
        })

    for employee in schedule.employees:
        for day in range(1, schedule.days_in_month + 1):
            roll = rng.random()
            day_state = schedule.get_day(employee, day)
            if roll < leave_probability:
                day_state.set_leave()
                metadata["blocked_days"].append({"employee": employee.display_name(), "day": day, "type": "leave"})
            elif roll < leave_probability + sick_probability:
                day_state.set_sick()
                metadata["blocked_days"].append({"employee": employee.display_name(), "day": day, "type": "sick"})
            elif roll < leave_probability + sick_probability + locked_probability:
                hours = shop.get_open_hours_for_day(day)
                if hours:
                    day_state.is_locked = True
                    day_state.start = hours[0]
                    day_state.end = calc_end(hours[0], get_effective_daily_hours(employee, shop))
                    metadata["blocked_days"].append({"employee": employee.display_name(), "day": day, "type": "locked"})

    return schedule, shop, metadata


def write_random_project(path: str | Path, **kwargs: Any) -> dict[str, Any]:
    """Write an openable project JSON and return its randomized input metadata."""
    schedule, shop, metadata = build_random_project(**kwargs)
    save_project(path, schedule, shop)
    return metadata
