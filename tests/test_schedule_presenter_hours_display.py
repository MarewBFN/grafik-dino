"""Menu Wygląd -> "Widok trybu szybkiego" (ui/main_window.py::_build_menu) -
`ShopConfig.hours_display_mode` ("standard" | "fractions") steruje tym, jak
godziny zmiany są pokazywane w komórce siatki grafiku, W OBU widokach:
- widok kompaktowy (ui/grid_view.py::ScheduleGrid.compact_mode, domyślny -
  to jest to, co użytkownik nazywa "trybem szybkim"): dziś skróty "N"/"1"/"2",
  "fractions" pokazuje zamiast nich realne godziny jako ułamek.
- widok rozszerzony (logic/schedule_presenter.py::SchedulePresenter.get_cell_view,
  przycisk "Rozszerz widok"): dziś dwie osobne linie "HH:MM"/"HH:MM",
  "fractions" ściska je do jednej linii.

Oba widoki współdzielą formatowanie ułamka (logic/utils/time_utils.py::
format_hours_as_fraction/fraction_hour) - "8:00-20:00" -> "8\n20" (godzina
początku nad godziną końca, jedna cyfra pod drugą - żeby zmieściło się w
wąskiej komórce - bez zera wiodącego, minuty na razie tylko zaokrąglane do
najbliższej pełnej godziny - dokładniejszy zapis to świadomie odłożone
rozszerzenie). Zmiany przez północ NIE dostają znacznika "(+1)" - usunięty
całkiem na życzenie użytkownika, tło komórki (SHIFT_NIGHT) już odróżnia
zmianę nocną."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from logic.schedule_presenter import SchedulePresenter
from logic.utils.time_utils import fraction_hour, format_hours_as_fraction
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from ui.grid_view import ScheduleGrid


def _schedule_with_employee():
    emp = Employee(last_name="Kowalski", first_name="Jan")
    schedule = MonthSchedule(2026, 3, employees=[emp])
    return schedule, emp


class FractionHelperTests(unittest.TestCase):
    def test_drops_leading_zero(self):
        self.assertEqual(fraction_hour("08:00"), "8")

    def test_rounds_down_below_half_past(self):
        self.assertEqual(fraction_hour("08:15"), "8")

    def test_rounds_up_at_half_past_or_later(self):
        self.assertEqual(fraction_hour("08:30"), "9")

    def test_wraps_past_midnight(self):
        self.assertEqual(fraction_hour("23:45"), "0")

    def test_format_hours_as_fraction(self):
        self.assertEqual(format_hours_as_fraction("08:00", "20:00"), "8\n20")


class HoursDisplayModeDefaultTests(unittest.TestCase):
    def test_default_is_standard(self):
        shop = ShopConfig(2026, 3)
        self.assertEqual(shop.hours_display_mode, "standard")


class HoursDisplayModePersistenceTests(unittest.TestCase):
    def test_round_trips_through_to_dict_from_dict(self):
        shop = ShopConfig(2026, 3)
        shop.hours_display_mode = "fractions"

        loaded = ShopConfig.from_dict(shop.to_dict())

        self.assertEqual(loaded.hours_display_mode, "fractions")

    def test_missing_field_defaults_to_standard(self):
        shop = ShopConfig(2026, 3)
        data = shop.to_dict()
        del data["hours_display_mode"]

        loaded = ShopConfig.from_dict(data)

        self.assertEqual(loaded.hours_display_mode, "standard")


class StandardModeUnchangedTests(unittest.TestCase):
    """Regresja: "standard" musi zostać dokładnie tym, co było zanim ta
    funkcja istniała (domyślny tryb, nieużywany dziś nigdzie indziej)."""

    def test_regular_shift(self):
        schedule, emp = _schedule_with_employee()
        schedule.get_day(emp, 3).set_hours("08:00", "20:00")
        shop = ShopConfig(2026, 3)

        cv = SchedulePresenter(schedule, shop).get_cell_view(emp, 3)

        self.assertEqual(cv.text_start, "08:00")
        self.assertEqual(cv.text_end, "20:00")

    def test_crosses_midnight(self):
        schedule, emp = _schedule_with_employee()
        schedule.get_day(emp, 3).set_hours("22:00", "06:00")
        shop = ShopConfig(2026, 3)

        cv = SchedulePresenter(schedule, shop).get_cell_view(emp, 3)

        self.assertEqual(cv.text_start, "22:00")
        self.assertEqual(cv.text_end, "06:00")


class FractionsModeTests(unittest.TestCase):
    def _presenter(self, schedule):
        shop = ShopConfig(2026, 3)
        shop.hours_display_mode = "fractions"
        return SchedulePresenter(schedule, shop)

    def test_regular_shift_becomes_a_single_fraction_line(self):
        schedule, emp = _schedule_with_employee()
        schedule.get_day(emp, 3).set_hours("08:00", "20:00")

        cv = self._presenter(schedule).get_cell_view(emp, 3)

        self.assertEqual(cv.text_start, "8\n20")
        self.assertEqual(cv.text_end, "")

    def test_crosses_midnight_becomes_a_single_fraction_line_without_marker(self):
        schedule, emp = _schedule_with_employee()
        schedule.get_day(emp, 3).set_hours("22:00", "06:00")

        cv = self._presenter(schedule).get_cell_view(emp, 3)

        self.assertEqual(cv.text_start, "22\n6")
        self.assertEqual(cv.text_end, "")

    def test_partial_hours_round_down_below_half_past(self):
        schedule, emp = _schedule_with_employee()
        schedule.get_day(emp, 3).set_hours("08:15", "16:00")

        cv = self._presenter(schedule).get_cell_view(emp, 3)

        self.assertEqual(cv.text_start, "8\n16")

    def test_partial_hours_round_up_at_half_past_or_later(self):
        schedule, emp = _schedule_with_employee()
        schedule.get_day(emp, 3).set_hours("08:30", "16:45")

        cv = self._presenter(schedule).get_cell_view(emp, 3)

        self.assertEqual(cv.text_start, "9\n17")

    def test_total_hours_are_not_affected(self):
        schedule, emp = _schedule_with_employee()
        schedule.get_day(emp, 3).set_hours("08:00", "20:00")

        cv = self._presenter(schedule).get_cell_view(emp, 3)

        self.assertEqual(cv.text_total, "12:00")

    def test_shift_starting_at_open_time_is_still_converted_to_a_fraction(self):
        # Nie ma już osobnej etykiety "OTW" (usunięta na życzenie
        # użytkownika - zostaje tylko kolor tła komórki), więc taka zmiana
        # podlega dokładnie tej samej konwersji co każda inna.
        emp = Employee(last_name="Kowalski", first_name="Jan", daily_hours=8)
        schedule = MonthSchedule(2026, 3, employees=[emp])
        shop = ShopConfig(2026, 3)
        shop.hours_display_mode = "fractions"

        location = shop.get_location(emp)
        open_t, close_t = location.get_open_hours_for_day(3)
        schedule.get_day(emp, 3).set_hours(open_t, "13:00")

        cv = SchedulePresenter(schedule, shop).get_cell_view(emp, 3)

        self.assertEqual(cv.text_start, format_hours_as_fraction(open_t, "13:00"))
        self.assertEqual(cv.text_end, "")

    def test_leave_day_is_not_affected(self):
        schedule, emp = _schedule_with_employee()
        schedule.get_day(emp, 3).set_leave()

        cv = self._presenter(schedule).get_cell_view(emp, 3)

        self.assertEqual(cv.text_start, "🌴")


class CompactModeGridCellTests(unittest.TestCase):
    """To jest widok, który użytkownik nazywa "trybem szybkim" -
    ScheduleGrid.compact_mode (domyślny widok, przed kliknięciem "Rozszerz
    widok"). Pierwsza wersja tej funkcji zmieniała tylko widok rozszerzony
    (logic/schedule_presenter.py), który w praktyce jest rzadziej używany -
    ta klasa pilnuje, żeby "fractions" faktycznie zmieniało to, co
    użytkownik widzi na co dzień."""

    def _grid(self, schedule, shop):
        grid = ScheduleGrid()
        grid.compact_mode = True
        grid.set_data(schedule, shop, controller=MagicMock())
        grid.refresh()
        return grid

    def test_standard_mode_is_unchanged_regular_shift(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        schedule = MonthSchedule(2026, 3, employees=[emp])
        schedule.get_day(emp, 3).set_hours("08:00", "20:00")
        shop = ShopConfig(2026, 3)

        grid = self._grid(schedule, shop)

        self.assertEqual(grid.item(0, 3).text(), "1")

    def test_standard_mode_is_unchanged_crosses_midnight(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        schedule = MonthSchedule(2026, 3, employees=[emp])
        schedule.get_day(emp, 3).set_hours("22:00", "06:00")
        shop = ShopConfig(2026, 3)

        grid = self._grid(schedule, shop)

        self.assertEqual(grid.item(0, 3).text(), "N")

    def test_fractions_mode_shows_the_actual_hours(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        schedule = MonthSchedule(2026, 3, employees=[emp])
        schedule.get_day(emp, 3).set_hours("08:00", "20:00")
        shop = ShopConfig(2026, 3)
        shop.hours_display_mode = "fractions"

        grid = self._grid(schedule, shop)

        self.assertEqual(grid.item(0, 3).text(), "8\n20")

    def test_fractions_mode_shows_shifts_crossing_midnight_without_marker(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        schedule = MonthSchedule(2026, 3, employees=[emp])
        schedule.get_day(emp, 3).set_hours("22:00", "06:00")
        shop = ShopConfig(2026, 3)
        shop.hours_display_mode = "fractions"

        grid = self._grid(schedule, shop)

        self.assertEqual(grid.item(0, 3).text(), "22\n6")

    def test_fractions_mode_rounds_partial_hours(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        schedule = MonthSchedule(2026, 3, employees=[emp])
        schedule.get_day(emp, 3).set_hours("08:30", "16:45")
        shop = ShopConfig(2026, 3)
        shop.hours_display_mode = "fractions"

        grid = self._grid(schedule, shop)

        self.assertEqual(grid.item(0, 3).text(), "9\n17")

    def test_switching_mode_and_refreshing_updates_existing_cells(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        schedule = MonthSchedule(2026, 3, employees=[emp])
        schedule.get_day(emp, 3).set_hours("08:00", "20:00")
        shop = ShopConfig(2026, 3)

        grid = self._grid(schedule, shop)
        self.assertEqual(grid.item(0, 3).text(), "1")

        shop.hours_display_mode = "fractions"
        grid.refresh()

        self.assertEqual(grid.item(0, 3).text(), "8\n20")


class MainWindowMenuWiringTests(unittest.TestCase):
    """ui/main_window.py::_build_menu - nowe menu "Wygląd" i jego
    podmenu "Widok trybu szybkiego". Pełna konstrukcja MainWindow() w
    izolowanym katalogu roboczym (patrz tests/test_main_window_tutorial_content.py),
    żeby autozapis last_project.json nie dotknął prawdziwego katalogu
    projektu."""

    def _window(self):
        import tempfile
        from ui.main_window import MainWindow

        tmp_dir = tempfile.mkdtemp()
        cwd = os.getcwd()
        os.chdir(tmp_dir)
        try:
            return MainWindow()
        finally:
            os.chdir(cwd)

    def test_wyglad_menu_exists_between_konfiguracja_and_pomoc(self):
        window = self._window()

        titles = [a.text() for a in window.menuBar().actions()]
        self.assertIn("Wygląd", titles)
        self.assertLess(titles.index("Konfiguracja"), titles.index("Wygląd"))
        self.assertLess(titles.index("Wygląd"), titles.index("Pomoc"))

    def test_standard_is_checked_by_default(self):
        window = self._window()

        self.assertTrue(window.hours_display_standard_action.isChecked())
        self.assertFalse(window.hours_display_fractions_action.isChecked())

    def test_triggering_fractions_updates_shop_config_and_checked_state(self):
        window = self._window()

        window.hours_display_fractions_action.trigger()

        self.assertEqual(window.shop_config.hours_display_mode, "fractions")
        self.assertFalse(window.hours_display_standard_action.isChecked())
        self.assertTrue(window.hours_display_fractions_action.isChecked())

    def test_sync_everything_keeps_menu_in_sync_with_shop_config(self):
        window = self._window()

        # Zmiana "z zewnątrz" (np. wczytanie projektu) - nie przez
        # _set_hours_display_mode - musi się i tak odzwierciedlić.
        window.shop_config.hours_display_mode = "fractions"
        window._update_hours_display_menu()

        self.assertTrue(window.hours_display_fractions_action.isChecked())


if __name__ == "__main__":
    unittest.main()
