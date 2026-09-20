from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QLabel, QPushButton

# Nazwa lokalizacji może być długa (do 35 znaków, patrz
# ui/locations_dialog.py::_LocationRow) - dłuższa niż mają miejsce widgety w
# lewym pasku bocznym (ui/main_window.py), które ją wyświetlają. Zwykły
# QPushButton/QLabel liczy swój sizeHint/minimumSizeHint na podstawie pełnego
# tekstu, więc długa nazwa "rozjeżdżała" cały pasek (wymuszała szerszy layout
# niż setMaximumWidth() paska pozwalał). Te dwie klasy odrywają
# sizeHint/minimumSizeHint od setFullText() - o widocznej szerokości decyduje
# wyłącznie rzeczywisty rozmiar przydzielony przez layout, a pełny tekst jest
# elidowany, a gdy nawet elidowany nie mieści się sensownie - przewijany
# (marquee), zamiast wpływać na rozmiar przycisku/etykiety.

_TICK_MS = 220
_GAP = "      "
_MIN_SENSIBLE_WIDTH = 40  # poniżej tego elide nie ma sensu - od razu marquee


class _MarqueeMixin:
    def _init_marquee(self, text: str) -> None:
        self._full_text = text or ""
        self._offset = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._marquee_tick)

    def setFullText(self, text: str) -> None:
        self._full_text = text or ""
        self._offset = 0
        self.setToolTip(self._full_text)
        self._refresh_marquee()

    def fullText(self) -> str:
        return self._full_text

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_marquee()

    def _available_width(self) -> int:
        return max(self.width() - self._text_padding(), 10)

    def _refresh_marquee(self) -> None:
        metrics = QFontMetrics(self.font())
        available = self._available_width()
        if metrics.horizontalAdvance(self._full_text) <= available or available < _MIN_SENSIBLE_WIDTH:
            self._timer.stop()
            self._offset = 0
            super().setText(metrics.elidedText(self._full_text, Qt.ElideRight, max(available, 1)))
            return

        if not self._timer.isActive():
            self._offset = 0
            self._timer.start(_TICK_MS)
        self._marquee_tick()

    def _marquee_tick(self) -> None:
        metrics = QFontMetrics(self.font())
        available = self._available_width()
        looped = self._full_text + _GAP
        n = len(looped)
        if n == 0:
            return
        self._offset = (self._offset + 1) % n
        doubled = looped + looped
        window = doubled[self._offset:self._offset + n]
        super().setText(metrics.elidedText(window, Qt.ElideRight, available))


class MarqueeButton(_MarqueeMixin, QPushButton):
    """QPushButton, którego widoczny rozmiar nie zależy od setFullText()."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._init_marquee(text)

    def _text_padding(self) -> int:
        return 24  # zapas na padding stylu (patrz ui/theme.py locationNameButton)

    def sizeHint(self) -> QSize:
        base = super().sizeHint()
        metrics = QFontMetrics(self.font())
        return QSize(min(base.width(), metrics.horizontalAdvance("Lokalizacja") + 40), base.height())

    def minimumSizeHint(self) -> QSize:
        return QSize(_MIN_SENSIBLE_WIDTH, super().minimumSizeHint().height())


class MarqueeLabel(_MarqueeMixin, QLabel):
    """QLabel, którego widoczny rozmiar nie zależy od setFullText()."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._init_marquee(text)

    def _text_padding(self) -> int:
        return 4

    def sizeHint(self) -> QSize:
        base = super().sizeHint()
        metrics = QFontMetrics(self.font())
        return QSize(min(base.width(), metrics.horizontalAdvance("Lokalizacja")), base.height())

    def minimumSizeHint(self) -> QSize:
        return QSize(_MIN_SENSIBLE_WIDTH, super().minimumSizeHint().height())
