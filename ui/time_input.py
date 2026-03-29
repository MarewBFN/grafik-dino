from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QLineEdit
from PySide6.QtCore import Qt


class TimeInputWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignCenter)

        self.input = QLineEdit()
        self.input.setMaxLength(5)
        self.input.setFixedWidth(70)
        self.input.setAlignment(Qt.AlignCenter)

        self.input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                background: white;
                padding: 2px;
                font-size: 14px;
                selection-background-color: #0078d4;
                selection-color: white;
            }
            QLineEdit:focus {
                border: 2px solid #0078d4;
                background-color: #f0f7ff;
            }
        """)

        self.input.textChanged.connect(self._format_time)

        layout.addWidget(self.input)

        self.set_time_str("00:00")

    def _format_time(self, text):
        digits = "".join(filter(str.isdigit, text))[:4]

        if len(digits) >= 3:
            formatted = f"{digits[:2]}:{digits[2:]}"
        else:
            formatted = digits

        if formatted != text:
            self.input.blockSignals(True)
            self.input.setText(formatted)
            self.input.blockSignals(False)

    def get_time_str(self):
        text = self.input.text()
        if len(text) == 5 and ":" in text:
            return text
        return "00:00"

    def set_time_str(self, time_str):
        if not time_str or ":" not in time_str:
            self.input.setText("00:00")
            return

        try:
            h, m = map(int, time_str.split(":"))
            self.input.setText(f"{h:02d}:{m:02d}")
        except ValueError:
            self.input.setText("00:00")
