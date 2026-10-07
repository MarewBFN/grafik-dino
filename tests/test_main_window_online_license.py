"""ui/main_window.py - licencja online zmienia stan pełna/demo w trakcie
działania programu (bez restartu): etykieta demo, przycisk zakupu i
komunikat o utracie pełnej wersji."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from licensing import online
from ui.main_window import MainWindow
import tests.test_online_license as signed


@pytest.fixture
def window(monkeypatch):
    monkeypatch.setattr(online, "LICENSE_SERVER_URL", "")  # bez sieci w teście
    monkeypatch.setattr(online, "LICENSE_PUBLIC_KEY", signed.PUBLIC_B64)
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp_dir:
        os.chdir(tmp_dir)
        # Bez kreatora pierwszego uruchomienia (modalny) przy processEvents().
        Path("first_run.flag").write_text("seen")
        try:
            win = MainWindow()
            win.user_id = signed.USER_ID
            win.online_license = online.OnlineLicense(signed.USER_ID)
            yield win
        finally:
            os.chdir(cwd)


def _now_record(status, **kwargs):
    return signed._record(status, issued_at=datetime.now(timezone.utc), **kwargs)


def test_starts_as_demo_with_demo_widgets(window):
    assert window.demo.is_demo
    assert not window.demo_label.isHidden()
    assert not window.btn_buy.isHidden()


def test_server_grants_trial_then_revokes(window):
    expires = (datetime.now() + timedelta(days=10)).date().isoformat()
    with patch("ui.main_window.QMessageBox") as box:
        window._on_license_check_finished(_now_record("trial", expires_at=expires), False)
        assert not window.demo.is_demo
        assert window.demo_label.isHidden() and window.btn_buy.isHidden()
        assert window.generate_limit_label.text() == ""
        box.information.assert_not_called()

        window._on_license_check_finished(_now_record("blocked"), False)
        assert window.demo.is_demo
        assert not window.demo_label.isHidden() and not window.btn_buy.isHidden()
        box.information.assert_called_once()
        assert "wyłączona" in box.information.call_args.args[2]


def test_offline_check_keeps_last_known_state(window):
    with patch("ui.main_window.QMessageBox"):
        window._on_license_check_finished(_now_record("full"), False)
        window._on_license_check_finished(None, False)
    assert not window.demo.is_demo


def test_legacy_key_is_overridden_by_block(window):
    with patch("ui.main_window.QMessageBox"):
        window._on_license_check_finished(_now_record("blocked"), False)
        state = window._on_license_key_saved()
    assert not state.is_full
    assert window.demo.is_demo


def test_legacy_key_activates_without_server(window):
    state = window._on_license_key_saved()
    assert state.is_full
    assert not window.demo.is_demo
    assert window.demo_label.isHidden()


def test_background_check_reaches_gui_thread(window, monkeypatch):
    import threading
    import time

    monkeypatch.setattr(online, "LICENSE_SERVER_URL", "https://licencje.example")
    calls = []

    def fake_fetch(user_id, legacy, version, channel):
        calls.append((user_id, legacy, threading.current_thread() is threading.main_thread()))
        return _now_record("full")

    monkeypatch.setattr(online, "fetch_record", fake_fetch)
    received = []
    original = window._on_license_check_finished

    def spy(record, manual):
        received.append(threading.current_thread() is threading.main_thread())
        original(record, manual)

    monkeypatch.setattr(window, "_on_license_check_finished", spy)
    window.license_bridge.finished.disconnect()
    window.license_bridge.finished.connect(spy)

    with patch("ui.main_window.QMessageBox") as box:
        window._start_license_check()
        window._start_license_check(manual=True)  # w trakcie - dopisuje okienko
        deadline = time.time() + 5
        while not received and time.time() < deadline:
            _app.processEvents()
            time.sleep(0.01)

        assert calls == [(signed.USER_ID, False, False)]  # jedno zapytanie, w tle
        assert received == [True]  # wynik obsłużony w wątku GUI
        assert not window.demo.is_demo
        box.information.assert_called_once()  # okienko z ręcznego sprawdzenia
