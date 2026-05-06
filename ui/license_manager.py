import os
import json
import uuid
import hashlib
import platform
from PySide6.QtWidgets import QInputDialog, QMessageBox

LICENSE_FILE = "license.json"

def get_user_id() -> str:
    raw = (
        platform.node()
        + platform.system()
        + str(uuid.getnode())
    )

    hash_hex = hashlib.sha256(raw.encode()).hexdigest()
    return hash_hex[:8].upper()


def validate_license(user_id: str, key: str) -> bool:
    secret = "dupadupa"

    raw = user_id + secret
    hash_hex = hashlib.sha256(raw.encode()).hexdigest()

    digits = ''.join(filter(str.isdigit, hash_hex))
    expected = digits[:8]

    return key == expected


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