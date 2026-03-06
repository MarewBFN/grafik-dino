from pyexpat import model

from ortools.sat.python import cp_model
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from model.constraint_policy import ConstraintPolicy


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

        self._clear_schedule()

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

        self._add_non_trade_day_constraints(model, x, employees, days)
        self._add_total_open_close_limit(model, x, employees, trade_days)
        self._add_leave_constraints(model, x, employees, days)
        self._add_day_off_constraints(model, x, employees, days)
        self._add_manual_shift_constraints(model, x, employees, days)
        self._add_work_dependency_constraint(model, x, employees, days)
        self._add_one_shift_per_day_constraint(model, x, employees, days)

        open_violations = self._apply_policy(
            "open",
            hard_fn=lambda: self._add_fixed_staff_shift_constraints(
                model, x, employees, trade_days,
                self.SHIFT_OPEN,
                min_open,
                soft=False
            ),
            soft_fn=lambda: self._add_fixed_staff_shift_constraints(
                model, x, employees, trade_days,
                self.SHIFT_OPEN,
                min_open,
                soft=True
            )
        )

        close_violations = self._apply_policy(
            "close",
            hard_fn=lambda: self._add_fixed_staff_shift_constraints(
                model, x, employees, trade_days,
                self.SHIFT_CLOSE,
                min_close,
                soft=False
            ),
            soft_fn=lambda: self._add_fixed_staff_shift_constraints(
                model, x, employees, trade_days,
                self.SHIFT_CLOSE,
                min_close,
                soft=True
            )
        )

        rest_violations = self._apply_policy(
            "rest_11h",
            hard_fn=lambda: self._add_rest_11h_constraint(
                model, x, employees, days, trade_days, soft=False
            ),
            soft_fn=lambda: self._add_rest_11h_constraint(
                model, x, employees, days, trade_days, soft=True
            )
        )

        balance_violations = self._apply_policy(
            "balance",
            hard_fn=lambda: self._add_balance_constraint(
                model, x, employees, days, soft=False
            ),
            soft_fn=lambda: self._add_balance_constraint(
                model, x, employees, days, soft=True
            )
        )

        meat_violations = self._apply_policy(
            "meat",
            hard_fn=lambda: self._add_meat_constraint(
                model, x, employees, days, trade_days, soft=False
            ),
            soft_fn=lambda: self._add_meat_constraint(
                model, x, employees, days, trade_days, soft=True
            )
        )

        coverage_violations = self._apply_policy(
            "meat_coverage",
            hard_fn=lambda: self._add_meat_coverage_constraint(
                model, x, employees, trade_days
            ),
            soft_fn=lambda: self._add_meat_coverage_constraint(
                model, x, employees, trade_days, soft=True
            )
        )

        max_consec_violations = self._apply_policy(
            "max_consecutive",
            hard_fn=lambda: self._add_max_consecutive_constraint(
                model, x, employees, days, max_consecutive, soft=False
            ),
            soft_fn=lambda: self._add_max_consecutive_constraint(
                model, x, employees, days, max_consecutive, soft=True
            )
        )

        monthly_hours_violations = self._apply_policy(
            "monthly_hours",
            hard_fn=lambda: self._add_monthly_hours_constraint(
                model, x, employees, days, soft=False
            ),
            soft_fn=lambda: self._add_monthly_hours_constraint(
                model, x, employees, days, soft=True
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
            self._add_work_balance_penalty(model, x, employees, trade_days)
        )
        all_soft_violations.extend(
            self._add_open_close_penalty(x, employees, trade_days)
        )
        
        self._build_objective(model, all_soft_violations)
        solver, status = self._solve_model(model)
        success = self._save_solution(solver, status, x, employees, trade_days)

        return {
            "status": status,
            "success": success,
            "conflicts": solver.NumConflicts(),
            "branches": solver.NumBranches(),
            "wall_time": solver.WallTime()
        }

    def _clear_schedule(self):
        for emp in self.schedule.employees:
            for day in range(1, self.schedule.days_in_month + 1):
                ds = self.schedule.get_day(emp, day)
                if (
                    ds.is_leave
                    or ds.is_locked
                    or getattr(ds, "is_day_off", False)
                    or getattr(ds, "start_time", None)
                ):
                    continue
                self.schedule.set_day_free(emp, day)

    def _calc_end(self, start_str, hours):
        from datetime import datetime, timedelta
        fmt = "%H:%M"
        start = datetime.strptime(start_str, fmt)
        end = start + timedelta(hours=hours)
        return end.strftime(fmt)

    def _calc_start(self, end_str, hours):
        from datetime import datetime, timedelta
        fmt = "%H:%M"
        end = datetime.strptime(end_str, fmt)
        start = end - timedelta(hours=hours)
        return start.strftime(fmt)
    
    def _create_variables(self, model, employees, days):
        x = {}
        for e in range(len(employees)):
            for d in days:
                for s in (self.ALL_SHIFTS):
                    x[e, d, s] = model.NewBoolVar(f"x_e{e}_d{d}_s{s}")
        print(f"[MODEL] variables: {len(x)}")
        return x
    
    def _add_non_trade_day_constraints(self, model, x, employees, days):
        for e in range(len(employees)):
            for d in days:
                if not self.shop.is_trade_day(d):
                    for s in self.ALL_SHIFTS:
                        model.Add(x[e, d, s] == 0)

    def _add_one_shift_per_day_constraint(self, model, x, employees, days):

        for e in range(len(employees)):
            for d in days:
                model.Add(
                    sum(x[e, d, s] for s in self.ALL_SHIFTS) <= 1
                )

    def _add_fixed_staff_shift_constraints(
        self,
        model,
        x,
        employees,
        trade_days,
        shift_type,
        min_staff,
        soft=False
    ):
        print(f"[CONSTRAINT] fixed_staff shift={shift_type} min={min_staff} soft={soft}")
        violations = []

        for d in trade_days:
            print(f"  day={d}")

            # tylko OPEN / CLOSE
            total_staff = sum(
                x[e, d, shift_type] for e in range(len(employees))
            )

            opener_staff = sum(
                x[e, d, shift_type]
                for e in range(len(employees))
                if employees[e].is_opener
            )

            if not soft:
                meat_staff = sum(
                    x[e, d, shift_type]
                    for e in range(len(employees))
                    if employees[e].is_meat
                )

                model.Add(total_staff == min_staff)
                model.Add(opener_staff == 1)
                model.Add(meat_staff == 1)

            else:
                # kara za brak ludzi
                total_violation = model.NewIntVar(
                    0, min_staff,
                    f"staff_v_d{d}_{shift_type}"
                )
                model.Add(total_staff + total_violation >= min_staff)
                violations.append(total_violation)

                # kara za brak opener
                opener_violation = model.NewBoolVar(
                    f"opener_v_d{d}_{shift_type}"
                )
                model.Add(opener_staff + opener_violation >= 1)
                violations.append(opener_violation)

        return violations

    def _add_max_consecutive_constraint(
        self,
        model,
        x,
        employees,
        days,
        max_consecutive,
        soft=False
    ):
        violations = []

        for e in range(len(employees)):
            for start in range(1, len(days) - max_consecutive + 1):

                work_sum = sum(
                    x[e, d, s]
                    for d in range(start, start + max_consecutive + 1)
                    for s in self.ALL_SHIFTS
                )

                if not soft:
                    model.Add(work_sum <= max_consecutive)

                else:
                    violation = model.NewIntVar(
                        0, len(days),   # ← duży zakres
                        f"max_consec_violation_e{e}_d{start}"
                    )

                    model.Add(work_sum <= max_consecutive + violation)
                    violations.append(violation)

        return violations

    def _add_rest_11h_constraint(
        self,
        model,
        x,
        employees,
        days,
        trade_days,
        soft=False
    ):
        from datetime import datetime, timedelta
        fmt = "%H:%M"

        violations = []
        rest_constraints = 0

        for e in range(len(employees)):

            for i in range(len(days) - 1):

                d = days[i]
                d_next = days[i + 1]

                if d not in trade_days or d_next not in trade_days:
                    continue

                hours_d = self.shop.get_open_hours_for_day(d)
                hours_next = self.shop.get_open_hours_for_day(d_next)

                if not hours_d or not hours_next:
                    continue

                open_d, close_d = hours_d
                open_next, close_next = hours_next

                shifts_today = {}

                # OPEN
                shifts_today[self.SHIFT_OPEN] = (
                    open_d,
                    self._calc_end(open_d, employees[e].daily_hours)
                )

                # CLOSE
                shifts_today[self.SHIFT_CLOSE] = (
                    self._calc_start(close_d, employees[e].daily_hours),
                    close_d
                )

                # WORK_START offsets
                for off, shift in [
                    (15, self.SHIFT_WORK_START_15),
                    (30, self.SHIFT_WORK_START_30),
                    (45, self.SHIFT_WORK_START_45),
                    (60, self.SHIFT_WORK_START_60),
                    (75, self.SHIFT_WORK_START_75),
                    (90, self.SHIFT_WORK_START_90),
                ]:
                    start = (
                        datetime.strptime(open_d, fmt)
                        + timedelta(minutes=off)
                    ).strftime(fmt)

                    shifts_today[shift] = (
                        start,
                        self._calc_end(start, employees[e].daily_hours)
                    )

                # WORK_END offsets
                for off, shift in [
                    (15, self.SHIFT_WORK_END_15),
                    (30, self.SHIFT_WORK_END_30),
                    (45, self.SHIFT_WORK_END_45),
                    (60, self.SHIFT_WORK_END_60),
                    (75, self.SHIFT_WORK_END_75),
                    (90, self.SHIFT_WORK_END_90),
                ]:
                    end = (
                        datetime.strptime(close_d, fmt)
                        - timedelta(minutes=off)
                    ).strftime(fmt)

                    shifts_today[shift] = (
                        self._calc_start(end, employees[e].daily_hours),
                        end
                    )

                shifts_next = {}

                # OPEN
                shifts_next[self.SHIFT_OPEN] = (
                    open_next,
                    self._calc_end(open_next, employees[e].daily_hours)
                )

                # CLOSE
                shifts_next[self.SHIFT_CLOSE] = (
                    self._calc_start(close_next, employees[e].daily_hours),
                    close_next
                )

                # WORK_START offsets
                for off, shift in [
                    (15, self.SHIFT_WORK_START_15),
                    (30, self.SHIFT_WORK_START_30),
                    (45, self.SHIFT_WORK_START_45),
                    (60, self.SHIFT_WORK_START_60),
                    (75, self.SHIFT_WORK_START_75),
                    (90, self.SHIFT_WORK_START_90),
                ]:
                    start = (
                        datetime.strptime(open_next, fmt)
                        + timedelta(minutes=off)
                    ).strftime(fmt)

                    shifts_next[shift] = (
                        start,
                        self._calc_end(start, employees[e].daily_hours)
                    )

                # WORK_END offsets
                for off, shift in [
                    (15, self.SHIFT_WORK_END_15),
                    (30, self.SHIFT_WORK_END_30),
                    (45, self.SHIFT_WORK_END_45),
                    (60, self.SHIFT_WORK_END_60),
                    (75, self.SHIFT_WORK_END_75),
                    (90, self.SHIFT_WORK_END_90),
                ]:
                    end = (
                        datetime.strptime(close_next, fmt)
                        - timedelta(minutes=off)
                    ).strftime(fmt)

                    shifts_next[shift] = (
                        self._calc_start(end, employees[e].daily_hours),
                        end
                    )

                for s1 in shifts_today:
                    for s2 in shifts_next:

                        end_today = datetime.strptime(shifts_today[s1][1], fmt)
                        start_next = datetime.strptime(shifts_next[s2][0], fmt)

                        rest = start_next - end_today
                        if rest.total_seconds() < 0:
                            rest += timedelta(days=1)

                        if rest < timedelta(hours=11):

                            if not soft:
                                model.Add(
                                    x[e, d, s1] + x[e, d_next, s2] <= 1
                                )
                            else:
                                violation = model.NewBoolVar(
                                    f"rest_violation_e{e}_d{d}_{s1}_{s2}"
                                )
                                model.Add(
                                    x[e, d, s1] + x[e, d_next, s2] <= 1 + violation
                                )
                                violations.append(violation)

                            rest_constraints += 1

        print("Constrainty 11h rest:", rest_constraints)
        return violations

    def _add_meat_constraint(self, model, x, employees, days, trade_days, soft=False):
        violations = []

        for d in trade_days:

            meat_on_open = sum(
                x[e, d, self.SHIFT_OPEN]
                for e in range(len(employees))
                if employees[e].is_meat
            )

            meat_on_close = sum(
                x[e, d, self.SHIFT_CLOSE]
                for e in range(len(employees))
                if employees[e].is_meat
            )

            meat_on_work = sum(
                x[e, d, s]
                for e in range(len(employees))
                for s in self.ALL_SHIFTS
                if s not in (self.SHIFT_OPEN, self.SHIFT_CLOSE)
                and employees[e].is_meat
            )

            total_work = sum(
                x[e, d, s]
                for e in range(len(employees))
                for s in self.ALL_SHIFTS
                if s not in (self.SHIFT_OPEN, self.SHIFT_CLOSE)
            )

            if not soft:
                work_exists = model.NewBoolVar(f"work_exists_d{d}")

                model.Add(total_work >= 1).OnlyEnforceIf(work_exists)
                model.Add(total_work == 0).OnlyEnforceIf(work_exists.Not())

                meat_on_work = sum(
                    x[e, d, s]
                    for e in range(len(employees))
                    for s in self.ALL_SHIFTS
                    if s not in (self.SHIFT_OPEN, self.SHIFT_CLOSE)
                    and employees[e].is_meat
                )

                model.Add(
                    meat_on_work >= 1
                ).OnlyEnforceIf(work_exists)

            else:
                v1 = model.NewBoolVar(f"meat_open_v_d{d}")
                model.Add(meat_on_open + v1 >= 1)
                violations.append(v1)

                v2 = model.NewBoolVar(f"meat_close_v_d{d}")
                model.Add(meat_on_close + v2 >= 1)
                violations.append(v2)

        return violations
    
    def _add_meat_coverage_constraint(
        self,
        model,
        x,
        employees,
        trade_days,
        soft=False
    ):

        from datetime import datetime, timedelta

        violations = []

        for d in trade_days:

            hours = self.shop.get_open_hours_for_day(d)
            if not hours:
                continue

            open_time, close_time = hours

            fmt = "%H:%M"
            open_dt = datetime.strptime(open_time, fmt)
            close_dt = datetime.strptime(close_time, fmt)

            t = open_dt

            while t < close_dt:

                slot = t.strftime(fmt)

                meat_cover = []

                for e in range(len(employees)):

                    if not employees[e].is_meat:
                        continue

                    emp = employees[e]
                    shift_len = timedelta(hours=emp.daily_hours)

                    # OPEN
                    start = open_dt
                    end = start + shift_len

                    if start <= t < end:
                        meat_cover.append(x[e, d, self.SHIFT_OPEN])

                    # CLOSE
                    end = close_dt
                    start = end - shift_len

                    if start <= t < end:
                        meat_cover.append(x[e, d, self.SHIFT_CLOSE])

                    for s in self.ALL_SHIFTS:

                        if s in (self.SHIFT_OPEN, self.SHIFT_CLOSE):
                            continue

                        meat_cover.append(x[e, d, s])

                if not meat_cover:
                    t += timedelta(minutes=15)
                    continue

                if not soft:

                    model.Add(sum(meat_cover) >= 1)

                else:

                    v = model.NewBoolVar(f"meat_cover_v_d{d}_{slot}")
                    model.Add(sum(meat_cover) + v >= 1)
                    violations.append(v)

                t += timedelta(minutes=15)

        return violations

 #tu trzeba sprawdzić, zmieniłem min_target na max_minutes, bo inaczej nie można było zrobić soft constraintu (nie można dać nierówności z zmienną boolowską po prawej stronie)   
    def _add_monthly_hours_constraint(
        self,
        model,
        x,
        employees,
        days,
        soft=False
    ):
        violations = []

        nominal_hours = self.shop.get_full_time_nominal_hours()
        nominal_minutes = nominal_hours * 60

        all_totals = []

        for e in range(len(employees)):

            emp = employees[e]
            shift_minutes = int(emp.daily_hours * 60)

            total_minutes = model.NewIntVar(0, 50000, f"month_total_e{e}")

            model.Add(
                total_minutes ==
                sum(
                    x[e, d, s] * shift_minutes
                    for d in days
                    for s in self.ALL_SHIFTS
                )
            )

            all_totals.append(total_minutes)
            leave_days = sum(
                1 for d in days
                if self.schedule.get_day(emp, d).is_leave
            )

            leave_minutes = leave_days * 480

            target_minutes = int(nominal_minutes * (emp.daily_hours / 8) - leave_minutes)
            max_minutes = target_minutes + (8 * 60)

            if not soft:
                model.Add(total_minutes >= target_minutes)
                model.Add(total_minutes <= max_minutes)

            else:
                under = model.NewIntVar(0, 50000, f"under_e{e}")
                model.Add(total_minutes + under >= max_minutes)

                over = model.NewIntVar(0, 50000, f"over_e{e}")
                model.Add(total_minutes <= target_minutes + over)

                violations.append(under)
                violations.append(over)

        # ⬇️ DODANE: fairness między pracownikami (tylko w soft)
        if soft and len(all_totals) > 1:

            max_total = model.NewIntVar(0, 50000, "month_max_total")
            min_total = model.NewIntVar(0, 50000, "month_min_total")

            model.AddMaxEquality(max_total, all_totals)
            model.AddMinEquality(min_total, all_totals)

            spread = model.NewIntVar(0, 50000, "month_spread")
            model.Add(spread == max_total - min_total)

            violations.append(spread)

        return violations
    
    def _add_leave_constraints(
        self,
        model,
        x,
        employees,
        days
    ):
        for e in range(len(employees)):
            emp = employees[e]

            for d in days:
                day_state = self.schedule.get_day(emp, d)

                if day_state.is_leave:
                    for s in self.ALL_SHIFTS:
                        model.Add(x[e, d, s] == 0)

    def _add_balance_constraint(
        self,
        model,
        x,
        employees,
        days,
        soft=True
    ):
        nominal = self.shop.get_full_time_nominal_hours()

        if not nominal:
            return []

        nominal_minutes = int(nominal * 60)
        violations = []

        for e in range(len(employees)):

            shift_minutes = int(employees[e].daily_hours * 60)

            total_minutes = model.NewIntVar(0, 20000, f"total_minutes_e{e}")

            model.Add(
                total_minutes ==
                sum(
                    sum(x[e, d, s] for s in self.ALL_SHIFTS) * shift_minutes
                    for d in days
                )
            )

            if not soft:
                # MANDATORY → dokładnie nominal
                model.Add(total_minutes == nominal_minutes)

            else:
                # PREFERRED → kara za odchylenie
                diff = model.NewIntVar(-20000, 20000, f"diff_e{e}")
                model.Add(diff == total_minutes - nominal_minutes)

                abs_diff = model.NewIntVar(0, 20000, f"abs_diff_e{e}")
                model.AddAbsEquality(abs_diff, diff)

                violations.append(abs_diff)

        return violations
    
    def _add_work_dependency_constraint(
        self,
        model,
        x,
        employees,
        days
    ):
        print("[CONSTRAINT] work_dependency")

        for d in days:

            total_open_close = sum(
                x[e, d, self.SHIFT_OPEN] + x[e, d, self.SHIFT_CLOSE]
                for e in range(len(employees))
            )

            for e in range(len(employees)):
                for s in self.ALL_SHIFTS:

                    if s in (self.SHIFT_OPEN, self.SHIFT_CLOSE):
                        continue

                    model.Add(
                        x[e, d, s] <= total_open_close
                    )

    def _add_total_open_close_limit(
        self,
        model,
        x,
        employees,
        trade_days
    ):
        print("[CONSTRAINT] total_open_close_limit = 6")
        for d in trade_days:
            print(f"  day={d}")

            total_open_close = sum(
                x[e, d, self.SHIFT_OPEN] + x[e, d, self.SHIFT_CLOSE]
                for e in range(len(employees))
            )

            model.Add(total_open_close == 6)

    def _add_open_close_penalty(
        self,
        x,
        employees,
        days
    ):
        print("[OBJECTIVE] penalty OPEN/CLOSE usage")
        penalties = []

        for e in range(len(employees)):
            for d in days:

                penalties.append(x[e, d, self.SHIFT_OPEN])
                penalties.append(x[e, d, self.SHIFT_CLOSE])

        return penalties
    
    def _add_work_offset_constraint(self, model, x, work_offset, employees, days):

        for e in range(len(employees)):
            for d in days:

                # jeśli nie WORK -> offset = 1 (dummy)
                model.Add(work_offset[e,d] == 1).OnlyEnforceIf(
                    x[e,d,self.SHIFT_WORK_START].Not(),
                    x[e,d,self.SHIFT_WORK_END].Not()
                )

    def _add_work_balance_penalty(
        self,
        model,
        x,
        employees,
        days
    ):
        penalties = []

        START_SHIFTS = (
            self.SHIFT_WORK_START_15,
            self.SHIFT_WORK_START_30,
            self.SHIFT_WORK_START_45,
            self.SHIFT_WORK_START_60,
            self.SHIFT_WORK_START_75,
            self.SHIFT_WORK_START_90,
        )

        END_SHIFTS = (
            self.SHIFT_WORK_END_15,
            self.SHIFT_WORK_END_30,
            self.SHIFT_WORK_END_45,
            self.SHIFT_WORK_END_60,
            self.SHIFT_WORK_END_75,
            self.SHIFT_WORK_END_90,
        )

        for e in range(len(employees)):

            work_start = sum(
                x[e, d, s]
                for d in days
                for s in START_SHIFTS
            )

            work_end = sum(
                x[e, d, s]
                for d in days
                for s in END_SHIFTS
            )

            diff = model.NewIntVar(-31, 31, f"work_balance_diff_e{e}")
            model.Add(diff == work_start - work_end)

            abs_diff = model.NewIntVar(0, 31, f"work_balance_abs_e{e}")
            model.AddAbsEquality(abs_diff, diff)

            penalties.append(abs_diff)

        return penalties


    def _add_day_off_constraints(
        self,
        model,
        x,
        employees,
        days
    ):
        for e in range(len(employees)):
            emp = employees[e]

            for d in days:
                day_state = self.schedule.get_day(emp, d)

                if getattr(day_state, "is_day_off", False):

                    for s in self.ALL_SHIFTS:
                        model.Add(x[e, d, s] == 0)

    def _add_manual_shift_constraints(
        self,
        model,
        x,
        employees,
        days
    ):
        from datetime import datetime

        fmt = "%H:%M"

        start_map = {
            15: self.SHIFT_WORK_START_15,
            30: self.SHIFT_WORK_START_30,
            45: self.SHIFT_WORK_START_45,
            60: self.SHIFT_WORK_START_60,
            75: self.SHIFT_WORK_START_75,
            90: self.SHIFT_WORK_START_90,
        }

        end_map = {
            15: self.SHIFT_WORK_END_15,
            30: self.SHIFT_WORK_END_30,
            45: self.SHIFT_WORK_END_45,
            60: self.SHIFT_WORK_END_60,
            75: self.SHIFT_WORK_END_75,
            90: self.SHIFT_WORK_END_90,
        }

        for e in range(len(employees)):
            emp = employees[e]

            for d in days:

                day_state = self.schedule.get_day(emp, d)

                start = getattr(day_state, "start_time", None)
                end = getattr(day_state, "end_time", None)

                if not start or not end:
                    continue

                hours = self.shop.get_open_hours_for_day(d)
                if not hours:
                    continue

                open_time, close_time = hours

                shift = None

                if start == open_time:
                    shift = self.SHIFT_OPEN

                elif end == close_time:
                    shift = self.SHIFT_CLOSE

                else:

                    open_dt = datetime.strptime(open_time, fmt)
                    start_dt = datetime.strptime(start, fmt)

                    diff = int((start_dt - open_dt).total_seconds() / 60)

                    if diff in start_map:
                        shift = start_map[diff]

                    else:
                        close_dt = datetime.strptime(close_time, fmt)
                        end_dt = datetime.strptime(end, fmt)

                        diff = int((close_dt - end_dt).total_seconds() / 60)

                        if diff in end_map:
                            shift = end_map[diff]

                if shift is None:
                    continue

                model.Add(x[e, d, shift] == 1)

                for s in self.ALL_SHIFTS:
                    if s != shift:
                        model.Add(x[e, d, s] == 0)

#########################################################
# Kalkulacja celu i zapisywanie rozwiązania
#########################################################

    def _build_objective(
        self,
        model,
        weighted_soft_terms
    ):
        if weighted_soft_terms:
            print("[OBJECTIVE] terms:", len(weighted_soft_terms))
            model.Maximize(-sum(weighted_soft_terms))

    def _solve_model(self, model):

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 20

        status = solver.Solve(model)

        print("Status:", solver.StatusName(status))
        print("Czas:", solver.WallTime(), "s")
        print("Conflicts:", solver.NumConflicts())
        print("Branches:", solver.NumBranches())

        return solver, status
    
    def _save_solution(
        self,
        solver,
        status,
        x,
        employees,
        trade_days
    ):
        from ortools.sat.python import cp_model
        from datetime import datetime, timedelta

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):

            print("❌ BRAK ROZWIĄZANIA")
            print("DEBUG INFEASIBLE:")
            print("- Sprawdź czy liczba mięsiarzy >= dni handlowe")
            print("- Sprawdź czy min_open/min_close nie za duże")
            print("- Sprawdź czy max_consecutive nie blokuje miesiąca")
            print("- Sprawdź czy 11h rest nie koliduje z mięsem")

            return False

        print("✅ ROZWIĄZANIE ZNALEZIONE")
        print("=== PODSUMOWANIE ZMIAN ===")

        for d in trade_days:

            open_count = sum(
                solver.Value(x[e, d, self.SHIFT_OPEN])
                for e in range(len(employees))
            )

            close_count = sum(
                solver.Value(x[e, d, self.SHIFT_CLOSE])
                for e in range(len(employees))
            )

            work_count = sum(
                solver.Value(x[e, d, s])
                for e in range(len(employees))
                for s in self.ALL_SHIFTS
                if s not in (self.SHIFT_OPEN, self.SHIFT_CLOSE)
            )

            print(f"Dzień {d}: OPEN={open_count} CLOSE={close_count} WORK={work_count}")

        START_SHIFTS = {
            self.SHIFT_WORK_START_15: 15,
            self.SHIFT_WORK_START_30: 30,
            self.SHIFT_WORK_START_45: 45,
            self.SHIFT_WORK_START_60: 60,
            self.SHIFT_WORK_START_75: 75,
            self.SHIFT_WORK_START_90: 90,
        }

        END_SHIFTS = {
            self.SHIFT_WORK_END_15: 15,
            self.SHIFT_WORK_END_30: 30,
            self.SHIFT_WORK_END_45: 45,
            self.SHIFT_WORK_END_60: 60,
            self.SHIFT_WORK_END_75: 75,
            self.SHIFT_WORK_END_90: 90,
        }

        for e in range(len(employees)):
            emp = employees[e]

            for d in trade_days:

                day_state = self.schedule.get_day(emp, d)

                if (
                    day_state.is_leave
                    or day_state.is_locked
                    or getattr(day_state, "is_day_off", False)
                    or getattr(day_state, "start_time", None)
                ):
                    continue

                hours = self.shop.get_open_hours_for_day(d)
                if not hours:
                    continue

                open_time, close_time = hours
                fmt = "%H:%M"

                if solver.Value(x[e, d, self.SHIFT_OPEN]) == 1:
                    end = self._calc_end(open_time, emp.daily_hours)
                    self.schedule.set_day_hours(emp, d, open_time, end)
                    continue

                if solver.Value(x[e, d, self.SHIFT_CLOSE]) == 1:
                    start = self._calc_start(close_time, emp.daily_hours)
                    self.schedule.set_day_hours(emp, d, start, close_time)
                    continue

                for shift, offset in START_SHIFTS.items():

                    if solver.Value(x[e, d, shift]) == 1:

                        start_dt = datetime.strptime(open_time, fmt) + timedelta(minutes=offset)
                        start = start_dt.strftime(fmt)

                        end = self._calc_end(start, emp.daily_hours)

                        self.schedule.set_day_hours(emp, d, start, end)
                        break

                for shift, offset in END_SHIFTS.items():

                    if solver.Value(x[e, d, shift]) == 1:

                        end_dt = datetime.strptime(close_time, fmt) - timedelta(minutes=offset)
                        end = end_dt.strftime(fmt)

                        start = self._calc_start(end, emp.daily_hours)

                        self.schedule.set_day_hours(emp, d, start, end)
                        break

        print("=== KONIEC GENERATORA ===")
        return True
    
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