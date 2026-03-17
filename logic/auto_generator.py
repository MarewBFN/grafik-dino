from ortools.sat.python import cp_model
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from model.constraint_policy import ConstraintPolicy
from model.day_schedule import calc_start, calc_end
from logic.generator.solver import build_objective, solve_model
from logic.generator.solution_mapper import save_solution
from logic.generator.constraints_basic import (
    add_one_shift_per_day_constraint,
    add_non_trade_day_constraints,
    add_leave_constraints,
    add_day_off_constraints,
    add_total_open_close_limit
)
from logic.generator.constraints_staff import (
    add_fixed_staff_shift_constraints,
    add_max_consecutive_constraint,
)
from logic.generator.rest_constraint import add_rest_11h_constraint
from logic.generator.meat_constraint import (add_meat_constraint, add_meat_coverage_constraint)
from logic.generator.hours_constraint import (
    add_monthly_hours_constraint,
    add_balance_constraint
)
from logic.generator.manual_constraint import add_manual_shift_constraints
from logic.generator.constraints_logic import add_work_dependency_constraint
from logic.generator.objective import (
    add_open_close_penalty,
    add_work_balance_penalty
)

class AutoScheduleGenerator:

    def __init__(self, schedule: MonthSchedule, shop: ShopConfig):
        self.schedule = schedule
        self.shop = shop

        # ===== SHIFT ID =====
        self.SHIFT_OPEN = 0
        self.SHIFT_CLOSE = 1

        # WORK od otwarcia
        self.SHIFT_WORK_START_15 = 2
        self.SHIFT_WORK_START_30 = 3
        self.SHIFT_WORK_START_45 = 4
        self.SHIFT_WORK_START_60 = 5
        self.SHIFT_WORK_START_75 = 6
        self.SHIFT_WORK_START_90 = 7

        # WORK od zamknięcia
        self.SHIFT_WORK_END_15 = 8
        self.SHIFT_WORK_END_30 = 9
        self.SHIFT_WORK_END_45 = 10
        self.SHIFT_WORK_END_60 = 11
        self.SHIFT_WORK_END_75 = 12
        self.SHIFT_WORK_END_90 = 13
        self.START_SHIFT_MAP = {
            self.SHIFT_WORK_START_15: 15,
            self.SHIFT_WORK_START_30: 30,
            self.SHIFT_WORK_START_45: 45,
            self.SHIFT_WORK_START_60: 60,
            self.SHIFT_WORK_START_75: 75,
            self.SHIFT_WORK_START_90: 90,
        }

        self.END_SHIFT_MAP = {
            self.SHIFT_WORK_END_15: 15,
            self.SHIFT_WORK_END_30: 30,
            self.SHIFT_WORK_END_45: 45,
            self.SHIFT_WORK_END_60: 60,
            self.SHIFT_WORK_END_75: 75,
            self.SHIFT_WORK_END_90: 90,
        }

        # wszystkie zmiany (tu można dodawać kolejne typy zmian)
        self.ALL_SHIFTS = (
            self.SHIFT_OPEN,
            self.SHIFT_CLOSE,

            self.SHIFT_WORK_START_15,
            self.SHIFT_WORK_START_30,
            self.SHIFT_WORK_START_45,
            self.SHIFT_WORK_START_60,
            self.SHIFT_WORK_START_75,
            self.SHIFT_WORK_START_90,

            self.SHIFT_WORK_END_15,
            self.SHIFT_WORK_END_30,
            self.SHIFT_WORK_END_45,
            self.SHIFT_WORK_END_60,
            self.SHIFT_WORK_END_75,
            self.SHIFT_WORK_END_90,
        )

        # Wagi dla soft constraintów (im wyższa, tym ważniejszy constraint)    
        self.constraint_weights = {
            "meat": 10000,
            "meat_coverage": 15000,
            "rest_11h": 5000,
            "balance": 1,
            "max_consecutive": 1000,
            "open": 20000,
            "close": 20000,
            "monthly_hours": 2000,
        }
    # ==================================================
    # PUBLIC
    # ==================================================

    def generate(self):

        print("=== START CP-SAT GENERATOR ===")

        self.schedule.clear_unlocked_days()

        model = cp_model.CpModel()

        employees = self.schedule.employees
        days = list(range(1, self.schedule.days_in_month + 1))

        min_open = self.shop.constraints.get("min_open_staff", 3)
        min_close = self.shop.constraints.get("min_close_staff", 3)
        max_consecutive = self.shop.constraints.get("max_consecutive_days", 4)
        trade_days = [d for d in days if self.shop.is_trade_day(d)]

        print("Liczba pracowników:", len(employees))
        print("Dni w miesiącu:", len(days))
        print("Dni handlowe:", len(trade_days))
        print("Min OPEN:", min_open)
        print("Min CLOSE:", min_close)
        print("Max consecutive:", max_consecutive)

        x = self._create_variables(model, employees, days)

        add_non_trade_day_constraints(model, x, employees, days, self.shop, self.ALL_SHIFTS)
        add_total_open_close_limit(model, x, employees, trade_days, self.SHIFT_OPEN, self.SHIFT_CLOSE)
        add_leave_constraints(model, x, employees, days, self.schedule, self.ALL_SHIFTS)
        add_day_off_constraints(model, x, employees, days, self.schedule, self.ALL_SHIFTS)
        add_manual_shift_constraints(
            model,
            x,
            employees,
            days,
            self.schedule,
            self.shop,
            self.ALL_SHIFTS,
            self.SHIFT_OPEN,
            self.SHIFT_CLOSE,
            self.START_SHIFT_MAP,
            self.END_SHIFT_MAP
        )
        add_work_dependency_constraint(
            model,
            x,
            employees,
            days,
            self.SHIFT_OPEN,
            self.SHIFT_CLOSE,
            self.ALL_SHIFTS
        )
        add_one_shift_per_day_constraint(model, x, employees, days, self.ALL_SHIFTS)

        open_violations = self._apply_policy(
            "open",
            hard_fn=lambda: add_fixed_staff_shift_constraints(
                model, x, employees, trade_days,
                self.SHIFT_OPEN,
                min_open,
                soft=False
            ),
            soft_fn=lambda: add_fixed_staff_shift_constraints(
                model, x, employees, trade_days,
                self.SHIFT_OPEN,
                min_open,
                soft=True
            )
        )

        close_violations = self._apply_policy(
            "close",
            hard_fn=lambda: add_fixed_staff_shift_constraints(
                model, x, employees, trade_days,
                self.SHIFT_CLOSE,
                min_close,
                soft=False
            ),
            soft_fn=lambda: add_fixed_staff_shift_constraints(
                model, x, employees, trade_days,
                self.SHIFT_CLOSE,
                min_close,
                soft=True
            )
        )

        rest_violations = self._apply_policy(
            "rest_11h",
            hard_fn=lambda: add_rest_11h_constraint(
                model,
                x,
                employees,
                days,
                trade_days,
                self.shop,
                self.SHIFT_OPEN,
                self.SHIFT_CLOSE,
                self.START_SHIFT_MAP,
                self.END_SHIFT_MAP,
                soft=False
            ),
            soft_fn=lambda: add_rest_11h_constraint(
                model,
                x,
                employees,
                days,
                trade_days,
                self.shop,
                self.SHIFT_OPEN,
                self.SHIFT_CLOSE,
                self.START_SHIFT_MAP,
                self.END_SHIFT_MAP,
                soft=True
            )
        )

        balance_violations = self._apply_policy(
            "balance",
            hard_fn=lambda: add_balance_constraint(
                model, x, employees, days, self.shop, self.ALL_SHIFTS, soft=False
            ),
            soft_fn=lambda: add_balance_constraint(
                model, x, employees, days, self.shop, self.ALL_SHIFTS, soft=True
            )
        )

        meat_violations = self._apply_policy(
            "meat",
            hard_fn=lambda: add_meat_constraint(
                model, x, employees, days, trade_days, self.ALL_SHIFTS, self.SHIFT_OPEN, self.SHIFT_CLOSE, soft=False
            ),
            soft_fn=lambda: add_meat_constraint(
                model, x, employees, days, trade_days, self.ALL_SHIFTS, self.SHIFT_OPEN, self.SHIFT_CLOSE, soft=True
            )
        )

        coverage_violations = self._apply_policy(
            "meat_coverage",
            hard_fn=lambda: add_meat_coverage_constraint(
                model, x, employees, trade_days, self.shop, self.ALL_SHIFTS, self.SHIFT_OPEN, self.SHIFT_CLOSE, soft=False
            ),
            soft_fn=lambda: add_meat_coverage_constraint(
                model, x, employees, trade_days, self.shop, self.ALL_SHIFTS, self.SHIFT_OPEN, self.SHIFT_CLOSE, soft=True
            )
        )

        max_consec_violations = self._apply_policy(
            "max_consecutive",
            hard_fn=lambda: add_max_consecutive_constraint(
                model, x, employees, days, max_consecutive, self.ALL_SHIFTS, soft=False
            ),
            soft_fn=lambda: add_max_consecutive_constraint(
                model, x, employees, days, max_consecutive, self.ALL_SHIFTS, soft=True
            )
        )

        monthly_hours_violations = self._apply_policy(
            "monthly_hours",
            hard_fn=lambda: add_monthly_hours_constraint(
                model, x, employees, days, self.schedule, self.shop, self.ALL_SHIFTS, soft=False
            ),
            soft_fn=lambda: add_monthly_hours_constraint(
                model, x, employees, days, self.schedule, self.shop, self.ALL_SHIFTS, soft=True
            )
        )


        all_soft_violations = []
        all_soft_violations.extend(rest_violations)
        all_soft_violations.extend(balance_violations)
        all_soft_violations.extend(meat_violations)
        all_soft_violations.extend(coverage_violations)
        all_soft_violations.extend(max_consec_violations)
        all_soft_violations.extend(open_violations)
        all_soft_violations.extend(close_violations)
        all_soft_violations.extend(monthly_hours_violations)
        all_soft_violations.extend(
            add_work_balance_penalty(
                model,
                x,
                employees,
                trade_days,
                self.START_SHIFT_MAP,
                self.END_SHIFT_MAP
            )
        )
        all_soft_violations.extend(
            add_open_close_penalty(
                x,
                employees,
                trade_days,
                self.SHIFT_OPEN,
                self.SHIFT_CLOSE
            )
        )
        
        build_objective(model, all_soft_violations)
        solver, status = solve_model(model)
        success = save_solution(
            self.schedule,
            self.shop,
            solver,
            status,
            x,
            employees,
            trade_days,
            self.SHIFT_OPEN,
            self.SHIFT_CLOSE,
            self.START_SHIFT_MAP,
            self.END_SHIFT_MAP,
        )

        return {
            "status": status,
            "success": success,
            "conflicts": solver.NumConflicts(),
            "branches": solver.NumBranches(),
            "wall_time": solver.WallTime()
        }
    
    def _create_variables(self, model, employees, days):
        x = {}
        for e in range(len(employees)):
            for d in days:
                for s in (self.ALL_SHIFTS):
                    x[e, d, s] = model.NewBoolVar(f"x_e{e}_d{d}_s{s}")
        print(f"[MODEL] variables: {len(x)}")
        return x
    
    def _apply_policy(
        self,
        policy_name,
        hard_fn,
        soft_fn=None
    ):
        from model.constraint_policy import ConstraintPolicy

        policy = self.shop.constraint_policies.get(policy_name)
        weight = self.constraint_weights.get(policy_name, 1)
        print(f"[POLICY] {policy_name} -> {policy}")

        if policy == ConstraintPolicy.MANDATORY:
            print(f"[HARD] {policy_name}")
            hard_fn()
            return []

        elif policy == ConstraintPolicy.PREFERRED:
            print(f"[SOFT] {policy_name} weight={weight}")
            if soft_fn:
                violations = soft_fn()
                # zamieniamy violation vars na weighted terms
                return [weight * v for v in violations]
            else:
                hard_fn()
                return []

        elif policy == ConstraintPolicy.DISABLED:
            return []

        return []