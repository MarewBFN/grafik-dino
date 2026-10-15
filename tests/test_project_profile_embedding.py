"""Kopia profilu custom w pliku projektu (F1.2): projekt otwiera się tak samo
na komputerze, który nie ma tego profilu; profil lokalny wygrywa z kopią;
stary plik z nieznanym profilem daje ostrzeżenie zamiast cichego Dino."""

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

import model.business_profile as bp
from model.custom_profile import CustomBusinessProfile, RoleDefinition, RuleInstance
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.monthly_project import MonthlyProject
from model.shop_config import ShopConfig
from persistence.project_io import (
    load_project,
    load_project_bundle,
    save_project,
    save_project_bundle,
    unknown_business_types,
)

_app = QApplication.instance() or QApplication([])

KEY = "custom_test_embedding"


def _profile(label="Kasa"):
    return CustomBusinessProfile(
        key=KEY, display_name="Test osadzania",
        roles=[RoleDefinition(key="kasa", label=label)],
        rules=[RuleInstance(type="min_staff_with_role", qualification_key="kasa", id="r1",
                            params={"min_count": 1, "scope": "any_shift"})],
    )


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Biblioteka profili tego "komputera" w katalogu tymczasowym; po teście
    profil testowy znika z rejestru."""
    import model.custom_profile_store as custom_store

    path = tmp_path / "custom_profiles.json"
    monkeypatch.setattr(custom_store, "_store_path", lambda: str(path))
    yield path
    bp.unregister_custom_profile(KEY)


def _project():
    project = MonthlyProject()
    shop = ShopConfig(2026, 10)
    shop.business_type = KEY
    project.put(2026, 10, MonthSchedule(2026, 10, employees=[Employee("A", "B")]), shop)
    return project


def test_bundle_carries_profile_to_a_machine_without_it(store, tmp_path):
    bp.register_custom_profile(_profile())
    path = tmp_path / "projekt.myp"
    save_project_bundle(path, _project(), 2026, 10)
    assert json.loads(path.read_text(encoding="utf-8"))["custom_profiles"][0]["key"] == KEY

    bp.unregister_custom_profile(KEY)  # "inny komputer"
    project, _year, _month = load_project_bundle(path)

    restored = bp.get_custom_profile(KEY)
    assert restored is not None and restored.rules[0].qualification_key == "kasa"
    assert unknown_business_types(project) == []
    assert project.qualifications["kasa"].name == "Kasa"
    # ... i trafił do biblioteki profili tego komputera.
    assert json.loads(store.read_text(encoding="utf-8"))["profiles"][0]["key"] == KEY


def test_local_profile_wins_over_copy_in_file(store, tmp_path):
    bp.register_custom_profile(_profile(label="Kasa"))
    path = tmp_path / "projekt.myp"
    save_project_bundle(path, _project(), 2026, 10)

    bp.register_custom_profile(_profile(label="Kasa fiskalna"))  # zmieniony w kreatorze
    load_project_bundle(path)
    assert bp.get_custom_profile(KEY).roles[0].label == "Kasa fiskalna"
    assert not store.exists()  # nic nie nadpisane w bibliotece


def test_single_month_file_carries_profile_too(store, tmp_path):
    bp.register_custom_profile(_profile())
    project = _project()
    schedule, shop = project.get(2026, 10)
    path = tmp_path / "miesiac.json"
    save_project(path, schedule, shop)

    bp.unregister_custom_profile(KEY)
    load_project(path)
    assert bp.get_custom_profile(KEY) is not None


def test_old_file_with_unknown_profile_is_reported(store, tmp_path):
    project = _project()  # profil nie jest zarejestrowany
    assert unknown_business_types(project) == [KEY]


def test_main_window_warns_about_unknown_profile(store, monkeypatch):
    from ui.main_window import MainWindow

    shown = []
    monkeypatch.setattr("ui.main_window.QTimer.singleShot", lambda _ms, fn: fn())
    monkeypatch.setattr("ui.main_window.QMessageBox.warning", lambda *a, **k: shown.append(a[2]))

    class _Window:
        project = _project()

    MainWindow._warn_unknown_profiles(_Window())
    assert shown and KEY in shown[0] and "Sklep (Dino)" in shown[0]
