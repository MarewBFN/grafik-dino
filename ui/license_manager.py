import os
import json
import hashlib
import platform
import socket
import getpass
from PySide6.QtWidgets import QInputDialog, QMessageBox

LICENSE_FILE = "license.json"
SECRET = "dupadupa"


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
        parts.append(uuid.getnode().__str__())
    except Exception:
        pass

    raw = "|".join(parts)
    hash_hex = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return hash_hex[:6].upper()


def get_user_id() -> str:
    return build_machine_fingerprint()


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
        parent.demo.is_demo = False

        # 🔥 odświeżenie UI bez restartu
        if hasattr(parent, "_update_generate_label"):
            parent._update_generate_label()

        if hasattr(parent, "demo_label"):
            parent.demo_label.hide()

        if hasattr(parent, "btn_buy"):
            parent.btn_buy.hide()

        QMessageBox.information(parent, "Sukces", "Program aktywowany!")
    else:
        QMessageBox.warning(parent, "Błąd", "Niepoprawny klucz.")