"""Etap F "plan profil ochrona (analiza specyfikacji klienta).md", sekcja
12: test scenariuszowy pełnego miesiąca (nie tylko wycinków/tygodni jak
tests/test_duty_rotation_constraint.py i tests/test_duty_rotation_rest_constraint.py) -
generuje raz, potem WERYFIKUJE WYNIK NIEZALEŻNIE od kodu constraintów
(licząc rzeczywiste godziny wprost z zapisanego DaySchedule), żeby
sprawdzić samą poprawność generatora, nie tylko że jego własne
constrainty się sobie nie zaprzeczają."""

import io
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
from model.custom_profile import CustomBusinessProfile, RoleDefinition
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig

FMT = "%H:%M"
MIN_REST = timedelta(hours=11)

ROTATION = {
    "weekday_long": {"start": "06:00", "end": "22:00"},
    "weekday_short": {"start": "22:00", "end": "06:00"},
    "weekend_full": {"start": "06:00"},
    "weekend_half_a": {"start": "06:00", "end": "18:00"},
    "weekend_half_b": {"start": "18:00", "end": "06:00"},
}

ROTATION_ONLY_12_24H = {
    "only_12_24h": True,
    "weekend_full": {"start": "06:00"},
    "weekend_half_a": {"start": "06:00", "end": "18:00"},
    "weekend_half_b": {"start": "18:00", "end": "06:00"},
}


def _anchor(day: int, time_str: str) -> datetime:
    t = datetime.strptime(time_str, FMT)
    return datetime(2000, 1, 1, t.hour, t.minute) + timedelta(days=day)


def _shift_end_dt(day: int, ds) -> datetime:
    start_dt = _anchor(day, ds.start)
    if ds.is_full_day:
        return start_dt + timedelta(hours=24)
    end_dt = _anchor(day, ds.end)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    return end_dt


def _build_month(year: int, month: int, n_employees: int, no24h_count: int, rotation=ROTATION):
    profile = CustomBusinessProfile(
        key=f"custom_test_scenario_{year}_{month}_{id(rotation)}",
        display_name="Test Ochrona Scenario",
        roles=[RoleDefinition(key="nie_chce_24h", label="Nie chce 24h", show_summary_row=False)],
        rules=[],
    )
    register_custom_profile(profile)

    shop = ShopConfig(year, month)
    shop.business_type = profile.key
    loc = LocationConfig(key="site1", name="Site 1")
    loc.set_duty_rotation(rotation)
    # Ten test sprawdza WYŁĄCZNIE pokrycie/rotację, nie automatyczne
    # zamknięcie w święta (patrz LocationConfig.closed_on_public_holidays,
    # domyślnie True) - wyłączone, żeby realne polskie święto wypadające w
    # danym miesiącu/roku testu nie fałszowało oczekiwanego "pokrycie
    # KAŻDEGO dnia".
    loc.closed_on_public_holidays = False
    shop.locations["site1"] = loc
    shop.constraint_policies.update(default_policies(profile))
    shop.constraint_policies["balance"] = ConstraintPolicy.DISABLED
    shop.constraint_policies["monthly_hours"] = ConstraintPolicy.DISABLED

    schedule = MonthSchedule(year, month)
    employees = []
    for i in range(n_employees):
        no24h = i < no24h_count
        emp = Employee(
            last_name=f"E{i}", first_name="Guard", location_key="site1",
            custom_roles={"nie_chce_24h": True} if no24h else {},
        )
        employees.append(emp)
        schedule.add_employee(emp)

    return shop, schedule, employees


def _rotation_capable_count(employees) -> int:
    return sum(1 for e in employees if not e.custom_roles.get("nie_chce_24h", False))


