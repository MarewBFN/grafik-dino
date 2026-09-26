"""Podgląd wygenerowanego obrazu (grafik albo karty pracy) przed
zapisaniem do pliku - użytkownik widzi dokładnie to, co trafi do JPG/PDF,
i może się wycofać (Anuluj) bez utworzenia pliku i bez wyboru ścieżki
zapisu. Wspólne dla eksportu grafiku i kart pracy: oba w praktyce to
lista gotowych obrazów PIL (`export/export_style.py::render_schedule_image`,
`export/employee_card_exporter.py::render_employee_card_image`) - stąd
jeden dialog przyjmujący `pages`, a nie osobny na każdy przypadek."""

from io import BytesIO

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
)

# Szerokość, do jakiej skalowany jest podgląd - sam plik zapisywany jest w
# oryginalnej rozdzielczości renderu, to ogranicza tylko wyświetlanie w
# oknie dialogowym.
_PREVIEW_MAX_WIDTH = 860


def _pil_to_pixmap(image) -> QPixmap:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    pixmap = QPixmap()
    pixmap.loadFromData(buffer.getvalue(), "PNG")
    return pixmap


class ExportPreviewDialog(QDialog):
    """Podgląd read-only jednej lub więcej "stron" (lista PIL Image) z
    przyciskami Eksportuj/Anuluj - `exec()` zwraca `QDialog.Accepted`
    tylko po kliknięciu Eksportuj. Więcej niż jedna strona (karty pracy
    dla kilku pracowników) dostaje nawigację Poprzednia/Następna."""

    def __init__(self, pages, title="Podgląd przed eksportem", parent=None):
        super().__init__(parent)
        if not pages:
            raise ValueError("ExportPreviewDialog wymaga co najmniej jednej strony")

        self.setWindowTitle(title)
        self.resize(900, 700)

        self._pages = pages
        self._index = 0

        layout = QVBoxLayout(self)

        if len(pages) > 1:
            nav = QHBoxLayout()
            self.prev_btn = QPushButton("‹ Poprzednia")
            self.prev_btn.clicked.connect(self._show_prev)
            nav.addWidget(self.prev_btn)
            self.page_label = QLabel()
            self.page_label.setAlignment(Qt.AlignCenter)
            nav.addWidget(self.page_label, 1)
            self.next_btn = QPushButton("Następna ›")
            self.next_btn.clicked.connect(self._show_next)
            nav.addWidget(self.next_btn)
            layout.addLayout(nav)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.scroll.setWidget(self.image_label)
        layout.addWidget(self.scroll, 1)

        buttons = QDialogButtonBox()
        self.export_btn = buttons.addButton("Eksportuj", QDialogButtonBox.AcceptRole)
        buttons.addButton("Anuluj", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.export_btn.setDefault(True)
        layout.addWidget(buttons)

        self._render_page()

    def _render_page(self):
        pixmap = _pil_to_pixmap(self._pages[self._index])
        if pixmap.width() > _PREVIEW_MAX_WIDTH:
            pixmap = pixmap.scaledToWidth(_PREVIEW_MAX_WIDTH, Qt.SmoothTransformation)
        self.image_label.setPixmap(pixmap)

        if len(self._pages) > 1:
            self.page_label.setText(f"Strona {self._index + 1} / {len(self._pages)}")
            self.prev_btn.setEnabled(self._index > 0)
            self.next_btn.setEnabled(self._index < len(self._pages) - 1)

    def _show_prev(self):
        if self._index > 0:
            self._index -= 1
            self._render_page()

    def _show_next(self):
        if self._index < len(self._pages) - 1:
            self._index += 1
            self._render_page()


def show_export_preview(pages, title="Podgląd przed eksportem", parent=None) -> bool:
    """`pages` - jeden obraz PIL albo lista obrazów (jedna "strona" na
    element). Zwraca True, jeśli użytkownik zatwierdził (Eksportuj), False
    przy Anuluj/zamknięciu okna."""
    if not isinstance(pages, list):
        pages = [pages]
    dialog = ExportPreviewDialog(pages, title=title, parent=parent)
    return dialog.exec() == QDialog.Accepted
