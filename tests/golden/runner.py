"""Uruchamianie projektów golden i porównanie z punktem odniesienia.

Nagranie punktu odniesienia (tylko gdy świadomie zmieniamy zachowanie
generatora albo zestaw przypadków - NIE po zwykłym kroku migracji):

    python -m tests.golden.runner record            # wszystkie przypadki
    python -m tests.golden.runner record dino_01    # tylko pasujące nazwy

Porównanie bez pytest (to samo robi tests/test_golden_schedules.py):

    python -m tests.golden.runner check

Co jest zapisywane dla przypadku (reference.json):
- status solvera (OPTIMAL/FEASIBLE/INFEASIBLE/UNKNOWN), czy się udało;
- wartość celu i najlepsze górne ograniczenie (generator maksymalizuje
  -suma kar) (suma po wszystkich modelach
  jednego generowania - przy różnych ustawieniach placówek generator
  rozwiązuje kilka niezależnych modeli po kolei);
- naruszenia z niezależnego walidatora (tests/schedule_validator.py):
  twarde, miękkie (liczba per zasada), sprzeczności danych wejściowych.

Tryb deterministyczny: zamiast produkcyjnego solve_model (do 8 wątków,
limit w sekundach - wynik zależy od szybkości komputera) golden używa
jednego wątku i limitu "deterministycznego czasu" CP-SAT. Ten sam model daje
wtedy zawsze ten sam grafik, na każdym komputerze z tą samą wersją OR-Tools.

Porównanie (compare_outcome) - dwa poziomy:
1. Odcisk modelu CP-SAT (sha256 modelu bez nazw zmiennych) taki sam jak w
   punkcie odniesienia = migracja nie zmieniła NICZEGO w tym, co solver
   dostaje -> wymagany identyczny grafik (odcisk komórek) i identyczna
   wartość celu. To główny tryb dla kroków migracji danych.
2. Odcisk modelu inny (świadomie przebudowany constraint) -> porównanie
   niezmienników: prawdziwe optimum leży w [wartość celu, górne
   ograniczenie] obu uruchomień, więc przedziały muszą się przecinać (dla OPTIMAL po
   obu stronach - równe wartości), wynik nie może być wyraźnie gorszy
   (QUALITY_TOLERANCE), walidator nie może znaleźć nowych twardych naruszeń.
"""

import contextlib
import hashlib
import io
import re
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GOLDEN_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = GOLDEN_DIR / "projects"
REFERENCE_FILE = GOLDEN_DIR / "reference.json"
DEFAULT_TIME_LIMIT = 30
# Limit pracy solvera w trybie deterministycznym (jednostki "deterministic
# time" CP-SAT, mniej więcej sekundy na typowym komputerze).
DETERMINISTIC_TIME = 20.0

# Wynik v2 może być gorszy od nagranego najwyżej o tyle (względnie) - tylko
# dla wyników nieoptymalnych (FEASIBLE), gdzie solver przerwał po limicie.
QUALITY_TOLERANCE = 0.03
# Bezwzględny luz porównań wartości celu (zaokrąglenia double z CP-SAT).
ABS_EPS = 1e-6

STATUS_NAMES = {0: "UNKNOWN", 1: "MODEL_INVALID", 2: "FEASIBLE", 3: "INFEASIBLE", 4: "OPTIMAL"}


def project_path(name):
    return PROJECTS_DIR / f"{name}.json"


def _cases():
    from tests.golden.cases import GOLDEN_CASES, register_golden_profiles

    register_golden_profiles()
    return GOLDEN_CASES


def case_names():
    from tests.golden.cases import GOLDEN_CASES

    return [c["name"] for c in GOLDEN_CASES]


def write_project_file(spec):
    """Buduje projekt jak GUI (harness audytu) i zapisuje go DZISIEJSZYM
    save_project - to jest zamrożony plik wejściowy przypadku."""
    from persistence.project_io import save_project
    from tests.generator_audit_harness import build_case

    schedule, shop = build_case(spec)
    shop.constraints["solver_time_limit_seconds"] = spec.get("time_limit", DEFAULT_TIME_LIMIT)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    save_project(project_path(spec["name"]), schedule, shop)


