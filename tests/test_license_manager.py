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
