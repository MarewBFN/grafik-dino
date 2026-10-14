"""Poprawki błędów znalezionych przy migracji na kwalifikacje (Krok 2.1):
etykieta czasu pracy w trybie szybkim przy niepoprawnej godzinie i jedno okno
dostępności zapisane bez listy."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from logic.generator.availability_mapper import get_allowed_shifts_for_day
from model.employee import Employee
from model.location import LocationConfig
from model.shop_config import ShopConfig

_app = QApplication.instance() or QApplication([])


class _Input:
    def __init__(self, text):
        self.text = text

    def get_time_str(self):
        return self.text


class _Label:
    text = None

    def setText(self, text):
        self.text = text


class _QuickPanel:
    def __init__(self, start, end):
        self.start_input, self.end_input = _Input(start), _Input(end)
        self.quick_duration_label = _Label()


def test_quick_duration_with_invalid_time_does_not_raise():
    from ui.main_window import MainWindow

    panel = _QuickPanel("25:99", "14:00")
    MainWindow._quick_update_duration(panel)  # wcześniej NameError
    assert panel.quick_duration_label.text == "Czas pracy: –"

    panel = _QuickPanel("06:00", "14:30")
    MainWindow._quick_update_duration(panel)
    assert panel.quick_duration_label.text == "Czas pracy: 8:30"


def _allowed(availability):
    shop = ShopConfig(2026, 8)
    shop.locations = {"s": LocationConfig(key="s", name="S", open_hours={wd: ("06:00", "22:00") for wd in range(7)})}
    emp = Employee("A", "", location_key="s", availability=availability)
    # 2026-08-03 - poniedziałek (weekday 0).
    return get_allowed_shifts_for_day(emp, 3, shop, 0, 1, {}, {})


def test_single_availability_window_without_list_works_like_list():
    window = {"start": "06:00", "end": "14:00", "mode": "hard"}
    assert _allowed({0: window}) == _allowed({0: [window]}) == [0]
