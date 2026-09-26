def add_fixed_staff_shift_constraints(
    model,
    x,
    employees,
    trade_days,
    shift_type,
    min_staff,
    soft=False,
    trace=None,
    meat_light_penalties=None,
    shift_duty_sum=None,
    employee_indices=None,
):
    if trace is not None:
        trace.log_constraint("fixed_staff_shift", f"shift={shift_type} min_staff={min_staff} soft={soft}")

    print(f"[CONSTRAINT] fixed_staff shift={shift_type} min={min_staff} soft={soft}")
    violations = []
    shift_duty_sum = shift_duty_sum or {}
    # employee_indices lets a caller restrict this to only some employees
    # (patrz dino_retail_profile.py::_build_open/_build_close - pracownicy
    # rotacji całodobowej/służby 24/7 mają x[e,d,shift_type] zablokowane
    # twardo przez własną bramę, więc nie powinni liczyć się do "nikogo nie
    # ma, kto mógłby spełnić min_staff") - domyślnie każdy pracownik,
    # dokładnie dzisiejsze zachowanie, ten sam wzorzec co
    # add_max_consecutive_constraint.
    indices = list(employee_indices) if employee_indices is not None else list(range(len(employees)))
    if not indices:
        # Nikt nie jest w stanie w ogóle spełnić tej zmiany (np. projekt, w
        # którym KAŻDY pracownik jest na lokalizacji rotacji całodobowej -
        # patrz round_clock_constraint.py - i nikt nie zostaje dla
        # klasycznego OPEN/CLOSE) - wymóg min_staff byłby strukturalnie
        # niespełnialny, więc constraint po prostu nie ma tu zastosowania,
        # zamiast wymuszać INFEASIBLE na całym miesiącu.
        return []

    for d in trade_days:
        total_staff = sum(
            x[e, d, shift_type] for e in indices
        )

        opener_staff = sum(
            x[e, d, shift_type]
            for e in indices
            if employees[e].is_opener
        )

        # Budżet "mięsa tymczasowego" (is_meat_light) - ograniczony twardo do
        # max 1h/dzień/osobę gdzie indziej (build_meat_light_duty), tu tylko
        # sumujemy przydzielony budżet w oknie tej zmiany.
        meat_light_staff = sum(
            shift_duty_sum.get((e, d, shift_type), 0)
            for e in indices
            if employees[e].is_meat_light
        )

        if not soft:
            meat_staff = sum(
                x[e, d, shift_type]
                for e in indices
                if employees[e].is_meat
            )

            model.Add(total_staff == min_staff)
            model.Add(opener_staff >= 1)
            model.Add(meat_staff + meat_light_staff >= 1)
            if meat_light_penalties is not None:
                meat_light_penalties.append(meat_light_staff)

        else:
            total_violation = model.NewIntVar(
                0, max(min_staff, 1),
                f"staff_v_d{d}_{shift_type}"
            )
            model.Add(total_staff + total_violation >= min_staff)
            violations.append(total_violation)

            opener_violation = model.NewBoolVar(
                f"opener_v_d{d}_{shift_type}"
            )
            model.Add(opener_staff + opener_violation >= 1)
            violations.append(opener_violation)

            meat_staff = sum(
                x[e, d, shift_type]
                for e in indices
                if employees[e].is_meat
            )
            meat_violation = model.NewBoolVar(f"meat_v_d{d}_{shift_type}")
            model.Add(meat_staff + meat_light_staff + meat_violation >= 1)
            violations.append(meat_violation)
            if meat_light_penalties is not None:
                meat_light_penalties.append(meat_light_staff)

    return violations

def add_max_consecutive_constraint(
    model,
    x,
    employees,
    days,
    max_consecutive,
    all_shifts,
    soft=False,
    trace=None,
    employee_indices=None,
    fixed_work_days=None,
):
    if trace is not None:
        trace.log_constraint("max_consecutive", f"max_consecutive={max_consecutive} soft={soft}")

    # fixed_work_days: {e: {dzień}} - dni pracy spoza zmiennych x (ręczne
    # wpisy pracowników rotacji służby liczone jako stałe przedziały planu,
    # patrz duty_rotation_manual_coverage.py) - liczone jak przepracowany
    # dzień. Domyślnie brak, dokładnie dotychczasowe zachowanie.
    fixed_work_days = fixed_work_days or {}

    violations = []

    # employee_indices lets a caller apply this same max_consecutive value
    # to only some employees (e.g. one per-location group at a time) while
    # keeping x[e,...] indices global - default is every employee, exactly
    # today's behavior.
    for e in (employee_indices if employee_indices is not None else range(len(employees))):
        for start in range(1, len(days) - max_consecutive + 1):

            work_sum = sum(
                x[e, d, s]
                for d in range(start, start + max_consecutive + 1)
                for s in all_shifts
            ) + sum(1 for d in range(start, start + max_consecutive + 1) if d in fixed_work_days.get(e, ()))

            if not soft:
                model.Add(work_sum <= max_consecutive)

            else:
                violation = model.NewIntVar(
                    0, len(days),
                    f"max_consec_violation_e{e}_d{start}"
                )

                model.Add(work_sum <= max_consecutive + violation)
                violations.append(violation)

    return violations