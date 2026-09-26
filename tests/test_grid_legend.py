"""ui/grid_legend.py::GridLegendWidget - legenda kolorów/zakreśleń komórek
siatki grafiku, zawsze pod ScheduleGrid, na życzenie użytkownika. Osobna
stylizacja dla >10 widocznych pracowników (patrz
ui/main_window.py::_update_grid_legend) - wyraźnie oddzielona sekcja
zamiast wtopionego w panel paska."""

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

from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from ui.grid_legend import GridLegendWidget, LEGEND_ENTRIES


class ShowGridLegendPersistenceTests(unittest.TestCase):
    def test_default_is_hidden(self):
        shop = ShopConfig(2026, 3)
        self.assertFalse(shop.show_grid_legend)

    def test_round_trips_through_to_dict_from_dict(self):
        shop = ShopConfig(2026, 3)
        shop.show_grid_legend = True

        loaded = ShopConfig.from_dict(shop.to_dict())

        self.assertTrue(loaded.show_grid_legend)

    def test_missing_field_defaults_to_hidden(self):
        shop = ShopConfig(2026, 3)
        data = shop.to_dict()
        del data["show_grid_legend"]

        loaded = ShopConfig.from_dict(data)

        self.assertFalse(loaded.show_grid_legend)


class GridLegendWidgetTests(unittest.TestCase):
    def test_renders_one_entry_per_legend_item(self):
        legend = GridLegendWidget()
        self.assertEqual(legend.layout().count(), len(LEGEND_ENTRIES))

    def test_every_entry_has_a_non_empty_label(self):
        for kind, color, label in LEGEND_ENTRIES:
            self.assertIn(kind, ("solid", "hatch"))
            self.assertTrue(label)
            if kind == "solid":
                self.assertIsNotNone(color)

    def test_default_section_style_is_not_compact(self):
        legend = GridLegendWidget()
        self.assertIn("transparent", legend.styleSheet())

    def test_compact_section_gets_a_distinct_border(self):
        legend = GridLegendWidget()
        legend.set_compact_section(True)
        self.assertIn("border-top", legend.styleSheet())

    def test_toggling_back_to_non_compact_restores_transparent_style(self):
        legend = GridLegendWidget()
        legend.set_compact_section(True)
        legend.set_compact_section(False)
        self.assertIn("transparent", legend.styleSheet())
        self.assertNotIn("border-top", legend.styleSheet())


class MainWindowLegendWiringTests(unittest.TestCase):
    """ui/main_window.py::_update_grid_legend - próg 10 pracowników liczony
    po pracownikach WIDOCZNYCH (przefiltrowanych po lokalizacji, tak jak w
    samej siatce), nie po całym projekcie."""

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

    def test_ten_or_fewer_employees_is_not_compact(self):
        window = self._window()
        for i in range(10):
            window.schedule.add_employee(Employee(last_name=f"E{i}", first_name=""))
        window._sync_everything()

        self.assertEqual(len(window.grid.get_visible_employees()), 10)
        self.assertIn("transparent", window.grid_legend.styleSheet())

    def test_more_than_ten_employees_is_compact(self):
        window = self._window()
        for i in range(11):
            window.schedule.add_employee(Employee(last_name=f"E{i}", first_name=""))
        window._sync_everything()

        self.assertEqual(len(window.grid.get_visible_employees()), 11)
        self.assertIn("border-top", window.grid_legend.styleSheet())

    def test_legend_is_hidden_by_default(self):
        window = self._window()
        self.assertTrue(window.grid_legend.isHidden())
        self.assertFalse(window.show_grid_legend_action.isChecked())

    def test_menu_toggle_shows_and_hides_the_legend(self):
        window = self._window()

        window.show_grid_legend_action.trigger()
        self.assertFalse(window.grid_legend.isHidden())
        self.assertTrue(window.show_grid_legend_action.isChecked())
        self.assertTrue(window.shop_config.show_grid_legend)

        window.show_grid_legend_action.trigger()
        self.assertTrue(window.grid_legend.isHidden())
        self.assertFalse(window.show_grid_legend_action.isChecked())
        self.assertFalse(window.shop_config.show_grid_legend)

    def test_sync_everything_keeps_menu_in_sync_with_shop_config(self):
        window = self._window()
        window.shop_config.show_grid_legend = True
        window._update_grid_legend()
        self.assertTrue(window.show_grid_legend_action.isChecked())
        self.assertFalse(window.grid_legend.isHidden())

    def test_legend_never_takes_the_grid_stretch_factor(self):
        """Legenda musi mieć stretch=0 w prawym panelu - siatka (self.grid)
        ma być jedynym widgetem, który rośnie i kurczy się z oknem."""
        window = self._window()
        layout = window.grid.parentWidget().layout()

        grid_index = layout.indexOf(window.grid)
        legend_index = layout.indexOf(window.grid_legend)

        self.assertGreater(legend_index, grid_index)
        self.assertEqual(layout.stretch(legend_index), 0)
        self.assertEqual(layout.stretch(grid_index), 1)


if __name__ == "__main__":
    unittest.main()
