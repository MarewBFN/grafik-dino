from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton,
    QHBoxLayout, QWidget
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt


class TutorialDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Samouczek")
        self.resize(520, 420)

        # === TEKSTY ===
        self.steps = [
            "Witaj w Grafik Dino v2!\n\n"
            "Program służy do tworzenia grafików pracy dla sklepów.\n"
            "Możesz generować grafik automatycznie lub układać go ręcznie.",

            "Krok 1 — Dodaj pracowników\n\n"
            "Kliknij 'Dodaj pracownika' i uzupełnij dane.\n"
            "Każdy pracownik może mieć:\n"
            "- wymiar etatu\n"
            "- godziny dzienne\n"
            "- role (np. otwarcie, mięso)",

            "Krok 2 — Generowanie grafiku\n\n"
            "Kliknij 'Generuj grafik', aby program ułożył grafik automatycznie.\n"
            "Uwzględniane są ograniczenia.\n"
            "Jeśli nie znajdzie rozwiązania — popraw dane.",

            "Krok 3 — Edycja ręczna\n\n"
            "Kliknij dwukrotnie komórkę, aby edytować dzień.\n"
            "Możesz ustawić:\n"
            "- godziny pracy\n"
            "- wolne\n"
            "- urlop",

            "Krok 4 — Tryb szybki\n\n"
            "1. Wybierasz typ\n"
            "2. Ustawiasz godziny\n"
            "3. Klikasz komórki\n\n"
            "Najszybsza metoda.",

            "Krok 5 — Menu kontekstowe\n\n"
            "Prawy klik:\n"
            "- zmiana poranna\n"
            "- zamknięcie\n"
            "- kopiuj / wklej",

            "Krok 6 — Eksport i zapis\n\n"
            "Zapisz projekt i wróć później.\n"
            "Eksport do Excela.",

            "Gotowe!\n\n"
            "1. Dodaj pracowników\n"
            "2. Generuj\n"
            "3. Popraw\n\n"
            "Koniec."
        ]

        # === OBRAZY (ścieżki do plików) ===
        # Podmienisz sobie później np. na: "assets/tutorial/step1.png"
        self.images = [
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None
        ]

        self.current_step = 0

        self.layout = QVBoxLayout(self)

        # === TEKST ===
        self.label = QLabel(self.steps[self.current_step])
        self.label.setWordWrap(True)
        self.layout.addWidget(self.label)

        # === OBRAZ ===
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.image_label)

        # === PRZYCISKI ===
        btn_row = QHBoxLayout()

        self.btn_prev = QPushButton("Wstecz")
        self.btn_prev.clicked.connect(self.prev_step)

        self.btn_next = QPushButton("Dalej")
        self.btn_next.clicked.connect(self.next_step)

        btn_row.addWidget(self.btn_prev)
        btn_row.addWidget(self.btn_next)

        self.layout.addLayout(btn_row)

        self._update_view()

    def next_step(self):
        if self.current_step < len(self.steps) - 1:
            self.current_step += 1
            self._update_view()
        else:
            self.accept()

    def prev_step(self):
        if self.current_step > 0:
            self.current_step -= 1
            self._update_view()

    def _update_view(self):
        self.label.setText(self.steps[self.current_step])
        self._update_image()
        self._update_buttons()

    def _update_image(self):
        path = self.images[self.current_step]

        if path:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self.image_label.setPixmap(
                    pixmap.scaled(400, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                self.image_label.show()
                return

        self.image_label.hide()

    def _update_buttons(self):
        self.btn_prev.setEnabled(self.current_step > 0)

        if self.current_step == len(self.steps) - 1:
            self.btn_next.setText("Zamknij")
        else:
            self.btn_next.setText("Dalej")