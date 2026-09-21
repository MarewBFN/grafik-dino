"""Main window tutorial (ui/main_window.py::MainWindow._build_tutorial_steps)
gained steps for the newest features (copy/paste day, employee icons,
"+ Dodaj własne..." quick-mode presets) in this session's UI/UX round - make
sure they stay well-formed and never reference hidden functionality (see
ENYO_ONLY_CHANGES.md)."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QWidget

_app = QApplication.instance() or QApplication([])

from ui.main_window import MainWindow

FORBIDDEN_PHRASES = [
    "Progi obsady",
    "Nazwa i Profil placówki",
    "Okres rozliczeniowy",
    "poprzedniego miesiąca",
    "Niedziele handlowe",
]


def _make_window(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return MainWindow()


def test_build_tutorial_steps_has_well_formed_steps(tmp_path, monkeypatch):
    window = _make_window(tmp_path, monkeypatch)

    steps = window._build_tutorial_steps()

    assert len(steps) > 0
    known = {
        window.btn_add_employee,
        window.btn_generate,
        window.grid,
        window.btn_quick_mode,
        window.btn_expand_view,
    }
    for step in steps:
        assert step.title.strip()
        assert step.text.strip()
        if step.target is not None:
            assert isinstance(step.target, QWidget)
            assert step.target in known
        for phrase in FORBIDDEN_PHRASES:
            assert phrase not in step.title
            assert phrase not in step.text


def test_tutorial_mentions_copy_paste_and_icons_and_custom_quick_presets(tmp_path, monkeypatch):
    window = _make_window(tmp_path, monkeypatch)

    steps = window._build_tutorial_steps()
    all_text = " ".join(f"{s.title} {s.text}" for s in steps)

    assert "Ctrl+C" in all_text and "Ctrl+V" in all_text
    assert "ikon" in all_text.lower()
    assert "Dodaj własne" in all_text
