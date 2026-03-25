def add_fixed_staff_shift_constraints(
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

            # Twarde ograniczenia: suma osób musi się zgadzać, 
            # ale składy specjalistyczne mogą się nakładać.
            model.Add(total_staff == min_staff)
            model.Add(opener_staff >= 1)
            model.Add(meat_staff >= 1)

        else:
            # Logika soft (kary) jest już poprawnie oparta na >= 1
            total_violation = model.NewIntVar(
                0, min_staff,
                f"staff_v_d{d}_{shift_type}"
            )
            model.Add(total_staff + total_violation >= min_staff)
            violations.append(total_violation)

            opener_violation = model.NewBoolVar(
                f"opener_v_d{d}_{shift_type}"
            )
            model.Add(opener_staff + opener_violation >= 1)
            violations.append(opener_violation)

            # Dodajmy mięso do wersji soft, skoro go brakowało
            meat_staff = sum(
                x[e, d, shift_type]
                for e in range(len(employees))
                if employees[e].is_meat
            )
            meat_violation = model.NewBoolVar(f"meat_v_d{d}_{shift_type}")
            model.Add(meat_staff + meat_violation >= 1)
            violations.append(meat_violation)

    return violations

def add_max_consecutive_constraint(
    model,
    x,
    employees,
    days,
    max_consecutive,
    all_shifts,
    soft=False
):
    violations = []

    for e in range(len(employees)):
        for start in range(1, len(days) - max_consecutive + 1):

            work_sum = sum(
                x[e, d, s]
                for d in range(start, start + max_consecutive + 1)
                for s in all_shifts
            )

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