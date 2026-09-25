import json
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
import unittest

from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.auto_generator import AutoScheduleGenerator
from logic.generator.diagnostics import build_infeasibility_summary
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
        policies = ShopConfig(2026, 8).constraint_policies
        self.assertEqual(policies["rest_11h"], ConstraintPolicy.MANDATORY)
        self.assertEqual(policies["open"], ConstraintPolicy.MANDATORY)
        self.assertEqual(policies["close"], ConstraintPolicy.MANDATORY)
        self.assertEqual(policies["balance"], ConstraintPolicy.PREFERRED)

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

    def test_constraint_policies_survive_project_save_and_load(self):
        schedule = MonthSchedule(2026, 8)
        shop = ShopConfig(2026, 8)
        shop.constraint_policies["open"] = ConstraintPolicy.MANDATORY
        shop.constraint_policies["monthly_hours"] = ConstraintPolicy.DISABLED

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "project.json"
            save_project(path, schedule, shop)
            _, restored_shop = load_project(path)

        self.assertEqual(restored_shop.constraint_policies["open"], ConstraintPolicy.MANDATORY)
        self.assertEqual(restored_shop.constraint_policies["monthly_hours"], ConstraintPolicy.DISABLED)

    def test_infeasible_generation_restores_schedule_and_explains_locked_staffing(self):
        schedule = MonthSchedule(2026, 8)
        shop = ShopConfig(2026, 8)
        shop.public_holidays = set(range(2, 32))
        for name in shop.constraint_policies:
            shop.constraint_policies[name] = ConstraintPolicy.DISABLED
        shop.constraint_policies["open"] = ConstraintPolicy.MANDATORY

        for index in range(4):
            employee = Employee(f"Locked{index}", "Test", is_opener=True, is_meat=True)
            schedule.add_employee(employee)
            state = schedule.get_day(employee, 1)
            state.is_locked = True
            state.start, state.end = "05:30", "14:00"

        # This unlocked entry is cleared before solving in normal generation.
        # It must come back unchanged when the model is infeasible.
        schedule.get_day(schedule.employees[0], 2).set_hours("08:00", "16:00")
        before = schedule.to_dict()

        with redirect_stdout(io.StringIO()):
            result = AutoScheduleGenerator(schedule, shop).generate(
                solver_time_limit_seconds=2,
                solver_workers=1,
            )

        self.assertFalse(result["success"])
        self.assertEqual(schedule.to_dict(), before)
        self.assertTrue(any("Dzień 1" in reason and "zablokowano 4" in reason
                            for reason in result["infeasibility_reasons"]))

        controller = ScheduleController(schedule, shop)
        with redirect_stdout(io.StringIO()):
            controller_result = controller.generate_schedule(force=True)
        self.assertFalse(controller_result["success"])
        self.assertEqual(controller.history, [])


if __name__ == "__main__":
    unittest.main()


class DutyRotationInfeasibilitySummaryTests(unittest.TestCase):
    """Projekt ochrony (rotacja służby 24/7) - komunikat o braku rozwiązania
    ma wskazać placówkę i dzień, a nie regułę otwarcia/zamknięcia Dino."""

    def _shop_and_schedule(self, n=3, no24h=False):
        from model.location import LocationConfig

        shop = ShopConfig(2026, 10)
        shop.business_type = "custom_test_diag_duty"
        loc = LocationConfig(key="site1", name="LakPol Słupsk")
        loc.set_24_7(True)
        loc.set_duty_rotation({
            "only_12_24h": True,
            "weekend_full": {"start": "07:00"},
            "weekend_half_a": {"start": "07:00", "end": "19:00"},
            "weekend_half_b": {"start": "19:00", "end": "07:00"},
        })
        shop.locations = {"site1": loc}
        employees = [
            Employee(
                last_name=f"E{i}", first_name="G", location_key="site1",
                custom_roles={"nie_chce_24h": True} if no24h else {},
            )
            for i in range(n)
        ]
        return shop, MonthSchedule(2026, 10, employees=employees), employees

    def test_whole_location_on_leave_names_location_and_day(self):
        shop, schedule, employees = self._shop_and_schedule()
        for emp in employees:
            schedule.get_day(emp, 20).set_leave()

        messages = build_infeasibility_summary(schedule, shop)

        self.assertEqual(
            messages,
            ["LakPol Słupsk, dzień 20: nikt z pracowników placówki nie jest dostępny "
             "(urlop/L4/wolne) - doby nie da się obsadzić."],
        )

    def test_single_available_person_who_refuses_24h(self):
        shop, schedule, employees = self._shop_and_schedule(n=2, no24h=True)
        schedule.get_day(employees[0], 5).set_leave()

        messages = build_infeasibility_summary(schedule, shop)

        self.assertTrue(any("dzień 5" in m and "Nie chce" in m for m in messages), messages)

    def test_no_dino_open_close_messages_for_duty_rotation_project(self):
        shop, schedule, employees = self._shop_and_schedule()
        for emp in employees:
            schedule.get_day(emp, 20).set_leave()

        messages = build_infeasibility_summary(schedule, shop)

        self.assertFalse(any("otwarci" in m or "zamknięci" in m for m in messages), messages)

    def test_no_single_person_hint_when_a_manual_entry_reaches_into_the_day(self):
        """10.10: E1 i E2 na urlopie, dostępna tylko E0 ("Nie chce 24h") - ale
        ręczna 24h E1 z 9.10 od 19:00 pokrywa dobę 10.10 do 19:00, a resztę
        (19:00-07:00) E0 może wziąć jako zmianę resztkową planu
        (duty_rotation_manual_coverage.py). Podpowiedź "doby nie da się
        obsadzić" byłaby tu fałszywa."""
        shop, schedule, employees = self._shop_and_schedule()
        employees[0].custom_roles["nie_chce_24h"] = True
        schedule.get_day(employees[1], 9).set_full_day_shift("19:00")
        schedule.get_day(employees[1], 9).is_locked = True
        for emp in employees[1:]:
            schedule.get_day(emp, 10).set_leave()

        messages = build_infeasibility_summary(schedule, shop)

        self.assertFalse(any("dzień 10" in m for m in messages), messages)

    def test_locked_24h_shift_for_employee_who_refuses_24h_names_person_and_day(self):
        """Ręcznie zablokowana zmiana 24h (od początku doby) osobie z "Nie
        chce zmian 24h" przy tej zasadzie jako Wymaganej - sprzeczność
        dowodliwa z danych, a komunikat był ogólny."""
        shop, schedule, employees = self._shop_and_schedule(n=3)
        employees[0].custom_roles["nie_chce_24h"] = True
        schedule.get_day(employees[0], 29).set_full_day_shift("07:00")
        schedule.get_day(employees[0], 29).is_locked = True

        messages = build_infeasibility_summary(schedule, shop)

        self.assertTrue(any("dzień 29" in m and "E0 G" in m and "24h" in m for m in messages), messages)
