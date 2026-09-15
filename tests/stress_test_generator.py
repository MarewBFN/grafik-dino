import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.auto_generator import AutoScheduleGenerator
from logic.generator.custom_profile_wiring import default_policies
from model.business_profile import register_custom_profile
from model.constraint_policy import ConstraintPolicy
from model.custom_profile import (
    RULE_TYPE_MIN_STAFF_WITH_ROLE,
    CustomBusinessProfile,
    RoleDefinition,
    RuleInstance,
)
from model.employee import Employee
from model.location import LocationConfig
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


def build_night_shift_scenario(guard_count: int, seed: int, min_on_night: int = 2) -> Tuple[dict, MonthSchedule, ShopConfig]:
    """Etap G planu zmian nocnych: profil 24/7 (bez OPEN/CLOSE) z jedną
    lokalizacją posiadającą night_shift i regułą MANDATORY "min. N
    ochroniarzy w nocy" (Etap F) - z losowymi urlopami/L4, ale zawsze z co
    najmniej dwoma ochroniarzami ponad wymagane minimum, żeby scenariusz
    nie stawał się strukturalnie niewykonalny przez zbieg okoliczności."""
    random.seed(seed)

    profile_key = f"stress_night_{guard_count}_{seed}"
    rule = RuleInstance(
        type=RULE_TYPE_MIN_STAFF_WITH_ROLE, role_key="guard",
        policy="MANDATORY", params={"min_count": min_on_night, "scope": "night"},
    )
    profile = CustomBusinessProfile(
        key=profile_key,
        display_name="Stress Ochrona 24/7",
        roles=[RoleDefinition(key="guard", label="Ochroniarz")],
        rules=[rule],
    )
    register_custom_profile(profile)
    rule_key = profile.rule_policy_key(rule)

    shop = ShopConfig(2026, 8)
    shop.business_type = profile.key
    shop.constraint_policies.update(default_policies(profile))
    shop.constraint_policies[rule_key] = ConstraintPolicy.MANDATORY

    loc = LocationConfig(key="site1", name="Obiekt 24/7")
    loc.set_night_shift("22:00", "06:00")
    shop.locations = {"site1": loc}

    schedule = MonthSchedule(2026, 8)
    employees = [
        Employee(last_name=f"Guard{i}", first_name=f"{i}", location_key="site1", custom_roles={"guard": True})
        for i in range(guard_count)
    ]
    for emp in employees:
        schedule.add_employee(emp)

    for emp in employees:
        for day in range(1, 32):
            if random.random() < 0.03:
                schedule.get_day(emp, day).set_leave()
            elif random.random() < 0.02:
                schedule.get_day(emp, day).set_sick()

    scenario = {
        "seed": seed,
        "guard_count": guard_count,
        "min_on_night": min_on_night,
        "business_type": profile.key,
    }
    return scenario, schedule, shop


def check_no_overlapping_shifts(schedule: MonthSchedule) -> list[str]:
    """Niezależny audyt (Etap G): dla każdego pracownika, żadne dwie
    przypisane zmiany nie mogą się realnie nakładać ani mieć odpoczynku
    krótszego niż 11h - liczone na prawdziwych datach, nie samym "HH:MM",
    żeby zmiana nocna (koniec w kolejnej dobie) była policzona poprawnie."""
    problems = []

    for emp in schedule.employees:
        intervals = []
        for day in range(1, schedule.days_in_month + 1):
            ds = schedule.get_day(emp, day)
            if ds.is_empty() or ds.is_leave or getattr(ds, "is_sick", False):
                continue
            start = datetime(schedule.year, schedule.month, day) + timedelta(
                hours=int(ds.start.split(":")[0]), minutes=int(ds.start.split(":")[1])
            )
            end = datetime(schedule.year, schedule.month, day) + timedelta(
                hours=int(ds.end.split(":")[0]), minutes=int(ds.end.split(":")[1])
            )
            if ds.crosses_midnight():
                end += timedelta(days=1)
            intervals.append((day, start, end))

        intervals.sort(key=lambda t: t[1])
        for (day_a, start_a, end_a), (day_b, start_b, end_b) in zip(intervals, intervals[1:]):
            if start_b < end_a:
                problems.append(f"{emp.display_name()}: dni {day_a}/{day_b} nakładają się")
            elif (start_b - end_a).total_seconds() / 3600 < 11:
                problems.append(f"{emp.display_name()}: odpoczynek < 11h między dniami {day_a} i {day_b}")

    return problems


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

    # Etap G planu zmian nocnych: profil 24/7 z SHIFT_NIGHT, sprawdzany
    # niezależnie (check_no_overlapping_shifts) na prawdziwych datach, nie
    # tylko przez solver.Solve() == OPTIMAL/FEASIBLE.
    night_results = []
    for guard_count in [4, 6, 10]:
        for seed in range(5):
            scenario, schedule, shop = build_night_shift_scenario(guard_count, seed)
            generator = AutoScheduleGenerator(schedule, shop)
            result = generator.generate(trace_output_path=None)
            overlap_problems = check_no_overlapping_shifts(schedule) if result["success"] else []
            night_results.append({
                "scenario": scenario,
                "result": result,
                "overlap_problems": overlap_problems,
            })

    out_path = Path(__file__).with_name("stress_test_results.json")
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")

    night_out_path = Path(__file__).with_name("stress_test_night_shift_results.json")
    night_out_path.write_text(json.dumps(night_results, indent=2), encoding="utf-8")
    print(f"Wrote {night_out_path}")

    failed = [r for r in night_results if not r["result"]["success"]]
    with_overlaps = [r for r in night_results if r["overlap_problems"]]
    print(f"Night shift scenarios: {len(night_results)} total, {len(failed)} infeasible, {len(with_overlaps)} with overlap problems")
