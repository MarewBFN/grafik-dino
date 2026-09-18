"""Etap G planu zmian nocnych: scenariuszowe/stress testy dla profili 24/7
z SHIFT_NIGHT. Nie ufamy tylko solver.Solve() == OPTIMAL/FEASIBLE - dla
każdy wygenerowany grafik niezależnie odtwarzamy rzeczywiste przedziały
czasu (z realną datą, nie samym "HH:MM") i sprawdzamy, że żaden pracownik
nie ma dwóch nakładających się zmian ani odpoczynku krótszego niż 11h -
dokładnie to, co plan nazywa "sprawdzić feasibility i brak nakładających
się zmian".
"""

import io
import itertools
import random
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.auto_generator import AutoScheduleGenerator
from logic.generator.custom_profile_wiring import default_policies
from model.business_profile import register_custom_profile
from model.constraint_policy import ConstraintPolicy
from model.custom_profile import (
    RULE_TYPE_MIN_STAFF_WITH_ROLE,
    CustomBusinessProfile,
    RoleDefinition,
    RuleInstance,
)
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig

YEAR, MONTH = 2026, 8
FMT = "%H:%M"


def _real_interval(schedule, year, month, employee, day):
    """(start_dt, end_dt) rzeczywistego przedziału pracy tego dnia, z prawdziwą
    datą - None jeśli dzień pusty/urlop/L4. Uwzględnia przejście przez
    północ (DaySchedule.crosses_midnight(), Etap A)."""
    ds = schedule.get_day(employee, day)
    if ds.is_empty() or ds.is_leave or getattr(ds, "is_sick", False):
        return None

    start = datetime(year, month, day) + timedelta(
        hours=int(ds.start.split(":")[0]), minutes=int(ds.start.split(":")[1])
    )
    end = datetime(year, month, day) + timedelta(
        hours=int(ds.end.split(":")[0]), minutes=int(ds.end.split(":")[1])
    )
    if ds.crosses_midnight():
        end += timedelta(days=1)
    return start, end


def assert_no_overlaps_and_enough_rest(schedule, min_rest_hours=11):
    """Niezależny audyt: dla każdego pracownika, dla każdej pary kolejnych
    przypisanych dni (niekoniecznie sąsiadujących w kalendarzu - dzień wolny
    pomiędzy nie ma tu znaczenia, sprawdzamy realną chronologię), zmiany nie
    mogą się nakładać i odpoczynek między nimi nie może być krótszy niż
    min_rest_hours."""
    problems = []

    for emp in schedule.employees:
        intervals = []
        for day in range(1, schedule.days_in_month + 1):
            interval = _real_interval(schedule, YEAR, MONTH, emp, day)
            if interval:
                intervals.append((day, *interval))

        intervals.sort(key=lambda t: t[1])

        for (day_a, start_a, end_a), (day_b, start_b, end_b) in zip(intervals, intervals[1:]):
            if start_b < end_a:
                problems.append(
                    f"{emp.display_name()}: dzień {day_a} ({start_a}-{end_a}) nakłada się "
                    f"z dniem {day_b} ({start_b}-{end_b})"
                )
                continue

            rest_hours = (start_b - end_a).total_seconds() / 3600
            if rest_hours < min_rest_hours:
                problems.append(
                    f"{emp.display_name()}: tylko {rest_hours:.2f}h odpoczynku między dniem "
                    f"{day_a} ({start_a}-{end_a}) a dniem {day_b} ({start_b}-{end_b})"
                )

    assert not problems, "\n".join(problems)


