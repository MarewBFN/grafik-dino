"""Persists a list of known project files for the "Placówki" menu
(ui/main_window.py) - lets a user running several placówki (each its own
project file, per the client's decision, patrz "plan profil ochrona
(analiza specyfikacji klienta).md", sekcja 11 pkt 2) switch between them
with one click instead of hunting for files via "Wczytaj" every time.

Uses utils.get_app_data_path - the same %LOCALAPPDATA%\\GrafikDino\\
location as model/custom_profile_store.py. This list is a cross-project
preference (which files does this user work with), not part of any single
project's own JSON, so it lives outside it exactly like custom profiles do.
"""

import json

from utils import get_app_data_path

FILE_NAME = "known_projects.json"


def _store_path():
    return get_app_data_path(FILE_NAME)


def load_known_projects() -> list[dict]:
    """[{"path": ..., "label": ...}, ...], most-recently-used first."""
    path = _store_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    projects = raw.get("projects", [])
    return [p for p in projects if isinstance(p, dict) and p.get("path")]


def _write_all(projects: list[dict]) -> None:
    with open(_store_path(), "w", encoding="utf-8") as f:
        json.dump({"projects": projects}, f, ensure_ascii=False, indent=2)


def register_known_project(path: str, label: str) -> None:
    """Adds `path` to the list (or refreshes its label if already known),
    moved to the front - most-recently-used first."""
    projects = [p for p in load_known_projects() if p["path"] != path]
    projects.insert(0, {"path": path, "label": label})
    _write_all(projects)


def remove_known_project(path: str) -> None:
    projects = [p for p in load_known_projects() if p["path"] != path]
    _write_all(projects)


def clear_known_projects() -> None:
    _write_all([])
