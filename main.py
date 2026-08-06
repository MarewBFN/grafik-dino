import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.theme import APP_STYLESHEET


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)

    # Double-clicking a .myp file (registered by the installer, see
    # "dla inno.iss") launches us with its path as an argument.
    open_path = next((arg for arg in sys.argv[1:] if os.path.isfile(arg)), None)

    window = MainWindow(open_path=open_path)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
