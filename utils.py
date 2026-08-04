import sys
import os


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def get_app_data_dir():
    base = os.getenv("LOCALAPPDATA")
    app_dir = os.path.join(base, "GrafikDino")
    os.makedirs(app_dir, exist_ok=True)
    return app_dir


def get_app_data_path(filename):
    return os.path.join(get_app_data_dir(), filename)