def model_fingerprint(model):
    """sha256 modelu CP-SAT bez nazw zmiennych/ograniczeń (nazwy nie
    zmieniają tego, co solver liczy)."""
    text = re.sub(r'^\s*name: ".*"$', "", str(model.Proto()), flags=re.M)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def schedule_fingerprint(schedule):
    cells = []
    for emp in sorted(schedule.employees, key=lambda e: (e.last_name, e.first_name)):
        for day in range(1, schedule.days_in_month + 1):
            ds = schedule.get_day(emp, day)
            cells.append((emp.last_name, emp.first_name, day, ds.start, ds.end, ds.is_full_day,
                          ds.is_leave, ds.is_sick, ds.is_day_off, ds.is_locked, ds.shift_class))
    return hashlib.sha256(repr(cells).encode("utf-8")).hexdigest()[:16]


@contextlib.contextmanager
def _deterministic_solves(solves):
    """Podmienia logic.auto_generator.solve_model na deterministyczny
    (1 wątek, limit pracy zamiast czasu) i zapisuje odcisk modelu, wartość
    celu i górne ograniczenie każdego rozwiązanego modelu."""
    from ortools.sat.python import cp_model

    import logic.auto_generator as auto_generator

    original = auto_generator.solve_model

    def deterministic(model, *args, **kwargs):
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 0
        solver.parameters.max_deterministic_time = DETERMINISTIC_TIME
        status = solver.Solve(model)
        found = status in (cp_model.FEASIBLE, cp_model.OPTIMAL)
        solves.append({
            "status": int(status),
            "model": model_fingerprint(model),
            "objective": solver.ObjectiveValue() if found else None,
            "bound": solver.BestObjectiveBound() if found else None,
        })
        return solver, status

    auto_generator.solve_model = deterministic
    try:
        yield
    finally:
        auto_generator.solve_model = original


def run_golden(name):
    """Wczytuje zamrożony plik projektu (tak jak program wczytuje projekt
    użytkownika), generuje grafik i zwraca podsumowanie do porównania."""
    from logic.schedule_controller import ScheduleController
    from persistence.project_io import load_project
    from tests.schedule_validator import evaluate, validate

    _cases()
    schedule, shop = load_project(project_path(name))
    before = schedule.snapshot()
    controller = ScheduleController(schedule, shop)

    solves = []
    started = time.time()
    with _deterministic_solves(solves), contextlib.redirect_stdout(io.StringIO()):
        result = controller.generate_schedule(force=True)
    elapsed = time.time() - started

    success = bool(result and result.get("success"))
    report = validate(before, controller.schedule, shop, generation_succeeded=success)
    ev = evaluate(report, shop)

    objectives = [s["objective"] for s in solves]
    bounds = [s["bound"] for s in solves]
    statuses = [STATUS_NAMES.get(s["status"], str(s["status"])) for s in solves]

    soft_by_rule = {}
    for v in ev["soft"]:
        soft_by_rule[v.rule] = soft_by_rule.get(v.rule, 0) + 1

    return {
        "success": success,
        "statuses": statuses,
        "models": [s["model"] for s in solves],
        "schedule": schedule_fingerprint(controller.schedule),
        "optimal": bool(statuses) and all(s == "OPTIMAL" for s in statuses),
        "objective": sum(objectives) if objectives and None not in objectives else None,
        "bound": sum(bounds) if bounds and None not in bounds else None,
        "hard_count": len(ev["hard"]),
        "hard_rules": sorted({v.rule for v in ev["hard"]}),
        "soft_by_rule": dict(sorted(soft_by_rule.items())),
        "input_conflicts": len(ev["input"]),
        "elapsed": round(elapsed, 1),
    }


