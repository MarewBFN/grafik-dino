import os

from ortools.sat.python import cp_model
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from logic.generator.solver import build_objective, solve_model
from logic.generator.solution_mapper import save_solution
from logic.generator.constraint_registry import ConstraintContext, apply_registry
from logic.generator.trace import ConstraintTraceLogger

# Only the "dino_retail" business profile exists today; AutoScheduleGenerator
# looks up shop.business_type through model.business_profile.get_profile, but
# there's only one constraint wiring module to look up so far.
from logic.generator import dino_retail_profile

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

        # Sztywny blok zmiany nocnej (Etap C planu zmian nocnych) - istnieje
        # w tej samej, wspólnej przestrzeni zmiennych x[e,d,s] dla KAŻDEGO
        # profilu (tak jak SHIFT_OPEN/CLOSE), ale logic/generator/night_shift_constraint.py
        # blokuje ją twardo (x[e,d,SHIFT_NIGHT]==0) dla każdego pracownika,
        # którego lokalizacja nie ma skonfigurowanego night_shift (Etap B) -
        # więc dla dzisiejszych projektów (żadna lokalizacja go nie ma) to
        # zero zmiany zachowania, tylko nieużywane zmienne w modelu.
        self.SHIFT_NIGHT = 14

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

            self.SHIFT_NIGHT,
        )

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

        # Kierowniczki (is_manager) mają sztywny, cotygodniowy grafik -
        # odświeżamy go przed każdym generowaniem, żeby nikt nie musiał
        # wpisywać tych godzin ręcznie ani pilnować, że ich dane przetrwały.
        from logic.manager_schedule import apply_all_manager_schedules
        apply_all_manager_schedules(self.schedule, self.shop)

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

        ctx = ConstraintContext(
            model=model,
            x=x,
            employees=employees,
            days=days,
            trade_days=trade_days,
            schedule=self.schedule,
            shop=self.shop,
            all_shifts=self.ALL_SHIFTS,
            shift_open=self.SHIFT_OPEN,
            shift_close=self.SHIFT_CLOSE,
            start_shift_map=self.START_SHIFT_MAP,
            end_shift_map=self.END_SHIFT_MAP,
            trace=trace,
            shift_night=self.SHIFT_NIGHT,
        )

        from model.business_profile import get_custom_profile
        custom = get_custom_profile(self.shop.business_type)

        if custom is not None:
            from logic.generator import custom_profile_wiring
            wiring = custom_profile_wiring
            wiring.setup_context(ctx)
            specs = wiring.build_specs(custom)
            weights = wiring.build_weights(custom)
        else:
            # Only "dino_retail" has its own hard-coded wiring module today;
            # every user-authored profile goes through custom_profile_wiring
            # above instead.
            wiring = dino_retail_profile
            wiring.setup_context(ctx)
            specs = wiring.ALL_SPECS
            weights = wiring.CONSTRAINT_WEIGHTS

        all_soft_violations = apply_registry(ctx, specs, weights)
        all_soft_violations.extend(
            wiring.build_objective_terms(ctx, self.SHIFT_WORK_START_15, self.SHIFT_WORK_END_15)
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
            trace=trace,
            shift_night=self.SHIFT_NIGHT,
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
