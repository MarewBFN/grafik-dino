"""Menu Plik -> "Usuń konfigurację" (ui/main_window.py::_reset_configuration) -
na życzenie użytkownika: przywraca WYŁĄCZNIE grafik/konfigurację (schedule,
shop_config, last_project.json) do stanu sprzed pierwszego uruchomienia.
Świadomie NIE dotyka first_run.flag/*_tutorial_seen.flag/license.json/
machine_id.json/demo.json/custom_profiles.json - użytkownik wprost poprosił
zostawić je w spokoju."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from model.employee import Employee
from model.location import LocationConfig


def _accept_confirmation():
    """Patchuje ui.main_window.QMessageBox tak, żeby _reset_configuration()
    zachowywał się jakby użytkownik kliknął "Tak, usuń" - ten sam wzorzec
    (addButton.side_effect + clickedButton) co realne dwuprzyciskowe
    QMessageBox w _open_new_project."""
    patcher = patch("ui.main_window.QMessageBox")
    mock_box_cls = patcher.start()
    instance = mock_box_cls.return_value
    yes_btn = object()
    instance.addButton.side_effect = [yes_btn, object()]
    instance.clickedButton.return_value = yes_btn
    return patcher


def _reject_confirmation():
    patcher = patch("ui.main_window.QMessageBox")
    mock_box_cls = patcher.start()
    instance = mock_box_cls.return_value
    yes_btn = object()
    no_btn = object()
    instance.addButton.side_effect = [yes_btn, no_btn]
    instance.clickedButton.return_value = no_btn
    return patcher


class ResetConfigurationTests(unittest.TestCase):
    def _window_in_tmp_dir(self, tmp_dir):
        from ui.main_window import MainWindow

        cwd = os.getcwd()
        os.chdir(tmp_dir)
        try:
            return MainWindow()
        finally:
            os.chdir(cwd)

    def test_menu_action_registered_after_nowy_projekt(self):
        # Sprawdzone przez źródło _build_menu, nie przez żywe menuBar() po
        # pełnej konstrukcji MainWindow - PySide6 potrafi skasować
        # Python-owy wrapper podmenu z addMenu(str) bez trzymanej
        # referencji (ten sam bug co przy analogicznym teście dla menu
        # Wygląd, patrz tests/test_previous_month_memory.py).
        import inspect
        import re
        from ui.main_window import MainWindow

        source = inspect.getsource(MainWindow._build_menu)
        collapsed = re.sub(r"\s+", " ", source)
        self.assertIn('file_menu.addAction("Usuń konfigurację", self._reset_configuration)', collapsed)
        self.assertLess(
            collapsed.index('"Nowy projekt...", self._open_new_project'),
            collapsed.index('"Usuń konfigurację", self._reset_configuration'),
        )

    def test_cancelling_the_confirmation_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            window = self._window_in_tmp_dir(tmp_dir)
            window.shop_config.name = "Mój projekt"
            window.schedule.add_employee(Employee(last_name="Kowalski", first_name=""))

            cwd = os.getcwd()
            os.chdir(tmp_dir)
            try:
                patcher = _reject_confirmation()
                try:
                    window._reset_configuration()
                finally:
                    patcher.stop()
            finally:
                os.chdir(cwd)

            self.assertEqual(window.shop_config.name, "Mój projekt")
            self.assertEqual(len(window.schedule.employees), 1)

    def test_confirming_clears_schedule_and_shop_config(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            window = self._window_in_tmp_dir(tmp_dir)
            window.shop_config.name = "Mój projekt"
            window.shop_config.locations["extra"] = LocationConfig(key="extra", name="Druga placówka")
            window.schedule.add_employee(Employee(last_name="Kowalski", first_name="", location_key="extra"))
            window._sync_everything()

            cwd = os.getcwd()
            os.chdir(tmp_dir)
            try:
                patcher = _accept_confirmation()
                try:
                    window._reset_configuration()
                finally:
                    patcher.stop()
            finally:
                os.chdir(cwd)

            self.assertEqual(window.schedule.employees, [])
            self.assertEqual(len(window.shop_config.locations), 1)  # tylko domyślna
            self.assertEqual(window.shop_config.name, "")
            self.assertNotEqual(window.shop_config.business_type, "dino_retail")

    def test_confirming_rewrites_last_project_json(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            window = self._window_in_tmp_dir(tmp_dir)
            window.schedule.add_employee(Employee(last_name="Kowalski", first_name=""))

            cwd = os.getcwd()
            os.chdir(tmp_dir)
            try:
                patcher = _accept_confirmation()
                try:
                    window._reset_configuration()
                finally:
                    patcher.stop()

                from persistence.project_io import load_project_bundle
                project, active_year, active_month = load_project_bundle("last_project.json")
                schedule, shop = project.get(active_year, active_month)
                self.assertEqual(schedule.employees, [])
            finally:
                os.chdir(cwd)

    def test_confirming_does_not_touch_first_run_license_or_tutorial_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cwd = os.getcwd()
            os.chdir(tmp_dir)
            try:
                untouched_files = {
                    "first_run.flag": "seen",
                    "config_tutorial_seen.flag": "seen",
                    "employee_tutorial_seen.flag": "seen",
                    "locations_tutorial_seen.flag": "seen",
                    "quick_mode_tutorial_seen.flag": "seen",
                    "license.json": '{"key": "ABC-123"}',
                    "machine_id.json": '{"id": "xyz"}',
                    "demo.json": '{"generations_used": 3}',
                }
                for name, content in untouched_files.items():
                    with open(name, "w") as f:
                        f.write(content)

                window = self._window_in_tmp_dir(tmp_dir)
                window.schedule.add_employee(Employee(last_name="Kowalski", first_name=""))

                patcher = _accept_confirmation()
                try:
                    window._reset_configuration()
                finally:
                    patcher.stop()

                for name, original_content in untouched_files.items():
                    with open(name) as f:
                        self.assertEqual(f.read(), original_content, f"{name} was modified")
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
