"""„Ilość osób na obłożeniu” placówki (LocationConfig.constraints
["coverage_staff"], okno Lokalizacje obok „Maks. dni pracy pod rząd”,
domyślnie 1): ile osób pilnuje placówki jednocześnie, w tych samych
godzinach. Generator obsadza każdą zmianę tyloma osobami naraz, a wiersz
„Obłożenie” w grafiku (logic/duty_coverage_presenter.py) sprawdza dokładnie
tę liczbę."""

import io
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from logic.auto_generator import AutoScheduleGenerator
from logic.duty_coverage_presenter import is_day_fully_covered
from logic.generator.custom_profile_wiring import default_policies
from logic.generator.duty_rotation_manual_coverage import _assign_layers
from logic.generator.duty_rotation_constraint import NIE_CHCE_24H_ROLE_KEY
from logic.schedule_controller import ScheduleController
from model.business_profile import register_custom_profile
from model.constraint_policy import ConstraintPolicy
from model.custom_profile import CustomBusinessProfile, RoleDefinition
from model.employee import Employee
from model.location import COVERAGE_STAFF_KEY, LocationConfig, coverage_staff_for, coverage_staff_from
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig

# Listopad 2026: 2 = poniedziałek, 7 = sobota.
YEAR, MONTH = 2026, 11
MONDAY, SATURDAY = 2, 7

ROTATION = {
    "weekday_long": {"start": "06:00", "end": "22:00"},
    "weekday_short": {"start": "22:00", "end": "06:00"},
    "weekend_full": {"start": "06:00"},
    "weekend_half_a": {"start": "06:00", "end": "18:00"},
    "weekend_half_b": {"start": "18:00", "end": "06:00"},
}


def _profile():
    profile = CustomBusinessProfile(
        key="test_coverage_staff",
        display_name="Test Coverage Staff",
        # Rola „Nie chce 24h” = profil Ochrony (model godzin otwarcia dla
        # placówek bez rotacji, patrz opening_hours_coverage.py).
        roles=[RoleDefinition(key=NIE_CHCE_24H_ROLE_KEY, label="Nie chce 24h", show_summary_row=False)],
        rules=[],
    )
    register_custom_profile(profile)
    return profile


def _setup(n_employees, staff, rotation=ROTATION, open_hours=None):
    profile = _profile()
    shop = ShopConfig(YEAR, MONTH)
    shop.business_type = profile.key
    loc = LocationConfig(key="site1", name="Site 1")
    if rotation is not None:
        loc.set_duty_rotation(rotation)
    else:
        loc.open_hours = open_hours
    loc.closed_on_public_holidays = False
    loc.constraints[COVERAGE_STAFF_KEY] = staff
    shop.locations = {"site1": loc}
    shop.constraint_policies.update(default_policies(profile))
    shop.constraint_policies["balance"] = ConstraintPolicy.DISABLED
    shop.constraint_policies["monthly_hours"] = ConstraintPolicy.DISABLED

    schedule = MonthSchedule(YEAR, MONTH)
    employees = [Employee(last_name=f"E{i}", first_name="Guard", location_key="site1") for i in range(n_employees)]
    for emp in employees:
        schedule.add_employee(emp)
    return shop, schedule, employees


def _generate(shop, schedule):
    with redirect_stdout(io.StringIO()):
        return AutoScheduleGenerator(schedule, shop).generate(solver_time_limit_seconds=60)


def _shifts(schedule, employees, day):
    return sorted(
        (ds.start, ds.end, ds.is_full_day)
        for emp in employees
        if not (ds := schedule.get_day(emp, day)).is_empty()
    )


# ---------------------------------------------------------------------------
# Ustawienie
# ---------------------------------------------------------------------------