def _build_24_7_guard_scenario(guard_count, seed, min_on_night=2, leave_probability=0.05):
    """Profil custom bez OPEN/CLOSE, jedna lokalizacja 24/7 z night_shift
    22:00-06:00, regułą MANDATORY "min. `min_on_night` ochroniarzy w nocy"
    (Etap F) i losowymi urlopami/L4 - żeby solver musiał realnie
    przetasować obsadę, nie tylko przydzielić tych samych ludzi co dzień."""
    random.seed(seed)

    profile_key = f"custom_stress_night_{guard_count}_{seed}"
    rule = RuleInstance(
        type=RULE_TYPE_MIN_STAFF_WITH_ROLE, role_key="guard",
        policy="MANDATORY", params={"min_count": min_on_night, "scope": "night"},
    )
    profile = CustomBusinessProfile(
        key=profile_key,
        display_name="Test Stress Ochrona",
        roles=[RoleDefinition(key="guard", label="Ochroniarz")],
        rules=[rule],
    )
    register_custom_profile(profile)
    rule_key = profile.rule_policy_key(rule)

    shop = ShopConfig(YEAR, MONTH)
    shop.business_type = profile.key
    shop.constraint_policies.update(default_policies(profile))
    shop.constraint_policies[rule_key] = ConstraintPolicy.MANDATORY
    shop.constraints["solver_time_limit_seconds"] = 20

    loc = LocationConfig(key="site1", name="Obiekt")
    shop.locations = {"site1": loc}

    schedule = MonthSchedule(YEAR, MONTH)
    employees = [
        Employee(last_name=f"Guard{i}", first_name="A", location_key="site1", custom_roles={"guard": True})
        for i in range(guard_count)
    ]
    for emp in employees:
        schedule.add_employee(emp)

    for emp in employees:
        for day in range(1, schedule.days_in_month + 1):
            if random.random() < leave_probability:
                schedule.get_day(emp, day).set_leave()

    return schedule, shop


def test_night_coverage_scenarios_are_feasible_and_conflict_free():
    """Macierz (liczba ochroniarzy x ziarno losowości), zawsze z co najmniej
    jednym ochroniarzem zapasowym ponad wymagane minimum, żeby urlopy nie
    robiły scenariusza strukturalnie niewykonalnym - to nie jest test na
    wykrywanie infeasibility (ten jest w test_night_shift_coverage_rule.py),
    tylko audyt poprawności realnie wygenerowanych grafików."""
    # Enough slack above min_on_night that a couple of simultaneous
    # leave/sick days can't make a single day structurally impossible
    # (with only min_on_night+1 guards, any 2 of them on leave the same day
    # already is) - this test audits correctness of feasible schedules, not
    # infeasibility detection under adversarial leave collisions (that's
    # test_night_shift_coverage_rule.py).
    min_on_night = 2
    failures = []

    for guard_count, seed in itertools.product((min_on_night + 2, min_on_night + 3), range(2)):
        schedule, shop = _build_24_7_guard_scenario(guard_count, seed, min_on_night=min_on_night, leave_probability=0.03)

        with redirect_stdout(io.StringIO()):
            result = AutoScheduleGenerator(schedule, shop).generate(
                solver_time_limit_seconds=10, solver_workers=1
            )

        if not result["success"]:
            failures.append(f"guard_count={guard_count} seed={seed}: {result['infeasibility_reasons']}")
            continue

        try:
            assert_no_overlaps_and_enough_rest(schedule)
        except AssertionError as exc:
            failures.append(f"guard_count={guard_count} seed={seed}: {exc}")

    assert not failures, "\n\n".join(failures)


def test_night_coverage_scenario_actually_uses_night_shifts():
    """Nie wystarczy, że grafik jest 'feasible' - reguła MANDATORY musi
    faktycznie wymusić realne przypisania SHIFT_NIGHT, inaczej test
    powyżej niczego by nie sprawdzał (pusty grafik też jest 'bez konfliktów')."""
    schedule, shop = _build_24_7_guard_scenario(guard_count=3, seed=0, min_on_night=2, leave_probability=0.0)

    with redirect_stdout(io.StringIO()):
        result = AutoScheduleGenerator(schedule, shop).generate(solver_time_limit_seconds=10, solver_workers=1)
    assert result["success"], result["infeasibility_reasons"]

    night_assignments = sum(
        1
        for emp in schedule.employees
        for day in range(1, schedule.days_in_month + 1)
        if schedule.get_day(emp, day).crosses_midnight()
    )
    assert night_assignments >= 2 * schedule.days_in_month, (
        "expected at least min_on_night night assignments every day of the month"
    )


if __name__ == "__main__":
    test_night_coverage_scenarios_are_feasible_and_conflict_free()
    test_night_coverage_scenario_actually_uses_night_shifts()
    print("OK")
