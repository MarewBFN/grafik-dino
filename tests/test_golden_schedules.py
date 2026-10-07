"""Golden testy generatora - siatka bezpieczeństwa migracji na Qualification.

Każdy przypadek wczytuje zamrożony plik projektu z tests/golden/projects/
(stary format pliku), generuje grafik i porównuje z tests/golden/reference.json
(walidator + wartość celu solvera; szczegóły i uzasadnienie porównania w
tests/golden/runner.py). Długie (ok. 30 s na przypadek) - uruchamiane po
każdym kroku migracji:

    python -m pytest tests/test_golden_schedules.py -n 2
"""

import pytest

from tests.golden.runner import case_names, compare_outcome, load_reference, run_golden

REFERENCE = load_reference()


@pytest.mark.parametrize("name", case_names())
def test_golden_schedule_matches_reference(name):
    assert name in REFERENCE, f"brak punktu odniesienia dla {name} - uruchom: python -m tests.golden.runner record {name}"
    problems = compare_outcome(REFERENCE[name], run_golden(name))
    assert not problems, "\n".join(problems)


# --- Samo porównanie (szybkie, bez solvera) ------------------------------

def _outcome(**overrides):
    base = {
        "success": True, "statuses": ["FEASIBLE"], "models": ["m1"], "schedule": "s1", "optimal": False,
        "objective": -1000.0, "bound": -900.0, "hard_count": 0, "hard_rules": [],
        "soft_by_rule": {}, "input_conflicts": 0,
    }
    return {**base, **overrides}


def test_compare_identical_model_requires_identical_schedule():
    assert compare_outcome(_outcome(), _outcome()) == []
    assert compare_outcome(_outcome(), _outcome(schedule="s2"))


def test_compare_other_model_accepts_overlapping_optimum_ranges():
    # Inny (równoważny) model: wynik w granicach tolerancji i przecinające się przedziały.
    assert compare_outcome(_outcome(), _outcome(models=["m2"], schedule="s2", objective=-990.0, bound=-950.0)) == []


def test_compare_other_model_rejects_worse_result_and_disjoint_ranges():
    worse = _outcome(models=["m2"], schedule="s2", objective=-1100.0, bound=-1050.0)
    problems = compare_outcome(_outcome(), worse)
    assert any("gorszy" in p for p in problems)
    assert any("rozłączne" in p for p in problems)


def test_compare_optimal_on_both_sides_requires_equal_objective():
    ref = _outcome(optimal=True, objective=-500.0, bound=-500.0)
    assert compare_outcome(ref, _outcome(models=["m2"], optimal=True, objective=-500.0, bound=-500.0)) == []
    assert compare_outcome(ref, _outcome(models=["m2"], optimal=True, objective=-501.0, bound=-501.0))


def test_compare_rejects_new_hard_violations_and_lost_success():
    assert compare_outcome(_outcome(), _outcome(hard_count=1, hard_rules=["rest_11h"]))
    assert compare_outcome(_outcome(), _outcome(success=False, objective=None, bound=None))
