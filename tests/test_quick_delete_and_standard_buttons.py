"""Przycisk "Usuń" w trybie szybkim (zeruje CAŁKOWICIE informacje o zmianie w
komórce, w odróżnieniu od "Wolne" - świadomej blokady) + konfigurowalna
widoczność wbudowanych przycisków trybu szybkiego (karta "Tryby domyślne" w
Ustawieniach trybu szybkiego) - decyzja użytkownika 2026-09-28."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from logic.schedule_controller import ScheduleController
from model.business_profile import DEFAULT_BUSINESS_TYPE, register_custom_profile
from model.custom_profile import CustomBusinessProfile
from model.day_schedule import DaySchedule
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import (
    STANDARD_QUICK_BUTTON_KEYS,
    STANDARD_QUICK_BUTTONS,
    ShopConfig,
    is_standard_button_visible,
    normalize_quick_mode_standard_buttons,
)
from ui.grid_view import ScheduleGrid, _quick_mode_context_menu_entries
from ui.quick_mode_settings_dialog import QuickModeSettingsDialog


class TestDayScheduleClear:
    def test_is_blank_true_for_a_fresh_day(self):
        assert DaySchedule().is_blank() is True

    def test_is_blank_false_once_anything_is_set(self):
        ds = DaySchedule()
        ds.set_hours("08:00", "16:00")
        assert ds.is_blank() is False

        ds2 = DaySchedule()
        ds2.is_locked = True
        assert ds2.is_blank() is False  # locked-as-off is NOT the same as blank

    def test_clear_resets_every_field_including_lock(self):
        ds = DaySchedule()
        ds.set_hours("08:00", "16:00")
        ds.is_locked = True

        ds.clear()

        assert ds == DaySchedule()
        assert ds.is_blank() is True

    def test_clear_resets_leave_sick_shift_class_and_full_day(self):
        ds = DaySchedule()
        ds.set_leave()
        ds.is_locked = True
        ds.shift_class = "W"
        ds.is_full_day = True  # deliberately inconsistent, just to prove clear() wipes it

        ds.clear()

        assert ds.is_leave is False
        assert ds.is_locked is False
        assert ds.shift_class is None
        assert ds.is_full_day is False
        assert ds.is_blank() is True


def test_schedule_controller_clear_day_resets_a_locked_manual_shift():
    shop = ShopConfig(2026, 8)
    schedule = MonthSchedule(2026, 8)
    emp = Employee(last_name="Kowalski", first_name="Jan")
    schedule.add_employee(emp)
    controller = ScheduleController(schedule, shop)

    controller.set_day_hours(emp, 3, "08:00", "16:00")
    assert schedule.get_day(emp, 3).is_locked is True

    controller.clear_day(emp, 3)

    ds = schedule.get_day(emp, 3)
    assert ds.is_blank() is True
    assert len(controller.history) == 2  # one snapshot per mutating call


def test_schedule_controller_clear_day_resets_leave():
    shop = ShopConfig(2026, 8)
    schedule = MonthSchedule(2026, 8)
    emp = Employee(last_name="Kowalski", first_name="Jan")
    schedule.add_employee(emp)
    controller = ScheduleController(schedule, shop)

    controller.set_day_leave(emp, 5)
    controller.clear_day(emp, 5)

    assert schedule.get_day(emp, 5).is_blank() is True


def test_schedule_controller_clear_day_is_a_noop_on_an_already_blank_day():
    shop = ShopConfig(2026, 8)
    schedule = MonthSchedule(2026, 8)
    emp = Employee(last_name="Kowalski", first_name="Jan")
    schedule.add_employee(emp)
    controller = ScheduleController(schedule, shop)

    controller.clear_day(emp, 5)

    assert controller.history == []  # no snapshot taken - genuinely nothing to undo


def test_schedule_controller_clear_day_supports_undo():
    shop = ShopConfig(2026, 8)
    schedule = MonthSchedule(2026, 8)
    emp = Employee(last_name="Kowalski", first_name="Jan")
    schedule.add_employee(emp)
    controller = ScheduleController(schedule, shop)

    controller.set_day_hours(emp, 3, "08:00", "16:00")
    controller.clear_day(emp, 3)
    assert schedule.get_day(emp, 3).is_blank() is True

    controller.undo()
    # undo() reassigns controller.schedule to a new object restored from the
    # snapshot - read back through the controller, not the now-stale local
    # `schedule` reference (same idiom as elsewhere in this test suite).
    ds = controller.get_day(emp, 3)
    assert (ds.start, ds.end, ds.is_locked) == ("08:00", "16:00", True)


def _grid_for_delete(business_type=DEFAULT_BUSINESS_TYPE):
    emp = Employee(last_name="Kowalski", first_name="Jan")
    schedule = MonthSchedule(2026, 9, employees=[emp])
    shop = ShopConfig(2026, 9)
    shop.business_type = business_type
    controller = ScheduleController(schedule, shop)

    main_window = SimpleNamespace(
        shop_config=shop,
        quick_mode_enabled=True,
        quick_selected_shift="DELETE",
    )

    grid = ScheduleGrid()
    grid.set_data(schedule, shop, controller, main_window=main_window)
    return grid, schedule, emp, controller


def test_clicking_a_cell_with_delete_selected_clears_a_manual_shift():
    grid, schedule, emp, controller = _grid_for_delete()
    controller.set_day_hours(emp, 1, "08:00", "16:00")

    grid._apply_quick_shift(0, 1)

    assert schedule.get_day(emp, 1).is_blank() is True


def test_clicking_a_cell_with_delete_selected_clears_leave():
    grid, schedule, emp, controller = _grid_for_delete()
    controller.set_day_leave(emp, 1)

    grid._apply_quick_shift(0, 1)

    assert schedule.get_day(emp, 1).is_blank() is True


class TestStandardQuickButtonsCatalog:
    def test_every_button_has_a_unique_key_label_and_description(self):
        keys = [b["key"] for b in STANDARD_QUICK_BUTTONS]
        assert len(keys) == len(set(keys))
        for button in STANDARD_QUICK_BUTTONS:
            assert button["label"].strip()
            assert button["description"].strip()

    def test_keys_tuple_matches_catalog_order(self):
        assert STANDARD_QUICK_BUTTON_KEYS == tuple(b["key"] for b in STANDARD_QUICK_BUTTONS)


class TestNormalizeQuickModeStandardButtons:
    def test_empty_or_none_normalizes_to_empty_dict(self):
        assert normalize_quick_mode_standard_buttons(None) == {}
        assert normalize_quick_mode_standard_buttons({}) == {}

    def test_unknown_keys_are_dropped(self):
        assert normalize_quick_mode_standard_buttons({"not_a_real_key": True}) == {}

    def test_known_keys_are_kept_and_coerced_to_bool(self):
        raw = {"delete": 1, "off": 0, "morning": True}
        normalized = normalize_quick_mode_standard_buttons(raw)
        assert normalized == {"delete": True, "off": False, "morning": True}


class TestIsStandardButtonVisible:
    def test_delete_defaults_to_visible_for_dino_and_custom_profiles(self):
        dino_shop = ShopConfig(2026, 3)
        assert is_standard_button_visible(dino_shop, "delete") is True

        custom_shop = ShopConfig(2026, 3)
        custom_shop.business_type = "some_custom_profile"
        assert is_standard_button_visible(custom_shop, "delete") is True

    def test_morning_afternoon_default_to_dino_only(self):
        dino_shop = ShopConfig(2026, 3)
        assert is_standard_button_visible(dino_shop, "morning") is True
        assert is_standard_button_visible(dino_shop, "afternoon") is True

        custom_shop = ShopConfig(2026, 3)
        custom_shop.business_type = "some_custom_profile"
        assert is_standard_button_visible(custom_shop, "morning") is False
        assert is_standard_button_visible(custom_shop, "afternoon") is False

    def test_can_work_defaults_to_non_dino_only(self):
        dino_shop = ShopConfig(2026, 3)
        assert is_standard_button_visible(dino_shop, "can_work") is False

        custom_shop = ShopConfig(2026, 3)
        custom_shop.business_type = "some_custom_profile"
        assert is_standard_button_visible(custom_shop, "can_work") is True

    def test_explicit_override_wins_over_profile_default(self):
        dino_shop = ShopConfig(2026, 3)
        dino_shop.quick_mode_standard_buttons = {"morning": False, "can_work": True}

        assert is_standard_button_visible(dino_shop, "morning") is False
        assert is_standard_button_visible(dino_shop, "can_work") is True

    def test_none_shop_config_falls_back_to_dino_defaults(self):
        assert is_standard_button_visible(None, "morning") is True
        assert is_standard_button_visible(None, "can_work") is False

    def test_unknown_key_is_never_visible(self):
        assert is_standard_button_visible(ShopConfig(2026, 3), "not_a_real_key") is False


class TestShopConfigStandardButtonsPersistence:
    def test_set_quick_mode_standard_buttons_normalizes(self):
        shop = ShopConfig(2026, 3)
        shop.set_quick_mode_standard_buttons({"delete": False, "bogus": True})
        assert shop.quick_mode_standard_buttons == {"delete": False}

    def test_round_trips_through_to_dict_from_dict(self):
        shop = ShopConfig(2026, 3)
        shop.set_quick_mode_standard_buttons({"delete": False, "can_work": True})

        restored = ShopConfig.from_dict(shop.to_dict())

        assert restored.quick_mode_standard_buttons == {"delete": False, "can_work": True}

    def test_old_project_without_the_field_defaults_to_empty_dict(self):
        shop = ShopConfig(2026, 3)
        data = shop.to_dict()
        del data["quick_mode_standard_buttons"]

        restored = ShopConfig.from_dict(data)

        assert restored.quick_mode_standard_buttons == {}
        # And behaves exactly like today - profile defaults still apply.
        assert is_standard_button_visible(restored, "delete") is True
        assert is_standard_button_visible(restored, "can_work") is False


class TestQuickModeSettingsDialogStandardButtonsTab:
    def test_builds_one_row_per_configurable_standard_button(self):
        dialog = QuickModeSettingsDialog(None, [])
        # "work" (Praca) is deliberately excluded - different UX, stays
        # permanently hidden regardless of this tab.
        assert set(dialog._standard_button_rows.keys()) == set(STANDARD_QUICK_BUTTON_KEYS) - {"work"}

    def test_row_checkbox_reflects_current_effective_visibility(self):
        shop = ShopConfig(2026, 3)  # Dino defaults: morning visible, can_work hidden
        dialog = QuickModeSettingsDialog(None, [], shop)

        assert dialog._standard_button_rows["morning"].is_visible() is True
        assert dialog._standard_button_rows["can_work"].is_visible() is False

    def test_save_produces_a_full_visibility_dict(self):
        dialog = QuickModeSettingsDialog(None, [])
        dialog._standard_button_rows["delete"].show_check.setChecked(False)

        dialog._save()

        assert dialog.result_standard_buttons["delete"] is False
        assert set(dialog.result_standard_buttons.keys()) == set(STANDARD_QUICK_BUTTON_KEYS) - {"work"}


class TestQuickModeContextMenuEntries:
    """PPM na komórkę (ScheduleGrid.contextMenuEvent) - "Odblokuj"/"Wyczyść
    komórkę" usunięte na rzecz dynamicznej listy trybów trybu szybkiego
    zaznaczonych jako "Widoczne" (decyzja użytkownika 2026-09-28).
    _quick_mode_context_menu_entries() jest czystą funkcją (bez QMenu) -
    dokładnie to, co contextMenuEvent wstawia do menu."""

    def test_none_shop_returns_no_entries(self):
        assert _quick_mode_context_menu_entries(None) == ([], [])

    def test_dino_defaults_include_morning_afternoon_not_can_work(self):
        shop = ShopConfig(2026, 3)
        standard, presets = _quick_mode_context_menu_entries(shop)

        labels = [label for label, _ in standard]
        assert "Rano" in labels
        assert "Popo" in labels
        assert "Może pracować" not in labels
        assert "Usuń" in labels  # visible by default for every profile
        assert presets == []

    def test_custom_profile_defaults_include_can_work_not_morning(self):
        shop = ShopConfig(2026, 3)
        shop.business_type = "some_custom_profile"
        standard, _presets = _quick_mode_context_menu_entries(shop)

        labels = [label for label, _ in standard]
        assert "Może pracować" in labels
        assert "Rano" not in labels

    def test_only_visible_presets_are_included_in_order(self):
        shop = ShopConfig(2026, 3)
        shop.quick_mode_presets = [
            {"name": "Zmiana16h", "start": "06:00", "end": "22:00", "full_day": False, "visible": True},
            {"name": "Ukryty", "start": "06:00", "end": "22:00", "full_day": False, "visible": False},
            {"name": "Doba24h", "start": "06:00", "end": None, "full_day": True, "visible": True},
        ]
        _standard, presets = _quick_mode_context_menu_entries(shop)

        assert presets == [
            ("Zmiana16h", "PRESET:Zmiana16h"),
            ("Doba24h", "PRESET:Doba24h"),
        ]

    def test_hiding_a_standard_button_removes_it_from_the_menu(self):
        shop = ShopConfig(2026, 3)
        shop.set_quick_mode_standard_buttons({"off": False})

        standard, _presets = _quick_mode_context_menu_entries(shop)

        assert "Wolne" not in [label for label, _ in standard]

    def test_work_is_never_in_the_menu_even_if_forced_visible(self):
        """"Praca" wymaga osobnego panelu godzin (Od/Do) - nie pasuje do
        jednego kliknięcia w menu kontekstowym, więc zawsze pominięta
        niezależnie od quick_mode_standard_buttons."""
        shop = ShopConfig(2026, 3)
        shop.set_quick_mode_standard_buttons({"work": True})

        standard, _presets = _quick_mode_context_menu_entries(shop)

        assert "Praca" not in [label for label, _ in standard]

    def test_each_standard_entry_shift_type_actually_applies_via_apply_quick_shift(self):
        """End-to-end: every entry this menu can offer must be a shift_type
        _apply_quick_shift actually understands - build a grid, fire each
        one, and confirm the cell state changed."""
        emp = Employee(last_name="Kowalski", first_name="Jan")
        schedule = MonthSchedule(2026, 9, employees=[emp])
        shop = ShopConfig(2026, 9)
        controller = ScheduleController(schedule, shop)
        main_window = SimpleNamespace(shop_config=shop)
        grid = ScheduleGrid()
        grid.set_data(schedule, shop, controller, main_window=main_window)

        # Expected, distinguishable effect of each shift_type on a fresh
        # (blank) day - catches a typo'd/renamed shift_type silently
        # falling through to nothing (the real risk this test guards
        # against), not just "did it raise".
        expected_effect = {
            "MORNING_CLASS": lambda ds: ds.shift_class == "1",
            "AFTERNOON_CLASS": lambda ds: ds.shift_class == "2",
            "CAN_WORK": lambda ds: ds.shift_class == "W",
            "DELETE": lambda ds: ds.is_blank(),  # no-op on an already-blank day
            "OFF": lambda ds: ds.is_locked is True,
            "LEAVE": lambda ds: ds.is_leave is True,
            "SICK": lambda ds: getattr(ds, "is_sick", False) is True,
        }

        standard, _presets = _quick_mode_context_menu_entries(shop)
        for day, (label, shift_type) in enumerate(standard, start=1):
            grid._apply_quick_shift(0, day, shift=shift_type)
            ds = schedule.get_day(emp, day)
            check = expected_effect.get(shift_type)
            assert check is not None, f"no expected-effect check defined for {shift_type} ({label})"
            assert check(ds), f"{label} ({shift_type}) did not produce its expected effect: {ds}"
