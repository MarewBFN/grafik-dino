"""Licencja online (serwer: license_server/).

Program przy starcie i co godzinę wysyła na serwer licencji WYŁĄCZNIE swoje
ID użytkownika, wersję i kanał wydania. Serwer odsyła status tego ID
(demo / trial / full / blocked / expired) podpisany kluczem Ed25519.
Podpisaną odpowiedź zapamiętujemy w CACHE_FILE, więc program działa też bez
internetu:

- "full"  - pełna wersja bez limitu, także offline;
- "trial" - pełna wersja do dnia expires_at, ale tylko przez OFFLINE_GRACE
            od ostatniej odpowiedzi serwera (wyłączenie internetu nie
            przedłuża testu);
- reszta  - wersja demo.

Stary 8-cyfrowy klucz produktu (ui/license_manager.py) dalej daje pełną
wersję - chyba że serwer odpowie "blocked" dla tego ID.
"""

import base64
import binascii
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import requests

from licensing import ed25519

# Adres serwera po `npx wrangler deploy` (bez "/" na końcu), np.
# "https://dingo-licencje.twoja-nazwa.workers.dev". Pusty = sprawdzanie
# online wyłączone i działa tylko stary klucz produktu.
LICENSE_SERVER_URL = ""

# Klucz publiczny wypisany przez `npm run keys` w license_server/.
LICENSE_PUBLIC_KEY = ""

CACHE_FILE = "license_status.json"
OFFLINE_GRACE = timedelta(days=7)
# Ile zegar komputera może się cofnąć/spóźniać, zanim uznamy go za cofnięty.
CLOCK_TOLERANCE = timedelta(days=1)
REQUEST_TIMEOUT = 5

REASON_LEGACY = "legacy"
REASON_FULL = "full"
REASON_TRIAL = "trial"
REASON_DEMO = "demo"
REASON_EXPIRED = "expired"
REASON_BLOCKED = "blocked"
REASON_OFFLINE = "offline"
REASON_CLOCK = "clock"


@dataclass(frozen=True)
class LicenseState:
    is_full: bool
    reason: str
    expires_at: Optional[date] = None


def is_configured() -> bool:
    return bool(LICENSE_SERVER_URL and LICENSE_PUBLIC_KEY)


def verify_record(record, user_id, public_key=None):
    """Zwraca payload (dict), jeśli podpis jest ważny i dotyczy tego ID."""
    try:
        payload_bytes = base64.b64decode(record["payload"], validate=True)
        signature = base64.b64decode(record["signature"], validate=True)
        key = base64.b64decode(public_key or LICENSE_PUBLIC_KEY, validate=True)
    except (KeyError, TypeError, ValueError, binascii.Error):
        return None

    if not ed25519.verify(key, payload_bytes, signature):
        return None

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except ValueError:
        return None

    if not isinstance(payload, dict) or payload.get("user_id") != user_id:
        return None
    return payload


