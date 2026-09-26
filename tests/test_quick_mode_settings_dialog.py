import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from ui.quick_mode_settings_dialog import QuickModeSettingsDialog


def test_dialog_builds_one_row_per_existing_preset():
    presets = [
        {"name": "Zmiana 16h", "start": "06:00", "end": "22:00", "full_day": False},
        {"name": "Doba 24h", "start": "06:00", "end": None, "full_day": True},
    ]
    dialog = QuickModeSettingsDialog(None, presets)

    assert len(dialog._rows) == 2
    assert dialog._rows[0].name() == "Zmiana 16h"
    assert dialog._rows[1].is_full_day() is True


def test_full_day_checkbox_disables_end_input():
    dialog = QuickModeSettingsDialog(None, [])
    dialog._add_row("Doba", "06:00", "06:00", full_day=False)
    row = dialog._rows[0]

    assert row.end_input.isEnabled() is True
    row.full_day_check.setChecked(True)
    assert row.end_input.isEnabled() is False


def test_saving_produces_normalized_presets():
    dialog = QuickModeSettingsDialog(None, [])
    dialog._add_row("Zmiana 16h", "06:00", "22:00", full_day=False)
    dialog._add_row("Doba 24h", "06:00", "06:00", full_day=True)

    dialog._save()

    assert dialog.result_presets == [
        {"name": "Zmiana 16h", "start": "06:00", "end": "22:00", "full_day": False, "visible": True},
        {"name": "Doba 24h", "start": "06:00", "end": None, "full_day": True, "visible": True},
    ]


def test_rows_with_empty_name_are_skipped_on_save():
    dialog = QuickModeSettingsDialog(None, [])
    dialog._add_row("", "06:00", "22:00")
    dialog._add_row("Zmiana", "06:00", "22:00")

    dialog._save()

    assert dialog.result_presets == [
        {"name": "Zmiana", "start": "06:00", "end": "22:00", "full_day": False, "visible": True},
    ]


def test_name_input_is_capped_at_ten_characters():
    dialog = QuickModeSettingsDialog(None, [])
    dialog._add_row()
    row = dialog._rows[0]

    row.name_edit.setText("Bardzo dlugi przedzial")

    assert len(row.name()) == 10


def test_show_checkbox_defaults_to_checked_for_new_rows():
    dialog = QuickModeSettingsDialog(None, [])
    dialog._add_row("Zmiana", "06:00", "22:00")

    assert dialog._rows[0].is_visible() is True


def test_unchecking_show_saves_preset_as_not_visible():
    dialog = QuickModeSettingsDialog(None, [])
    dialog._add_row("Zmiana", "06:00", "22:00")
    dialog._rows[0].show_check.setChecked(False)

    dialog._save()

    assert dialog.result_presets == [
        {"name": "Zmiana", "start": "06:00", "end": "22:00", "full_day": False, "visible": False},
    ]


def test_existing_hidden_preset_loads_with_show_unchecked():
    presets = [
        {"name": "Zmiana", "start": "06:00", "end": "22:00", "full_day": False, "visible": False},
    ]
    dialog = QuickModeSettingsDialog(None, presets)

    assert dialog._rows[0].is_visible() is False


def test_duplicate_names_show_an_error_and_do_not_accept(monkeypatch):
    dialog = QuickModeSettingsDialog(None, [])
    dialog._add_row("Zmiana", "06:00", "14:00")
    dialog._add_row("Zmiana", "14:00", "22:00")

    shown = []
    monkeypatch.setattr(
        "ui.quick_mode_settings_dialog.QMessageBox.critical",
        lambda *args, **kwargs: shown.append(args),
    )

    dialog._save()

    assert shown
    assert dialog.result_presets is None


def test_remove_row_drops_it_from_the_list():
    dialog = QuickModeSettingsDialog(None, [])
    dialog._add_row("Zmiana", "06:00", "14:00")
    row = dialog._rows[0]

    dialog._remove_row(row)

    assert dialog._rows == []
