"""licensing/online.py + licensing/ed25519.py - licencja online z serwera
licencji (license_server/): podpis odpowiedzi, okres testowy, 7 dni bez
internetu, cofnięty zegar, stary klucz produktu i jego blokada."""

import base64
import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from licensing import ed25519, online


# --- podpisywanie w testach (RFC 8032, jak robi to serwer) -------------------

def _sha512_int(data):
    return int.from_bytes(hashlib.sha512(data).digest(), "little")


def _expand(secret):
    digest = hashlib.sha512(secret).digest()
    a = int.from_bytes(digest[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, digest[32:]


def _compress(point):
    zinv = pow(point[2], ed25519._P - 2, ed25519._P)
    x = point[0] * zinv % ed25519._P
    y = point[1] * zinv % ed25519._P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _public_key(secret):
    a, _ = _expand(secret)
    return _compress(ed25519._point_mul(a, ed25519._G))


def _sign(secret, message):
    a, prefix = _expand(secret)
    public = _compress(ed25519._point_mul(a, ed25519._G))
    r = _sha512_int(prefix + message) % ed25519._L
    r_bytes = _compress(ed25519._point_mul(r, ed25519._G))
    h = _sha512_int(r_bytes + public + message) % ed25519._L
    s = (r + h * a) % ed25519._L
    return r_bytes + s.to_bytes(32, "little")


SECRET = bytes(range(32))
PUBLIC_B64 = base64.b64encode(_public_key(SECRET)).decode()
USER_ID = "3FA9C1"
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


def _record(status, expires_at=None, issued_at=NOW, user_id=USER_ID, secret=SECRET):
    payload = json.dumps({
        "v": 1,
        "user_id": user_id,
        "status": status,
        "expires_at": expires_at,
        "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
    }).encode()
    return {
        "payload": base64.b64encode(payload).decode(),
        "signature": base64.b64encode(_sign(secret, payload)).decode(),
    }


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setattr(online, "LICENSE_SERVER_URL", "https://licencje.example")
    monkeypatch.setattr(online, "LICENSE_PUBLIC_KEY", PUBLIC_B64)


# --- Ed25519 -----------------------------------------------------------------

def test_rfc8032_test_vectors():
    vectors = [
        (
            "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
            "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
            "",
            "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
        ),
        (
            "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
            "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
            "72",
            "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
        ),
    ]
    for secret, public, message, signature in vectors:
        secret, public, message, signature = map(bytes.fromhex, (secret, public, message, signature))
        assert _public_key(secret) == public
        assert _sign(secret, message) == signature
        assert ed25519.verify(public, message, signature)
        assert not ed25519.verify(public, message + b"x", signature)
        assert not ed25519.verify(public, message, signature[:-1] + bytes([signature[-1] ^ 1]))


def test_matches_cryptography_library_when_available():
    keys = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    from cryptography.hazmat.primitives import serialization

    private = keys.Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    for message in (b"", b"licencja", bytes(range(200))):
        signature = private.sign(message)
        assert ed25519.verify(public, message, signature)
        assert not ed25519.verify(public, message + b"!", signature)


def test_verify_rejects_malformed_input():
    assert not ed25519.verify(b"short", b"", bytes(64))
    assert not ed25519.verify(bytes(32), b"", b"short")
    assert not ed25519.verify(b"\xff" * 32, b"", bytes(64))


# --- podpisany rekord ---------------------------------------------------------

def test_verify_record_accepts_valid_and_rejects_tampering():
    record = _record("full")
    assert online.verify_record(record, USER_ID)["status"] == "full"

    # Rekord innego komputera.
    assert online.verify_record(record, "000000") is None

    # Ręcznie przerobiony status.
    payload = json.loads(base64.b64decode(record["payload"]))
    payload["status"] = "full" if payload["status"] != "full" else "trial"
    tampered = dict(record, payload=base64.b64encode(json.dumps(payload).encode()).decode())
    assert online.verify_record(tampered, USER_ID) is None

    # Podpisane innym kluczem (fałszywy serwer).
    assert online.verify_record(_record("full", secret=b"\x01" * 32), USER_ID) is None

    assert online.verify_record({}, USER_ID) is None
    assert online.verify_record({"payload": "!!!", "signature": "???"}, USER_ID) is None


def test_not_configured_without_url_or_key(monkeypatch):
    monkeypatch.setattr(online, "LICENSE_SERVER_URL", "")
    assert not online.is_configured()
    assert online.fetch_record(USER_ID, False, "1.0", "dino") is None


# --- rozstrzyganie licencji ---------------------------------------------------

def _payload(status, **kwargs):
    return online.verify_record(_record(status, **kwargs), USER_ID)


def test_resolve_without_anything_is_demo():
    state = online.resolve_license(False, None, NOW)
    assert not state.is_full and state.reason == online.REASON_DEMO


def test_legacy_key_is_full_unless_blocked():
    assert online.resolve_license(True, None, NOW).is_full
    assert online.resolve_license(True, _payload("demo"), NOW).is_full
    assert online.resolve_license(True, _payload("expired", expires_at="2026-10-01"), NOW).is_full

    blocked = online.resolve_license(True, _payload("blocked"), NOW)
    assert not blocked.is_full and blocked.reason == online.REASON_BLOCKED


def test_full_works_offline_without_limit():
    state = online.resolve_license(False, _payload("full"), NOW + timedelta(days=400))
    assert state.is_full


def test_trial_active_until_expiry_date_inclusive():
    payload = _payload("trial", expires_at="2026-10-08")
    state = online.resolve_license(False, payload, NOW)
    assert state.is_full and state.expires_at == date(2026, 10, 8)

    on_last_day = online.resolve_license(False, payload, datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc))
    assert on_last_day.is_full

    after = online.resolve_license(False, payload, datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc))
    assert not after.is_full and after.reason == online.REASON_EXPIRED


