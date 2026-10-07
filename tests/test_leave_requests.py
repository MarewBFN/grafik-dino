"""logic/leave_requests.py - automatyczne odejmowanie zaznaczonego urlopu od
puli pracownika i wnioski urlopowe (menu Plik -> "Wnioski urlopowe...",
export/leave_request_exporter.py, pasek pod grafikiem w ui/main_window.py).

Październik 2026: 1.10 to czwartek, brak świąt. Listopad 2026: 11.11
(środa) to święto."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from logic.leave_requests import (
    build_leave_requests,
    format_days,
    generate_button_text,
    is_leave_working_day,
    leave_day_value,
    leave_days_used,
    mark_leave_requests_printed,
    pending_leave_requests_count,
    pending_requests_text,
    sync_vacation_balances,
)
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig


def _setup(year=2026, month=10, vacation=20, **employee_fields):
    shop = ShopConfig(year, month)
    shop.constraints["force_fulltime_845"] = False
    emp = Employee(last_name="Kowalski", first_name="Jan", vacation_days_left=vacation, **employee_fields)
    schedule = MonthSchedule(year, month, employees=[emp])
    # Pierwsza synchronizacja (pusty grafik) - punkt odniesienia.
    sync_vacation_balances(schedule, shop)
    return schedule, shop


def _employee(schedule):
    return schedule.employees[0]


def _set_leave(schedule, *days):
    for day in days:
        schedule.get_day(_employee(schedule), day).set_leave()


class LeaveDayValueTests(unittest.TestCase):
    def test_full_day_is_one_day(self):
        schedule, shop = _setup()
        self.assertEqual(leave_day_value(_employee(schedule), shop), 1)

    def test_half_time_is_half_day(self):
        schedule, shop = _setup(employment_fraction=0.5)
        self.assertEqual(leave_day_value(_employee(schedule), shop), 0.5)

    def test_24h_service_is_three_days(self):
        schedule, shop = _setup()
        shop.standard_daily_hours = 24.0
        self.assertEqual(leave_day_value(_employee(schedule), shop), 3)

    def test_minimum_is_half_day(self):
        schedule, shop = _setup(employment_fraction=0.125)
        self.assertEqual(leave_day_value(_employee(schedule), shop), 0.5)

    def test_8h30_full_time_rounds_to_one_day(self):
        schedule, shop = _setup()
        shop.constraints["force_fulltime_845"] = True
        self.assertEqual(leave_day_value(_employee(schedule), shop), 1)


class WorkingDayTests(unittest.TestCase):
    def test_weekdays_count_weekends_do_not(self):
        self.assertTrue(is_leave_working_day(2026, 10, 2))   # piątek
        self.assertFalse(is_leave_working_day(2026, 10, 3))  # sobota
        self.assertFalse(is_leave_working_day(2026, 10, 4))  # niedziela
        self.assertTrue(is_leave_working_day(2026, 10, 5))   # poniedziałek

    def test_public_holiday_does_not_count(self):
        self.assertFalse(is_leave_working_day(2026, 11, 11))
        self.assertTrue(is_leave_working_day(2026, 11, 12))


class SyncVacationBalanceTests(unittest.TestCase):
    def test_marking_leave_subtracts_immediately(self):
        schedule, shop = _setup()
        _set_leave(schedule, 5, 6)

        changes = sync_vacation_balances(schedule, shop)

        self.assertEqual(_employee(schedule).vacation_days_left, 18)
        self.assertEqual(changes, [(_employee(schedule), -2)])

    def test_removing_leave_gives_days_back(self):
        schedule, shop = _setup()
        _set_leave(schedule, 5, 6)
        sync_vacation_balances(schedule, shop)

        schedule.get_day(_employee(schedule), 6).clear()
        sync_vacation_balances(schedule, shop)

        self.assertEqual(_employee(schedule).vacation_days_left, 19)

    def test_weekend_leave_is_free(self):
        schedule, shop = _setup()
        _set_leave(schedule, 3, 4)

        sync_vacation_balances(schedule, shop)

        self.assertEqual(_employee(schedule).vacation_days_left, 20)

    def test_half_time_subtracts_half_days(self):
        schedule, shop = _setup(employment_fraction=0.5)
        _set_leave(schedule, 5, 6, 7)

        sync_vacation_balances(schedule, shop)

        self.assertEqual(_employee(schedule).vacation_days_left, 18.5)

    def test_repeated_sync_is_idempotent(self):
        schedule, shop = _setup()
        _set_leave(schedule, 5)
        sync_vacation_balances(schedule, shop)

        self.assertEqual(sync_vacation_balances(schedule, shop), [])
        self.assertEqual(_employee(schedule).vacation_days_left, 19)

    def test_balance_can_go_negative(self):
        schedule, shop = _setup(vacation=1)
        _set_leave(schedule, 5, 6)

        sync_vacation_balances(schedule, shop)

        self.assertEqual(_employee(schedule).vacation_days_left, -1)

    def test_first_sync_of_old_project_does_not_subtract_existing_leave(self):
        shop = ShopConfig(2026, 10)
        emp = Employee(last_name="Kowalski", first_name="Jan", vacation_days_left=20)
        schedule = MonthSchedule(2026, 10, employees=[emp])
        _set_leave(schedule, 5, 6)

        sync_vacation_balances(schedule, shop)

        self.assertEqual(_employee(schedule).vacation_days_left, 20)
        self.assertEqual(leave_days_used(schedule, shop, _employee(schedule)), 2)

    def test_manual_balance_edit_is_not_overwritten(self):
        schedule, shop = _setup()
        _set_leave(schedule, 5)
        sync_vacation_balances(schedule, shop)

        edited = Employee(last_name="Kowalski", first_name="Jan", vacation_days_left=26)
        schedule.replace_employee(_employee(schedule), edited)
        sync_vacation_balances(schedule, shop)

        self.assertEqual(_employee(schedule).vacation_days_left, 26)

    def test_balance_swap_keeps_schedule_data(self):
        schedule, shop = _setup()
        schedule.set_settlement_target(_employee(schedule), 9600)
        _set_leave(schedule, 5)

        sync_vacation_balances(schedule, shop)

        emp = _employee(schedule)
        self.assertEqual(schedule.get_settlement_target(emp), 9600)
        self.assertTrue(schedule.get_day(emp, 5).is_leave)
        self.assertIs(next(iter(schedule.leave_days_charged)), emp)


class BuildLeaveRequestsTests(unittest.TestCase):
    def test_consecutive_days_make_one_request(self):
        schedule, shop = _setup()
        _set_leave(schedule, 5, 6, 7)

        requests = build_leave_requests(schedule, shop)

        self.assertEqual([(r.start_day, r.end_day, r.days) for r in requests], [(5, 7, 3)])
        self.assertEqual(requests[0].start_date, date(2026, 10, 5))

    def test_separate_ranges_make_separate_requests(self):
        schedule, shop = _setup()
        _set_leave(schedule, 5, 6, 14)

        requests = build_leave_requests(schedule, shop)

        self.assertEqual([(r.start_day, r.end_day) for r in requests], [(5, 6), (14, 14)])

    def test_unmarked_weekend_does_not_split_request(self):
        schedule, shop = _setup()
        _set_leave(schedule, 2, 5)  # piątek + poniedziałek

        requests = build_leave_requests(schedule, shop)

        self.assertEqual([(r.start_day, r.end_day, r.days) for r in requests], [(2, 5, 2)])

    def test_weekend_only_leave_makes_no_request(self):
        schedule, shop = _setup()
        _set_leave(schedule, 3, 4)

        self.assertEqual(build_leave_requests(schedule, shop), [])

    def test_request_does_not_start_or_end_on_weekend(self):
        schedule, shop = _setup()
        _set_leave(schedule, 3, 4, 5, 6)

        requests = build_leave_requests(schedule, shop)

        self.assertEqual([(r.start_day, r.end_day, r.days) for r in requests], [(5, 6, 2)])

    def test_holiday_is_skipped_in_count(self):
        schedule, shop = _setup(year=2026, month=11)
        _set_leave(schedule, 10, 11, 12)

        requests = build_leave_requests(schedule, shop)

        self.assertEqual([(r.start_day, r.end_day, r.days) for r in requests], [(10, 12, 2)])

    def test_only_current_location(self):
        schedule, shop = _setup()
        other = Employee(last_name="Nowak", first_name="Anna", location_key="b")
        schedule.add_employee(other)
        _set_leave(schedule, 5)
        schedule.get_day(other, 6).set_leave()

        names = [r.employee.last_name for r in build_leave_requests(schedule, shop, location_key="b")]

        self.assertEqual(names, ["Nowak"])
        self.assertEqual(len(build_leave_requests(schedule, shop)), 2)

    def test_printed_requests_stay_listed_but_marked(self):
        schedule, shop = _setup()
        _set_leave(schedule, 5, 14)
        mark_leave_requests_printed(schedule, build_leave_requests(schedule, shop)[:1])

        requests = build_leave_requests(schedule, shop)

        self.assertEqual([r.printed for r in requests], [True, False])
        self.assertEqual(pending_leave_requests_count(schedule, shop), 1)

    def test_extending_printed_period_makes_new_pending_request(self):
        schedule, shop = _setup()
        _set_leave(schedule, 5)
        mark_leave_requests_printed(schedule, build_leave_requests(schedule, shop))
        _set_leave(schedule, 6)

        self.assertEqual(pending_leave_requests_count(schedule, shop), 1)


class PersistenceTests(unittest.TestCase):
    def test_charged_and_printed_round_trip(self):
        schedule, shop = _setup()
        _set_leave(schedule, 5)
        sync_vacation_balances(schedule, shop)
        mark_leave_requests_printed(schedule, build_leave_requests(schedule, shop))

        loaded = MonthSchedule.from_dict(schedule.to_dict())
        emp = loaded.employees[0]

        self.assertEqual(emp.vacation_days_left, 19)
        self.assertEqual(loaded.leave_days_charged[emp], 1)
        self.assertEqual(loaded.printed_leave_requests[emp], {(5, 5)})
        self.assertEqual(sync_vacation_balances(loaded, shop), [])

    def test_rename_keeps_printed_requests(self):
        schedule, shop = _setup()
        _set_leave(schedule, 5)
        mark_leave_requests_printed(schedule, build_leave_requests(schedule, shop))

        renamed = Employee(last_name="Kowalska", first_name="Jana", vacation_days_left=19)
        schedule.replace_employee(_employee(schedule), renamed)

        self.assertEqual(pending_leave_requests_count(schedule, shop), 0)


class TextTests(unittest.TestCase):
    def test_format_days(self):
        self.assertEqual(format_days(3), "3")
        self.assertEqual(format_days(2.5), "2,5")
        self.assertEqual(format_days(-0.5), "-0,5")

    def test_days_noun(self):
        from logic.leave_requests import days_noun

        self.assertEqual(days_noun(1), "dzień")
        self.assertEqual(days_noun(-1), "dzień")
        self.assertEqual(days_noun(2.5), "dnia")
        self.assertEqual(days_noun(5), "dni")

    def test_pending_text_plural_forms(self):
        self.assertEqual(pending_requests_text(1), "Istnieje 1 wniosek oczekujący na wydruk")
        self.assertEqual(pending_requests_text(3), "Istnieją 3 wnioski oczekujące na wydruk")
        self.assertEqual(pending_requests_text(5), "Istnieje 5 wniosków oczekujących na wydruk")
        self.assertEqual(pending_requests_text(12), "Istnieje 12 wniosków oczekujących na wydruk")
        self.assertEqual(pending_requests_text(22), "Istnieją 22 wnioski oczekujące na wydruk")

    def test_button_text(self):
        self.assertEqual(generate_button_text(1), "Wygeneruj wniosek")
        self.assertEqual(generate_button_text(2), "Wygeneruj wnioski")


class ExporterTests(unittest.TestCase):
    def _request(self, **personal):
        schedule, shop = _setup(**personal)
        _set_leave(schedule, 5, 6)
        return build_leave_requests(schedule, shop)[0]

    def test_text(self):
        from export.leave_request_exporter import leave_request_text

        self.assertEqual(
            leave_request_text(self._request()),
            "Proszę o udzielenie urlopu wypoczynkowego od dnia 05.10.2026 do dnia 06.10.2026.",
        )

    def test_pdf_has_one_page_per_request(self):
        from export.leave_request_exporter import export_leave_requests_to_pdf

        request = self._request(street="ul. Leśna 1", postal_code="84-200", city="Wejherowo")
        path = os.path.join(tempfile.mkdtemp(), "wnioski.pdf")

        self.assertTrue(export_leave_requests_to_pdf([request, request], path, date(2026, 10, 2)))

        data = Path(path).read_bytes()
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertEqual(data.count(b"/Type /Page\n") + data.count(b"/Type /Page\r") + data.count(b"/Type /Page>"), 2)

    def test_preview_image_is_a4_and_not_blank(self):
        from export.leave_request_exporter import render_leave_request_image

        image = render_leave_request_image(self._request(), date(2026, 10, 2), width_px=420)

        self.assertEqual((image.width(), image.height()), (420, 594))
        colors = {image.pixel(x, y) for x in range(0, 420, 3) for y in range(0, 594, 3)}
        self.assertGreater(len(colors), 1)


class LeaveRequestsDialogTests(unittest.TestCase):
    def test_printed_requests_listed_unchecked(self):
        from PySide6.QtCore import Qt
        from ui.leave_requests_dialog import LeaveRequestsDialog

        schedule, shop = _setup()
        _set_leave(schedule, 5, 14)
        mark_leave_requests_printed(schedule, build_leave_requests(schedule, shop)[:1])

        dialog = LeaveRequestsDialog(
            None, lambda: build_leave_requests(schedule, shop), lambda requests: None, "x.pdf",
        )

        self.assertEqual(dialog.table.rowCount(), 2)
        self.assertEqual(dialog.table.item(0, 0).checkState(), Qt.Unchecked)
        self.assertEqual(dialog.table.item(1, 0).checkState(), Qt.Checked)
        self.assertEqual([r.start_day for r in dialog.checked_requests()], [14])

    def test_saving_marks_requests_and_unchecks_them(self):
        from PySide6.QtCore import Qt
        from ui import leave_requests_dialog as module

        schedule, shop = _setup()
        _set_leave(schedule, 5)
        path = os.path.join(tempfile.mkdtemp(), "wnioski")
        dialog = module.LeaveRequestsDialog(
            None,
            lambda: build_leave_requests(schedule, shop),
            lambda requests: mark_leave_requests_printed(schedule, requests),
            "x.pdf",
        )
        original_save = module.QFileDialog.getSaveFileName
        original_info = module.QMessageBox.information
        module.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (path, ""))
        module.QMessageBox.information = staticmethod(lambda *a, **k: None)
        try:
            dialog._save_checked()
        finally:
            module.QFileDialog.getSaveFileName = original_save
            module.QMessageBox.information = original_info

        self.assertTrue(os.path.exists(path + ".pdf"))
        self.assertEqual(pending_leave_requests_count(schedule, shop), 0)
        self.assertEqual(dialog.table.rowCount(), 1)
        self.assertEqual(dialog.table.item(0, 0).checkState(), Qt.Unchecked)
        self.assertFalse(dialog.save_btn.isEnabled())


class InsufficientVacationTests(unittest.TestCase):
    def _dialog(self, vacation):
        from ui.leave_requests_dialog import LeaveRequestsDialog

        schedule, shop = _setup(vacation=vacation)
        _set_leave(schedule, 5, 6)
        sync_vacation_balances(schedule, shop)
        saved = []
        dialog = LeaveRequestsDialog(
            None, lambda: build_leave_requests(schedule, shop), saved.extend, "x.pdf",
        )
        return dialog, saved

    def _save(self, dialog, answer):
        from PySide6.QtWidgets import QMessageBox
        from ui import leave_requests_dialog as module

        asked = []
        path = os.path.join(tempfile.mkdtemp(), "wnioski.pdf")
        patches = {
            (module.QMessageBox, "question"): staticmethod(lambda *a, **k: asked.append(a[2]) or answer),
            (module.QMessageBox, "information"): staticmethod(lambda *a, **k: None),
            (module.QFileDialog, "getSaveFileName"): staticmethod(lambda *a, **k: (path, "")),
        }
        originals = {key: getattr(*key) for key in patches}
        for (owner, name), value in patches.items():
            setattr(owner, name, value)
        try:
            dialog._save_checked()
        finally:
            for (owner, name), value in originals.items():
                setattr(owner, name, value)
        return asked

    def test_negative_balance_shown_in_red(self):
        dialog, _ = self._dialog(vacation=1)

        item = dialog.table.item(0, 3)
        self.assertEqual(item.text(), "-1")
        self.assertEqual(item.foreground().color().name(), "#c62828")

    def test_insufficient_balance_asks_and_saves_on_yes(self):
        from PySide6.QtWidgets import QMessageBox
        from ui.leave_requests_dialog import INSUFFICIENT_VACATION_MESSAGE

        dialog, saved = self._dialog(vacation=1)

        asked = self._save(dialog, QMessageBox.Yes)

        self.assertEqual(asked, [INSUFFICIENT_VACATION_MESSAGE])
        self.assertEqual(len(saved), 1)

    def test_insufficient_balance_cancelled_on_no(self):
        from PySide6.QtWidgets import QMessageBox

        dialog, saved = self._dialog(vacation=1)

        self._save(dialog, QMessageBox.No)

        self.assertEqual(saved, [])

    def test_enough_balance_does_not_ask(self):
        from PySide6.QtWidgets import QMessageBox

        dialog, saved = self._dialog(vacation=2)

        asked = self._save(dialog, QMessageBox.No)

        self.assertEqual(asked, [])
        self.assertEqual(len(saved), 1)


class MainWindowIntegrationTests(unittest.TestCase):
    def _window(self):
        from ui.main_window import MainWindow

        tmp_dir = tempfile.mkdtemp()
        cwd = os.getcwd()
        os.chdir(tmp_dir)
        try:
            return MainWindow()
        finally:
            os.chdir(cwd)

    def _working_day(self, schedule):
        return next(
            day for day in range(1, schedule.days_in_month + 1)
            if is_leave_working_day(schedule.year, schedule.month, day)
        )

    def test_leave_from_context_menu_updates_balance_and_bar(self):
        window = self._window()
        window.schedule.add_employee(Employee(last_name="Kowalski", first_name="Jan", vacation_days_left=10))
        window._sync_everything()
        self.assertTrue(window.leave_requests_bar.isHidden())

        emp = window.schedule.employees[0]
        day = self._working_day(window.schedule)
        window._ctx_leave(emp, day)

        emp = window.schedule.employees[0]
        self.assertEqual(emp.vacation_days_left, 10 - leave_day_value(emp, window.shop_config))
        self.assertFalse(window.leave_requests_bar.isHidden())
        self.assertEqual(window.leave_requests_label.text(), "Istnieje 1 wniosek oczekujący na wydruk")
        self.assertEqual(window.leave_requests_button.text(), "Wygeneruj wniosek")

        window._undo()

        self.assertEqual(window.schedule.employees[0].vacation_days_left, 10)
        self.assertTrue(window.leave_requests_bar.isHidden())

    def test_printed_marks_survive_undo(self):
        window = self._window()
        window.schedule.add_employee(Employee(last_name="Kowalski", first_name="Jan", vacation_days_left=10))
        window._sync_everything()
        emp = window.schedule.employees[0]
        day = self._working_day(window.schedule)
        window._ctx_leave(emp, day)
        mark_leave_requests_printed(window.schedule, window._current_leave_requests())
        other_day = next(
            d for d in range(day + 2, window.schedule.days_in_month + 1)
            if is_leave_working_day(window.schedule.year, window.schedule.month, d)
        )
        window._ctx_free(window.schedule.employees[0], other_day)

        window._undo()

        self.assertEqual(pending_leave_requests_count(window.schedule, window.shop_config), 0)

    def _two_month_window(self):
        window = self._window()
        window.schedule.add_employee(Employee(last_name="Kowalski", first_name="Jan", vacation_days_left=10))
        window._sync_everything()
        first = (window.year, window.month)
        second = (window.year + 1, window.month)
        window._switch_to_month(*second)
        return window, first, second

    def _mark_leave(self, window):
        window._ctx_leave(window.schedule.employees[0], self._working_day(window.schedule))
        return leave_day_value(window.schedule.employees[0], window.shop_config)

    def test_balance_is_shared_between_months(self):
        window, first, second = self._two_month_window()
        used_second = self._mark_leave(window)

        window._switch_to_month(*first)
        self.assertEqual(window.schedule.employees[0].vacation_days_left, 10 - used_second)

        used_first = self._mark_leave(window)
        expected = 10 - used_second - used_first
        self.assertEqual(window.schedule.employees[0].vacation_days_left, expected)

        window._switch_to_month(*second)
        self.assertEqual(window.schedule.employees[0].vacation_days_left, expected)

    def test_undo_restores_balance_in_other_months(self):
        window, first, _second = self._two_month_window()
        self._mark_leave(window)

        window._undo()
        window._switch_to_month(*first)

        self.assertEqual(window.schedule.employees[0].vacation_days_left, 10)


if __name__ == "__main__":
    unittest.main()
