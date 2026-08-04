import json
from pathlib import Path
import sys
import tempfile
import unittest

from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.auto_generator import AutoScheduleGenerator
from logic.generator.night_constraint import add_no_night_constraint
from logic.generator.trace import build_random_project
from model.constraint_policy import ConstraintPolicy
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from logic.schedule_controller import ScheduleController
from persistence.project_io import load_project, save_project


class GeneratorDiagnosticsTests(unittest.TestCase):
    def test_diagnostics_finds_the_first_infeasible_hard_constraint(self):
        shop = ShopConfig(2026, 8)
        shop.constraints["min_open_staff"] = 2
        for name in shop.constraint_policies:
            shop.constraint_policies[name] = ConstraintPolicy.DISABLED
        shop.constraint_policies["open"] = ConstraintPolicy.MANDATORY

        schedule = MonthSchedule(2026, 8)
        schedule.add_employee(Employee("One", "Employee", is_opener=True, is_meat=True))

        report = AutoScheduleGenerator(schedule, shop).diagnose(time_limit_seconds=1)

        self.assertEqual(report["infeasibility"]["first_infeasible_stage"], "open")
        self.assertEqual(report["infeasibility"]["irreducible_constraint_groups"], ["open"])
        self.assertEqual(report["stages"][0]["status"], "OPTIMAL")

    def test_11_hour_rest_is_mandatory_by_default(self):
        self.assertEqual(
            ShopConfig(2026, 8).constraint_policies["rest_11h"],
            ConstraintPolicy.MANDATORY,
        )

    def test_random_project_round_trip_preserves_inputs_used_by_constraints(self):
        schedule, shop, metadata = build_random_project(
            seed=19,
            employee_count=4,
            availability_probability=1.0,
            locked_probability=0.2,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "random-project.json"
            save_project(path, schedule, shop)
            reloaded_schedule, reloaded_shop = load_project(path)
            raw = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(len(reloaded_schedule.employees), 4)
        self.assertEqual(reloaded_shop.constraint_policies["no_night"], ConstraintPolicy.PREFERRED)
        self.assertTrue(any(employee.availability for employee in reloaded_schedule.employees))
        self.assertIn("constraint_policies", raw["shop_config"])
        self.assertTrue(metadata["blocked_days"])

    def test_soft_no_night_penalty_is_charged_for_a_forbidden_assignment(self):
        model = cp_model.CpModel()
        employee = Employee("Night", "Worker", no_night=True)
        shop = ShopConfig(2026, 8)
        x = {(0, 1, shift): model.NewBoolVar(f"shift_{shift}") for shift in (0, 1)}
        model.Add(x[0, 1, 0] == 1)

        penalties = add_no_night_constraint(
            model, x, [employee], [1], shop, (0, 1), 0, 1, {}, {}, soft=True
        )
        model.Minimize(sum(penalties))
        solver = cp_model.CpSolver()
        status = solver.Solve(model)

        self.assertEqual(status, cp_model.OPTIMAL)
        self.assertEqual(sum(solver.Value(penalty) for penalty in penalties), 1)

    def test_undo_redo_restores_day_working_status_and_hours(self):
        schedule = MonthSchedule(2026, 8)
        shop = ShopConfig(2026, 8)
        controller = ScheduleController(schedule, shop)

        controller.snapshot()
        shop.day_overrides[4] = ("08:00", "18:00")
        shop.public_holidays.add(4)

        controller.undo()
        self.assertNotIn(4, controller.shop_config.day_overrides)
        self.assertNotIn(4, controller.shop_config.public_holidays)

        controller.redo()
        self.assertEqual(controller.shop_config.day_overrides[4], ("08:00", "18:00"))
        self.assertIn(4, controller.shop_config.public_holidays)


if __name__ == "__main__":
    unittest.main()
