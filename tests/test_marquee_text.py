"""ui/marquee_text.py:
- MarqueeLabel/MarqueeButton.sizeHint() naprawiony bug (zgłoszenie
  użytkownika: nazwa placówki nad siatką grafiku ucinała się po ~2
  znakach mimo dostępnego miejsca) - sizeHint liczył się od AKTUALNIE
  wyświetlanego (już skróconego przez poprzedni przebieg) tekstu zamiast
  od stałego pełnego tekstu, co w layoucie ze stretch=0 zbiegało do
  minimumSizeHint.
- WrappingLocationButton (nowa klasa) - zamiast przewijać za długą nazwę
  w poziomie (marquee), zawija ją na kilka linii i rośnie w pionie;
  minimalna wysokość rośnie monotonicznie w ramach sesji, żeby
  przełączenie na krótszą nazwę nie zmniejszało już wysokości wiersza."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from ui.marquee_text import MarqueeButton, MarqueeLabel, WrappingLocationButton, _wrap_text_to_width


_LONG_NAME = "Ubojnia Drobiu GOSZ - waga i biuro, bardzo długa nazwa testowa placówki"
_SHORT_NAME = "PGE"


class SizeHintDoesNotCollapseTests(unittest.TestCase):
    """Regresja na dokładnie ten bug: wielokrotne odświeżenie na wąskim
    widgecie nie może z czasem zredukować sizeHint do minimum."""

    def test_marquee_label_size_hint_is_stable_across_refreshes(self):
        label = MarqueeLabel("")
        label.setFullText(_LONG_NAME)
        first = label.sizeHint().width()

        # Symuluje kilka przebiegów layoutu na wąskim widgecie - dawniej
        # każdy przebieg dalej zwężał sizeHint (spirala do minimum).
        for _ in range(5):
            label.resize(50, label.sizeHint().height())
            label._refresh_marquee()

        second = label.sizeHint().width()
        self.assertEqual(first, second)
        self.assertGreater(second, 40)  # dawny bug zbiegał do ~40px (_MIN_SENSIBLE_WIDTH)

    def test_marquee_button_size_hint_is_stable_across_refreshes(self):
        button = MarqueeButton("")
        button.setFullText(_LONG_NAME)
        first = button.sizeHint().width()

        for _ in range(5):
            button.resize(50, button.sizeHint().height())
            button._refresh_marquee()

        second = button.sizeHint().width()
        self.assertEqual(first, second)
        self.assertGreater(second, 40)

    def test_short_text_is_not_capped_below_its_natural_width(self):
        label = MarqueeLabel("")
        label.setFullText(_SHORT_NAME)
        # Krótki tekst nie powinien być winowany przez sam cap "Lokalizacja"
        # - to jest minimum, nie ograniczenie w dół.
        self.assertGreaterEqual(label.sizeHint().width(), 4)


class WrapTextToWidthTests(unittest.TestCase):
    def test_single_short_word_is_not_split(self):
        from PySide6.QtGui import QFont, QFontMetrics
        metrics = QFontMetrics(QFont())
        self.assertEqual(_wrap_text_to_width("PGE", metrics, 500), "PGE")

    def test_long_text_wraps_into_multiple_lines(self):
        from PySide6.QtGui import QFont, QFontMetrics
        metrics = QFontMetrics(QFont())
        wrapped = _wrap_text_to_width(_LONG_NAME, metrics, 100)
        self.assertIn("\n", wrapped)
        # Każda linia musi się zmieścić w budżecie.
        for line in wrapped.split("\n"):
            self.assertLessEqual(metrics.horizontalAdvance(line), 100)

    def test_reassembled_words_match_original(self):
        from PySide6.QtGui import QFont, QFontMetrics
        metrics = QFontMetrics(QFont())
        wrapped = _wrap_text_to_width(_LONG_NAME, metrics, 80)
        self.assertEqual(wrapped.replace("\n", " "), _LONG_NAME)


class WrappingLocationButtonTests(unittest.TestCase):
    def test_short_name_fits_on_one_line(self):
        button = WrappingLocationButton("")
        button.resize(300, 40)
        button.setFullText(_SHORT_NAME)

        self.assertEqual(button.text(), _SHORT_NAME)
        self.assertNotIn("\n", button.text())

    def test_long_name_wraps_and_grows_the_minimum_height(self):
        button = WrappingLocationButton("")
        button.resize(150, 40)
        default_min_height = button.minimumHeight()

        button.setFullText(_LONG_NAME)

        self.assertIn("\n", button.text())
        self.assertGreater(button.minimumHeight(), default_min_height)

    def test_minimum_height_never_shrinks_when_switching_to_a_shorter_name(self):
        button = WrappingLocationButton("")
        button.resize(150, 40)

        button.setFullText(_LONG_NAME)
        grown_height = button.minimumHeight()
        self.assertGreater(grown_height, 0)

        button.setFullText(_SHORT_NAME)

        self.assertEqual(button.text(), _SHORT_NAME)
        self.assertEqual(button.minimumHeight(), grown_height)

    def test_tooltip_reflects_the_full_name(self):
        button = WrappingLocationButton("")
        button.resize(150, 40)
        button.setFullText(_LONG_NAME)

        self.assertEqual(button.toolTip(), _LONG_NAME)

    def test_full_text_is_recoverable(self):
        button = WrappingLocationButton("")
        button.resize(150, 40)
        button.setFullText(_LONG_NAME)

        self.assertEqual(button.fullText(), _LONG_NAME)

    def test_rewrapping_on_resize_uses_the_new_width(self):
        # resize() aktualizuje width()/height() synchronicznie, ale samo
        # wywołanie resizeEvent() bez realnej pętli zdarzeń/pokazania
        # widgetu bywa niemiarodajne w headless testach - wołamy _rewrap()
        # wprost, żeby przetestować samą logikę zawijania niezależnie od
        # dostarczania zdarzeń przez Qt.
        button = WrappingLocationButton("")
        button.resize(500, 40)
        button.setFullText(_LONG_NAME)
        wide_text = button.text()

        button.resize(120, 40)
        button._rewrap()

        narrow_text = button.text()
        self.assertNotEqual(wide_text, narrow_text)
        self.assertIn("\n", narrow_text)


if __name__ == "__main__":
    unittest.main()