def test_trial_needs_server_contact_every_seven_days():
    payload = _payload("trial", expires_at="2027-01-01")
    assert online.resolve_license(False, payload, NOW + timedelta(days=6, hours=23)).is_full

    state = online.resolve_license(False, payload, NOW + timedelta(days=7, hours=1))
    assert not state.is_full and state.reason == online.REASON_OFFLINE


def test_trial_rejects_clock_set_back():
    payload = _payload("trial", expires_at="2027-01-01")

    before_server_time = online.resolve_license(False, payload, NOW - timedelta(days=3))
    assert not before_server_time.is_full and before_server_time.reason == online.REASON_CLOCK

    before_last_run = online.resolve_license(
        False, payload, NOW + timedelta(days=1), last_seen_time=NOW + timedelta(days=5)
    )
    assert not before_last_run.is_full and before_last_run.reason == online.REASON_CLOCK

    # Drobne różnice zegara (strefy, synchronizacja) są tolerowane.
    assert online.resolve_license(False, payload, NOW - timedelta(hours=3)).is_full


def test_server_side_statuses():
    assert online.resolve_license(False, _payload("expired", expires_at="2026-10-01"), NOW).reason == online.REASON_EXPIRED
    assert online.resolve_license(False, _payload("blocked"), NOW).reason == online.REASON_BLOCKED
    assert online.resolve_license(False, _payload("demo"), NOW).reason == online.REASON_DEMO
    assert online.resolve_license(False, _payload("trial"), NOW).reason == online.REASON_DEMO  # brak daty


# --- OnlineLicense (zapamiętana odpowiedź) -------------------------------------

def test_store_and_evaluate_from_cache(tmp_path):
    cache_file = tmp_path / "license_status.json"
    lic = online.OnlineLicense(USER_ID, cache_file=str(cache_file))

    state, lost = lic.evaluate(False, now=NOW)
    assert not state.is_full and not lost

    lic.store_record(_record("trial", expires_at="2026-10-20"))
    state, lost = lic.evaluate(False, now=NOW + timedelta(hours=1))
    assert state.is_full and state.reason == online.REASON_TRIAL and not lost

    # Nowy obiekt (= ponowne uruchomienie programu bez internetu).
    restarted = online.OnlineLicense(USER_ID, cache_file=str(cache_file))
    assert restarted.evaluate(False, now=NOW + timedelta(days=2))[0].is_full


