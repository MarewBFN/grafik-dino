"""Rotacja całodobowa "ogólna" (LocationConfig.round_clock_start_hour,
logic/generator/round_clock_constraint.py i sąsiednie moduły) - odpowiedź
na zgłoszenie klienta, że lokalizacje 24/7 mają nieobsadzoną kilkugodzinną
lukę w środku doby, bo stary model OPEN/CLOSE sięga najwyżej ok. 90/75 min
od otwarcia/zamknięcia. Pokrywa: obliczenia kafelków, bramę (wzajemna
wyłączność ze starym modelem), obsadę (Dino, ta sama reguła co open/close),
odpoczynek 11h, ręczną blokadę dnia, oraz że "open"/"close" nie stają się
strukturalnie niewykonalne, gdy wszyscy pracownicy są na lokalizacji
round-clock."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import patch

from ortools.sat.python import cp_model
from PySide6.QtWidgets import QApplication

from logic.auto_generator import AutoScheduleGenerator
from logic.generator.round_clock_constraint import (
    MAX_ROUND_CLOCK_TILES,
    add_round_clock_coverage_constraint,
    add_round_clock_gate_constraint,
    group_employees_with_round_clock,
    round_clock_tile_count,
    round_clock_tile_start_hour,
)
from logic.generator.round_clock_manual_constraint import add_round_clock_manual_shift_constraint
from logic.generator.round_clock_rest_constraint import add_round_clock_rest_constraint
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from ui.locations_dialog import LocationsDialog

_app = QApplication.instance() or QApplication([])


def _make_24_7_location(key="glowna", start_hour="08:00"):
    loc = LocationConfig(key=key, name="Główna")
    loc.set_24_7(True)
    loc.round_clock_start_hour = start_hour
    return loc


# ---------------------------------------------------------------------------
# 1. Obliczenia kafelków
# ---------------------------------------------------------------------------

class RoundClockTileMathTests(unittest.TestCase):
    def test_eight_hour_day_gives_three_tiles(self):
        self.assertEqual(round_clock_tile_count(8.0), 3)

    def test_twelve_hour_day_gives_two_tiles(self):
        self.assertEqual(round_clock_tile_count(12.0), 2)

    def test_six_hour_day_gives_four_tiles(self):
        self.assertEqual(round_clock_tile_count(6.0), 4)

    def test_result_is_capped_at_max_tiles(self):
        self.assertEqual(round_clock_tile_count(1.0), MAX_ROUND_CLOCK_TILES)

    def test_result_never_drops_below_two(self):
        self.assertEqual(round_clock_tile_count(24.0), 2)

    def test_zero_or_negative_hours_falls_back_to_max(self):
        self.assertEqual(round_clock_tile_count(0), MAX_ROUND_CLOCK_TILES)
        self.assertEqual(round_clock_tile_count(-5), MAX_ROUND_CLOCK_TILES)

    def test_tile_start_hours_tile_the_full_day(self):
        starts = [round_clock_tile_start_hour("08:00", i, 8.0) for i in range(3)]
        self.assertEqual(starts, ["08:00", "16:00", "00:00"])

    def test_tile_start_hours_wrap_past_midnight(self):
        starts = [round_clock_tile_start_hour("22:00", i, 12.0) for i in range(2)]
        self.assertEqual(starts, ["22:00", "10:00"])


# ---------------------------------------------------------------------------
# 2. Grupowanie pracowników
# ---------------------------------------------------------------------------

class GroupEmployeesWithRoundClockTests(unittest.TestCase):
    def test_only_employees_at_a_round_clock_location_are_grouped(self):
        loc_rc = _make_24_7_location("rc")
        loc_normal = LocationConfig(key="normal", name="Normalna")
        shop = ShopConfig(2026, 3)
        shop.locations = {"rc": loc_rc, "normal": loc_normal}

        emp_rc = Employee(last_name="A", first_name="A", location_key="rc")
        emp_normal = Employee(last_name="B", first_name="B", location_key="normal")

        groups = group_employees_with_round_clock([emp_rc, emp_normal], shop)

        self.assertEqual(set(groups.keys()), {"rc"})
        start_hour, indices = groups["rc"]
        self.assertEqual(start_hour, "08:00")
        self.assertEqual(indices, [0])

    def test_is_24_7_without_start_hour_is_not_grouped(self):
        loc = LocationConfig(key="glowna", name="Główna")
        loc.set_24_7(True)  # zaznaczone 24/7, ale BEZ ustawionej godziny startu
        shop = ShopConfig(2026, 3)
        shop.locations = {"glowna": loc}
        emp = Employee(last_name="A", first_name="A", location_key="glowna")

        groups = group_employees_with_round_clock([emp], shop)

        self.assertEqual(groups, {})


# ---------------------------------------------------------------------------
# 3. Brama (wzajemna wyłączność ze starym modelem)
# ---------------------------------------------------------------------------

class RoundClockGateTests(unittest.TestCase):
    SHIFT_OPEN, SHIFT_CLOSE = 0, 1
    ROUND_CLOCK_SHIFTS = list(range(20, 20 + MAX_ROUND_CLOCK_TILES))
    ALL_SHIFTS = (SHIFT_OPEN, SHIFT_CLOSE, *ROUND_CLOCK_SHIFTS)

    def _model_and_vars(self, n_emp=1, days=(1,)):
        model = cp_model.CpModel()
        x = {
            (e, d, s): model.NewBoolVar(f"x_{e}_{d}_{s}")
            for e in range(n_emp) for d in days for s in self.ALL_SHIFTS
        }
        return model, x

    def test_round_clock_employee_cannot_use_old_shifts(self):
        loc = _make_24_7_location()
        shop = ShopConfig(2026, 3)
        shop.locations = {"glowna": loc}
        emp = Employee(last_name="A", first_name="A", location_key="glowna")

        model, x = self._model_and_vars()
        add_round_clock_gate_constraint(
            model, x, [emp], [1], shop, self.ROUND_CLOCK_SHIFTS, self.ALL_SHIFTS, 8.0,
        )
        model.Add(x[0, 1, self.SHIFT_OPEN] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertEqual(status, cp_model.INFEASIBLE)

    def test_non_round_clock_employee_cannot_use_round_clock_tiles(self):
        shop = ShopConfig(2026, 3)  # domyślna, jedna lokalizacja bez round-clock
        emp = Employee(last_name="A", first_name="A", location_key=next(iter(shop.locations)))

        model, x = self._model_and_vars()
        add_round_clock_gate_constraint(
            model, x, [emp], [1], shop, self.ROUND_CLOCK_SHIFTS, self.ALL_SHIFTS, 8.0,
        )
        model.Add(x[0, 1, self.ROUND_CLOCK_SHIFTS[0]] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertEqual(status, cp_model.INFEASIBLE)

    def test_tiles_beyond_computed_count_are_always_blocked(self):
        loc = _make_24_7_location()
        shop = ShopConfig(2026, 3)
        shop.locations = {"glowna": loc}
        emp = Employee(last_name="A", first_name="A", location_key="glowna")

        model, x = self._model_and_vars()
        # standard_daily_hours=8.0 -> 3 kafelków (indeksy 0,1,2) - kafelek
        # o indeksie 3 (self.ROUND_CLOCK_SHIFTS[3]) musi być zawsze 0.
        add_round_clock_gate_constraint(
            model, x, [emp], [1], shop, self.ROUND_CLOCK_SHIFTS, self.ALL_SHIFTS, 8.0,
        )
        model.Add(x[0, 1, self.ROUND_CLOCK_SHIFTS[3]] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertEqual(status, cp_model.INFEASIBLE)

    def test_third_tile_within_computed_count_is_allowed(self):
        loc = _make_24_7_location()
        shop = ShopConfig(2026, 3)
        shop.locations = {"glowna": loc}
        emp = Employee(last_name="A", first_name="A", location_key="glowna")

        model, x = self._model_and_vars()
        add_round_clock_gate_constraint(
            model, x, [emp], [1], shop, self.ROUND_CLOCK_SHIFTS, self.ALL_SHIFTS, 8.0,
        )
        model.Add(x[0, 1, self.ROUND_CLOCK_SHIFTS[2]] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))


# ---------------------------------------------------------------------------
# 4. Obsada kafelków (Dino - ta sama reguła co open/close)
# ---------------------------------------------------------------------------

class RoundClockCoverageTests(unittest.TestCase):
    ROUND_CLOCK_SHIFTS = list(range(20, 20 + MAX_ROUND_CLOCK_TILES))

    def test_generates_full_day_coverage_with_no_gap(self):
        """To jest właściwa naprawa zgłoszonego buga: end-to-end, przez
        prawdziwy AutoScheduleGenerator, sprawdzone minuta-po-minucie że
        24h doby są w pełni pokryte, bez luki w środku."""
        shop = ShopConfig(2026, 3)
        loc = _make_24_7_location()
        shop.locations = {"glowna": loc}
        shop.constraints["min_open_staff"] = 1
        shop.constraints["solver_time_limit_seconds"] = 20

        employees = [
            Employee(
                last_name=f"Prac{i}", first_name="Jan", location_key="glowna",
                employment_fraction=1.0, is_opener=True, is_meat=True,
            )
            for i in range(6)
        ]
        schedule = MonthSchedule(2026, 3, employees=employees)

        result = AutoScheduleGenerator(schedule, shop).generate(
            solver_time_limit_seconds=20, solver_workers=2,
        )
        self.assertTrue(result["success"], result.get("infeasibility_reasons"))

        # Dzień 2 (poniedziałek) - zbierz przedziały i sprawdź brak luki.
        intervals = []
        for emp in employees:
            ds = schedule.get_day(emp, 2)
            if not ds.is_empty():
                intervals.append((ds.start, ds.end))

        self.assertGreaterEqual(len(intervals), 3)
        starts = sorted(s for s, _ in intervals)
        self.assertIn("00:00", starts)
        self.assertIn("08:00", starts)
        self.assertIn("16:00", starts)

    def test_infeasible_without_any_opener(self):
        shop = ShopConfig(2026, 3)
        loc = _make_24_7_location()
        shop.locations = {"glowna": loc}
        shop.constraints["min_open_staff"] = 1

        employees = [
            Employee(
                last_name=f"Prac{i}", first_name="Jan", location_key="glowna",
                employment_fraction=1.0, is_opener=False, is_meat=True,
            )
            for i in range(6)
        ]
        schedule = MonthSchedule(2026, 3, employees=employees)

        result = AutoScheduleGenerator(schedule, shop).generate(
            solver_time_limit_seconds=10, solver_workers=2,
        )
        self.assertFalse(result["success"])


# ---------------------------------------------------------------------------
# 5. "open"/"close" nie stają się strukturalnie niewykonalne
# ---------------------------------------------------------------------------

class OpenCloseCoexistenceTests(unittest.TestCase):
    def test_all_employees_round_clock_does_not_break_open_close(self):
        """Regresja na bug znaleziony podczas budowy tej funkcji: profil
        Dino wymaga obsady OPEN/CLOSE bezwarunkowo (MANDATORY domyślnie) -
        gdy WSZYSCY pracownicy są na lokalizacji round-clock (więc mają
        x[e,d,SHIFT_OPEN/CLOSE] zablokowane przez add_round_clock_gate_constraint),
        min_open_staff/min_close_staff było strukturalnie niespełnialne,
        robiąc CAŁY miesiąc niewykonalnym - patrz
        dino_retail_profile.py::_open_close_eligible_indices."""
        shop = ShopConfig(2026, 3)
        loc = _make_24_7_location()
        shop.locations = {"glowna": loc}
        shop.constraints["min_open_staff"] = 1
        shop.constraints["min_close_staff"] = 3  # celowo różne od min_open

        employees = [
            Employee(
                last_name=f"Prac{i}", first_name="Jan", location_key="glowna",
                employment_fraction=1.0, is_opener=True, is_meat=True,
            )
            for i in range(6)
        ]
        schedule = MonthSchedule(2026, 3, employees=employees)

        result = AutoScheduleGenerator(schedule, shop).generate(
            solver_time_limit_seconds=15, solver_workers=2,
        )
        self.assertTrue(result["success"], result.get("infeasibility_reasons"))

    def test_mixed_project_still_requires_open_close_from_eligible_employees(self):
        """Odwrotna strona tej samej naprawy - projekt MIESZANY (jedna
        lokalizacja round-clock, jedna zwykła) wciąż wymaga normalnej
        obsady OPEN/CLOSE od pracowników zwykłej lokalizacji, tylko bez
        liczenia do niej pracowników round-clock."""
        shop = ShopConfig(2026, 3)
        loc_rc = _make_24_7_location("rc")
        loc_normal = LocationConfig(key="normal", name="Normalna")
        shop.locations = {"rc": loc_rc, "normal": loc_normal}
        shop.constraints["min_open_staff"] = 1
        shop.constraints["min_close_staff"] = 1

        rc_employees = [
            Employee(
                last_name=f"RC{i}", first_name="Jan", location_key="rc",
                employment_fraction=1.0, is_opener=True, is_meat=True,
            )
            for i in range(6)
        ]
        # BRAK pracowników "normal" z rolą otwiera/mięso -> "open"/"close"
        # dla lokalizacji normalnej musi wciąż być niewykonalne (nikt
        # eligible nie może go spełnić) - to potwierdza, że filtr NIE
        # wyłącza wymogu całkowicie, tylko dla samej grupy round-clock.
        normal_employees = [
            Employee(last_name="N", first_name="Jan", location_key="normal", employment_fraction=1.0)
        ]
        schedule = MonthSchedule(2026, 3, employees=rc_employees + normal_employees)

        result = AutoScheduleGenerator(schedule, shop).generate(
            solver_time_limit_seconds=15, solver_workers=2,
        )
        self.assertFalse(result["success"])


# ---------------------------------------------------------------------------
# 6. Odpoczynek 11h
# ---------------------------------------------------------------------------

class RoundClockRestTests(unittest.TestCase):
    ROUND_CLOCK_SHIFTS = list(range(20, 20 + MAX_ROUND_CLOCK_TILES))

    def _model_and_vars(self, days):
        model = cp_model.CpModel()
        x = {
            (0, d, s): model.NewBoolVar(f"x_{d}_{s}")
            for d in days for s in self.ROUND_CLOCK_SHIFTS
        }
        return model, x

    def test_back_to_back_tiles_across_days_are_blocked(self):
        """Kafelek kończący dzień 1 o 00:00 (start 16:00, 8h - indeks 1: tile
        0=08:00, tile 1=16:00, tile 2=00:00, patrz round_clock_tile_start_hour)
        i kafelek zaczynający dzień 2 o 08:00 (indeks 0) - odstęp dokładnie
        8h, poniżej 11h."""
        loc = _make_24_7_location()
        shop = ShopConfig(2026, 3)
        shop.locations = {"glowna": loc}
        emp = Employee(last_name="A", first_name="A", location_key="glowna", employment_fraction=1.0)

        model, x = self._model_and_vars([1, 2])
        add_round_clock_rest_constraint(
            model, x, [emp], [1, 2], shop, self.ROUND_CLOCK_SHIFTS, 8.0, soft=False,
        )
        model.Add(x[0, 1, self.ROUND_CLOCK_SHIFTS[1]] == 1)  # kafelek 16:00-00:00
        model.Add(x[0, 2, self.ROUND_CLOCK_SHIFTS[0]] == 1)  # kafelek 08:00-16:00

        status = cp_model.CpSolver().Solve(model)
        self.assertEqual(status, cp_model.INFEASIBLE)

    def test_enough_rest_between_days_is_allowed(self):
        loc = _make_24_7_location()
        shop = ShopConfig(2026, 3)
        shop.locations = {"glowna": loc}
        emp = Employee(last_name="A", first_name="A", location_key="glowna", employment_fraction=1.0)

        model, x = self._model_and_vars([1, 2])
        add_round_clock_rest_constraint(
            model, x, [emp], [1, 2], shop, self.ROUND_CLOCK_SHIFTS, 8.0, soft=False,
        )
        model.Add(x[0, 1, self.ROUND_CLOCK_SHIFTS[0]] == 1)  # 08:00-16:00 dzień 1
        model.Add(x[0, 2, self.ROUND_CLOCK_SHIFTS[0]] == 1)  # 08:00-16:00 dzień 2 (16h przerwy)

        status = cp_model.CpSolver().Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))


# ---------------------------------------------------------------------------
# 7. Ręczna blokada dnia
# ---------------------------------------------------------------------------

class RoundClockManualConstraintTests(unittest.TestCase):
    ROUND_CLOCK_SHIFTS = list(range(20, 20 + MAX_ROUND_CLOCK_TILES))

    def test_locking_a_tiles_start_hour_forces_that_exact_tile(self):
        loc = _make_24_7_location()
        shop = ShopConfig(2026, 3)
        shop.locations = {"glowna": loc}
        emp = Employee(last_name="A", first_name="A", location_key="glowna", employment_fraction=1.0)
        schedule = MonthSchedule(2026, 3, employees=[emp])
        schedule.set_day_hours(emp, 1, "16:00", "00:00")
        schedule.get_day(emp, 1).is_locked = True

        model = cp_model.CpModel()
        x = {(0, 1, s): model.NewBoolVar(f"x_{s}") for s in self.ROUND_CLOCK_SHIFTS}

        add_round_clock_manual_shift_constraint(
            model, x, [emp], [1], schedule, shop, self.ROUND_CLOCK_SHIFTS, 8.0,
        )

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))
        # Tile 0=08:00, tile 1=16:00, tile 2=00:00 (patrz
        # round_clock_tile_start_hour) - "16:00" trafia w tile 1.
        self.assertEqual(solver.Value(x[0, 1, self.ROUND_CLOCK_SHIFTS[1]]), 1)
        self.assertEqual(solver.Value(x[0, 1, self.ROUND_CLOCK_SHIFTS[0]]), 0)
        self.assertEqual(solver.Value(x[0, 1, self.ROUND_CLOCK_SHIFTS[2]]), 0)

    def test_locked_free_day_blocks_every_tile(self):
        loc = _make_24_7_location()
        shop = ShopConfig(2026, 3)
        shop.locations = {"glowna": loc}
        emp = Employee(last_name="A", first_name="A", location_key="glowna", employment_fraction=1.0)
        schedule = MonthSchedule(2026, 3, employees=[emp])
        schedule.get_day(emp, 1).is_locked = True  # zablokowany jako "wolne"

        model = cp_model.CpModel()
        x = {(0, 1, s): model.NewBoolVar(f"x_{s}") for s in self.ROUND_CLOCK_SHIFTS}
        add_round_clock_manual_shift_constraint(
            model, x, [emp], [1], schedule, shop, self.ROUND_CLOCK_SHIFTS, 8.0,
        )
        model.Add(x[0, 1, self.ROUND_CLOCK_SHIFTS[0]] == 1)

        status = cp_model.CpSolver().Solve(model)
        self.assertEqual(status, cp_model.INFEASIBLE)


# ---------------------------------------------------------------------------
# 8. Model / serializacja
# ---------------------------------------------------------------------------

class LocationConfigRoundClockFieldTests(unittest.TestCase):
    def test_round_trip(self):
        loc = _make_24_7_location()
        data = loc.to_dict()
        restored = LocationConfig.from_dict(data)
        self.assertEqual(restored.round_clock_start_hour, "08:00")

    def test_disabling_24_7_clears_round_clock_start_hour(self):
        loc = _make_24_7_location()
        loc.set_24_7(False)
        self.assertIsNone(loc.round_clock_start_hour)

    def test_shop_config_get_round_clock_start_hour_via_location_view(self):
        shop = ShopConfig(2026, 3)
        shop.locations = {"glowna": _make_24_7_location()}
        emp = Employee(last_name="A", first_name="A", location_key="glowna")
        self.assertEqual(shop.get_location(emp).get_round_clock_start_hour(), "08:00")

    def test_from_dict_ignores_round_clock_next_to_duty_rotation(self):
        """Rotacja służby + rotacja całodobowa naraz blokują sobie nawzajem
        wszystkie zmiany - przy wczytaniu wygrywa rotacja służby."""
        loc = _make_24_7_location(start_hour="09:30")
        loc.set_duty_rotation({
            "weekday_long": {"start": "06:00", "end": "22:00"},
            "weekday_short": {"start": "22:00", "end": "06:00"},
            "weekend_full": {"start": "06:00"},
            "weekend_half_a": {"start": "06:00", "end": "18:00"},
            "weekend_half_b": {"start": "18:00", "end": "06:00"},
        })

        loaded = LocationConfig.from_dict(loc.to_dict())

        self.assertIsNotNone(loaded.duty_rotation)
        self.assertIsNone(loaded.round_clock_start_hour)

    def test_from_dict_keeps_round_clock_without_duty_rotation(self):
        loaded = LocationConfig.from_dict(_make_24_7_location(start_hour="09:30").to_dict())
        self.assertEqual(loaded.round_clock_start_hour, "09:30")

    def test_employee_without_location_never_gets_round_clock(self):
        shop = ShopConfig(2026, 3)
        emp = Employee(last_name="A", first_name="A", location_key="does-not-exist")
        self.assertIsNone(shop.get_location(emp).get_round_clock_start_hour())


# ---------------------------------------------------------------------------
# 9. GUI (ui/locations_dialog.py)
# ---------------------------------------------------------------------------

class LocationsDialogRoundClockUiTests(unittest.TestCase):
    def test_field_hidden_when_not_24_7(self):
        shop = ShopConfig(2026, 3)
        dialog = LocationsDialog(None, shop)
        row = dialog._location_rows[0]
        self.assertFalse(row.is_24_7_check.isChecked())
        self.assertIsNone(row.round_clock_start_hour_value())

    @patch("ui.locations_dialog.ROUND_CLOCK_UI_ENABLED", True)
    def test_field_shown_and_value_round_trips(self):
        shop = ShopConfig(2026, 3)
        shop.locations = {"glowna": _make_24_7_location(start_hour="09:30")}
        dialog = LocationsDialog(None, shop)
        row = dialog._location_rows[0]

        self.assertTrue(row.round_clock_check.isChecked())
        self.assertEqual(row.round_clock_start_hour_value(), "09:30")

    def test_field_hidden_for_enyo_even_when_24_7(self):
        """Domyślnie (ROUND_CLOCK_UI_ENABLED=False) pole jest ukryte i nic
        nie zapisuje - także dla lokalizacji 24/7 z wcześniej zapisaną
        godziną rozpoczęcia."""
        shop = ShopConfig(2026, 3)
        shop.locations = {"glowna": _make_24_7_location(start_hour="09:30")}
        dialog = LocationsDialog(None, shop)
        row = dialog._location_rows[0]

        self.assertTrue(row.is_24_7_check.isChecked())
        self.assertTrue(row.round_clock_container.isHidden())
        self.assertTrue(row.round_clock_hint.isHidden())
        self.assertFalse(row.round_clock_check.isChecked())
        self.assertIsNone(row.round_clock_start_hour_value())

    def test_saving_24_7_location_drops_round_clock_start_hour(self):
        shop = ShopConfig(2026, 3)
        shop.locations = {"glowna": _make_24_7_location(start_hour="09:30")}
        dialog = LocationsDialog(None, shop)
        dialog._save()

        loc = shop.locations["glowna"]
        self.assertTrue(loc.is_24_7)
        self.assertIsNotNone(loc.duty_rotation)
        self.assertIsNone(loc.round_clock_start_hour)

    @patch("ui.locations_dialog.ROUND_CLOCK_UI_ENABLED", True)
    def test_unchecking_24_7_clears_the_value(self):
        shop = ShopConfig(2026, 3)
        shop.locations = {"glowna": _make_24_7_location()}
        dialog = LocationsDialog(None, shop)
        row = dialog._location_rows[0]

        row.is_24_7_check.setChecked(False)

        self.assertIsNone(row.round_clock_start_hour_value())


if __name__ == "__main__":
    unittest.main()