def _verify_full_month(shop, schedule, employees):

    days = schedule.days_in_month
    rotation_capable = _rotation_capable_count(employees)
    required_full_day_rest = timedelta(hours=24 * max(rotation_capable - 1, 1))
    only_12_24h = bool(shop.locations["site1"].get_duty_rotation().get("only_12_24h"))

    assignments_by_day: dict[int, list[tuple[Employee, object]]] = {}

    for day in range(1, days + 1):
        wd = shop.weekday(day)
        assigned = [
            (emp, schedule.get_day(emp, day))
            for emp in employees
            if not schedule.get_day(emp, day).is_empty()
        ]
        assignments_by_day[day] = assigned

        if wd < 5 and not only_12_24h:
            assert len(assigned) == 2, f"day {day} (weekday): expected 2 people on duty, got {len(assigned)}"
            starts_ends = sorted((ds.start, ds.end) for _, ds in assigned)
            assert starts_ends == [("06:00", "22:00"), ("22:00", "06:00")], (
                f"day {day}: unexpected weekday shift times {starts_ends}"
            )
            assert not any(ds.is_full_day for _, ds in assigned)
        else:
            full_day = [(emp, ds) for emp, ds in assigned if ds.is_full_day]
            halves = [(emp, ds) for emp, ds in assigned if not ds.is_full_day]

            if full_day:
                assert len(full_day) == 1 and not halves, (
                    f"day {day} (weekend): full-day variant must be exactly 1 person, no halves - got {assigned}"
                )
                emp, ds = full_day[0]
                assert not emp.custom_roles.get("nie_chce_24h", False), (
                    f"day {day}: employee with nie_chce_24h got a 24h shift"
                )
            else:
                assert len(halves) == 2, (
                    f"day {day} (weekend): halves variant must be exactly 2 people - got {assigned}"
                )
                starts_ends = sorted((ds.start, ds.end) for _, ds in halves)
                assert starts_ends == [("06:00", "18:00"), ("18:00", "06:00")], (
                    f"day {day}: unexpected weekend half shift times {starts_ends}"
                )

    # Niezależna weryfikacja odpoczynku: dla KAŻDEGO pracownika i KAŻDEJ
    # pary jego kolejnych przydzielonych dni, licząc wprost z zapisanych
    # godzin (nie przez ponowne wywołanie kodu constraintu).
    for emp in employees:
        assigned_days = [d for d in range(1, days + 1) if not schedule.get_day(emp, d).is_empty()]

        for idx in range(len(assigned_days) - 1):
            d1 = assigned_days[idx]
            ds1 = schedule.get_day(emp, d1)
            end1 = _shift_end_dt(0, ds1)

            for d2 in assigned_days[idx + 1:]:
                ds2 = schedule.get_day(emp, d2)
                start2 = _anchor(d2 - d1, ds2.start)

                required = required_full_day_rest if ds1.is_full_day else MIN_REST
                gap = start2 - end1

                assert gap >= required, (
                    f"{emp.display_name()}: rest between day {d1} ({ds1.start}-{ds1.end}, "
                    f"full_day={ds1.is_full_day}) and day {d2} ({ds2.start}-{ds2.end}) is "
                    f"{gap}, required {required}"
                )

                if gap >= required_full_day_rest:
                    # Odstęp już wystarczający na najsurowszy możliwy
                    # wymóg (24h) - każdy kolejny, jeszcze późniejszy dzień
                    # tym bardziej, nie ma sensu iterować dalej.
                    break


def _generate_and_verify(year, month, n_employees, no24h_count, rotation=ROTATION):
    shop, schedule, employees = _build_month(year, month, n_employees, no24h_count, rotation=rotation)

    with redirect_stdout(io.StringIO()):
        result = AutoScheduleGenerator(schedule, shop).generate(solver_time_limit_seconds=60)

    assert result["success"] is True, result.get("infeasibility_reasons")
    _verify_full_month(shop, schedule, employees)


def test_full_month_four_employees_one_no24h():
    """Odpowiada mniej więcej realnej załodze demo (Etap D)."""
    _generate_and_verify(2026, 11, n_employees=4, no24h_count=1)


def test_full_month_three_employees_all_rotation_capable():
    """N=3 -> (N-1)x24h = 48h odpoczynku po każdej zmianie 24h, przez
    KAŻDY weekend całego miesiąca - najbardziej wymagający test dla
    wielodniowego "lookahead" z Etapu C (48h przekracza jedną dobę)."""
    _generate_and_verify(2026, 11, n_employees=3, no24h_count=0)


def test_full_month_five_employees_two_no24h():
    """Większa, luźniejsza załoga z dwiema osobami niechętnymi 24h -
    sprawdza że reszta i tak swobodnie rotuje na zmianie 24h (N=3)."""
    _generate_and_verify(2026, 11, n_employees=5, no24h_count=2)


def test_full_month_only_12_24h_three_employees():
    """Toggle "Używaj tylko zmian 12/24h": KAŻDY dzień miesiąca (nie tylko
    weekend) używa wariantu 24h-albo-12h+12h, nigdy weekday_long/short. N=3
    -> 48h odpoczynku po zmianie 24h, teraz przez cały miesiąc, nie tylko
    weekendy - najbardziej wymagający wariant tego trybu."""
    _generate_and_verify(2026, 11, n_employees=3, no24h_count=0, rotation=ROTATION_ONLY_12_24H)


def test_full_month_only_12_24h_four_employees_one_no24h():
    _generate_and_verify(2026, 11, n_employees=4, no24h_count=1, rotation=ROTATION_ONLY_12_24H)
