"""„Wolne płatne” (WP, DaySchedule.is_paid_off): dzień wolny za święto,
płatny 8 h w każdej placówce. Wpisywany ręcznie (tryb szybki, menu
kontekstowe), liczony do kolumn godzin (+8 h na dzień), pokazywany jako
„WP” w siatce i na wydrukach; generator traktuje taką komórkę jak pustą -
kasuje ją i może nadpisać zmianą."""

import io
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from logic.auto_generator import AutoScheduleGenerator
from logic.generator.custom_profile_wiring import default_policies
from logic.monthly_hours_status import monthly_hours_status
from logic.schedule_controller import ScheduleController
from model.business_profile import register_custom_profile
from model.constraint_policy import ConstraintPolicy
from model.custom_profile import CustomBusinessProfile
from model.day_schedule import PAID_OFF_MINUTES, DaySchedule
from model.employee import Employee
from model.location import LocationConfig
from model.month_schedule import MonthSchedule
from model.shop_config import STANDARD_QUICK_BUTTON_KEYS, ShopConfig, is_standard_button_visible
from ui.grid_view import ScheduleGrid, _quick_mode_context_menu_entries

YEAR, MONTH = 2026, 8


def _schedule(daily_hours=12):
    emp = Employee(last_name="Kowalski", first_name="Jan", daily_hours=daily_hours)
    schedule = MonthSchedule(YEAR, MONTH, employees=[emp])
    shop = ShopConfig(YEAR, MONTH)
    return emp, schedule, shop


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def test_paid_off_always_counts_8h_regardless_of_daily_hours():
    ds = DaySchedule()
    ds.set_paid_off()

    assert ds.is_paid_off and not ds.is_locked
    assert ds.is_empty()  # bez godzin zmiany - pracownika fizycznie nie ma
    assert int(ds.total_duration().total_seconds() // 60) == PAID_OFF_MINUTES == 480
    assert ds.as_rows() == ("WP", "", "8:00")

    emp = Employee(last_name="A", first_name="B", daily_hours=24)
    assert ds.total_minutes(emp, ShopConfig(YEAR, MONTH)) == 480


def test_every_other_day_state_clears_paid_off():
    setters = [
        lambda ds: ds.set_hours("08:00", "20:00"),
        lambda ds: ds.set_full_day_shift("08:00"),
        lambda ds: ds.set_free(),
        lambda ds: ds.set_leave(),
        lambda ds: ds.set_leave(half=True),
        lambda ds: ds.set_sick(),
        lambda ds: ds.set_shift_class("W"),
        lambda ds: ds.clear(),
    ]
    for setter in setters:
        ds = DaySchedule()
        ds.set_paid_off()
        setter(ds)
        assert not ds.is_paid_off


def test_summary_columns_add_8h_per_paid_off_day():
    emp, schedule, shop = _schedule(daily_hours=12)
    schedule.get_day(emp, 3).set_hours("08:00", "20:00")
    schedule.get_day(emp, 4).set_paid_off()
    schedule.get_day(emp, 5).set_paid_off()
    schedule.get_day(emp, 6).set_leave()

    assert schedule.total_hours_for_employee(emp) == "28:00"  # Praca: 12 + 2 x 8
    assert schedule.leave_hours_for_employee(emp) == "12:00"  # Urlop bez zmian
    assert schedule.total_with_leave_and_sick_for_employee(emp) == "40:00"  # Razem
    assert monthly_hours_status(schedule, shop, emp)["worked_minutes"] == 28 * 60


def test_paid_off_survives_save_and_load():
    emp, schedule, _shop = _schedule()
    schedule.get_day(emp, 7).set_paid_off()

    loaded = MonthSchedule.from_dict(schedule.to_dict())
    loaded_emp = loaded.employees[0]

    assert loaded.get_day(loaded_emp, 7).is_paid_off
    assert not loaded.get_day(loaded_emp, 7).is_locked
    assert not loaded.get_day(loaded_emp, 8).is_paid_off


def test_clear_generated_keeps_paid_off_but_generator_clear_removes_it():
    emp, schedule, _shop = _schedule()
    schedule.get_day(emp, 3).set_paid_off()

    schedule.clear_generated_days()  # „Wyczyść auto” - WP to wpis ręczny
    assert schedule.get_day(emp, 3).is_paid_off

    schedule.clear_paid_off_days([emp])
    assert schedule.get_day(emp, 3).is_blank()


# ---------------------------------------------------------------------------
# Kontroler, tryb szybki, siatka
# ---------------------------------------------------------------------------

def test_controller_sets_unlocked_paid_off_with_undo_and_copy_paste():
    emp, schedule, shop = _schedule()
    controller = ScheduleController(schedule, shop)

    controller.set_day_paid_off(emp, 3)
    ds = schedule.get_day(emp, 3)
    assert ds.is_paid_off and not ds.is_locked
    assert len(controller.history) == 1

    controller.set_day_paid_off(emp, 3)  # już WP - bez kolejnego wpisu undo
    assert len(controller.history) == 1

    controller.paste_day_snapshot(emp, 4, controller.copy_day_snapshot(emp, 3))
    assert schedule.get_day(emp, 4).is_paid_off

    controller.set_day_free(emp, 4)  # „Wolne” na komórce WP
    assert not schedule.get_day(emp, 4).is_paid_off
    assert schedule.get_day(emp, 4).is_locked


def test_quick_mode_button_is_visible_by_default_and_in_context_menu():
    assert "paid_off" in STANDARD_QUICK_BUTTON_KEYS
    for business_type in ("dino_retail", "custom_ochrona"):
        shop = ShopConfig(YEAR, MONTH)
        shop.business_type = business_type
        assert is_standard_button_visible(shop, "paid_off")

    shop = ShopConfig(YEAR, MONTH)
    standard, _presets = _quick_mode_context_menu_entries(shop)
    assert ("Wolne płatne", "PAID_OFF") in standard


def _grid(schedule, shop, compact):
    controller = ScheduleController(schedule, shop)
    grid = ScheduleGrid()
    grid.set_data(schedule, shop, controller, main_window=SimpleNamespace(shop_config=shop))
    grid.compact_mode = compact
    return grid


def test_quick_shift_paid_off_and_cell_text():
    emp, schedule, shop = _schedule()
    grid = _grid(schedule, shop, compact=True)

    grid._apply_quick_shift(0, 3, shift="PAID_OFF")
    assert schedule.get_day(emp, 3).is_paid_off

    grid.refresh()
    assert grid.item(0, 3).text() == "WP"
    # Kolumna „Praca (h)” - pierwsza po dniach miesiąca.
    assert grid.item(0, schedule.days_in_month + 1).text() == "8:00"

    grid.compact_mode = False
    grid.refresh()
    assert grid.item(0, 3).text() == "WP\n8:00"


# ---------------------------------------------------------------------------
# Wydruki
# ---------------------------------------------------------------------------

def test_exports_show_wp(tmp_path):
    from openpyxl import load_workbook

    from export.employee_card_exporter import _day_rows
    from export.security_excel_exporter import export_security_schedule_to_excel

    emp, schedule, shop = _schedule()
    shop.business_type = "custom_ochrona"
    schedule.get_day(emp, 3).set_paid_off()

    path = tmp_path / "grafik.xlsx"
    export_security_schedule_to_excel(schedule, YEAR, MONTH, str(path), shop=shop)
    ws = load_workbook(path).active
    assert ws.cell(row=5, column=3 + 2).value == "WP"  # dzień 3 = kolumna 5
    hours_col = schedule.days_in_month + 3  # „Godziny”
    assert ws.cell(row=5, column=hours_col).value == "8:00"

    row = _day_rows(schedule, emp)[2]
    assert row[1] == "WP" and row[3] == "8"


def test_image_export_renders_paid_off_day():
    from export.export_style import render_schedule_image

    emp, schedule, shop = _schedule()
    shop.business_type = "custom_ochrona"
    schedule.get_day(emp, 3).set_paid_off()

    image = render_schedule_image(schedule, YEAR, MONTH, shop=shop)
    assert image.size[0] > 0


# ---------------------------------------------------------------------------
# Generator: WP traktowane jak pusta komórka
# ---------------------------------------------------------------------------

ROTATION = {
    "only_12_24h": True,
    "weekend_full": {"start": "08:00"},
    "weekend_half_a": {"start": "08:00", "end": "20:00"},
    "weekend_half_b": {"start": "20:00", "end": "08:00"},
}


def _rotation_setup(n_employees=4):
    profile = CustomBusinessProfile(key="test_paid_off", display_name="Test Paid Off", roles=[], rules=[])
    register_custom_profile(profile)

    shop = ShopConfig(YEAR, MONTH)
    shop.business_type = profile.key
    loc = LocationConfig(key="site1", name="Site 1")
    loc.set_duty_rotation(ROTATION)
    loc.closed_on_public_holidays = False
    shop.locations = {"site1": loc}
    shop.constraint_policies.update(default_policies(profile))
    shop.constraint_policies["balance"] = ConstraintPolicy.PREFERRED
    shop.constraint_policies["monthly_hours"] = ConstraintPolicy.PREFERRED

    schedule = MonthSchedule(YEAR, MONTH)
    employees = [Employee(last_name=f"Guard{i}", first_name="R", location_key="site1") for i in range(n_employees)]
    for emp in employees:
        schedule.add_employee(emp)
    return shop, schedule, employees


def _generate(shop, schedule):
    with redirect_stdout(io.StringIO()):
        return AutoScheduleGenerator(schedule, shop).generate(solver_time_limit_seconds=30)


def test_generator_ignores_and_clears_paid_off_cells():
    shop, schedule, employees = _rotation_setup()
    for emp in employees:
        for day in range(1, 8):
            schedule.get_day(emp, day).set_paid_off()

    result = _generate(shop, schedule)

    assert result["success"], result
    assert not any(schedule.get_day(emp, day).is_paid_off for emp in employees for day in range(1, 8))
    # Komórki WP były dla generatora puste - doby 1-7 są normalnie obsadzone.
    for day in range(1, 8):
        assert any(not schedule.get_day(emp, day).is_empty() for emp in employees)


def test_regeneration_overwrites_paid_off_added_after_generation():
    """Szef wpisuje WP po wygenerowaniu - ponowne „Generuj grafik” (UI:
    ScheduleController.generate_schedule(force=True)) traktuje je jak puste."""
    shop, schedule, employees = _rotation_setup()
    controller = ScheduleController(schedule, shop)
    with redirect_stdout(io.StringIO()):
        assert controller.generate_schedule(force=True)["success"]

    worked = next(
        (emp, day) for emp in employees for day in range(1, schedule.days_in_month + 1)
        if not schedule.get_day(emp, day).is_empty()
    )
    controller.set_day_paid_off(*worked)
    assert schedule.get_day(*worked).is_paid_off

    with redirect_stdout(io.StringIO()):
        result = controller.generate_schedule(force=True)

    assert result["success"], result
    assert not any(
        schedule.get_day(emp, day).is_paid_off
        for emp in employees for day in range(1, schedule.days_in_month + 1)
    )


def test_failed_generation_keeps_paid_off():
    shop, schedule, employees = _rotation_setup(n_employees=1)
    shop.locations["site1"].constraints["coverage_staff"] = 2  # 1 osoba na 2 miejsca - brak rozwiązania
    schedule.get_day(employees[0], 3).set_paid_off()

    result = _generate(shop, schedule)

    assert not result["success"]
    assert schedule.get_day(employees[0], 3).is_paid_off


def test_main_window_quick_button_sets_paid_off(tmp_path, monkeypatch):
    from ui.main_window import MainWindow

    monkeypatch.chdir(tmp_path)
    window = MainWindow()
    window.schedule.add_employee(Employee(last_name="Kowalski", first_name="Jan"))
    window._sync_everything()

    assert window.btn_paid_off.text() == "Wolne płatne"
    assert window.btn_paid_off.isVisibleTo(window.quick_panel)

    window._set_quick_shift("PAID_OFF")
    assert window.btn_paid_off.isChecked()

    emp = window.schedule.employees[0]
    row = window.grid._visible_employees.index(emp)
    col = next(c for c in range(window.grid.columnCount()) if window.grid._column_to_day(c) == 5)
    window.grid._apply_quick_shift(row, col)

    assert window.schedule.get_day(emp, 5).is_paid_off
    assert window.schedule.total_hours_for_employee(emp) == "8:00"
