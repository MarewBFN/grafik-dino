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
        # UWAGA: celowo NIE super().sizeHint().width() - to zależy od
        # aktualnie WYŚWIETLANEGO tekstu, który _refresh_marquee() mógł już
        # skrócić/zelidować w poprzednim przebiegu layoutu. Użycie go tutaj
        # tworzy pętlę sprzężenia zwrotnego (węższy widget -> krótszy
        # wyświetlany tekst -> jeszcze mniejszy sizeHint -> ...), która w
        # layoucie bez stretcha zbiega do minimumSizeHint (~2 znaki) -
        # zgłoszone jako bug. Liczymy więc od stałego _full_text.
        base_height = super().sizeHint().height()
        metrics = QFontMetrics(self.font())
        full_text = getattr(self, "_full_text", "")
        natural_width = metrics.horizontalAdvance(full_text) + self._text_padding()
        cap = metrics.horizontalAdvance("Lokalizacja") + 40
        return QSize(min(natural_width, cap), base_height)

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
        # Patrz komentarz w MarqueeButton.sizeHint() - ta sama poprawka.
        base_height = super().sizeHint().height()
        metrics = QFontMetrics(self.font())
        full_text = getattr(self, "_full_text", "")
        natural_width = metrics.horizontalAdvance(full_text) + self._text_padding()
        cap = metrics.horizontalAdvance("Lokalizacja")
        return QSize(min(natural_width, cap), base_height)


def _wrap_text_to_width(text: str, metrics: QFontMetrics, max_width: int) -> str:
    """Zachłanne zawijanie po spacjach do `max_width` - jedno za długie
    słowo trafia na własną linię bez dalszego dzielenia po znakach (nazwy
    placówek to zwykłe słowa, nie długie ciągi bez spacji)."""
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or metrics.horizontalAdvance(candidate) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return "\n".join(lines)


class WrappingLocationButton(QPushButton):
    """Jak MarqueeButton, ale zamiast przewijać za długi tekst w poziomie
    (marquee), zawija go do wielu linii i rośnie w pionie, żeby się
    zmieścił - na życzenie użytkownika, konkretnie dla
    ui/main_window.py::btn_location_name (nazwa placówki w lewym pasku).
    Szerokość zawijania nadąża za faktyczną szerokością przycisku
    (resizeEvent - reaguje np. na przeciąganie splittera). Minimalna
    wysokość rośnie monotonicznie w ramach sesji (nigdy się nie zmniejsza),
    żeby przełączenie na krótszą nazwę nie "skakało" resztą panelu -
    patrz _rewrap()."""

    _TEXT_PADDING = 24  # jak MarqueeButton._text_padding()
    _VERTICAL_PADDING = 16  # zapas na padding stylu w pionie (4px * 2 + zapas)

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._full_text = text or ""
        self._min_height_reached = 0

    def setFullText(self, text: str) -> None:
        self._full_text = text or ""
        self.setToolTip(self._full_text)
        self._rewrap()

    def fullText(self) -> str:
        return self._full_text

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rewrap()

    def _available_width(self) -> int:
        return max(self.width() - self._TEXT_PADDING, 20)

    def _rewrap(self) -> None:
        if not self._full_text:
            self.setText("")
            return

        metrics = QFontMetrics(self.font())
        available = self._available_width()
        wrapped = _wrap_text_to_width(self._full_text, metrics, available)
        self.setText(wrapped)

        needed_height = metrics.boundingRect(
            0, 0, available, 10_000, Qt.TextWordWrap, wrapped,
        ).height() + self._VERTICAL_PADDING
        self._min_height_reached = max(self._min_height_reached, needed_height)
        self.setMinimumHeight(self._min_height_reached)

    def minimumSizeHint(self) -> QSize:
        return QSize(_MIN_SENSIBLE_WIDTH, super().minimumSizeHint().height())