def fetch_record(user_id, legacy_key, app_version, channel):
    """Zgłasza ID na serwer. Zwraca podpisany rekord albo None (brak
    internetu, błąd serwera, zły podpis). Wołane w wątku roboczym."""
    if not is_configured():
        return None

    try:
        response = requests.post(
            f"{LICENSE_SERVER_URL}/api/check",
            json={
                "user_id": user_id,
                "legacy_key": bool(legacy_key),
                "app_version": app_version,
                "channel": channel,
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        record = {"payload": data["payload"], "signature": data["signature"]}
    except Exception as e:
        print("[LICENSE CHECK ERROR]", e)
        return None

    if verify_record(record, user_id) is None:
        print("[LICENSE CHECK ERROR] niepoprawny podpis odpowiedzi serwera")
        return None
    return record


def resolve_license(legacy_valid, payload, now, last_seen_time=None) -> LicenseState:
    status = payload.get("status") if payload else None

    if status == "blocked":
        return LicenseState(False, REASON_BLOCKED)
    if legacy_valid:
        return LicenseState(True, REASON_LEGACY)
    if status == "full":
        return LicenseState(True, REASON_FULL)

    expires_at = _parse_date(payload.get("expires_at")) if payload else None
    if status == "expired":
        return LicenseState(False, REASON_EXPIRED, expires_at)
    if status != "trial":
        return LicenseState(False, REASON_DEMO)

    issued_at = _parse_time(payload.get("issued_at"))
    if expires_at is None or issued_at is None:
        return LicenseState(False, REASON_DEMO)

    clock_rolled_back = now + CLOCK_TOLERANCE < issued_at or (
        last_seen_time is not None and now + CLOCK_TOLERANCE < last_seen_time
    )
    if clock_rolled_back:
        return LicenseState(False, REASON_CLOCK, expires_at)
    if now.astimezone().date() > expires_at:
        return LicenseState(False, REASON_EXPIRED, expires_at)
    if now - issued_at > OFFLINE_GRACE:
        return LicenseState(False, REASON_OFFLINE, expires_at)
    return LicenseState(True, REASON_TRIAL, expires_at)


class OnlineLicense:
    """Stan licencji jednego komputera + zapamiętana odpowiedź serwera."""

    def __init__(self, user_id, cache_file=CACHE_FILE):
        self.user_id = user_id
        self.cache_file = cache_file

    def evaluate(self, legacy_valid, now=None):
        """Zwraca (LicenseState, lost_full). lost_full=True, gdy poprzednio
        program miał pełną wersję, a teraz już nie - wtedy warto to
        użytkownikowi wyjaśnić (raz)."""
        now = now or datetime.now(timezone.utc)
        cache = self._load()

        payload = verify_record(cache, self.user_id) if "payload" in cache else None
        last_seen_time = _parse_time(cache.get("last_seen_time"))
        state = resolve_license(legacy_valid, payload, now, last_seen_time)

        lost_full = bool(cache.get("was_full")) and not state.is_full
        if last_seen_time is None or now > last_seen_time:
            cache["last_seen_time"] = now.isoformat()
        cache["was_full"] = state.is_full
        self._save(cache)

        return state, lost_full

    def store_record(self, record):
        payload = verify_record(record, self.user_id)
        if payload is None:
            return
        cache = self._load()
        cache["payload"] = record["payload"]
        cache["signature"] = record["signature"]
        # Czas serwera jest wiarygodny - prostuje zapamiętany czas, gdyby
        # zegar komputera kiedyś chwilowo uciekł w przyszłość.
        if payload.get("issued_at"):
            cache["last_seen_time"] = payload["issued_at"]
        self._save(cache)

    def _load(self):
        if not os.path.exists(self.cache_file):
            return {}
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save(self, cache):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(cache, f)
        except Exception:
            pass


def describe_state(state: LicenseState) -> str:
    if state.reason in (REASON_LEGACY, REASON_FULL):
        return "Pełna wersja programu jest aktywna."
    if state.reason == REASON_TRIAL:
        return f"Pełna wersja testowa jest aktywna do {_format_date(state.expires_at)}."
    if state.reason == REASON_EXPIRED:
        if state.expires_at:
            return f"Okres testowy pełnej wersji zakończył się {_format_date(state.expires_at)}."
        return "Okres testowy pełnej wersji zakończył się."
    if state.reason == REASON_BLOCKED:
        return "Licencja na tym komputerze została wyłączona."
    if state.reason == REASON_OFFLINE:
        return (
            "Program nie mógł potwierdzić licencji testowej przez ponad "
            f"{OFFLINE_GRACE.days} dni. Połącz komputer z internetem i uruchom "
            "program ponownie."
        )
    if state.reason == REASON_CLOCK:
        return (
            "Data w komputerze wygląda na nieprawidłową. Ustaw poprawną datę "
            "i godzinę, a potem uruchom program ponownie."
        )
    return "Program działa w wersji demonstracyjnej."


def _parse_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _format_date(value):
    return value.strftime("%d.%m.%Y") if value else "?"
