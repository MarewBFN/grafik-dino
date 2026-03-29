from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class LoadingSpinner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.start(16)

        self.setFixedSize(80, 80)

    def _rotate(self):
        self._angle = (self._angle + 5) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(10, 10, -10, -10)

        painter.setPen(QColor(255, 255, 255, 40))
        painter.drawEllipse(rect)

        pen = painter.pen()
        pen.setWidth(4)
        pen.setColor(QColor(255, 255, 255))
        painter.setPen(pen)

        painter.drawArc(rect, int(self._angle * 16), int(120 * 16))


class LoadingOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setStyleSheet("background-color: rgba(0, 0, 0, 120);")
        self.hide()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.spinner = LoadingSpinner(self)
        layout.addWidget(self.spinner, alignment=Qt.AlignCenter)

        self.label = QLabel("Start...")
        self.label.setStyleSheet("color: white; font-size: 20px;")
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

        self.messages = [
            "Analizowanie dostępności pracowników...",
            "Układanie zmian porannych...",
            "Układanie zmian popołudniowych...",
            "Dopasowywanie otwarcia sklepu...",
            "Dopasowywanie zamknięcia sklepu...",
            "Sprawdzanie ograniczeń (odpoczynek, dni pod rząd)...",
            "Balansowanie godzin pracy...",
            "Układanie mięsiarzy...",
            "Optymalizowanie pokrycia zmian...",
            "Wyrównywanie obciążenia między pracownikami...",
        ]

        self._msg_index = 0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._next_message)

    def _next_message(self):
        self.label.setText(self.messages[self._msg_index])
        self._msg_index = (self._msg_index + 1) % len(self.messages)

    def show_overlay(self):
        self.setGeometry(0, 0, self.parent().width(), self.parent().height())
        self.raise_()
        self._msg_index = 0
        self.label.setText(self.messages[0])
        self.show()
        self.timer.start(3000)

    def hide_overlay(self):
        self.timer.stop()
        self.hide()