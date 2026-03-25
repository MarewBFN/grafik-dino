from PySide6.QtWidgets import QWidget, QHBoxLayout, QSpinBox, QLabel
from PySide6.QtCore import Qt

class CleanSpinBox(QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QSpinBox.NoButtons)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(30)
        self.setStyleSheet("""
            QSpinBox {
                border: 1px solid #ccc;
                border-radius: 4px;
                background: white;
                padding: 2px;
                font-size: 14px;
                selection-background-color: #0078d4; 
                selection-color: white;
            }
            QSpinBox:focus {
                border: 2px solid #0078d4;
                background-color: #f0f7ff;
            }
        """)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.focusNextChild()
        else:
            super().keyPressEvent(event)

class TimeInputWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        # Ustawienie wyrównania layoutu do środka, aby elementy nie "uciekały" od siebie
        layout.setAlignment(Qt.AlignCenter)

        self.hour_box = CleanSpinBox()
        self.hour_box.setRange(0, 23)
        self.hour_box.setFixedWidth(45)
        self.hour_box.textFromValue = lambda v: f"{v:02d}"

        self.minute_box = CleanSpinBox()
        self.minute_box.setRange(0, 59)
        self.minute_box.setSingleStep(5)
        self.minute_box.setFixedWidth(45)
        self.minute_box.textFromValue = lambda v: f"{v:02d}"

        layout.addWidget(self.hour_box)
        
        colon = QLabel(":")
        colon.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(colon)
        
        layout.addWidget(self.minute_box)

    def get_time_str(self):
        return f"{self.hour_box.value():02d}:{self.minute_box.value():02d}"

    def set_time_str(self, time_str):
        if not time_str:
            return

        try:
            h, m = map(int, time_str.split(":"))
            self.hour_box.setValue(h)
            self.minute_box.setValue(m)
        except ValueError:
            pass