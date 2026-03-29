import sys
import hashlib

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
)


SECRET = "dupadupa"


def generate_license(user_id: str) -> str:
    raw = user_id + SECRET
    hash_hex = hashlib.sha256(raw.encode()).hexdigest()

    digits = ''.join(filter(str.isdigit, hash_hex))
    return digits[:8]


class KeygenWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Generator kluczy")
        self.setFixedSize(300, 180)

        layout = QVBoxLayout(self)

        self.label = QLabel("Podaj ID użytkownika:")
        layout.addWidget(self.label)

        self.input = QLineEdit()
        layout.addWidget(self.input)

        self.button = QPushButton("Generuj klucz")
        self.button.clicked.connect(self.generate)
        layout.addWidget(self.button)

        self.result_label = QLabel("Klucz: -")
        self.result_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.result_label)

    def generate(self):
        user_id = self.input.text().strip()

        if not user_id:
            QMessageBox.warning(self, "Błąd", "Podaj ID użytkownika")
            return

        key = generate_license(user_id)
        self.result_label.setText(f"Klucz: {key}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = KeygenWindow()
    window.show()
    sys.exit(app.exec())