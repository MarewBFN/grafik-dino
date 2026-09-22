from PySide6.QtWidgets import QMessageBox
import os
import json

DEMO_FILE = "demo.json"


class DemoManager:
    MAX_GENERATIONS = 5

    def __init__(self):
        self.is_demo = True
        self.generations_used = 0
        self._load()

    def can_generate(self, parent):
        if not self.is_demo:
            return True

        if self.generations_used >= self.MAX_GENERATIONS:
            QMessageBox.warning(
                parent,
                "Limit wersji demo",
                "Wykorzystałeś limit generowania grafiku.\n\nAby kontynuować, aktywuj pełną wersję."
            )
            return False

        return True

    def register_generation(self):
        if not self.is_demo:
            return

        self.generations_used += 1
        self._save()

    def get_remaining_generations(self):
        if not self.is_demo:
            return None

        return self.MAX_GENERATIONS - self.generations_used

    def block_save(self, parent):
        if not self.is_demo:
            return False

        QMessageBox.warning(
            parent,
            "Wersja demo",
            "Zapis projektu dostępny tylko w pełnej wersji."
        )
        return True

    def block_export(self, parent):
        if not self.is_demo:
            return False

        QMessageBox.warning(
            parent,
            "Wersja demo",
            "Eksport dostępny tylko w pełnej wersji."
        )
        return True

    def show_after_generate(self, parent, extra_note=None):
        if not self.is_demo:
            return

        message = "Grafik wygenerowany.\n\nAby zapisać lub wyeksportować – wymagana pełna wersja."
        if extra_note:
            message += f"\n\n{extra_note}"

        QMessageBox.information(parent, "Wersja demo", message)

    def _save(self):
        try:
            with open(DEMO_FILE, "w") as f:
                json.dump({"generations_used": self.generations_used}, f)
        except:
            pass

    def _load(self):
        if not os.path.exists(DEMO_FILE):
            return

        try:
            with open(DEMO_FILE, "r") as f:
                data = json.load(f)
                self.generations_used = data.get("generations_used", 0)
        except:
            pass