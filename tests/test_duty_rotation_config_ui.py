import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from model.location import LocationConfig
from model.shop_config import ShopConfig
from ui.config_dialog import ConfigDialog

ROTATION = {
    "weekday_long": {"start": "06:00", "end": "22:00"},
    "weekday_short": {"start": "22:00", "end": "06:00"},
    "weekend_full": {"start": "06:00"},
    "weekend_half_a": {"start": "06:00", "end": "18:00"},
    "weekend_half_b": {"start": "18:00", "end": "06:00"},
    "only_12_24h": False,
}


def test_toggle_absent_without_any_duty_rotation():
    shop = ShopConfig(2026, 8)  # dino_retail, no duty_rotation anywhere
    dialog = ConfigDialog(None, shop)
    assert dialog.only_12_24h is None


def test_toggle_present_and_unchecked_for_project_level_rotation():
    shop = ShopConfig(2026, 8)
    shop.set_duty_rotation(ROTATION)
    dialog = ConfigDialog(None, shop)
    assert dialog.only_12_24h is not None
    assert dialog.only_12_24h.isChecked() is False


def test_toggle_checked_when_only_12_24h_already_set():
    shop = ShopConfig(2026, 8)
    shop.set_duty_rotation({**ROTATION, "only_12_24h": True})
    dialog = ConfigDialog(None, shop)
    assert dialog.only_12_24h.isChecked() is True


def test_checking_the_toggle_and_saving_updates_project_level_rotation():
    shop = ShopConfig(2026, 8)
    shop.set_duty_rotation(ROTATION)
    dialog = ConfigDialog(None, shop)

    dialog.only_12_24h.setChecked(True)
    dialog._save()

    assert shop.get_duty_rotation()["only_12_24h"] is True
    # Other windows survive the round-trip untouched.
    assert shop.get_duty_rotation()["weekend_half_a"] == ROTATION["weekend_half_a"]


def test_unchecking_the_toggle_restores_weekday_shifts():
    shop = ShopConfig(2026, 8)
    shop.set_duty_rotation({**ROTATION, "only_12_24h": True})
    dialog = ConfigDialog(None, shop)

    dialog.only_12_24h.setChecked(False)
    dialog._save()

    assert shop.get_duty_rotation()["only_12_24h"] is False
    assert shop.get_duty_rotation()["weekday_long"] == ROTATION["weekday_long"]


def test_unchecking_without_configured_weekday_windows_shows_an_error(monkeypatch):
    """Sam toggle nie daje jeszcze UI do wpisania godzin weekday_long/short -
    wyłączenie only_12_24h dla lokalizacji, która nigdy ich nie miała, musi
    być zgłoszone jako błąd konfiguracji, nie ciche uszkodzenie danych."""
    shop = ShopConfig(2026, 8)
    shop.set_duty_rotation({
        "only_12_24h": True,
        "weekend_full": {"start": "06:00"},
        "weekend_half_a": {"start": "06:00", "end": "18:00"},
        "weekend_half_b": {"start": "18:00", "end": "06:00"},
    })
    dialog = ConfigDialog(None, shop)
    dialog.only_12_24h.setChecked(False)

    shown = []
    monkeypatch.setattr(
        "ui.config_dialog.QMessageBox.critical",
        lambda *args, **kwargs: shown.append(args),
    )

    dialog._save()

    assert shown, "expected a QMessageBox.critical error when weekday windows are missing"
    # Untouched - the save aborted before committing the invalid config.
    assert shop.get_duty_rotation()["only_12_24h"] is True


def test_location_duty_rotation_survives_a_config_save_round_trip():
    """Regresja: _LocationRow nie niesie duty_rotation (brak UI do jego
    edycji), więc rekonstrukcja LocationConfig przy zapisie musiała się
    nauczyć nie gubić tego, czego sama nie edytuje."""
    # Klucz musi być tym, co faktycznie wyprodukowałby slugify(name) przy
    # zapisie (patrz ConfigDialog._save()) - tak jak w prawdziwym UI, gdzie
    # klucz zawsze powstaje z nazwy, nigdy nie jest wybierany niezależnie.
    shop = ShopConfig(2026, 8)
    loc = LocationConfig(key="site_1", name="Site 1")
    loc.set_duty_rotation(ROTATION)
    shop.locations["site_1"] = loc

    dialog = ConfigDialog(None, shop)
    dialog._save()

    assert shop.locations["site_1"].get_duty_rotation() == ROTATION
