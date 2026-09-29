"""Persists user-authored CustomBusinessProfile objects to disk.

Uses utils.get_app_data_path, which already points at
%LOCALAPPDATA%\\GrafikDino\\ - a writable per-user location even when the app
itself is installed somewhere read-only. Profiles are shared across every
project file (a client's business rules don't change month to month), so this
lives outside any single project's JSON.
"""

import json

from model.custom_profile import CustomBusinessProfile
from utils import get_app_data_path

FILE_NAME = "custom_profiles.json"


def _store_path():
    return get_app_data_path(FILE_NAME)


def load_custom_profiles() -> list[CustomBusinessProfile]:
    path = _store_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    profiles = []
    for entry in raw.get("profiles", []):
        try:
            profiles.append(CustomBusinessProfile.from_dict(entry))
        except (KeyError, TypeError):
            continue
    return profiles


def _write_all(profiles: list[CustomBusinessProfile]) -> None:
    with open(_store_path(), "w", encoding="utf-8") as f:
        json.dump({"profiles": [p.to_dict() for p in profiles]}, f, ensure_ascii=False, indent=2)


def save_custom_profile(profile: CustomBusinessProfile) -> None:
    profiles = load_custom_profiles()
    profiles = [p for p in profiles if p.key != profile.key]
    profiles.append(profile)
    _write_all(profiles)


def delete_custom_profile(key: str) -> None:
    profiles = [p for p in load_custom_profiles() if p.key != key]
    _write_all(profiles)
