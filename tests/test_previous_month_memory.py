"""'Pamięć poprzedniego miesiąca' (PreviousMonthShiftEnd, patrz
model/month_schedule.py) - przejęcie końca ostatniej zmiany każdego
pracownika przy zmianie miesiąca w tym samym projekcie
(ui/main_window.py::_switch_to_month), jego wpływ na 11h rest na
początku dnia 1 (zwykły tryb i rotacja 24/7), pojawianie/znikanie kolumny
w ScheduleGrid i round-trip zapisu/wczytania projektu."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

from ortools.sat.python import cp_model
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_app = QApplication.instance() or QApplication([])

from logic.generator.duty_rotation_rest_constraint import add_duty_rotation_rest_constraint
from logic.generator.rest_constraint import add_rest_11h_constraint, add_rest_11h_constraint_simplified
from logic.utils.time_utils import is_next_calendar_month
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule, PreviousMonthShiftEnd
from model.monthly_project import MonthlyProject
from model.shop_config import ShopConfig
from persistence.project_io import load_project, save_project
from ui.grid_view import ScheduleGrid
from ui.main_window import MainWindow


# ---------------------------------------------------------------------------
# 1. Przejęcie danych przy zmianie miesiąca
# ---------------------------------------------------------------------------

class IsNextCalendarMonthTests(unittest.TestCase):
    def test_true_for_consecutive_months(self):
        self.assertTrue(is_next_calendar_month(2026, 1, 2026, 2))

    def test_true_across_year_boundary(self):
        self.assertTrue(is_next_calendar_month(2025, 12, 2026, 1))

    def test_false_for_a_skipped_month(self):
        self.assertFalse(is_next_calendar_month(2026, 1, 2026, 3))

    def test_false_going_backwards(self):
        self.assertFalse(is_next_calendar_month(2026, 2, 2026, 1))

    def test_false_for_same_month(self):
        self.assertFalse(is_next_calendar_month(2026, 1, 2026, 1))


class CarryOverPreviousMonthEndShiftsTests(unittest.TestCase):
    """Konstruuje MainWindow przez __new__ (patrz
    tests/test_night_shift_manual_editing.py) - pomija ciężki __init__
    (menu/paski narzędzi/wczytywanie ostatniego projektu)."""

    def _make_window(self):
        window = MainWindow.__new__(MainWindow)
        return window

    def test_carries_over_end_and_crosses_midnight_flag_per_employee(self):
        emp1 = Employee(last_name="Kowalski", first_name="Jan")
        emp2 = Employee(last_name="Nowak", first_name="Anna")
        old_schedule = MonthSchedule(2026, 1, employees=[emp1, emp2])
        old_schedule.set_day_hours(emp1, 31, "14:00", "22:00")
        old_schedule.set_day_hours(emp2, 31, "22:00", "06:00")  # crosses midnight

        window = self._make_window()
        window.schedule = MonthSchedule(2026, 2, employees=[emp1, emp2])

        window._carry_over_previous_month_end_shifts(old_schedule)

        carry1 = window.schedule.get_previous_month_end_shift(emp1)
        carry2 = window.schedule.get_previous_month_end_shift(emp2)
        self.assertEqual(carry1, PreviousMonthShiftEnd("22:00", False))
        self.assertEqual(carry2, PreviousMonthShiftEnd("06:00", True))

    def test_skips_employees_with_an_empty_last_day(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        old_schedule = MonthSchedule(2026, 1, employees=[emp])
        # Dzień 31 pozostaje pusty (wolne) - nic do przejęcia.

        window = self._make_window()
        window.schedule = MonthSchedule(2026, 2, employees=[emp])

        window._carry_over_previous_month_end_shifts(old_schedule)

        self.assertIsNone(window.schedule.get_previous_month_end_shift(emp))

    def test_switch_to_month_carries_over_only_for_the_immediately_next_month(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        old_schedule = MonthSchedule(2026, 1, employees=[emp])
        old_schedule.set_day_hours(emp, 31, "14:00", "22:00")

        shop = ShopConfig(2026, 1)

        window = self._make_window()
        window.year, window.month = 2026, 1
        window.schedule = old_schedule
        window.shop_config = shop
        window.project = MonthlyProject()
        window.project.put(2026, 1, old_schedule, shop)
        window.date_display_label = MagicMock()
        window.statusBar = MagicMock(return_value=MagicMock())
        window._update_nominal_hours_label = MagicMock()
        window._sync_everything = MagicMock()

        # Mechanizm jest teraz domyślnie odblokowany (patrz
        # PreviousMonthMemoryEnabledByDefaultTests), ale wymuszamy True jawnie
        # tutaj też - ta klasa testuje samo zachowanie przejęcia, niezależnie
        # od aktualnej wartości flagi w main_window.py. Zmiana miesiąca nie
        # jest już destrukcyjna (pamięć wielu miesięcy).
        with patch("ui.main_window.PREVIOUS_MONTH_MEMORY_ENABLED", True):
            window._switch_to_month(2026, 2)  # skok o jeden miesiąc

        carry = window.schedule.get_previous_month_end_shift(emp)
        self.assertEqual(carry, PreviousMonthShiftEnd("22:00", False))

    def test_switch_to_month_does_not_carry_over_when_skipping_a_month(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        old_schedule = MonthSchedule(2026, 1, employees=[emp])
        old_schedule.set_day_hours(emp, 31, "14:00", "22:00")

        shop = ShopConfig(2026, 1)

        window = self._make_window()
        window.year, window.month = 2026, 1
        window.schedule = old_schedule
        window.shop_config = shop
        window.project = MonthlyProject()
        window.project.put(2026, 1, old_schedule, shop)
        window.date_display_label = MagicMock()
        window.statusBar = MagicMock(return_value=MagicMock())
        window._update_nominal_hours_label = MagicMock()
        window._sync_everything = MagicMock()

        # Skok o DWA miesiące - luty (miesiąc bezpośrednio poprzedzający
        # marzec) nigdy nie istniał w projekcie.
        window._switch_to_month(2026, 3)

        self.assertIsNone(window.schedule.get_previous_month_end_shift(emp))


# ---------------------------------------------------------------------------
# 2. Rest-constraint na granicy z poprzednim miesiącem
# ---------------------------------------------------------------------------

def _shop_with_default_hours():
    shop = ShopConfig(2026, 2)  # February 2026: day 1 = Sunday
    loc = LocationConfig(key="site1", name="Site 1")
    loc.trade_sundays.add(1)  # dzień 1 musi być dniem handlowym, żeby w ogóle miał godziny
    shop.locations["site1"] = loc
    return shop


class RegularModeCrossMonthRestTests(unittest.TestCase):
    """add_rest_11h_constraint: dzień 1 lutego 2026 - domyślne godziny
    otwarcia (05:30-22:45), efektywne 8h/dzień => OPEN 05:30-13:30."""

    SHIFT_OPEN, SHIFT_CLOSE = 0, 1

    def _model(self, employees, days=(1,)):
        model = cp_model.CpModel()
        x = {
            (e, d, s): model.NewBoolVar(f"x_{e}_{d}_{s}")
            for e in range(len(employees)) for d in days for s in (self.SHIFT_OPEN, self.SHIFT_CLOSE)
        }
        return model, x

    def test_late_previous_month_end_blocks_opening_shift_on_day1(self):
        shop = _shop_with_default_hours()
        emp = Employee(last_name="Kowalski", first_name="Jan", location_key="site1")
        schedule = MonthSchedule(2026, 2, employees=[emp])
        # Kończy 21:00 dzień przed dniem 1 - tylko 8.5h do 05:30 startu OPEN.
        schedule.set_previous_month_end_shift(emp, "21:00", False)

        model, x = self._model([emp])
        add_rest_11h_constraint(
            model, x, [emp], [1], [1], shop,
            self.SHIFT_OPEN, self.SHIFT_CLOSE, {}, {}, schedule=schedule, soft=False,
        )
        model.Add(x[0, 1, self.SHIFT_OPEN] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertEqual(status, cp_model.INFEASIBLE)

    def test_previous_month_end_far_enough_allows_opening_shift_on_day1(self):
        shop = _shop_with_default_hours()
        emp = Employee(last_name="Kowalski", first_name="Jan", location_key="site1")
        schedule = MonthSchedule(2026, 2, employees=[emp])
        # Kończy 18:00 dzień przed dniem 1 - 11.5h do 05:30 startu OPEN.
        schedule.set_previous_month_end_shift(emp, "18:00", False)

        model, x = self._model([emp])
        add_rest_11h_constraint(
            model, x, [emp], [1], [1], shop,
            self.SHIFT_OPEN, self.SHIFT_CLOSE, {}, {}, schedule=schedule, soft=False,
        )
        model.Add(x[0, 1, self.SHIFT_OPEN] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))

    def test_shift_crossing_into_day1_blocks_same_employee_starting_right_after(self):
        shop = _shop_with_default_hours()
        emp = Employee(last_name="Kowalski", first_name="Jan", location_key="site1")
        schedule = MonthSchedule(2026, 2, employees=[emp])
        # Zmiana z poprzedniego miesiąca kończy się o 06:00 JUŻ w dniu 1 -
        # zaraz po (05:30) starcie OPEN, więc niemożliwe/zbyt blisko.
        schedule.set_previous_month_end_shift(emp, "06:00", True)

        model, x = self._model([emp])
        add_rest_11h_constraint(
            model, x, [emp], [1], [1], shop,
            self.SHIFT_OPEN, self.SHIFT_CLOSE, {}, {}, schedule=schedule, soft=False,
        )
        model.Add(x[0, 1, self.SHIFT_OPEN] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertEqual(status, cp_model.INFEASIBLE)

    def test_no_carryover_data_leaves_day1_unrestricted(self):
        shop = _shop_with_default_hours()
        emp = Employee(last_name="Kowalski", first_name="Jan", location_key="site1")
        schedule = MonthSchedule(2026, 2, employees=[emp])  # brak wpisu

        model, x = self._model([emp])
        add_rest_11h_constraint(
            model, x, [emp], [1], [1], shop,
            self.SHIFT_OPEN, self.SHIFT_CLOSE, {}, {}, schedule=schedule, soft=False,
        )
        model.Add(x[0, 1, self.SHIFT_OPEN] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))


class SimplifiedModeCrossMonthRestTests(unittest.TestCase):
    SHIFT_OPEN, SHIFT_CLOSE = 0, 1

    def test_late_previous_month_end_blocks_opening_shift_on_day1(self):
        shop = _shop_with_default_hours()
        emp = Employee(last_name="Kowalski", first_name="Jan", location_key="site1")
        schedule = MonthSchedule(2026, 2, employees=[emp])
        schedule.set_previous_month_end_shift(emp, "21:00", False)

        model = cp_model.CpModel()
        x = {(0, 1, s): model.NewBoolVar(f"x_{s}") for s in (self.SHIFT_OPEN, self.SHIFT_CLOSE)}

        add_rest_11h_constraint_simplified(
            model, x, [emp], [1], [1],
            self.SHIFT_OPEN, self.SHIFT_CLOSE, {}, {},
            shop=shop, schedule=schedule, soft=False,
        )
        model.Add(x[0, 1, self.SHIFT_OPEN] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertEqual(status, cp_model.INFEASIBLE)

    def test_without_shop_the_cross_month_boundary_is_simply_skipped(self):
        """Kompatybilność wsteczna - wywołania bez shop/schedule (stare
        wywołania, patrz tests/test_rest_11h_simplified.py) nadal działają,
        po prostu bez granicy z poprzednim miesiącem."""
        model = cp_model.CpModel()
        x = {(0, 1, s): model.NewBoolVar(f"x_{s}") for s in (self.SHIFT_OPEN, self.SHIFT_CLOSE)}

        add_rest_11h_constraint_simplified(
            model, x, [object()], [1], [1],
            self.SHIFT_OPEN, self.SHIFT_CLOSE, {}, {},
        )
        model.Add(x[0, 1, self.SHIFT_OPEN] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))


class DutyRotationCrossMonthRestTests(unittest.TestCase):
    """August 2026: day 1 = Saturday (weekend rotation keys)."""

    WEEKDAY_LONG, WEEKDAY_SHORT, WEEKEND_FULL, WEEKEND_HALF_A, WEEKEND_HALF_B = 15, 16, 17, 18, 19
    ALL_SHIFTS = (WEEKDAY_LONG, WEEKDAY_SHORT, WEEKEND_FULL, WEEKEND_HALF_A, WEEKEND_HALF_B)
    DUTY_SHIFTS = {
        "weekday_long": WEEKDAY_LONG,
        "weekday_short": WEEKDAY_SHORT,
        "weekend_full": WEEKEND_FULL,
        "weekend_half_a": WEEKEND_HALF_A,
        "weekend_half_b": WEEKEND_HALF_B,
    }
    ROTATION = {
        "weekday_long": {"start": "06:00", "end": "22:00"},
        "weekday_short": {"start": "22:00", "end": "06:00"},
        "weekend_full": {"start": "06:00"},
        "weekend_half_a": {"start": "06:00", "end": "18:00"},
        "weekend_half_b": {"start": "18:00", "end": "06:00"},
    }
    SAT = 1

    def _shop(self):
        shop = ShopConfig(2026, 8)
        loc = LocationConfig(key="site1", name="Site 1")
        loc.set_duty_rotation(self.ROTATION)
        shop.locations["site1"] = loc
        return shop

    def _model(self, n, days):
        model = cp_model.CpModel()
        x = {
            (e, d, s): model.NewBoolVar(f"x_{e}_{d}_{s}")
            for e in range(n) for d in days for s in self.ALL_SHIFTS
        }
        return model, x

    def test_carryover_ending_at_day1_start_blocks_same_employee_weekend_full(self):
        shop = self._shop()
        emp = Employee(last_name="Guard", first_name="One", location_key="site1")
        schedule = MonthSchedule(2026, 8, employees=[emp])
        # Zmiana z poprzedniego miesiąca kończy się dokładnie o starcie
        # weekend_full/weekend_half_a dnia 1 (06:00), już W dniu 1.
        schedule.set_previous_month_end_shift(emp, "06:00", True)

        model, x = self._model(1, [self.SAT])
        add_duty_rotation_rest_constraint(
            model, x, [emp], [self.SAT], shop, self.DUTY_SHIFTS, schedule=schedule, soft=False,
        )
        model.Add(x[0, self.SAT, self.WEEKEND_FULL] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertEqual(status, cp_model.INFEASIBLE)

    def test_carryover_with_enough_rest_allows_weekend_full_on_day1(self):
        shop = self._shop()
        emp = Employee(last_name="Guard", first_name="One", location_key="site1")
        schedule = MonthSchedule(2026, 8, employees=[emp])
        # Kończy 19:00 dzień przed dniem 1 - 11h dokładnie do startu 06:00.
        schedule.set_previous_month_end_shift(emp, "19:00", False)

        model, x = self._model(1, [self.SAT])
        add_duty_rotation_rest_constraint(
            model, x, [emp], [self.SAT], shop, self.DUTY_SHIFTS, schedule=schedule, soft=False,
        )
        model.Add(x[0, self.SAT, self.WEEKEND_FULL] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))

    def test_no_carryover_data_leaves_day1_unrestricted(self):
        shop = self._shop()
        emp = Employee(last_name="Guard", first_name="One", location_key="site1")
        schedule = MonthSchedule(2026, 8, employees=[emp])  # brak wpisu

        model, x = self._model(1, [self.SAT])
        add_duty_rotation_rest_constraint(
            model, x, [emp], [self.SAT], shop, self.DUTY_SHIFTS, schedule=schedule, soft=False,
        )
        model.Add(x[0, self.SAT, self.WEEKEND_FULL] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))


# ---------------------------------------------------------------------------
# 3. Kolumna w ScheduleGrid
# ---------------------------------------------------------------------------

class GridPreviousMonthColumnTests(unittest.TestCase):
    def _grid(self, schedule, shop):
        grid = ScheduleGrid()
        grid.set_data(schedule, shop, controller=None)
        grid.refresh()
        return grid

    def test_column_appears_when_at_least_one_employee_has_data(self):
        shop = ShopConfig(2026, 2)
        emp1 = Employee(last_name="Kowalski", first_name="Jan")
        emp2 = Employee(last_name="Nowak", first_name="Anna")
        schedule = MonthSchedule(2026, 2, employees=[emp1, emp2])
        schedule.set_previous_month_end_shift(emp1, "22:00", False)

        # Mechanizm jest teraz domyślnie odblokowany (patrz
        # PreviousMonthMemoryEnabledByDefaultTests), ale wymuszamy True jawnie
        # tutaj też - ta klasa testuje samo zachowanie kolumny, niezależnie od
        # aktualnej wartości flagi w ui/grid_view.py.
        with patch("ui.grid_view.PREVIOUS_MONTH_MEMORY_ENABLED", True):
            grid = self._grid(schedule, shop)

        self.assertEqual(grid._prev_col_offset, 1)
        header = grid.horizontalHeaderItem(1)
        self.assertIn("31", header.text())  # ostatni dzień stycznia 2026
        self.assertEqual(grid.item(0, 1).text(), "22:00")
        self.assertEqual(grid.item(1, 1).text(), "")

    def test_column_header_shows_the_weekday_using_grid_view_naming(self):
        """31 stycznia 2026 to sobota - nagłówek ma pokazywać dzień
        tygodnia tym samym skrótem co reszta siatki ("So", nie "Poprz.",
        patrz ui/grid_view.py::build() weekday_names), w tym samym
        dwuliniowym formacie "SKRÓT\\ndzień" co kolumny dni tego miesiąca."""
        shop = ShopConfig(2026, 2)
        emp = Employee(last_name="Kowalski", first_name="Jan")
        schedule = MonthSchedule(2026, 2, employees=[emp])
        schedule.set_previous_month_end_shift(emp, "22:00", False)

        with patch("ui.grid_view.PREVIOUS_MONTH_MEMORY_ENABLED", True):
            grid = self._grid(schedule, shop)

        header = grid.horizontalHeaderItem(1)
        self.assertEqual(header.text(), "So\n31")

    def test_column_absent_when_nobody_has_data(self):
        shop = ShopConfig(2026, 2)
        emp = Employee(last_name="Kowalski", first_name="Jan")
        schedule = MonthSchedule(2026, 2, employees=[emp])

        grid = self._grid(schedule, shop)

        self.assertEqual(grid._prev_col_offset, 0)
        # Kolumna 1 to teraz od razu dzień 1 (nagłówek dnia, nie "Poprz.").
        header = grid.horizontalHeaderItem(1)
        self.assertNotIn("Poprz.", header.text())

    def test_day1_column_shifts_by_one_when_info_column_present(self):
        shop = ShopConfig(2026, 2)  # February 2026: day 1 = Sunday
        shop.trade_sundays.add(1)
        emp = Employee(last_name="Kowalski", first_name="Jan")
        schedule = MonthSchedule(2026, 2, employees=[emp])
        schedule.set_previous_month_end_shift(emp, "22:00", False)
        schedule.set_day_hours(emp, 1, "08:00", "16:00")

        with patch("ui.grid_view.PREVIOUS_MONTH_MEMORY_ENABLED", True):
            grid = self._grid(schedule, shop)

        # Dzień 1 wylądował w kolumnie 2 (0=nazwisko, 1=info, 2=dzień 1).
        self.assertEqual(grid._column_to_day(2), 1)
        cell = grid.item(0, 2)
        self.assertIn("08:00", cell.text())


# ---------------------------------------------------------------------------
# 4. Round-trip zapisu/wczytania projektu
# ---------------------------------------------------------------------------

class PersistenceRoundTripTests(unittest.TestCase):
    def test_previous_month_end_shift_survives_save_and_load(self, tmp_path=None):
        import tempfile

        emp1 = Employee(last_name="Kowalski", first_name="Jan")
        emp2 = Employee(last_name="Nowak", first_name="Anna")
        schedule = MonthSchedule(2026, 2, employees=[emp1, emp2])
        schedule.set_previous_month_end_shift(emp1, "22:00", False)
        schedule.set_previous_month_end_shift(emp2, "06:00", True)
        shop = ShopConfig(2026, 2)

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "project.json")
            save_project(path, schedule, shop)
            loaded_schedule, _ = load_project(path)

        loaded_emp1 = next(e for e in loaded_schedule.employees if e.first_name == "Jan")
        loaded_emp2 = next(e for e in loaded_schedule.employees if e.first_name == "Anna")

        self.assertEqual(
            loaded_schedule.get_previous_month_end_shift(loaded_emp1),
            PreviousMonthShiftEnd("22:00", False),
        )
        self.assertEqual(
            loaded_schedule.get_previous_month_end_shift(loaded_emp2),
            PreviousMonthShiftEnd("06:00", True),
        )

    def test_employee_without_previous_month_data_round_trips_to_none(self):
        import tempfile

        emp = Employee(last_name="Kowalski", first_name="Jan")
        schedule = MonthSchedule(2026, 2, employees=[emp])
        shop = ShopConfig(2026, 2)

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "project.json")
            save_project(path, schedule, shop)
            loaded_schedule, _ = load_project(path)

        loaded_emp = loaded_schedule.employees[0]
        self.assertIsNone(loaded_schedule.get_previous_month_end_shift(loaded_emp))


# ---------------------------------------------------------------------------
# 8. Bug: pamięć poprzedniego miesiąca robiła generowanie niewykonalnym bez
#    wyjaśnienia, gdy WSZYSCY pracownicy dostali tę samą (np. domyślną z
#    ui/previous_month_shift_dialog.py) godzinę końca zbyt blisko otwarcia
#    dnia 1 - zgłoszone przez użytkownika jako "wywala infeasible nawet na
#    pustym grafiku". Odtworzone: domyślny profil dino_retail (min_open_staff
#    MANDATORY) + wszyscy pracownicy "22:00" (DEFAULT_END_TIME w dialogu),
#    crosses_midnight=False - 22:00 dnia przed do domyślnego otwarcia
#    (05:30) to tylko 7.5h, mniej niż wymagane 11h, więc NIKT nie mógł objąć
#    otwarcia. Naprawa: logic/generator/diagnostics.py teraz to rozpoznaje i
#    tłumaczy wprost, zamiast generycznego "za mało osób możliwych".
# ---------------------------------------------------------------------------

class PreviousMonthBlocksDay1DiagnosticsTests(unittest.TestCase):
    def test_uniform_late_carryover_is_explained_not_silently_infeasible(self):
        from logic.generator.diagnostics import build_infeasibility_summary

        shop = ShopConfig(2026, 8)  # default profile: min_open_staff=3, MANDATORY "open"
        emps = [
            Employee(last_name=f"E{i}", first_name="X", is_opener=(i == 0), is_meat=(i == 1))
            for i in range(5)
        ]
        schedule = MonthSchedule(2026, 8, employees=emps)
        for e in emps:
            schedule.set_previous_month_end_shift(e, "22:00", False)

        messages = build_infeasibility_summary(schedule, shop)

        self.assertTrue(
            any("pamięć poprzedniego miesiąca" in m for m in messages),
            messages,
        )

    def test_generation_reports_the_specific_reason_end_to_end(self):
        shop = ShopConfig(2026, 8)
        emps = [
            Employee(last_name=f"E{i}", first_name="X", is_opener=(i == 0), is_meat=(i == 1))
            for i in range(5)
        ]
        schedule = MonthSchedule(2026, 8, employees=emps)
        for e in emps:
            schedule.set_previous_month_end_shift(e, "22:00", False)

        from logic.schedule_controller import ScheduleController
        controller = ScheduleController(schedule, shop)
        result = controller.generate_schedule(force=True)

        self.assertFalse(result["success"])
        self.assertTrue(
            any("pamięć poprzedniego miesiąca" in reason for reason in result["infeasibility_reasons"]),
            result["infeasibility_reasons"],
        )

    def test_enough_rest_before_open_is_not_flagged(self):
        from logic.generator.diagnostics import build_infeasibility_summary

        shop = ShopConfig(2026, 8)
        emp = Employee(last_name="Kowalski", first_name="Jan", is_opener=True, is_meat=True)
        schedule = MonthSchedule(2026, 8, employees=[emp])
        # Default open hour is 05:30 - ending well before midnight leaves > 11h.
        schedule.set_previous_month_end_shift(emp, "14:00", False)

        messages = build_infeasibility_summary(schedule, shop)

        self.assertFalse(any("pamięć poprzedniego miesiąca" in m for m in messages))

    def test_no_carryover_data_is_not_flagged(self):
        from logic.generator.diagnostics import build_infeasibility_summary

        shop = ShopConfig(2026, 8)
        emp = Employee(last_name="Kowalski", first_name="Jan")
        schedule = MonthSchedule(2026, 8, employees=[emp])  # no carryover set

        messages = build_infeasibility_summary(schedule, shop)

        self.assertFalse(any("pamięć poprzedniego miesiąca" in m for m in messages))


# ---------------------------------------------------------------------------
# 9. Mechanizm odblokowany (2026-09-21, przy okazji pamięci wielu miesięcy) -
#    patrz model/month_schedule.py::PREVIOUS_MONTH_MEMORY_ENABLED. Ta klasa
#    sprawdza, że domyślnie (bez żadnego jawnego patchowania flagi) dwa
#    punkty "wpięcia" - auto-przejęcie przy zmianie miesiąca, wpływ na
#    generator przez base_specs.py - faktycznie działają. Ręczny edytor w
#    menu Edycja został od tego momentu na stałe schowany (patrz
#    test_previous_month_dialog_menu_action_is_permanently_hidden niżej i
#    komentarz w ui/main_window.py::_build_menu_bar) - to był tylko
#    testowy dostęp do tej samej pamięci, nie osobny mechanizm.
# ---------------------------------------------------------------------------

class PreviousMonthMemoryEnabledByDefaultTests(unittest.TestCase):
    def test_flag_is_currently_enabled(self):
        from model.month_schedule import PREVIOUS_MONTH_MEMORY_ENABLED
        self.assertTrue(PREVIOUS_MONTH_MEMORY_ENABLED)

    def test_build_rest_11h_passes_schedule_through_by_default(self):
        import logic.generator.base_specs as base_specs

        ctx = MagicMock()
        ctx.shop.constraints.get.return_value = "standard"
        ctx.duty_shifts = None
        ctx.shift_night = None
        ctx.schedule = MagicMock(name="real_schedule")

        with patch.object(base_specs, "add_rest_11h_constraint", return_value=[]) as mock_rest:
            base_specs._build_rest_11h(ctx, soft=False)

        self.assertIs(mock_rest.call_args.kwargs.get("schedule"), ctx.schedule)

    def test_build_rest_11h_simplified_passes_schedule_through_by_default(self):
        import logic.generator.base_specs as base_specs

        ctx = MagicMock()
        ctx.shop.constraints.get.return_value = "simplified"
        ctx.duty_shifts = None
        ctx.shift_night = None
        ctx.schedule = MagicMock(name="real_schedule")

        with patch.object(base_specs, "add_rest_11h_constraint_simplified", return_value=[]) as mock_rest:
            base_specs._build_rest_11h(ctx, soft=False)

        self.assertIs(mock_rest.call_args.kwargs.get("schedule"), ctx.schedule)

    def test_build_rest_11h_duty_rotation_passes_schedule_through_by_default(self):
        import logic.generator.base_specs as base_specs

        ctx = MagicMock()
        ctx.shop.constraints.get.return_value = "standard"
        ctx.duty_shifts = {"weekday_long": 0}
        ctx.shift_night = None
        ctx.schedule = MagicMock(name="real_schedule")

        with patch.object(base_specs, "add_rest_11h_constraint", return_value=[]), \
             patch.object(base_specs, "add_duty_rotation_rest_constraint", return_value=[]) as mock_duty_rest:
            base_specs._build_rest_11h(ctx, soft=False)

        self.assertIs(mock_duty_rest.call_args.kwargs.get("schedule"), ctx.schedule)

    def test_previous_month_dialog_menu_action_is_permanently_hidden(self):
        """Ręczny edytor "Godziny zakończenia z poprzedniego miesiąca..."
        (PreviousMonthShiftDialog, wołany przez
        _open_previous_month_shift_dialog) zniknął z menu Edycja na
        prośbę użytkownika - był tylko testowym rozwiązaniem i źródłem
        błędu (patrz PreviousMonthBlocksDay1DiagnosticsTests wyżej).
        Sama pamięć poprzedniego miesiąca zostaje w pełni aktywna -
        działa automatycznie przy zmianie miesiąca, co sprawdzają
        pozostałe testy w tej klasie/pliku.

        Sprawdzone przez źródło _build_menu (nie przez żywe menuBar() po
        pełnej konstrukcji MainWindow) - QMenuBar.addMenu(str) w PySide6
        potrafi skasować Python-owy wrapper podmenu zaraz po wyjściu z
        metody budującej, jeśli referencja nie jest nigdzie trzymana
        (self.edit_menu itp.), więc odpytanie o realne akcje później
        kończy się "Internal C++ object already deleted" niezależnie od
        tej zmiany."""
        import inspect
        import re

        source = inspect.getsource(MainWindow._build_menu)
        # Nie samego tekstu (zostaje w komentarzu wyjaśniającym decyzję),
        # tylko faktycznego wywołania rejestrującego akcję w menu - stąd
        # zwinięcie białych znaków przed porównaniem (wywołanie bywa
        # zawinięte w wielu liniach).
        collapsed = re.sub(r"\s+", " ", source)
        self.assertNotIn(
            'edit_menu.addAction( "Godziny zakończenia z poprzedniego miesiąca...",',
            collapsed,
        )

    def test_grid_column_shows_by_default_when_data_present(self):
        shop = ShopConfig(2026, 3)
        emp = Employee(last_name="Kowalski", first_name="Jan")
        schedule = MonthSchedule(2026, 3, employees=[emp])
        schedule.set_previous_month_end_shift(emp, "22:00", False)

        grid = ScheduleGrid()
        grid.set_data(schedule, shop, MagicMock())
        grid.build()

        self.assertEqual(grid._previous_month_last_day_if_shown(), 28)
        self.assertEqual(grid._prev_col_offset, 1)

    def test_auto_carry_over_happens_on_month_change_by_default(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        old_schedule = MonthSchedule(2026, 1, employees=[emp])
        old_schedule.set_day_hours(emp, 31, "14:00", "22:00")

        shop = ShopConfig(2026, 1)

        window = MainWindow.__new__(MainWindow)
        window.year, window.month = 2026, 1
        window.schedule = old_schedule
        window.shop_config = shop
        window.project = MonthlyProject()
        window.project.put(2026, 1, old_schedule, shop)
        window.date_display_label = MagicMock()
        window._update_nominal_hours_label = MagicMock()
        window._sync_everything = MagicMock()
        window.statusBar = MagicMock(return_value=MagicMock())

        window._switch_to_month(2026, 2)

        new_emp = window.schedule.employees[0]
        self.assertEqual(
            window.schedule.get_previous_month_end_shift(new_emp),
            PreviousMonthShiftEnd("22:00", False),
        )


# ---------------------------------------------------------------------------
# 10. Informacja o pominiętej pamięci poprzedniego miesiąca w oknie po
#     generacji (_previous_month_memory_note) - zastępuje ręczny edytor
#     schowany w sekcji 9: generator już wcześniej po cichu pomijał
#     sprawdzenie przerwy 11h, gdy nie miał danych (patrz sekcja 2, `if
#     carry is None: continue`) - teraz o tym dodatkowo informuje w oknie
#     "Sukces"/"Wersja demo" po udanej generacji, zamiast zostawiać to
#     niezauważone.
# ---------------------------------------------------------------------------

class PreviousMonthMemoryNoteTests(unittest.TestCase):
    def _window(self, employees, carryover_for=()):
        window = MainWindow.__new__(MainWindow)
        window.schedule = MonthSchedule(2026, 3, employees=employees)
        for emp in carryover_for:
            window.schedule.set_previous_month_end_shift(emp, "22:00", False)
        return window

    def test_none_when_at_least_one_employee_has_carryover_data(self):
        emp1 = Employee(last_name="Kowalski", first_name="Jan")
        emp2 = Employee(last_name="Nowak", first_name="Anna")
        window = self._window([emp1, emp2], carryover_for=[emp1])

        self.assertIsNone(window._previous_month_memory_note())

    def test_note_when_nobody_has_carryover_data(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        window = self._window([emp])

        note = window._previous_month_memory_note()
        self.assertIsNotNone(note)
        self.assertIn("poprzedniego miesiąca", note)

    def test_none_when_no_employees_at_all(self):
        window = self._window([])
        self.assertIsNone(window._previous_month_memory_note())

    def test_none_when_mechanism_disabled(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        window = self._window([emp])

        with patch("ui.main_window.PREVIOUS_MONTH_MEMORY_ENABLED", False):
            self.assertIsNone(window._previous_month_memory_note())

    def test_generation_success_message_includes_the_note_for_full_version(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        window = self._window([emp])
        window.controller = MagicMock(schedule=window.schedule)
        window.demo = MagicMock(is_demo=False)
        window._hide_loading = MagicMock()
        window._sync_everything = MagicMock()
        window._update_generate_label = MagicMock()

        with patch("ui.main_window.QMessageBox") as mock_box:
            window._on_generation_finished({"success": True})

        message = mock_box.information.call_args.args[2]
        self.assertIn("poprzedniego miesiąca", message)

    def test_generation_success_message_passes_note_through_in_demo_mode(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        window = self._window([emp])
        window.controller = MagicMock(schedule=window.schedule)
        window.demo = MagicMock(is_demo=True)
        window._hide_loading = MagicMock()
        window._sync_everything = MagicMock()
        window._update_generate_label = MagicMock()

        window._on_generation_finished({"success": True})

        note = window.demo.show_after_generate.call_args.kwargs["extra_note"]
        self.assertIn("poprzedniego miesiąca", note)

    def test_generation_success_message_has_no_note_when_data_present(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        window = self._window([emp], carryover_for=[emp])
        window.controller = MagicMock(schedule=window.schedule)
        window.demo = MagicMock(is_demo=False)
        window._hide_loading = MagicMock()
        window._sync_everything = MagicMock()
        window._update_generate_label = MagicMock()

        with patch("ui.main_window.QMessageBox") as mock_box:
            window._on_generation_finished({"success": True})

        message = mock_box.information.call_args.args[2]
        self.assertEqual(message, "Grafik został wygenerowany.")


if __name__ == "__main__":
    unittest.main()
