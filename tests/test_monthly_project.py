"""Pamięć wielu miesięcy (model/monthly_project.py, rozszerzenia
persistence/project_io.py, ui/main_window.py::_switch_to_month i
ui/month_picker_dialog.py) - kontener trzymający każdy odwiedzony miesiąc
projektu zamiast tylko aktualnie otwartego, swobodna nawigacja bez utraty
danych, opis stanu miesiąca do kafelka w oknie wyboru i round-trip
zapisu/wczytania (w tym starego, jednomiesięcznego formatu plików)."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest

from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication, QDialog

from model.employee import Employee
from model.month_schedule import MonthSchedule, PreviousMonthShiftEnd
from model.monthly_project import (
    MONTH_STATE_EDITING,
    MONTH_STATE_EMPTY,
    MONTH_STATE_READY,
    MonthlyProject,
    describe_month_state,
    month_state_class,
)
from model.shop_config import ShopConfig
from persistence.project_io import (
    load_project,
    load_project_bundle,
    save_project,
    save_project_bundle,
)
from ui.main_window import MainWindow
from ui.month_picker_dialog import MonthPickerDialog

_app = QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------------
# 1. MonthlyProject - kontener
# ---------------------------------------------------------------------------

class MonthlyProjectContainerTests(unittest.TestCase):
    def test_put_and_get_round_trip(self):
        project = MonthlyProject()
        sched = MonthSchedule(2026, 1)
        shop = ShopConfig(2026, 1)
        project.put(2026, 1, sched, shop)

        self.assertTrue(project.has(2026, 1))
        self.assertEqual(project.get(2026, 1), (sched, shop))

    def test_get_missing_month_returns_none(self):
        project = MonthlyProject()
        self.assertIsNone(project.get(2026, 5))
        self.assertFalse(project.has(2026, 5))

    def test_sorted_keys_orders_chronologically_across_year_boundary(self):
        project = MonthlyProject()
        for year, month in [(2026, 3), (2025, 12), (2026, 1)]:
            project.put(year, month, MonthSchedule(year, month), ShopConfig(year, month))

        self.assertEqual(project.sorted_keys(), [(2025, 12), (2026, 1), (2026, 3)])


# ---------------------------------------------------------------------------
# 2. Opis stanu miesiąca (kafelek w oknie wyboru)
# ---------------------------------------------------------------------------

class DescribeMonthStateTests(unittest.TestCase):
    def test_none_pair_is_empty(self):
        self.assertEqual(month_state_class(None), MONTH_STATE_EMPTY)
        self.assertEqual(describe_month_state(None), "Pusty grafik")

    def test_month_with_no_employees_and_no_data_is_empty(self):
        sched = MonthSchedule(2026, 1)
        shop = ShopConfig(2026, 1)
        self.assertEqual(month_state_class((sched, shop)), MONTH_STATE_EMPTY)
        self.assertEqual(describe_month_state((sched, shop)), "Pusty grafik")

    def test_month_with_shift_data_but_not_generated_is_editing(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        sched = MonthSchedule(2026, 1, employees=[emp])
        sched.set_day_hours(emp, 5, "08:00", "16:00")
        shop = ShopConfig(2026, 1)

        self.assertEqual(month_state_class((sched, shop)), MONTH_STATE_EDITING)
        text = describe_month_state((sched, shop))
        self.assertIn("w trakcie edycji", text.lower())

    def test_generated_month_is_ready_regardless_of_shift_data(self):
        sched = MonthSchedule(2026, 1)
        sched.is_generated = True
        shop = ShopConfig(2026, 1)

        self.assertEqual(month_state_class((sched, shop)), MONTH_STATE_READY)
        self.assertIn("grafik gotowy", describe_month_state((sched, shop)).lower())

    def test_describe_includes_location_and_employee_counts(self):
        from model.location import LocationConfig

        emp1 = Employee(last_name="Kowalski", first_name="Jan")
        emp2 = Employee(last_name="Nowak", first_name="Anna")
        sched = MonthSchedule(2026, 1, employees=[emp1, emp2])
        sched.is_generated = True
        shop = ShopConfig(2026, 1)
        shop.locations = {
            f"loc{i}": LocationConfig(key=f"loc{i}", name=f"Sklep {i}") for i in range(10)
        }

        text = describe_month_state((sched, shop))
        self.assertIn("10 lokacji", text)
        self.assertIn("2 pracowników", text)
        self.assertIn("grafik gotowy", text.lower())

    def test_polish_plural_forms(self):
        from model.location import LocationConfig

        sched = MonthSchedule(2026, 1)
        sched.is_generated = True
        shop = ShopConfig(2026, 1)
        shop.locations = {"only": LocationConfig(key="only", name="Jedyna")}

        text = describe_month_state((sched, shop))
        self.assertIn("1 lokacja", text)


# ---------------------------------------------------------------------------
# 3. Zapis/wczytanie kontenera wielu miesięcy (persistence/project_io.py)
# ---------------------------------------------------------------------------

class ProjectBundlePersistenceTests(unittest.TestCase):
    def _project_with_two_months(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        jan_sched = MonthSchedule(2026, 1, employees=[emp])
        jan_sched.set_day_hours(emp, 31, "14:00", "22:00")
        jan_shop = ShopConfig(2026, 1)

        feb_sched = MonthSchedule(2026, 2, employees=[emp])
        feb_sched.set_previous_month_end_shift(emp, "22:00", False)
        feb_shop = ShopConfig(2026, 2)

        project = MonthlyProject()
        project.put(2026, 1, jan_sched, jan_shop)
        project.put(2026, 2, feb_sched, feb_shop)
        return project

    def test_round_trip_preserves_every_month_and_active_month(self):
        project = self._project_with_two_months()

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "project.myp")
            save_project_bundle(path, project, 2026, 2)
            loaded, active_year, active_month = load_project_bundle(path)

        self.assertEqual((active_year, active_month), (2026, 2))
        self.assertEqual(loaded.sorted_keys(), [(2026, 1), (2026, 2)])

        jan_sched, _ = loaded.get(2026, 1)
        emp = jan_sched.employees[0]
        self.assertEqual(jan_sched.get_day(emp, 31).start, "14:00")

        feb_sched, _ = loaded.get(2026, 2)
        feb_emp = feb_sched.employees[0]
        self.assertEqual(
            feb_sched.get_previous_month_end_shift(feb_emp),
            PreviousMonthShiftEnd("22:00", False),
        )

    def test_loading_old_single_month_format_wraps_it_as_lone_month(self):
        sched = MonthSchedule(2026, 3)
        shop = ShopConfig(2026, 3)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "old.json")
            save_project(path, sched, shop)  # stary, jednomiesięczny format
            loaded, active_year, active_month = load_project_bundle(path)

        self.assertEqual((active_year, active_month), (2026, 3))
        self.assertEqual(loaded.sorted_keys(), [(2026, 3)])

    def test_old_load_project_still_reads_files_saved_by_bundle_format(self):
        """Kompatybilność w drugą stronę: demo/*.py i logic/generator/trace.py
        wciąż wołają load_project() na plikach zapisanych starą funkcją - ta
        NIE musi (i nie umie) czytać nowego formatu, więc to save_project()/
        load_project() na starym, jednomiesięcznym pliku nadal działają bez
        zmian."""
        sched = MonthSchedule(2026, 4)
        shop = ShopConfig(2026, 4)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "single.json")
            save_project(path, sched, shop)
            loaded_sched, loaded_shop = load_project(path)

        self.assertEqual((loaded_sched.year, loaded_sched.month), (2026, 4))

    def test_missing_active_month_key_falls_back_to_latest(self):
        project = self._project_with_two_months()

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "project.myp")
            save_project_bundle(path, project, 2026, 1)

            import json
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            del data["active_month"]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)

            _, active_year, active_month = load_project_bundle(path)

        self.assertEqual((active_year, active_month), (2026, 2))


# ---------------------------------------------------------------------------
# 4. MainWindow._switch_to_month - nawigacja bez utraty danych
# ---------------------------------------------------------------------------

class SwitchToMonthTests(unittest.TestCase):
    def _make_window(self, year, month, employees=None):
        window = MainWindow.__new__(MainWindow)
        window.year, window.month = year, month
        window.schedule = MonthSchedule(year, month, employees=employees or [])
        window.shop_config = ShopConfig(year, month)
        window.project = MonthlyProject()
        window.project.put(year, month, window.schedule, window.shop_config)
        window.date_display_label = MagicMock()
        window.statusBar = MagicMock(return_value=MagicMock())
        window._update_nominal_hours_label = MagicMock()
        window._sync_everything = MagicMock()
        return window

    def test_switching_to_a_new_month_does_not_touch_the_old_one(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        window = self._make_window(2026, 1, employees=[emp])
        window.schedule.set_day_hours(emp, 15, "08:00", "16:00")

        window._switch_to_month(2026, 2)

        jan_sched, _ = window.project.get(2026, 1)
        self.assertEqual(jan_sched.get_day(emp, 15).start, "08:00")
        self.assertEqual((window.year, window.month), (2026, 2))
        self.assertTrue(window.schedule.get_day(emp, 15).is_empty())

    def test_revisiting_a_month_restores_it_exactly(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        window = self._make_window(2026, 1, employees=[emp])
        window.schedule.set_day_hours(emp, 15, "08:00", "16:00")

        window._switch_to_month(2026, 2)
        window.schedule.set_day_hours(emp, 3, "09:00", "17:00")  # edit Feb too
        window._switch_to_month(2026, 1)

        self.assertEqual(window.schedule.get_day(emp, 15).start, "08:00")
        self.assertEqual((window.year, window.month), (2026, 1))

        window._switch_to_month(2026, 2)
        self.assertEqual(window.schedule.get_day(emp, 3).start, "09:00")

    def test_new_month_keeps_locations_and_generator_settings(self):
        window = self._make_window(2026, 1)
        window.shop_config.name = "Sklep testowy"
        window.shop_config.constraints["min_open_staff"] = 7

        window._switch_to_month(2026, 2)

        self.assertEqual(window.shop_config.name, "Sklep testowy")
        self.assertEqual(window.shop_config.constraints["min_open_staff"], 7)
        # ale nie ten sam obiekt co stycznia - edycja lutego nie ma cofać się
        # do stycznia, patrz test niżej.
        jan_shop = window.project.get(2026, 1)[1]
        self.assertIsNot(window.shop_config, jan_shop)

    def test_editing_a_new_months_shop_config_does_not_affect_the_source_month(self):
        window = self._make_window(2026, 1)
        window._switch_to_month(2026, 2)
        window.shop_config.constraints["min_open_staff"] = 99

        jan_shop = window.project.get(2026, 1)[1]
        self.assertNotEqual(jan_shop.constraints["min_open_staff"], 99)

    def test_carry_over_uses_the_calendar_predecessor_not_whatever_was_open(self):
        """Nawigacja jest teraz swobodna - użytkownik mógł być akurat na
        marcu i stamtąd od razu utworzyć nowy czerwiec, a mimo to źródłem
        pamięci końca poprzedniego miesiąca powinien być MAJ, jeśli majowe
        dane już istnieją w projekcie (patrz previous_calendar_month w
        _switch_to_month), niezależnie od tego, co było otwarte przed
        przełączeniem."""
        emp = Employee(last_name="Kowalski", first_name="Jan")
        window = self._make_window(2026, 3, employees=[emp])

        may_sched = MonthSchedule(2026, 5, employees=[emp])
        may_sched.set_day_hours(emp, 31, "10:00", "18:00")
        window.project.put(2026, 5, may_sched, ShopConfig(2026, 5))

        window._switch_to_month(2026, 6)

        carry = window.schedule.get_previous_month_end_shift(emp)
        self.assertEqual(carry, PreviousMonthShiftEnd("18:00", False))

    def test_no_carry_over_when_predecessor_month_never_existed(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        window = self._make_window(2026, 1, employees=[emp])
        window.schedule.set_day_hours(emp, 31, "14:00", "22:00")

        window._switch_to_month(2026, 6)  # maj nigdy nie istniał

        self.assertIsNone(window.schedule.get_previous_month_end_shift(emp))

    def test_switching_to_the_same_month_is_a_no_op(self):
        window = self._make_window(2026, 1)
        original_schedule = window.schedule

        window._switch_to_month(2026, 1)

        self.assertIs(window.schedule, original_schedule)
        window._sync_everything.assert_not_called()


# ---------------------------------------------------------------------------
# 5. MonthPickerDialog
# ---------------------------------------------------------------------------

class MonthPickerDialogTests(unittest.TestCase):
    def test_shows_twelve_tiles_for_the_displayed_year(self):
        project = MonthlyProject()
        dialog = MonthPickerDialog(project, 2026, 1)
        self.assertEqual(len(dialog._tiles), 12)
        self.assertEqual(set(m for _, m in dialog._tiles.keys()), set(range(1, 13)))

    def test_selecting_and_confirming_a_different_month_sets_result(self):
        project = MonthlyProject()
        dialog = MonthPickerDialog(project, 2026, 1)

        dialog._select(2026, 5)
        dialog._confirm_selected()

        self.assertEqual((dialog.result_year, dialog.result_month), (2026, 5))

    def test_double_click_open_confirms_immediately(self):
        project = MonthlyProject()
        dialog = MonthPickerDialog(project, 2026, 1)

        dialog._open(2026, 9)

        self.assertEqual((dialog.result_year, dialog.result_month), (2026, 9))
        self.assertEqual(dialog.result(), QDialog.Accepted)

    def test_year_navigation_rebuilds_tiles_for_new_year(self):
        project = MonthlyProject()
        dialog = MonthPickerDialog(project, 2026, 1)

        dialog._shift_year(1)

        self.assertEqual(dialog._displayed_year, 2027)
        self.assertEqual(set(y for y, _ in dialog._tiles.keys()), {2027})

    def test_tile_status_reflects_project_state(self):
        project = MonthlyProject()
        sched = MonthSchedule(2026, 4)
        sched.is_generated = True
        project.put(2026, 4, sched, ShopConfig(2026, 4))

        dialog = MonthPickerDialog(project, 2026, 1)

        self.assertIn("gotowy", describe_month_state(project.get(2026, 4)).lower())


# ---------------------------------------------------------------------------
# 6. Zasięg zmian konfiguracji/lokalizacji/pracowników - tylko ten miesiąc
#    i miesiące utworzone od teraz, NIE wstecz i NIE do już istniejących
#    późniejszych miesięcy (świadoma decyzja, patrz
#    logic/utils/time_utils.py::month_scope_note).
# ---------------------------------------------------------------------------

class MonthScopeIsolationTests(unittest.TestCase):
    def _window_with_months(self, *months):
        """MainWindow z podanymi (year, month) już utworzonymi w projekcie,
        wszystkie startujące z identyczną, domyślną konfiguracją - tak jakby
        użytkownik po kolei je odwiedził."""
        window = MainWindow.__new__(MainWindow)
        first_year, first_month = months[0]
        window.year, window.month = first_year, first_month
        window.schedule = MonthSchedule(first_year, first_month)
        window.shop_config = ShopConfig(first_year, first_month)
        window.project = MonthlyProject()
        window.project.put(first_year, first_month, window.schedule, window.shop_config)
        window.date_display_label = MagicMock()
        window.statusBar = MagicMock(return_value=MagicMock())
        window._update_nominal_hours_label = MagicMock()
        window._sync_everything = MagicMock()

        for year, month in months[1:]:
            window._switch_to_month(year, month)

        return window

    def test_location_self_heals_to_first_when_switching_to_a_month_without_it(self):
        from model.location import LocationConfig

        window = self._window_with_months((2026, 1), (2026, 2))
        window.shop_config.locations["sklep_b"] = LocationConfig(key="sklep_b", name="Sklep B")
        window.selected_location_key = "sklep_b"
        window.btn_location_name = MagicMock()
        window.btn_location_prev = MagicMock()
        window.btn_location_next = MagicMock()
        window.grid_header_location_label = MagicMock()
        window.grid_header_hours_label = MagicMock()

        window._switch_to_month(2026, 1)  # miesiąc bez "sklep_b"
        window._update_location_switcher()

        self.assertEqual(window.selected_location_key, next(iter(window.shop_config.locations)))
        window.btn_location_name.setFullText.assert_called_with(
            window.shop_config.locations[window.selected_location_key].name
        )

    def test_config_edit_does_not_retroactively_affect_already_existing_later_months(self):
        window = self._window_with_months((2026, 1), (2026, 2), (2026, 3))

        window._switch_to_month(2026, 1)
        window.shop_config.constraints["min_open_staff"] = 99

        self.assertEqual(window.project.get(2026, 2)[1].constraints["min_open_staff"], 3)
        self.assertEqual(window.project.get(2026, 3)[1].constraints["min_open_staff"], 3)

    def test_config_edit_does_not_affect_earlier_months(self):
        window = self._window_with_months((2026, 1), (2026, 2))

        window.shop_config.constraints["min_open_staff"] = 99  # na miesiącu 2

        self.assertEqual(window.project.get(2026, 1)[1].constraints["min_open_staff"], 3)

    def test_config_edit_is_inherited_by_a_brand_new_month_created_afterwards(self):
        window = self._window_with_months((2026, 1),)
        window.shop_config.constraints["min_open_staff"] = 99

        window._switch_to_month(2026, 2)  # nowy miesiąc, tworzony po edycji

        self.assertEqual(window.shop_config.constraints["min_open_staff"], 99)

    def test_new_employee_does_not_appear_in_other_already_existing_months(self):
        window = self._window_with_months((2026, 1), (2026, 2))

        window._switch_to_month(2026, 1)
        emp = Employee(last_name="Kowalski", first_name="Jan")
        window.schedule.add_employee(emp)

        self.assertEqual(window.project.get(2026, 2)[0].employees, [])


class MonthScopeNoteTests(unittest.TestCase):
    def test_format_month_label(self):
        from logic.utils.time_utils import format_month_label

        self.assertEqual(format_month_label(2026, 1), "Styczeń 2026")
        self.assertEqual(format_month_label(2026, 1, capitalize=False), "styczeń 2026")

    def test_scope_note_mentions_the_month_and_the_isolation_rule(self):
        from logic.utils.time_utils import month_scope_note

        note = month_scope_note(2026, 5)
        self.assertIn("maj 2026", note)
        self.assertIn("dotychczasowe ustawienia", note)

    def test_config_dialog_shows_scope_note(self):
        from ui.config_dialog import ConfigDialog

        shop = ShopConfig(2026, 5)
        dialog = ConfigDialog(None, shop)
        note = _find_label(dialog, "quickInfoHint")
        self.assertIsNotNone(note)
        self.assertIn("maj 2026", note.text())

    def test_locations_dialog_shows_scope_note(self):
        from ui.locations_dialog import LocationsDialog

        shop = ShopConfig(2026, 6)
        dialog = LocationsDialog(None, shop)
        note = _find_label(dialog, "quickInfoHint")
        self.assertIsNotNone(note)
        self.assertIn("czerwiec 2026", note.text())

    def test_employee_dialog_shows_scope_note_when_shop_config_given(self):
        from ui.employee_dialog import EmployeeDialog

        shop = ShopConfig(2026, 7)
        dialog = EmployeeDialog(None, shop_config=shop)
        note = _find_label(dialog, "quickInfoHint")
        self.assertIsNotNone(note)
        self.assertIn("lipiec 2026", note.text())

    def test_employee_dialog_survives_without_shop_config(self):
        from ui.employee_dialog import EmployeeDialog

        dialog = EmployeeDialog(None, shop_config=None)
        self.assertIsNone(_find_label(dialog, "quickInfoHint"))


def _find_label(widget, object_name):
    from PySide6.QtWidgets import QLabel

    return widget.findChild(QLabel, object_name)


if __name__ == "__main__":
    unittest.main()
