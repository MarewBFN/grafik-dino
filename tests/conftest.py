"""Wspólne ustawienia testów: MainWindow() tworzone w testach nie łączy się
z siecią.

- Licencja online: z wpisanym LICENSE_SERVER_URL (licensing/online.py)
  każde okno sprawdzałoby licencję na prawdziwym serwerze z ID tego
  komputera, a odłożone sprawdzenie (QTimer 1,5 s) wpadało do późniejszych
  testów. Testy licencji ustawiają własny adres przez monkeypatch.
- Sprawdzanie aktualizacji (QTimer 1 s -> zapytanie do GitHuba w wątku GUI,
  timeout 5 s) z okien poprzednich testów blokowało pętlę zdarzeń w
  późniejszych testach. Sam update_checker testuje test_update_checker.py."""

import pytest

from licensing import online
from ui.main_window import MainWindow


@pytest.fixture(autouse=True)
def _no_network_from_main_window(monkeypatch):
    monkeypatch.setattr(online, "LICENSE_SERVER_URL", "")
    monkeypatch.setattr(MainWindow, "_check_updates", lambda self, manual=False: None)
