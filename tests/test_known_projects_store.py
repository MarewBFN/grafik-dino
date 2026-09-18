from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from persistence import known_projects_store as store


def _isolate_store(monkeypatch, tmp_path):
    fake_path = tmp_path / "known_projects.json"
    monkeypatch.setattr(store, "_store_path", lambda: str(fake_path))
    return fake_path


def test_load_known_projects_defaults_empty(monkeypatch, tmp_path):
    _isolate_store(monkeypatch, tmp_path)
    assert store.load_known_projects() == []


def test_register_and_load_round_trip(monkeypatch, tmp_path):
    _isolate_store(monkeypatch, tmp_path)
    store.register_known_project("C:/projects/obiekt1.myp", "Obiekt 1")

    projects = store.load_known_projects()
    assert projects == [{"path": "C:/projects/obiekt1.myp", "label": "Obiekt 1"}]


def test_registering_the_same_path_again_updates_label_and_moves_to_front(monkeypatch, tmp_path):
    _isolate_store(monkeypatch, tmp_path)
    store.register_known_project("C:/a.myp", "A")
    store.register_known_project("C:/b.myp", "B")
    store.register_known_project("C:/a.myp", "A (zmieniona nazwa)")

    projects = store.load_known_projects()
    assert projects[0] == {"path": "C:/a.myp", "label": "A (zmieniona nazwa)"}
    assert projects[1] == {"path": "C:/b.myp", "label": "B"}
    assert len(projects) == 2


def test_most_recently_registered_project_is_first(monkeypatch, tmp_path):
    _isolate_store(monkeypatch, tmp_path)
    store.register_known_project("C:/a.myp", "A")
    store.register_known_project("C:/b.myp", "B")

    projects = store.load_known_projects()
    assert [p["path"] for p in projects] == ["C:/b.myp", "C:/a.myp"]


def test_remove_known_project(monkeypatch, tmp_path):
    _isolate_store(monkeypatch, tmp_path)
    store.register_known_project("C:/a.myp", "A")
    store.register_known_project("C:/b.myp", "B")

    store.remove_known_project("C:/a.myp")

    projects = store.load_known_projects()
    assert [p["path"] for p in projects] == ["C:/b.myp"]


def test_clear_known_projects(monkeypatch, tmp_path):
    _isolate_store(monkeypatch, tmp_path)
    store.register_known_project("C:/a.myp", "A")

    store.clear_known_projects()

    assert store.load_known_projects() == []


def test_load_ignores_malformed_entries(monkeypatch, tmp_path):
    fake_path = _isolate_store(monkeypatch, tmp_path)
    fake_path.write_text(
        '{"projects": [{"path": "C:/a.myp", "label": "A"}, {"label": "no path"}, "not even a dict"]}',
        encoding="utf-8",
    )

    projects = store.load_known_projects()
    assert projects == [{"path": "C:/a.myp", "label": "A"}]