def test_lost_full_reported_once(tmp_path):
    lic = online.OnlineLicense(USER_ID, cache_file=str(tmp_path / "c.json"))
    lic.store_record(_record("trial", expires_at="2026-10-07"))
    assert lic.evaluate(False, now=NOW)[0].is_full

    state, lost = lic.evaluate(False, now=NOW + timedelta(days=2))
    assert not state.is_full and state.reason == online.REASON_EXPIRED and lost

    _, lost_again = lic.evaluate(False, now=NOW + timedelta(days=3))
    assert not lost_again


def test_cache_edited_by_hand_is_ignored(tmp_path):
    cache_file = tmp_path / "c.json"
    lic = online.OnlineLicense(USER_ID, cache_file=str(cache_file))
    lic.store_record(_record("demo"))

    data = json.loads(cache_file.read_text())
    payload = json.loads(base64.b64decode(data["payload"]))
    payload["status"] = "full"
    data["payload"] = base64.b64encode(json.dumps(payload).encode()).decode()
    cache_file.write_text(json.dumps(data))

    assert not lic.evaluate(False, now=NOW)[0].is_full


def test_store_record_ignores_invalid_signature(tmp_path):
    cache_file = tmp_path / "c.json"
    lic = online.OnlineLicense(USER_ID, cache_file=str(cache_file))
    lic.store_record(_record("full", secret=b"\x02" * 32))
    assert not cache_file.exists()


def test_server_time_repairs_clock_that_ran_ahead(tmp_path):
    lic = online.OnlineLicense(USER_ID, cache_file=str(tmp_path / "c.json"))
    # Zegar komputera chwilowo uciekł o miesiąc do przodu...
    lic.evaluate(False, now=NOW + timedelta(days=30))
    # ...po poprawieniu zegara świeża odpowiedź serwera prostuje stan.
    lic.store_record(_record("trial", expires_at="2026-12-01"))
    assert lic.evaluate(False, now=NOW + timedelta(minutes=5))[0].is_full


def test_corrupted_cache_file_means_demo(tmp_path):
    cache_file = tmp_path / "c.json"
    cache_file.write_text("{nie json")
    state, lost = online.OnlineLicense(USER_ID, cache_file=str(cache_file)).evaluate(False, now=NOW)
    assert not state.is_full and not lost


# --- komunikacja z serwerem ---------------------------------------------------

class _Response:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._data


def test_fetch_record_sends_only_id_version_channel(monkeypatch):
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent.update(url=url, body=json)
        return _Response(_record("full"))

    monkeypatch.setattr(online.requests, "post", fake_post)
    record = online.fetch_record(USER_ID, True, "1.2.0", "dino")

    assert record is not None
    assert sent["url"] == "https://licencje.example/api/check"
    assert sent["body"] == {"user_id": USER_ID, "legacy_key": True, "app_version": "1.2.0", "channel": "dino"}


def test_fetch_record_rejects_forged_or_failed_responses(monkeypatch):
    monkeypatch.setattr(online.requests, "post", lambda *a, **k: _Response(_record("full", secret=b"\x03" * 32)))
    assert online.fetch_record(USER_ID, False, "1.2.0", "dino") is None

    monkeypatch.setattr(online.requests, "post", lambda *a, **k: _Response({}, status=500))
    assert online.fetch_record(USER_ID, False, "1.2.0", "dino") is None

    def offline(*a, **k):
        raise ConnectionError("brak internetu")

    monkeypatch.setattr(online.requests, "post", offline)
    assert online.fetch_record(USER_ID, False, "1.2.0", "dino") is None


def test_describe_state_texts():
    assert "aktywna do 08.10.2026" in online.describe_state(online.LicenseState(True, online.REASON_TRIAL, date(2026, 10, 8)))
    assert "zakończył się" in online.describe_state(online.LicenseState(False, online.REASON_EXPIRED))
    assert "wyłączona" in online.describe_state(online.LicenseState(False, online.REASON_BLOCKED))
    assert "7 dni" in online.describe_state(online.LicenseState(False, online.REASON_OFFLINE))
