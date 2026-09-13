from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import Qt, QEvent, QPoint, QRect, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


@dataclass
class TutorialStep:
    title: str
    text: str
    target: Optional[QWidget] = None
    on_show: Optional[Callable[[], None]] = None


class TutorialOverlay(QWidget):
    """Interaktywny samouczek — przyciemnia okno i podświetla po kolei prawdziwe
    widgety programu zamiast pokazywać statyczne zrzuty ekranu."""

    HIGHLIGHT_MARGIN = 8
    HIGHLIGHT_RADIUS = 10
    CARD_MARGIN = 16
    CARD_WIDTH = 320

    def __init__(self, parent, steps, on_finished=None):
        super().__init__(parent)
        self.steps = steps
        self.on_finished = on_finished
        self.current_step = 0

        self.hide()
        self._card = self._build_card()
        parent.installEventFilter(self)

    def _build_card(self):
        card = QFrame(self)
        card.setObjectName("tutorialCard")
        card.setAttribute(Qt.WA_StyledBackground, True)
        card.setFixedWidth(self.CARD_WIDTH)
        card.setStyleSheet("""
            #tutorialCard { background-color: #1f2430; border-radius: 10px; }
            #tutorialCard QLabel { color: white; background: transparent; }
        """)

        layout = QVBoxLayout(card)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.text_label = QLabel()
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label)

        self.step_label = QLabel()
        self.step_label.setStyleSheet("color: #9aa4b2; font-size: 11px; background: transparent;")
        layout.addWidget(self.step_label)

        btn_row = QHBoxLayout()

        self.btn_skip = QPushButton("Pomiń")
        self.btn_skip.clicked.connect(self._finish)

        self.btn_prev = QPushButton("Wstecz")
        self.btn_prev.clicked.connect(self._prev)

        self.btn_next = QPushButton("Dalej")
        self.btn_next.clicked.connect(self._next)

        btn_row.addWidget(self.btn_skip)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_prev)
        btn_row.addWidget(self.btn_next)

        layout.addLayout(btn_row)
        return card

    def start(self):
        self.current_step = 0
        self.setGeometry(self.parentWidget().rect())
        self._show_step()
        self.show()
        self.raise_()

    def _current(self):
        return self.steps[self.current_step]

    def _target_widget(self):
        target = self._current().target
        if target is None or not target.isVisible():
            return None
        return target

    def _mapped_target_rect(self, target):
        top_left = target.mapTo(self.parentWidget(), QPoint(0, 0))
        return QRect(top_left, target.size())

    def _show_step(self):
        step = self._current()
        if step.on_show:
            step.on_show()
        self.title_label.setText(step.title)
        self.text_label.setText(step.text)
        self.step_label.setText(f"Krok {self.current_step + 1} z {len(self.steps)}")

        self.btn_prev.setEnabled(self.current_step > 0)
        self.btn_next.setText("Zakończ" if self.current_step == len(self.steps) - 1 else "Dalej")

        self._position_card()
        self.update()

    def _position_card(self):
        self._card.adjustSize()
        target = self._target_widget()
        margin = self.CARD_MARGIN

        if target is None:
            center = self.rect().center()
            x = center.x() - self._card.width() // 2
            y = center.y() - self._card.height() // 2
        else:
            rect = self._mapped_target_rect(target)
            x = rect.left()
            y = rect.bottom() + margin

            if y + self._card.height() > self.height() - margin:
                y = rect.top() - self._card.height() - margin

        x = max(margin, min(x, self.width() - self._card.width() - margin))
        y = max(margin, min(y, self.height() - self._card.height() - margin))

        self._card.move(int(x), int(y))
        self._card.show()

    def _next(self):
        if self.current_step >= len(self.steps) - 1:
            self._finish()
            return
        self.current_step += 1
        self._show_step()

    def _prev(self):
        if self.current_step > 0:
            self.current_step -= 1
            self._show_step()

    def _finish(self):
        self.hide()
        if self.on_finished:
            self.on_finished()

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() == QEvent.Resize and self.isVisible():
            self.setGeometry(self.parentWidget().rect())
            self._position_card()
            self.update()
        return super().eventFilter(obj, event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        overlay_path = QPainterPath()
        overlay_path.addRect(QRectF(self.rect()))

        target = self._target_widget()
        rect = None
        if target is not None:
            rect = self._mapped_target_rect(target).adjusted(
                -self.HIGHLIGHT_MARGIN, -self.HIGHLIGHT_MARGIN,
                self.HIGHLIGHT_MARGIN, self.HIGHLIGHT_MARGIN,
            )
            hole = QPainterPath()
            hole.addRoundedRect(QRectF(rect), self.HIGHLIGHT_RADIUS, self.HIGHLIGHT_RADIUS)
            overlay_path = overlay_path.subtracted(hole)

        painter.fillPath(overlay_path, QColor(15, 18, 24, 190))

        if rect is not None:
            painter.setPen(QPen(QColor("#0078d4"), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(rect), self.HIGHLIGHT_RADIUS, self.HIGHLIGHT_RADIUS)
