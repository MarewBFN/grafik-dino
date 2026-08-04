import json
import random
from pathlib import Path
from typing import Any


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