def test_default_is_one_and_old_files_need_no_key():
    loc = LocationConfig(key="a", name="A")
    assert COVERAGE_STAFF_KEY not in loc.constraints
    assert coverage_staff_from(loc.constraints) == 1

    shop = ShopConfig(YEAR, MONTH)
    assert coverage_staff_for(shop, "nie_ma_takiej") == 1
    assert coverage_staff_from({COVERAGE_STAFF_KEY: "x"}) == 1
    assert coverage_staff_from({COVERAGE_STAFF_KEY: 0}) == 1


def test_value_round_trips_through_project_file():
    loc = LocationConfig(key="a", name="A")
    loc.constraints[COVERAGE_STAFF_KEY] = 2
    restored = LocationConfig.from_dict(loc.to_dict())
    assert coverage_staff_from(restored.constraints) == 2


def test_locations_dialog_field_next_to_max_consecutive_days_saves_value():
    from PySide6.QtWidgets import QWidget

    from ui.locations_dialog import LocationsDialog

    shop = ShopConfig(YEAR, MONTH)
    key = next(iter(shop.locations))
    parent = QWidget()
    dialog = LocationsDialog(parent, shop)
    row = dialog._location_rows[0]

    assert row.coverage_staff_spin.value() == 1
    # Ten sam wiersz co „Maks. dni pracy pod rząd”.
    assert row.coverage_staff_spin.parentWidget() is row.max_consecutive_spin.parentWidget()

    row.coverage_staff_spin.setValue(2)
    dialog._save()
    assert shop.locations[key].constraints[COVERAGE_STAFF_KEY] == 2

    reopened = LocationsDialog(parent, shop)
    assert reopened._location_rows[0].coverage_staff_spin.value() == 2


# ---------------------------------------------------------------------------
# Wiersz „Obłożenie” (bez generatora - ręcznie wpisany grafik)
# ---------------------------------------------------------------------------

def _manual_weekday(staff, people):
    shop, schedule, employees = _setup(4, staff)
    for emp in employees[:people]:
        schedule.get_day(emp, MONDAY).set_hours("06:00", "22:00")
    for emp in employees[2:2 + people]:
        schedule.get_day(emp, MONDAY).set_hours("22:00", "06:00")
    return shop, schedule, employees


def test_coverage_row_expects_configured_number_of_people():
    shop, schedule, employees = _manual_weekday(staff=2, people=2)
    assert is_day_fully_covered(schedule, shop, employees, MONDAY)

    # Te same dwie osoby naraz przy obłożeniu 1 - za dużo osób.
    shop.locations["site1"].constraints[COVERAGE_STAFF_KEY] = 1
    assert not is_day_fully_covered(schedule, shop, employees, MONDAY)

    # Obłożenie 2, a na grafiku po jednej osobie - luka.
    shop, schedule, employees = _manual_weekday(staff=2, people=1)
    assert not is_day_fully_covered(schedule, shop, employees, MONDAY)
    shop.locations["site1"].constraints[COVERAGE_STAFF_KEY] = 1
    assert is_day_fully_covered(schedule, shop, employees, MONDAY)


def test_coverage_row_in_grid_shows_ok_for_two_people():
    from types import SimpleNamespace

    from ui.grid_view import ScheduleGrid

    shop, schedule, employees = _manual_weekday(staff=2, people=2)
    grid = ScheduleGrid()
    grid.set_data(
        schedule, shop, ScheduleController(schedule, shop),
        main_window=SimpleNamespace(shop_config=shop), location_filter="site1",
    )
    grid.refresh()

    rows = grid._summary_rows()
    coverage_row = len(employees) + [key for _label, key in rows].index("coverage")
    item = grid.item(coverage_row, MONDAY)
    assert item.text() == "✅"
    assert "2 osoby" in item.toolTip()


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def test_rotation_with_two_people_doubles_every_shift():
    shop, schedule, employees = _setup(8, staff=2)

    result = _generate(shop, schedule)

    assert result["success"], result
    assert _shifts(schedule, employees, MONDAY) == [
        ("06:00", "22:00", False), ("06:00", "22:00", False),
        ("22:00", "06:00", False), ("22:00", "06:00", False),
    ]
    weekend = _shifts(schedule, employees, SATURDAY)
    full = [s for s in weekend if s[2]]
    halves_a = [s for s in weekend if not s[2] and s[0] == "06:00"]
    halves_b = [s for s in weekend if not s[2] and s[0] == "18:00"]
    assert len(full) + len(halves_a) == 2 and len(full) + len(halves_b) == 2
    assert all(is_day_fully_covered(schedule, shop, employees, d) for d in range(1, schedule.days_in_month + 1))


