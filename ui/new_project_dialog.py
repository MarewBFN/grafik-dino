from datetime import date

from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

from model.business_profile import BUSINESS_PROFILES
from ui.profile_wizard_dialog import ProfileWizardDialog


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

        self._profile_radios: dict[str, QRadioButton] = {}
        self._button_group = QButtonGroup(self)

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        title = QLabel("Nowy projekt")
        title.setObjectName("sectionLabel")
        root.addWidget(title)

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

        root.addLayout(form)

        root.addWidget(QLabel("Branża:"))
        self.profiles_container = QVBoxLayout()
        root.addLayout(self.profiles_container)
        self._reload_profile_radios()

        new_branch_btn = QPushButton("+ Nowa branża...")
        new_branch_btn.setObjectName("secondaryButton")
        new_branch_btn.clicked.connect(self._open_profile_wizard)
        root.addWidget(new_branch_btn)

        root.addStretch()

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

    def _reload_profile_radios(self, select_key: str | None = None):
        select_key = select_key or self._selected_key() or next(iter(BUSINESS_PROFILES), None)

        for radio in self._profile_radios.values():
            self._button_group.removeButton(radio)
            radio.setParent(None)
            radio.deleteLater()
        self._profile_radios.clear()

        for profile in BUSINESS_PROFILES.values():
            row = QFrame()
            row.setObjectName("configCard")
            row_layout = QHBoxLayout(row)
            radio = QRadioButton(profile.display_name)
            row_layout.addWidget(radio)
            self._button_group.addButton(radio)
            self._profile_radios[profile.key] = radio
            self.profiles_container.addWidget(row)

        if select_key in self._profile_radios:
            self._profile_radios[select_key].setChecked(True)
        elif self._profile_radios:
            next(iter(self._profile_radios.values())).setChecked(True)

    def _selected_key(self):
        for key, radio in self._profile_radios.items():
            if radio.isChecked():
                return key
        return None

    def _open_profile_wizard(self):
        wizard = ProfileWizardDialog(self)
        if wizard.exec() != QDialog.Accepted or not wizard.new_profile_key:
            return
        self._reload_profile_radios(select_key=wizard.new_profile_key)

    def _confirm(self):
        self.result_business_type = self._selected_key()
        self.result_year = self.year_spin.value()
        self.result_month = self.month_spin.value()
        self.accept()
