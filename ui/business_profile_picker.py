from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from model.business_profile import get_custom_profile, visible_profiles
from ui.profile_wizard_dialog import ProfileWizardDialog


class BusinessProfilePicker(QWidget):
    """Radio list of every registered business profile a user should actually
    see (visible_profiles() - excludes dino_retail, see ENYO_ONLY_CHANGES.md),
    each with Edit/Delete for custom profiles and a "+ Nowa branża..." button
    to create one on the spot. Shared by NewProjectDialog and the first-run
    wizard (ui/first_run_wizard.py) so the two don't drift."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._profile_radios: dict[str, QRadioButton] = {}
        self._button_group = QButtonGroup(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.profiles_container = QVBoxLayout()
        layout.addLayout(self.profiles_container)
        self._reload()

        new_branch_btn = QPushButton("+ Nowa branża...")
        new_branch_btn.setObjectName("secondaryButton")
        new_branch_btn.clicked.connect(self._open_profile_wizard)
        layout.addWidget(new_branch_btn)

    def selected_key(self):
        for key, radio in self._profile_radios.items():
            if radio.isChecked():
                return key
        return None

    def _reload(self, select_key: str | None = None):
        profiles = visible_profiles()
        select_key = select_key or self.selected_key() or (profiles[0].key if profiles else None)

        for radio in self._profile_radios.values():
            self._button_group.removeButton(radio)
            radio.setParent(None)
            radio.deleteLater()
        self._profile_radios.clear()

        while self.profiles_container.count():
            item = self.profiles_container.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        for profile in profiles:
            row = QFrame()
            row.setObjectName("configCard")
            row_layout = QHBoxLayout(row)
            radio = QRadioButton(profile.display_name)
            row_layout.addWidget(radio, 1)

            custom = get_custom_profile(profile.key)
            if custom is not None:
                edit_btn = QPushButton("Edytuj...")
                edit_btn.setObjectName("secondaryButton")
                edit_btn.clicked.connect(lambda _=False, key=profile.key: self._open_profile_wizard_for_edit(key))
                row_layout.addWidget(edit_btn)

                delete_btn = QPushButton("Usuń...")
                delete_btn.setObjectName("dangerButton")
                delete_btn.clicked.connect(lambda _=False, key=profile.key: self._delete_profile(key))
                row_layout.addWidget(delete_btn)

            self._button_group.addButton(radio)
            self._profile_radios[profile.key] = radio
            self.profiles_container.addWidget(row)

        if select_key in self._profile_radios:
            self._profile_radios[select_key].setChecked(True)
        elif self._profile_radios:
            next(iter(self._profile_radios.values())).setChecked(True)

    def _open_profile_wizard(self):
        wizard = ProfileWizardDialog(self)
        if wizard.exec() != QDialog.Accepted or not wizard.new_profile_key:
            return
        self._reload(select_key=wizard.new_profile_key)

    def _open_profile_wizard_for_edit(self, profile_key: str):
        custom = get_custom_profile(profile_key)
        if custom is None:
            return
        wizard = ProfileWizardDialog(self, existing=custom)
        if wizard.exec() != QDialog.Accepted or not wizard.new_profile_key:
            return
        self._reload(select_key=wizard.new_profile_key)

    def _delete_profile(self, profile_key: str):
        from model.business_profile import unregister_custom_profile
        from model.custom_profile_store import delete_custom_profile

        custom = get_custom_profile(profile_key)
        if custom is None:
            return

        reply = QMessageBox.question(
            self,
            "Usuń profil",
            f"Usunąć profil \"{custom.display_name}\"? Projekty, które go już "
            "używają, przy następnym otwarciu przełączą się na profil Dino "
            "(nic w nich nie zostanie skasowane).",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            delete_custom_profile(profile_key)
        except OSError as exc:
            QMessageBox.critical(self, "Błąd", f"Nie udało się usunąć profilu: {exc}")
            return
        unregister_custom_profile(profile_key)
        self._reload()
