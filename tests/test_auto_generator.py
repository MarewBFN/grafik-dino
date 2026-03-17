import calendar
import random
import unittest

try:
    from ortools.sat.python import cp_model

    from logic.auto_generator import AutoScheduleGenerator
    from model.constraint_policy import ConstraintPolicy
    from model.employee import Employee
    from model.month_schedule import MonthSchedule
    from model.shop_config import ShopConfig

    HAS_ORTOOLS = True
except ModuleNotFoundError:
    HAS_ORTOOLS = False


@unittest.skipUnless(HAS_ORTOOLS, "ortools is required for solver integration tests")
class TestAutoScheduleGeneratorSolverEdgeCases(unittest.TestCase):
    ACTIVE_DAYS = [3, 4, 5, 6, 7]  # celowo krótki horyzont dla szybszych testów

    def _make_shop(self, year, month, rng):
        shop = ShopConfig(year, month)

        # Zostawiamy tylko kilka dni handlowych, resztę oznaczamy jako święta.
        days_in_month = calendar.monthrange(year, month)[1]
        shop.public_holidays = set(range(1, days_in_month + 1)) - set(self.ACTIVE_DAYS)

        # Losowe godziny otwarcia (różne przypadki sklepów)
        start = rng.choice(["05:30", "06:00", "06:30"])
        end = rng.choice(["20:00", "21:00", "22:00", "22:45"])
        for wd in range(7):
            shop.open_hours[wd] = (start, end)

        # Upraszczamy pozostałe constrainty, żeby testować głównie obsadę i role.
        for key in ["rest_11h", "balance", "max_consecutive", "monthly_hours", "meat_coverage"]:
            shop.constraint_policies[key] = ConstraintPolicy.DISABLED

        shop.constraint_policies["open"] = ConstraintPolicy.MANDATORY
        shop.constraint_policies["close"] = ConstraintPolicy.MANDATORY
        shop.constraint_policies["meat"] = ConstraintPolicy.MANDATORY
        return shop

    def _build_case(self, rng, force_infeasible=False):
        year, month = 2025, 2
        schedule = MonthSchedule(year, month)
        shop = self._make_shop(year, month, rng)

        num_employees = rng.randint(5, 8)

        if force_infeasible:
            # Edge-case: za mało openerów i/lub mięsa + za wysoka wymagana obsada
            opener_count = rng.randint(0, 1)
            meat_count = rng.randint(0, 1)
            min_open = rng.randint(3, 5)
            min_close = rng.randint(3, 5)
        else:
            # Feasible: minimum 2 openerów i 2 mięsa (open + close każdego dnia)
            opener_count = rng.randint(2, min(4, num_employees))
            meat_count = rng.randint(2, min(4, num_employees))
            min_open = rng.randint(2, 3)
            min_close = rng.randint(2, 3)

        opener_indices = set(rng.sample(range(num_employees), k=opener_count))
        meat_indices = set(rng.sample(range(num_employees), k=meat_count))

        for i in range(num_employees):
            emp = Employee(
                last_name=f"Test{i}",
                first_name=f"Emp{i}",
                is_opener=i in opener_indices,
                is_meat=i in meat_indices,
                daily_hours=rng.randint(6, 8),
            )
            schedule.add_employee(emp)

        shop.constraints["min_open_staff"] = min_open
        shop.constraints["min_close_staff"] = min_close
        shop.constraints["max_consecutive_days"] = 10

        case = {
            "num_employees": num_employees,
            "openers": opener_count,
            "meat": meat_count,
            "min_open": min_open,
            "min_close": min_close,
            "open_hours": shop.open_hours[0],
            "active_days": list(self.ACTIVE_DAYS),
            "force_infeasible": force_infeasible,
        }

        return schedule, shop, case

    def test_solver_random_small_store_feasible_cases(self):
        rng = random.Random(20250219)
        iterations = 40

        for idx in range(iterations):
            schedule, shop, case = self._build_case(rng, force_infeasible=False)
            gen = AutoScheduleGenerator(schedule, shop)
            result = gen.generate()

            self.assertTrue(
                result["success"],
                msg=f"Expected feasible but got infeasible at iter={idx}, case={case}, result={result}",
            )
            self.assertIn(result["status"], (cp_model.OPTIMAL, cp_model.FEASIBLE))

    def test_solver_random_small_store_infeasible_cases_print_config(self):
        rng = random.Random(20250220)
        iterations = 60
        infeasible_seen = 0

        for idx in range(iterations):
            schedule, shop, case = self._build_case(rng, force_infeasible=True)
            gen = AutoScheduleGenerator(schedule, shop)
            result = gen.generate()

            if not result["success"]:
                infeasible_seen += 1
                print(f"[INFEASIBLE CASE {idx}] {case}")

            self.assertFalse(
                result["success"],
                msg=f"Expected infeasible but solver found solution at iter={idx}, case={case}, result={result}",
            )

        self.assertEqual(
            infeasible_seen,
            iterations,
            msg="Każdy case w tym teście powinien być INFEASIBLE.",
        )


if __name__ == "__main__":
    unittest.main()