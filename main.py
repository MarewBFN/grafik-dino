import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.no_scroll_widgets import install_wheel_guard
from ui.theme import APP_STYLESHEET


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def main():
    # Double-clicking a .myp file (registered by the installer, see
    # "dla inno.iss") launches us with its path as an argument - resolved
    # BEFORE chdir below, in case it was given relative to the caller's cwd.
    open_path = next((os.path.abspath(arg) for arg in sys.argv[1:] if os.path.isfile(arg)), None)

    # Wszystkie pliki programu (last_project.json, license.json,
    # license_status.json, user_id.json, *.flag) są względne do katalogu
    # roboczego. Uruchomienie z ostatniego ekranu instalatora ([Run] bez
    # WorkingDir) dawało C:\Windows\System32 - bez prawa zapisu, więc cała
    # pierwsza sesja po instalacji przepadała i kolejne uruchomienie startowało
    # od zera. Tak samo dwuklik w plik .myp.
    os.chdir(_app_dir())

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)
    install_wheel_guard(app)

    window = MainWindow(open_path=open_path)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