def compare_outcome(reference, outcome):
    """Lista problemów (pusta = zgodne z punktem odniesienia)."""
    problems = []
    if outcome["models"] == reference["models"]:
        # Ten sam model, deterministyczny solver -> ten sam grafik.
        if outcome["schedule"] != reference["schedule"]:
            problems.append("identyczny model CP-SAT, ale inny grafik (inne dane wejściowe po wczytaniu pliku?)")
        if outcome["objective"] != reference["objective"]:
            problems.append(f"identyczny model CP-SAT, ale inna wartość celu: było {reference['objective']}, jest {outcome['objective']}")
    if outcome["success"] != reference["success"]:
        problems.append(f"success: było {reference['success']}, jest {outcome['success']}")
        return problems

    if outcome["hard_count"] > reference["hard_count"]:
        problems.append(
            f"twarde naruszenia walidatora: było {reference['hard_count']} {reference['hard_rules']}, "
            f"jest {outcome['hard_count']} {outcome['hard_rules']}"
        )
    new_hard_rules = set(outcome["hard_rules"]) - set(reference["hard_rules"])
    if new_hard_rules:
        problems.append(f"nowe rodzaje twardych naruszeń: {sorted(new_hard_rules)}")
    if outcome["input_conflicts"] != reference["input_conflicts"]:
        problems.append(
            f"sprzeczności danych wejściowych: było {reference['input_conflicts']}, jest {outcome['input_conflicts']}"
        )

    ref_obj, ref_bound = reference["objective"], reference["bound"]
    obj, bound = outcome["objective"], outcome["bound"]
    if ref_obj is None or obj is None:
        if (ref_obj is None) != (obj is None):
            problems.append(f"wartość celu: było {ref_obj}, jest {obj}")
        return problems

    if reference["optimal"] and outcome["optimal"]:
        if abs(obj - ref_obj) > ABS_EPS + 1e-9 * abs(ref_obj):
            problems.append(f"optimum się zmieniło: było {ref_obj}, jest {obj}")
        return problems

    # Generator MAKSYMALIZUJE -suma kar (logic/generator/solver.py::
    # build_objective), więc optimum leży w [wartość celu, górne
    # ograniczenie]. Przedziały obu uruchomień muszą się przecinać.
    if obj > ref_bound + ABS_EPS or ref_obj > bound + ABS_EPS:
        problems.append(
            f"rozłączne przedziały optimum: było [{ref_obj}, {ref_bound}], jest [{obj}, {bound}]"
        )
    if obj < ref_obj - QUALITY_TOLERANCE * abs(ref_obj) - ABS_EPS:
        problems.append(f"wynik wyraźnie gorszy: było {ref_obj}, jest {obj} (tolerancja {QUALITY_TOLERANCE:.0%})")
    return problems


def load_reference():
    with open(REFERENCE_FILE, encoding="utf-8") as f:
        return json.load(f)


def record(filters=()):
    cases = [c for c in _cases() if not filters or any(f in c["name"] for f in filters)]
    reference = load_reference() if REFERENCE_FILE.exists() else {}
    for spec in cases:
        write_project_file(spec)
        outcome = run_golden(spec["name"])
        reference[spec["name"]] = outcome
        print(f"{spec['name']}: {outcome['statuses']} obj={outcome['objective']} bound={outcome['bound']} "
              f"model={','.join(outcome['models'])} "
              f"hard={outcome['hard_count']} soft={sum(outcome['soft_by_rule'].values())} {outcome['elapsed']}s",
              flush=True)
    ordered = {name: reference[name] for name in case_names() if name in reference}
    with open(REFERENCE_FILE, "w", encoding="utf-8") as f:
        json.dump(ordered, f, indent=2, ensure_ascii=False)
        f.write("\n")


def check(filters=()):
    reference = load_reference()
    failed = 0
    for name in case_names():
        if filters and not any(f in name for f in filters):
            continue
        outcome = run_golden(name)
        problems = compare_outcome(reference[name], outcome)
        status = "OK" if not problems else "FAIL"
        failed += bool(problems)
        same = "ten sam model" if outcome["models"] == reference[name]["models"] else "INNY model"
        print(f"{status} {name}: {same}, obj={outcome['objective']} (ref {reference[name]['objective']}) "
              f"{outcome['elapsed']}s" + "".join(f"\n    - {p}" for p in problems), flush=True)
    return failed


if __name__ == "__main__":
    command, *rest = sys.argv[1:] or ["check"]
    if command == "record":
        record(rest)
    elif command == "check":
        sys.exit(1 if check(rest) else 0)
    else:
        raise SystemExit(f"Nieznana komenda: {command} (record | check)")
