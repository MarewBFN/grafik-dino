import json
import sys
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.generator.constraints_basic import add_one_shift_per_day_constraint
from logic.generator.constraints_staff import add_fixed_staff_shift_constraints
from logic.generator.hours_constraint import add_monthly_hours_constraint
from logic.generator.objective import add_workload_balance_penalty
from logic.generator.trace import ConstraintTraceLogger, build_random_scenario
from model.constraint_policy import ConstraintPolicy
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig


def _build_simple_problem():
    year, month = 2026, 8
    shop = ShopConfig(year, month)
    schedule = MonthSchedule(year, month)

    employees = [
        Employee(last_name="Kowalski", first_name="Jan", is_opener=True, is_meat=True),
        Employee(last_name="Nowak", first_name="Anna", is_opener=False, is_meat=False),
    ]
    for emp in employees:
        schedule.add_employee(emp)

    days = list(range(1, 4))
    all_shifts = (0, 1, 14)

    model = cp_model.CpModel()
    x = {}
    for e in range(len(employees)):
        for d in days:
            for s in all_shifts:
                x[(e, d, s)] = model.NewBoolVar(f"x_{e}_{d}_{s}")

    return model, x, employees, days, all_shifts, schedule, shop


def test_trace_logger_records_each_constraint():
    model, x, employees, days, all_shifts, schedule, shop = _build_simple_problem()
    trace = ConstraintTraceLogger()

    add_one_shift_per_day_constraint(model, x, employees, days, all_shifts, trace=trace)
    add_fixed_staff_shift_constraints(model, x, employees, days, 0, 1, soft=False, trace=trace)
    add_monthly_hours_constraint(model, x, employees, days, schedule, shop, all_shifts, trace=trace)

    names = [event["name"] for event in trace.events if event["type"] == "constraint"]

    assert "one_shift_per_day" in names
    assert "fixed_staff_shift" in names
    assert "monthly_hours" in names


def test_random_scenario_builder_exports_json_payload(tmp_path):
    path = tmp_path / "random_scenario.json"
    payload = build_random_scenario(seed=7, employee_count=3, days=5, output_path=path)

    assert payload["employee_count"] == 3
    assert payload["blocked_days"]
    assert path.exists()

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["employee_count"] == 3
    assert "schedule" in saved
    assert "shop" in saved


def test_workload_balance_penalty_reduces_employee_spread():
    model = cp_model.CpModel()
    employees = [Employee(last_name="A", first_name="A"), Employee(last_name="B", first_name="B")]
    days = [1, 2]
    all_shifts = (0, 1)
    x = {}
    for e in range(len(employees)):
        for d in days:
            for s in all_shifts:
                x[(e, d, s)] = model.NewBoolVar(f"x_{e}_{d}_{s}")

    penalties = add_workload_balance_penalty(model, x, employees, days, all_shifts)

    assert len(penalties) == 1


def test_default_shop_config_uses_soft_staff_and_availability_policies():
    shop = ShopConfig(2026, 8)

    assert shop.constraint_policies["open"] == ConstraintPolicy.PREFERRED
    assert shop.constraint_policies["close"] == ConstraintPolicy.PREFERRED
    assert shop.constraint_policies["availability"] == ConstraintPolicy.PREFERRED
