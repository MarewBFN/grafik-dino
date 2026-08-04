import json
import random
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.auto_generator import AutoScheduleGenerator
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from model.constraints import ConstraintEngine

random.seed(7)


def build_scenario(employee_count: int, seed: int) -> Tuple[dict, MonthSchedule, ShopConfig]:
    random.seed(seed)
    shop = ShopConfig(2026, 8)
    schedule = MonthSchedule(2026, 8)

    employees = []
    for idx in range(employee_count):
        is_opener = random.random() < 0.35
        is_meat = random.random() < 0.35
        employment_fraction = 1.0 if random.random() < 0.7 else random.choice([0.5, 0.75, 0.8, 0.9])
        emp = Employee(
            last_name=f"Emp{idx}",
            first_name=f"{idx}",
            is_opener=is_opener,
            is_meat=is_meat,
            monthly_target_hours=160,
            daily_hours=8,
            employment_fraction=employment_fraction,
        )
        employees.append(emp)
        schedule.add_employee(emp)

    for emp in employees:
        for day in range(1, 32):
            if random.random() < 0.08:
                schedule.get_day(emp, day).set_leave()
            elif random.random() < 0.05:
                schedule.get_day(emp, day).set_sick()

    for emp in employees:
        for day in range(1, 32):
            if random.random() < 0.04:
                ds = schedule.get_day(emp, day)
                ds.is_locked = True
                ds.start = "05:30"
                ds.end = "13:30"

    scenario = {
        "seed": seed,
        "employee_count": employee_count,
        "employees": [
            {
                "name": emp.display_name(),
                "is_opener": emp.is_opener,
                "is_meat": emp.is_meat,
                "employment_fraction": emp.employment_fraction,
            }
            for emp in employees
        ],
    }
    return scenario, schedule, shop


def summarize(schedule: MonthSchedule, shop: ShopConfig) -> dict:
    summary = {}
    for emp in schedule.employees:
        total_hours = schedule.total_hours_for_employee(emp)
        violations = ConstraintEngine.evaluate(schedule, shop)
        summary[emp.display_name()] = {
            "hours": total_hours,
            "leave_days": sum(1 for day in range(1, 32) if schedule.get_day(emp, day).is_leave),
            "sick_days": sum(1 for day in range(1, 32) if getattr(schedule.get_day(emp, day), 'is_sick', False)),
            "locked_days": sum(1 for day in range(1, 32) if schedule.get_day(emp, day).is_locked),
        }
    return {"employees": summary, "violations": [v.type for v in violations]}


if __name__ == "__main__":
    results = []
    for employee_count in [3, 5, 8, 10, 12, 15, 20]:
        for seed in range(5):
            scenario, schedule, shop = build_scenario(employee_count, seed)
            generator = AutoScheduleGenerator(schedule, shop)
            result = generator.generate(trace_output_path=None)
            results.append({
                "scenario": scenario,
                "result": result,
                "summary": summarize(schedule, shop),
            })

    out_path = Path(__file__).with_name("stress_test_results.json")
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
