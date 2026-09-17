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
        {"name": "Zmiana 16h", "start": "06:00", "end": "22:00", "full_day": False},
        {"name": "Doba 24h", "start": "06:00", "end": None, "full_day": True},
    ]


def test_rows_with_empty_name_are_skipped_on_save():
    dialog = QuickModeSettingsDialog(None, [])
    dialog._add_row("", "06:00", "22:00")
    dialog._add_row("Zmiana", "06:00", "22:00")

    dialog._save()

    assert dialog.result_presets == [
        {"name": "Zmiana", "start": "06:00", "end": "22:00", "full_day": False},
    ]


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
