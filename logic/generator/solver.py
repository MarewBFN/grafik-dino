from ortools.sat.python import cp_model


def build_objective(model, weighted_soft_terms):
    if weighted_soft_terms:
        print("[OBJECTIVE] terms:", len(weighted_soft_terms))
        model.Maximize(-sum(weighted_soft_terms))


def solve_model(model, time_limit_seconds=60, num_search_workers=10):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = num_search_workers

    status = solver.Solve(model)

    print("Status:", solver.StatusName(status))
    print("Czas:", solver.WallTime(), "s")
    print("Conflicts:", solver.NumConflicts())
    print("Branches:", solver.NumBranches())


    return solver, status
