from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from simple_mode.grid_widget import SimpleModeGrid
from simple_mode.image_exporter import export_simple_schedule_to_image
from simple_mode.storage import load_simple_mode_data, save_simple_mode_data


class SimpleModeWindow(QDialog):
    """Osobne okno trybu uproszczonego: kliknij komórkę, aby ustawić 1 / 2 / W."""

    def __init__(self, parent, schedule):
        super().__init__(parent)
        self.setWindowTitle("Tryb uproszczony")
        self.setModal(True)
        self.resize(900, 500)

        self.schedule = schedule
        self.simple_data = load_simple_mode_data()

        root = QVBoxLayout(self)

        info = QLabel("Klikaj komórki, aby ustawić kod: puste → 1 → 2 → W → puste.")
        root.addWidget(info)

        self.grid = SimpleModeGrid()
        self.grid.set_data(schedule, self.simple_data)
        root.addWidget(self.grid, 1)

        buttons = QHBoxLayout()
        export_btn = QPushButton("Eksportuj JPG")
        export_btn.clicked.connect(self._export_image)
        buttons.addWidget(export_btn)
        buttons.addStretch()

        close_btn = QPushButton("Zamknij")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)

        root.addLayout(buttons)

    def _export_image(self):
        path, _ = QFileDialog.getSaveFileName(self, "Eksportuj JPG", "grafik_uproszczony.jpg", "Obrazy (*.jpg)")
        if not path:
            return

        try:
            export_simple_schedule_to_image(
                self.schedule, self.simple_data, self.schedule.year, self.schedule.month, path
            )
        except OSError as exc:
            QMessageBox.critical(self, "Błąd", f"Nie udało się zapisać pliku: {exc}")
            return

        QMessageBox.information(self, "Eksport", "Zapisano grafik uproszczony.")

    def closeEvent(self, event):
        save_simple_mode_data(self.simple_data)
        super().closeEvent(event)

    def accept(self):
        save_simple_mode_data(self.simple_data)
        super().accept()
