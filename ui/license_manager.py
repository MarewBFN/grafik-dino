import os
import json
import hashlib
import platform
import socket
import getpass
from PySide6.QtWidgets import QInputDialog, QMessageBox

LICENSE_FILE = "license.json"
MACHINE_ID_FILE = "machine_id.json"
USER_ID_FILE = "user_id.json"
SECRET = "dupadupa"


def _get_or_create_persisted_node() -> str:
    """Return a random id that is generated once and reused on every call.

    Used as a fallback for uuid.getnode() below, so it must be persisted
    to disk to stay stable across process restarts.
    """
    if os.path.exists(MACHINE_ID_FILE):
        try:
            with open(MACHINE_ID_FILE, "r") as f:
                node = json.load(f).get("node")
                if node:
                    return node
        except Exception:
            pass

    import uuid as uuid_module
    node = uuid_module.uuid4().hex

    try:
        with open(MACHINE_ID_FILE, "w") as f:
            json.dump({"node": node}, f)
    except Exception:
        pass

    return node


def build_machine_fingerprint() -> str:
    """Build a stable machine fingerprint from non-changing machine data.

    We intentionally avoid the MAC address because it can change after certain
    network adapter changes. The fingerprint combines OS, hostname, username,
    and a few other stable values that are specific to the current machine.
    """

    parts = [
        platform.system(),
        platform.release(),
        platform.version(),
        platform.machine(),
        socket.gethostname(),
        getpass.getuser(),
    ]

    # Add a couple of platform-specific values that are usually stable,
    # but still unique enough per machine.
    try:
        import uuid
        node = uuid.getnode()
        if (node >> 40) & 0x01:
            # uuid.getnode() couldn't find a real network adapter, so it
            # returned a random 48-bit number (RFC 4122 multicast bit set)
            # that changes on every single process run. Using it as-is
            # would make the fingerprint — and therefore the license key —
            # change every time the app restarts. Fall back to an id we
            # persist ourselves so it stays stable instead.
            parts.append(_get_or_create_persisted_node())
        else:
            parts.append(str(node))
    except Exception:
        pass

    raw = "|".join(parts)
    hash_hex = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return hash_hex[:6].upper()


def _windows_machine_guid():
    """Identyfikator instalacji Windows (rejestr: HKLM, SOFTWARE/Microsoft/Cryptography
    -> MachineGuid). Nie zmienia się przy aktualizacjach Windows, zmienia
    się dopiero przy nowej instalacji systemu. None poza Windows/przy
    błędzie odczytu."""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
        return str(value) or None
    except Exception:
        return None


def _user_id_check(user_id: str, machine_guid: str) -> str:
    return hashlib.sha256(f"{user_id}|{machine_guid}|{SECRET}".encode("utf-8")).hexdigest()


def get_user_id() -> str:
    """ID użytkownika (prawy dolny róg okna, klucz produktu, licencja online).

    build_machine_fingerprint() zawiera numer kompilacji Windows, więc
    większa aktualizacja Windows zmieniała ID - i odbierała licencję.
    Dlatego ID liczone przy pierwszym uruchomieniu (identycznie jak dawniej,
    więc istniejące klucze i wpisy w panelu dalej pasują) jest zapamiętywane
    w USER_ID_FILE razem z MachineGuid i sumą kontrolną:
    - folder skopiowany na inny komputer ma inny MachineGuid -> ID liczone
      od nowa, licencja się nie przenosi;
    - ręcznie wpisane cudze ID nie ma poprawnej sumy -> liczone od nowa."""
    machine_guid = _windows_machine_guid()
    if machine_guid is None:
        return build_machine_fingerprint()

    try:
        with open(USER_ID_FILE, "r", encoding="utf-8") as f:
            stored = json.load(f)
        user_id = stored.get("user_id", "")
        if (
            stored.get("machine_guid") == machine_guid
            and stored.get("check") == _user_id_check(user_id, machine_guid)
        ):
            return user_id
    except Exception:
        pass

    user_id = build_machine_fingerprint()
    try:
        with open(USER_ID_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"user_id": user_id, "machine_guid": machine_guid,
                 "check": _user_id_check(user_id, machine_guid)},
                f,
            )
    except OSError:
        pass
    return user_id


def generate_license(user_id: str) -> str:
    raw = user_id + SECRET
    hash_hex = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    digits = ''.join(filter(str.isdigit, hash_hex))
    return digits[:8]


def validate_license(user_id: str, key: str) -> bool:
    return generate_license(user_id) == key


def save_license(key: str):
    with open(LICENSE_FILE, "w") as f:
        json.dump({"key": key}, f)


def load_license():
    if not os.path.exists(LICENSE_FILE):
        return None

    try:
        with open(LICENSE_FILE, "r") as f:
            data = json.load(f)
            return data.get("key")
    except:
        return None


def show_license_dialog(parent):
    text, ok = QInputDialog.getText(
        parent,
        "Aktywacja produktu",
        "Podaj klucz produktu:"
    )

    if not ok or not text:
        return

    user_id = get_user_id()

    if validate_license(user_id, text):
        save_license(text)

        # Odświeża UI bez restartu; licencja online może mimo poprawnego
        # klucza trzymać to ID w demo (status "blocked" na serwerze).
        state = parent._on_license_key_saved()
        if state.is_full:
            QMessageBox.information(parent, "Sukces", "Program aktywowany!")
        else:
            QMessageBox.warning(
                parent,
                "Licencja wyłączona",
                "Klucz jest poprawny, ale licencja na tym komputerze została "
                "wyłączona. Skontaktuj się ze sprzedawcą programu.",
            )
    else:
        QMessageBox.warning(parent, "Błąd", "Niepoprawny klucz.")