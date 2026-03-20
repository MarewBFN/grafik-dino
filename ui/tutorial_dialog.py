from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout


class TutorialDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Samouczek")
        self.resize(460, 260)

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
            "Uwzględniane są ograniczenia (np. godziny pracy, role).\n"
            "Jeśli nie znajdzie rozwiązania — trzeba poprawić dane.",

            "Krok 3 — Edycja ręczna\n\n"
            "Kliknij dwukrotnie komórkę, aby edytować dzień.\n"
            "Możesz ustawić:\n"
            "- godziny pracy\n"
            "- wolne\n"
            "- urlop",

            "Krok 4 — Tryb szybki\n\n"
            "Włącz 'Tryb szybki', aby szybko wypełniać grafik.\n"
            "Działa tak:\n"
            "1. Wybierasz typ (Praca / Wolne / Urlop)\n"
            "2. (dla pracy) ustawiasz godziny\n"
            "3. Klikasz w komórki → wpisuje się automatycznie\n\n"
            "To najszybszy sposób ręcznego układania grafiku.",

            "Krok 5 — Menu kontekstowe\n\n"
            "Kliknij prawym przyciskiem na komórkę:\n"
            "- ustaw poranną zmianę\n"
            "- ustaw zamknięcie\n"
            "- kopiuj / wklej dzień\n\n"
            "To przyspiesza poprawki grafiku.",

            "Krok 6 — Eksport i zapis\n\n"
            "Możesz zapisać projekt do pliku i wrócić do niego później.\n"
            "Dostępny jest też eksport do Excela.",

            "Gotowe!\n\n"
            "Najprostszy workflow:\n"
            "1. Dodaj pracowników\n"
            "2. Kliknij 'Generuj grafik'\n"
            "3. Popraw ręcznie lub trybem szybkim\n\n"
            "I masz gotowy grafik."
        ]

        self.current_step = 0

        self.layout = QVBoxLayout(self)

        self.label = QLabel(self.steps[self.current_step])
        self.label.setWordWrap(True)
        self.layout.addWidget(self.label)

        btn_row = QHBoxLayout()

        self.btn_prev = QPushButton("Wstecz")
        self.btn_prev.clicked.connect(self.prev_step)

        self.btn_next = QPushButton("Dalej")
        self.btn_next.clicked.connect(self.next_step)

        btn_row.addWidget(self.btn_prev)
        btn_row.addWidget(self.btn_next)

        self.layout.addLayout(btn_row)

        self._update_buttons()

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
        self._update_buttons()

    def _update_buttons(self):
        self.btn_prev.setEnabled(self.current_step > 0)
        if self.current_step == len(self.steps) - 1:
            self.btn_next.setText("Zamknij")
        else:
            self.btn_next.setText("Dalej")