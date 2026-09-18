from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.business_profile_picker import BusinessProfilePicker


class NewProjectDialog(QDialog):
    """First step of creating a new project: pick the period and which
    business profile (branża) it should use. The profile list is whatever's
    actually registered in BUSINESS_PROFILES - dino_retail plus any custom
    profiles created through the wizard - not a fixed, partly-fake list of
    industries."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nowy projekt")
        self.setModal(True)
        self.setMinimumWidth(420)

        self.result_business_type = None
        self.result_year = None
        self.result_month = None

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        title = QLabel("Nowy projekt")
        title.setObjectName("sectionLabel")
        root.addWidget(title)

        # Lista profili rośnie z każdym zapisanym profilem custom - bez
        # scrolla treść (i przyciski Utwórz/Anuluj) wypadały poza okno przy
        # kilku profilach naraz. Wzorem sidebaru głównego okna
        # (ui/main_window.py::_build_left_panel).
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(scroll, 1)

        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 4, 0)

        form = QFormLayout()
        today = date.today()

        self.year_spin = QSpinBox()
        self.year_spin.setRange(2000, 2100)
        self.year_spin.setValue(today.year)
        form.addRow("Rok:", self.year_spin)

        self.month_spin = QSpinBox()
        self.month_spin.setRange(1, 12)
        self.month_spin.setValue(today.month)
        form.addRow("Miesiąc:", self.month_spin)

        content_layout.addLayout(form)

        content_layout.addWidget(QLabel("Branża:"))
        self.profile_picker = BusinessProfilePicker(self)
        content_layout.addWidget(self.profile_picker)

        content_layout.addStretch()

        buttons = QDialogButtonBox()
        cancel_btn = QPushButton("Anuluj")
        cancel_btn.setObjectName("secondaryButton")
        create_btn = QPushButton("Utwórz")
        create_btn.setObjectName("primaryButton")
        buttons.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        buttons.addButton(create_btn, QDialogButtonBox.AcceptRole)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._confirm)
        root.addWidget(buttons)

    def _confirm(self):
        self.result_business_type = self.profile_picker.selected_key()
        self.result_year = self.year_spin.value()
        self.result_month = self.month_spin.value()
        self.accept()
