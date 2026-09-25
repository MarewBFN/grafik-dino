"""Konfiguracja -> "Godziny otwarcia" now edits the CURRENTLY SELECTED
location directly (same data as Konfiguracja -> Lokalizacje for that
location), instead of a separate project-wide ShopConfig.open_hours - see
ui/config_dialog.py (location_key param) and ui/main_window.py::_open_config.

Also covers the "Rozwiń/Zwiń" per-location hours collapse toggle in
ui/locations_dialog.py."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from model.location import LocationConfig
from model.shop_config import ShopConfig
from ui.config_dialog import ConfigDialog
from ui.locations_dialog import LocationsDialog, _LocationRow


def test_hours_tab_shows_the_selected_locations_name():
    shop = ShopConfig(2026, 8)
    loc = LocationConfig(key="site1", name="Galeria Płn")
    shop.locations["site1"] = loc

    dialog = ConfigDialog(None, shop, location_key="site1")

    assert "Galeria Płn" in dialog.location.name


def test_hours_tab_loads_the_selected_locations_own_hours():
    shop = ShopConfig(2026, 8)  # project default: 05:30-22:45/23:00
    loc = LocationConfig(key="site1", name="Site 1")
    loc.open_hours[0] = ("08:00", "20:00")
    shop.locations["site1"] = loc

    dialog = ConfigDialog(None, shop, location_key="site1")

    start_edit, end_edit = dialog.hours_editor._edits[0]
    assert start_edit.get_time_str() == "08:00"
    assert end_edit.get_time_str() == "20:00"


def test_saving_hours_tab_writes_to_the_location_not_the_project():
    shop = ShopConfig(2026, 8)
    loc = LocationConfig(key="site1", name="Site 1")
    shop.locations["site1"] = loc
    original_project_hours = dict(shop.open_hours)

    dialog = ConfigDialog(None, shop, location_key="site1")
    start_edit, end_edit = dialog.hours_editor._edits[0]
    start_edit.set_time_str("09:00")
    end_edit.set_time_str("17:00")

    dialog._save()

    assert loc.open_hours[0] == ("09:00", "17:00")
    assert shop.open_hours == original_project_hours


def test_no_location_key_falls_back_to_project_wide_hours():
    """Back-compat for callers that don't pass location_key (e.g. old tests)."""
    shop = ShopConfig(2026, 8)

    dialog = ConfigDialog(None, shop)
    assert dialog.location is None

    start_edit, end_edit = dialog.hours_editor._edits[0]
    start_edit.set_time_str("09:00")
    end_edit.set_time_str("17:00")
    dialog._save()

    assert shop.open_hours[0] == ("09:00", "17:00")


def _row(is_24_7=False):
    return _LocationRow(lambda r: None, name="Test", is_24_7=is_24_7)


def test_hours_editor_collapsed_by_default_for_a_non_24_7_location():
    row = _row(is_24_7=False)
    assert row._hours_expanded is False
    assert row.toggle_hours_btn.text() == "Rozwiń"


def test_toggle_button_expands_and_collapses_the_hours_editor():
    row = _row(is_24_7=False)

    row._toggle_hours_expanded()
    assert row._hours_expanded is True
    assert row.toggle_hours_btn.text() == "Zwiń"

    row._toggle_hours_expanded()
    assert row._hours_expanded is False
    assert row.toggle_hours_btn.text() == "Rozwiń"


def test_24_7_location_hides_the_toggle_button_and_the_hours_editor():
    row = _row(is_24_7=True)
    row._update_hours_visibility()
    assert row.toggle_hours_btn.isHidden()
    assert row.hours_editor.isHidden()


def test_turning_on_24_7_hides_hours_regardless_of_expand_state():
    row = _row(is_24_7=False)
    row._toggle_hours_expanded()  # expand it first
    assert row._hours_expanded is True

    row.is_24_7_check.setChecked(True)

    assert row.toggle_hours_btn.isHidden()
    assert row.hours_editor.isHidden()


def test_turning_off_24_7_restores_the_previous_expand_state():
    row = _row(is_24_7=False)
    row._toggle_hours_expanded()  # expanded
    row.is_24_7_check.setChecked(True)
    row.is_24_7_check.setChecked(False)

    assert row._hours_expanded is True
    assert not row.toggle_hours_btn.isHidden()
    assert not row.hours_editor.isHidden()


# --- "Zamknięte w polskie święta ustawowe" (LocationConfig.
# closed_on_public_holidays) - patrz model/location.py, zgłoszenie
# użytkownika 2026-09-25 ---


def test_new_location_row_defaults_to_closed_on_public_holidays():
    row = _row()
    assert row.closed_on_public_holidays_check.isChecked() is True


def test_locations_dialog_saves_closed_on_public_holidays_per_row():
    shop = ShopConfig(2026, 8)
    dialog = LocationsDialog(None, shop)
    row = dialog._location_rows[0]
    row.closed_on_public_holidays_check.setChecked(False)

    dialog._save()

    saved = next(iter(shop.locations.values()))
    assert saved.closed_on_public_holidays is False


def test_locations_dialog_loads_existing_locations_closed_on_public_holidays():
    shop = ShopConfig(2026, 8)
    loc = LocationConfig(key="site1", name="Site 1", closed_on_public_holidays=False)
    shop.locations = {"site1": loc}

    dialog = LocationsDialog(None, shop)

    assert dialog._location_rows[0].closed_on_public_holidays_check.isChecked() is False


def test_config_dialog_hours_tab_loads_and_saves_closed_on_public_holidays():
    shop = ShopConfig(2026, 8)
    loc = LocationConfig(key="site1", name="Site 1", closed_on_public_holidays=False)
    shop.locations["site1"] = loc

    dialog = ConfigDialog(None, shop, location_key="site1")
    assert dialog.closed_on_public_holidays_check.isChecked() is False

    dialog.closed_on_public_holidays_check.setChecked(True)
    dialog._save()

    assert shop.locations["site1"].closed_on_public_holidays is True
