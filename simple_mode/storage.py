import json
import os

from simple_mode.data import SimpleModeData

SIMPLE_MODE_FILE = "last_project_simple.json"


def load_simple_mode_data(path=SIMPLE_MODE_FILE):
    if not os.path.exists(path):
        return SimpleModeData()

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return SimpleModeData()

    return SimpleModeData.from_dict(raw)


def save_simple_mode_data(data, path=SIMPLE_MODE_FILE):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data.to_dict(), f, indent=2, ensure_ascii=False)
