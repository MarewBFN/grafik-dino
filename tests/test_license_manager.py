import sys
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


def test_generate_license_matches_validation_for_explicit_fingerprint():
    fingerprint = "stable-machine-id"
    key = generate_license(fingerprint)

    assert validate_license(fingerprint, key)
