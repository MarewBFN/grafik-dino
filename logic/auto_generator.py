import os
from pyexpat import model

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
)
from logic.generator.constraints_staff import (
    add_fixed_staff_shift_constraints,
    add_max_consecutive_constraint,
)
from logic.generator.rest_constraint import (
    add_rest_11h_constraint,
    add_rest_11h_constraint_simplified,
)
from logic.generator.meat_constraint import (add_meat_constraint, add_meat_coverage_constraint)
from logic.generator.hours_constraint import (
    add_monthly_hours_constraint,
    add_balance_constraint
)
from logic.generator.manual_constraint import add_manual_shift_constraints
from logic.generator.constraints_logic import add_work_dependency_constraint
from logic.generator.objective import (
    add_open_close_penalty,
    add_work_balance_penalty,
    add_morning_afternoon_balance_penalty,
    add_edge_shift_bonus,
    add_workload_balance_penalty,
)
from logic.generator.availability_constraint import add_availability_constraint
from logic.generator.night_constraint import add_no_night_constraint
from logic.generator.trace import ConstraintTraceLogger

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
        )

        # Wagi dla soft constraintów (im wyższa, tym ważniejszy constraint)    
        self.constraint_weights = {
            "meat": 1000,
            "meat_coverage": 1500,
            "meat_light_usage": 400,
            "rest_11h": 5000,
            "balance": 1000,
            "max_consecutive": 100,
            "open": 200,
            "close": 200,
            "monthly_hours": 250,
            "availability": 5000,
            "no_night": 5000,
            "morning_afternoon_balance": 10000,
            "add_edge_shift_bonus": 1000,
        }
    # ==================================================
    # PUBLIC
    # ==================================================

    def generate(
        self,
        is_fix=False,
        trace=None,
        trace_output_path=None,
        solver_time_limit_seconds=60,
        solver_workers=None,
    ):
        if solver_workers is None:
            # Zahardkodowane 10 wątków przeciążało słabsze maszyny (mniej
            # rdzeni niż wątków = solver wolniejszy, nie szybszy).
            solver_workers = max(1, min(8, os.cpu_count() or 4))

        print("=== START CP-SAT GENERATOR ===")

        schedule_before_generation = self.schedule.snapshot()

        if trace is None:
            trace = ConstraintTraceLogger()

        if not is_fix:
            self.schedule.clear_unlocked_days()

        for emp in self.schedule.employees:
            object.__setattr__(emp, '_orig_daily_hours', emp.daily_hours)

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

        for d in trade_days:
            available = 0

            for emp in employees:
                ds = self.schedule.get_day(emp, d)

                if not (
                    ds.is_leave
                    or ds.is_locked
                    or getattr(ds, "is_sick", False)
                    or getattr(ds, "is_day_off", False)
                ):
                    available += 1

            print(f"[DEBUG] DAY {d}: available={available}")

        x = self._create_variables(model, employees, days)

        add_non_trade_day_constraints(model, x, employees, days, self.shop, self.ALL_SHIFTS, trace=trace)
        add_leave_constraints(model, x, employees, days, self.schedule, self.ALL_SHIFTS, trace=trace)
        add_day_off_constraints(model, x, employees, days, self.schedule, self.ALL_SHIFTS, trace=trace)
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
            self.END_SHIFT_MAP,
            trace=trace
        )
        add_work_dependency_constraint(
            model,
            x,
            employees,
            days,
            self.SHIFT_OPEN,
            self.SHIFT_CLOSE,
            self.ALL_SHIFTS,
            trace=trace
        )
        add_one_shift_per_day_constraint(model, x, employees, days, self.ALL_SHIFTS, trace=trace)

        # Osoby is_meat_light: pula zapasowa dla obłożenia mięsa, używana tylko
        # gdy brak innej możliwości - patrz waga "meat_light_usage" w objective.
        meat_light_penalties = []

        open_violations = self._apply_policy(
            "open",
            hard_fn=lambda: add_fixed_staff_shift_constraints(
                model, x, employees, trade_days,
                self.SHIFT_OPEN,
                min_open,
                soft=False,
                trace=trace,
                meat_light_penalties=meat_light_penalties
            ),
            soft_fn=lambda: add_fixed_staff_shift_constraints(
                model, x, employees, trade_days,
                self.SHIFT_OPEN,
                min_open,
                soft=True,
                trace=trace,
                meat_light_penalties=meat_light_penalties
            )
        )

        close_violations = self._apply_policy(
            "close",
            hard_fn=lambda: add_fixed_staff_shift_constraints(
                model, x, employees, trade_days,
                self.SHIFT_CLOSE,
                min_close,
                soft=False,
                trace=trace,
                meat_light_penalties=meat_light_penalties
            ),
            soft_fn=lambda: add_fixed_staff_shift_constraints(
                model, x, employees, trade_days,
                self.SHIFT_CLOSE,
                min_close,
                soft=True,
                trace=trace,
                meat_light_penalties=meat_light_penalties
            )
        )

        rest_11h_mode = self.shop.constraints.get("rest_11h_mode", "standard")

        if rest_11h_mode == "simplified":
            rest_hard_fn = lambda: add_rest_11h_constraint_simplified(
                model,
                x,
                employees,
                days,
                trade_days,
                self.SHIFT_OPEN,
                self.SHIFT_CLOSE,
                self.START_SHIFT_MAP,
                self.END_SHIFT_MAP,
                soft=False,
                trace=trace
            )
            rest_soft_fn = lambda: add_rest_11h_constraint_simplified(
                model,
                x,
                employees,
                days,
                trade_days,
                self.SHIFT_OPEN,
                self.SHIFT_CLOSE,
                self.START_SHIFT_MAP,
                self.END_SHIFT_MAP,
                soft=True,
                trace=trace
            )
        else:
            rest_hard_fn = lambda: add_rest_11h_constraint(
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
                soft=False,
                trace=trace
            )
            rest_soft_fn = lambda: add_rest_11h_constraint(
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
                soft=True,
                trace=trace
            )

        rest_violations = self._apply_policy(
            "rest_11h",
            hard_fn=rest_hard_fn,
            soft_fn=rest_soft_fn
        )

        balance_violations = self._apply_policy(
            "balance",
            hard_fn=lambda: add_balance_constraint(
                model, x, employees, days, self.shop, self.ALL_SHIFTS, soft=False, trace=trace
            ),
            soft_fn=lambda: add_balance_constraint(
                model, x, employees, days, self.shop, self.ALL_SHIFTS, soft=True, trace=trace
            )
        )

        availability_violations = self._apply_policy(
            "availability",
            hard_fn=lambda: add_availability_constraint(
                model,
                x,
                employees,
                days,
                self.shop,
                self.ALL_SHIFTS,
                self.SHIFT_OPEN,
                self.SHIFT_CLOSE,
                self.START_SHIFT_MAP,
                self.END_SHIFT_MAP,
                soft=False,
                trace=trace
            ),
            soft_fn=lambda: add_availability_constraint(
                model,
                x,
                employees,
                days,
                self.shop,
                self.ALL_SHIFTS,
                self.SHIFT_OPEN,
                self.SHIFT_CLOSE,
                self.START_SHIFT_MAP,
                self.END_SHIFT_MAP,
                soft=True,
                trace=trace
            )
        )

        night_violations = self._apply_policy(
            "no_night",
            hard_fn=lambda: add_no_night_constraint(
                model,
                x,
                employees,
                days,
                self.shop,
                self.ALL_SHIFTS,
                self.SHIFT_OPEN,
                self.SHIFT_CLOSE,
                self.START_SHIFT_MAP,
                self.END_SHIFT_MAP,
                soft=False,
                trace=trace
            ),
            soft_fn=lambda: add_no_night_constraint(
                model,
                x,
                employees,
                days,
                self.shop,
                self.ALL_SHIFTS,
                self.SHIFT_OPEN,
                self.SHIFT_CLOSE,
                self.START_SHIFT_MAP,
                self.END_SHIFT_MAP,
                soft=True,
                trace=trace
            )
        )

        meat_violations = self._apply_policy(
            "meat",
            hard_fn=lambda: add_meat_constraint(
                model, x, employees, days, trade_days, self.ALL_SHIFTS, self.SHIFT_OPEN, self.SHIFT_CLOSE, soft=False, trace=trace,
                meat_light_penalties=meat_light_penalties
            ),
            soft_fn=lambda: add_meat_constraint(
                model, x, employees, days, trade_days, self.ALL_SHIFTS, self.SHIFT_OPEN, self.SHIFT_CLOSE, soft=True, trace=trace,
                meat_light_penalties=meat_light_penalties
            )
        )

        coverage_violations = self._apply_policy(
            "meat_coverage",
            hard_fn=lambda: add_meat_coverage_constraint(
                model, x, employees, trade_days, self.shop, self.SHIFT_OPEN, self.SHIFT_CLOSE, self.START_SHIFT_MAP, self.END_SHIFT_MAP, soft=False, trace=trace,
                meat_light_penalties=meat_light_penalties
            ),
            soft_fn=lambda: add_meat_coverage_constraint(
                model, x, employees, trade_days, self.shop,
                self.SHIFT_OPEN,
                self.SHIFT_CLOSE,
                self.START_SHIFT_MAP,
                self.END_SHIFT_MAP,
                soft=True,
                trace=trace,
                meat_light_penalties=meat_light_penalties
            )
        )

        max_consec_violations = self._apply_policy(
            "max_consecutive",
            hard_fn=lambda: add_max_consecutive_constraint(
                model, x, employees, days, max_consecutive, self.ALL_SHIFTS, soft=False, trace=trace
            ),
            soft_fn=lambda: add_max_consecutive_constraint(
                model, x, employees, days, max_consecutive, self.ALL_SHIFTS, soft=True, trace=trace
            )
        )

        monthly_hours_violations = self._apply_policy(
            "monthly_hours",
            hard_fn=lambda: add_monthly_hours_constraint(
                model, x, employees, days, self.schedule, self.shop, self.ALL_SHIFTS, soft=False, trace=trace
            ),
            soft_fn=lambda: add_monthly_hours_constraint(
                model, x, employees, days, self.schedule, self.shop, self.ALL_SHIFTS, soft=True, trace=trace
            )
        )


        all_soft_violations = []
        all_soft_violations.extend(rest_violations)
        all_soft_violations.extend(balance_violations)
        all_soft_violations.extend(meat_violations)
        all_soft_violations.extend(coverage_violations)
        if meat_light_penalties:
            meat_light_weight = self.constraint_weights.get("meat_light_usage", 400)
            all_soft_violations.extend(meat_light_weight * t for t in meat_light_penalties)
        all_soft_violations.extend(max_consec_violations)
        all_soft_violations.extend(open_violations)
        all_soft_violations.extend(close_violations)
        all_soft_violations.extend(monthly_hours_violations)
        all_soft_violations.extend(
            add_edge_shift_bonus(
                model,
                x,
                employees,
                trade_days,
                self.SHIFT_WORK_START_15,
                self.SHIFT_WORK_END_15
            )
        )        
        all_soft_violations.extend(
            add_morning_afternoon_balance_penalty(
                model,
                x,
                employees,
                days,
                self.shop,
                self.SHIFT_OPEN,
                self.SHIFT_CLOSE,
                self.START_SHIFT_MAP,
                self.END_SHIFT_MAP
            )
        )
        all_soft_violations.extend(availability_violations)
        all_soft_violations.extend(night_violations)
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
            add_workload_balance_penalty(
                model,
                x,
                employees,
                days,
                self.ALL_SHIFTS
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
        if is_fix:
            from logic.generator.fix import setup_fix_hints_and_penalties
            fix_penalties = setup_fix_hints_and_penalties(
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
            all_soft_violations.extend(fix_penalties)

        build_objective(model, all_soft_violations)
        solver, status = solve_model(
            model,
            time_limit_seconds=solver_time_limit_seconds,
            num_search_workers=solver_workers,
        )
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
            trace=trace
        )

        # SPRZĄTANIE: Przywracamy oryginalne daily_hours, żeby UI i zapisy nie świrowały
        for emp in employees:
            if hasattr(emp, '_orig_daily_hours'):
                object.__setattr__(emp, 'daily_hours', emp._orig_daily_hours)

        infeasibility_reasons = []
        if not success:
            # clear_unlocked_days() runs before solving. Never leave its partial
            # changes in the UI when CP-SAT could not produce a full schedule.
            self.schedule.restore(schedule_before_generation)
            from logic.generator.diagnostics import build_infeasibility_summary
            infeasibility_reasons = build_infeasibility_summary(
                schedule_before_generation,
                self.shop,
            )

        if trace_output_path is not None:
            trace.write_json(trace_output_path)

        return {
            "status": status,
            "success": success,
            "conflicts": solver.NumConflicts(),
            "branches": solver.NumBranches(),
            "wall_time": solver.WallTime(),
            "infeasibility_reasons": infeasibility_reasons,
        }

    def diagnose(self, output_path=None, time_limit_seconds=5):
        """Build and solve the model in stages without changing this schedule."""
        from logic.generator.diagnostics import GeneratorDiagnostics

        report = GeneratorDiagnostics(
            self.schedule,
            self.shop,
            time_limit_seconds=time_limit_seconds,
        ).run()
        if output_path is not None:
            GeneratorDiagnostics.write_report(report, output_path)
        return report
    
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