def test_rotation_with_one_person_is_unchanged():
    shop, schedule, employees = _setup(4, staff=1)

    result = _generate(shop, schedule)

    assert result["success"], result
    assert _shifts(schedule, employees, MONDAY) == [("06:00", "22:00", False), ("22:00", "06:00", False)]
    assert all(is_day_fully_covered(schedule, shop, employees, d) for d in range(1, schedule.days_in_month + 1))


def test_manual_entry_takes_one_of_two_places():
    shop, schedule, employees = _setup(8, staff=2)
    ScheduleController(schedule, shop).set_day_hours(employees[0], 3, "07:00", "19:00")

    result = _generate(shop, schedule)

    assert result["success"], result
    ds = schedule.get_day(employees[0], 3)
    assert (ds.start, ds.end, ds.is_locked) == ("07:00", "19:00", True)
    assert all(is_day_fully_covered(schedule, shop, employees, d) for d in range(1, schedule.days_in_month + 1))


def test_assign_layers_puts_each_manual_entry_into_one_place():
    entries = [(60, 120), (90, 150), (200, 260)]
    assert _assign_layers(entries, 1) == [entries]
    assert _assign_layers(entries, 2) == [[(60, 120), (200, 260)], [(90, 150)]]
    # Więcej ręcznych osób naraz niż obłożenie - nadmiar w ostatniej warstwie.
    assert _assign_layers([(0, 10), (0, 10), (0, 10)], 2) == [[(0, 10)], [(0, 10), (0, 10)]]


def test_rest_after_24h_counts_teams_not_people():
    """4 osoby po 2 na dobę = dwa składy: 24h pracy, 24h odpoczynku (przy
    obłożeniu 1 byłoby (4-1) x 24h)."""
    rotation = {
        "only_12_24h": True,
        "prefer_24h": True,
        "weekend_full": {"start": "06:00"},
        "weekend_half_a": {"start": "06:00", "end": "18:00"},
        "weekend_half_b": {"start": "18:00", "end": "06:00"},
    }
    shop, schedule, employees = _setup(4, staff=2, rotation=rotation)

    result = _generate(shop, schedule)

    assert result["success"], result
    days = range(1, schedule.days_in_month + 1)
    assert all(is_day_fully_covered(schedule, shop, employees, d) for d in days)
    # „Preferuj zmiany 24h”: codziennie dwie zmiany 24h - możliwe tylko przy
    # odpoczynku 24h (przy 72h każdy mógłby wziąć 24h najwyżej co 4. dzień).
    assert all([s[2] for s in _shifts(schedule, employees, d)] == [True, True] for d in days)


def test_opening_hours_location_with_two_people():
    open_hours = {wd: ("08:00", "20:00") for wd in range(7)}
    shop, schedule, employees = _setup(6, staff=2, rotation=None, open_hours=open_hours)

    result = _generate(shop, schedule)

    assert result["success"], result
    for day in range(1, schedule.days_in_month + 1):
        assert _shifts(schedule, employees, day) == [("08:00", "20:00", False), ("08:00", "20:00", False)]
        assert is_day_fully_covered(schedule, shop, employees, day)


def test_too_few_people_gives_clear_message():
    shop, schedule, employees = _setup(1, staff=2)

    result = _generate(shop, schedule)

    assert not result["success"]
    assert any("Ilość osób na obłożeniu" in reason for reason in result["infeasibility_reasons"])
