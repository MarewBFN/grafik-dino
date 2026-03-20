from ortools.sat.python import cp_model


def build_objective(model, weighted_soft_terms):
    if weighted_soft_terms:
        print("[OBJECTIVE] terms:", len(weighted_soft_terms))
        model.Maximize(-sum(weighted_soft_terms))


def solve_model(model):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60
    solver.parameters.num_search_workers = 10

    status = solver.Solve(model)

    print("Status:", solver.StatusName(status))
    print("Czas:", solver.WallTime(), "s")
    print("Conflicts:", solver.NumConflicts())
    print("Branches:", solver.NumBranches())


    return solver, status