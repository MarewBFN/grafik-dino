import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui.license_manager import build_machine_fingerprint, generate_license, validate_license


def test_build_machine_fingerprint_is_stable_and_not_mac_based():
    fingerprint = build_machine_fingerprint()
    assert isinstance(fingerprint, str)
    assert len(fingerprint) == 6
    assert fingerprint == build_machine_fingerprint()


def test_fingerprint_stays_stable_when_uuid_getnode_returns_random_value(monkeypatch, tmp_path):
    """Regression test: on machines where uuid.getnode() can't find a real
    network adapter, it returns a new random (multicast-bit-set) number on
    every process run. Simulate that here and make sure the fingerprint
    -- and therefore the stored license key -- no longer changes across
    what would be separate app launches (e.g. after a reboot).
    """
    monkeypatch.chdir(tmp_path)

    calls = iter([
        uuid.uuid4().int & ((1 << 48) - 1) | (1 << 40),
        uuid.uuid4().int & ((1 << 48) - 1) | (1 << 40),
    ])
    monkeypatch.setattr(uuid, "getnode", lambda: next(calls))

    first_run_fingerprint = build_machine_fingerprint()
    second_run_fingerprint = build_machine_fingerprint()

    assert first_run_fingerprint == second_run_fingerprint


def test_generate_license_matches_validation_for_explicit_fingerprint():
    fingerprint = "stable-machine-id"
    key = generate_license(fingerprint)

    assert validate_license(fingerprint, key)


# --- get_user_id: ID zapamiętane, odporne na aktualizacje Windows ----------

import json

from ui import license_manager


def _machine(monkeypatch, guid, fingerprint):
    monkeypatch.setattr(license_manager, "_windows_machine_guid", lambda: guid)
    monkeypatch.setattr(license_manager, "build_machine_fingerprint", lambda: fingerprint)


def test_first_run_uses_the_same_id_as_before(monkeypatch, tmp_path):
    """Istniejące klucze/wpisy w panelu muszą dalej pasować."""
    monkeypatch.chdir(tmp_path)
    _machine(monkeypatch, "guid-1", "AAAAAA")
    assert license_manager.get_user_id() == "AAAAAA"


def test_id_survives_windows_update(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _machine(monkeypatch, "guid-1", "AAAAAA")
    license_manager.get_user_id()

    _machine(monkeypatch, "guid-1", "BBBBBB")  # nowy numer kompilacji Windows
    assert license_manager.get_user_id() == "AAAAAA"


def test_copied_folder_on_another_computer_gets_its_own_id(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _machine(monkeypatch, "guid-1", "AAAAAA")
    license_manager.get_user_id()

    _machine(monkeypatch, "guid-2", "CCCCCC")
    assert license_manager.get_user_id() == "CCCCCC"


def test_hand_edited_id_is_rejected(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _machine(monkeypatch, "guid-1", "AAAAAA")
    license_manager.get_user_id()

    path = tmp_path / license_manager.USER_ID_FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    data["user_id"] = "DDDDDD"  # ID płacącego klienta wpisane ręcznie
    path.write_text(json.dumps(data), encoding="utf-8")

    assert license_manager.get_user_id() == "AAAAAA"


def test_without_machine_guid_falls_back_to_fingerprint(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _machine(monkeypatch, None, "AAAAAA")
    assert license_manager.get_user_id() == "AAAAAA"
    assert not (tmp_path / license_manager.USER_ID_FILE).exists()
