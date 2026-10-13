"""Zarządzanie profilami (kreator: nowy / edycja / usunięcie) widoczne na
każdym kanale wydań, także "enyo" - w kreatorze ustawia się reguły
kwalifikacji ("min. N osób z kwalifikacją X na poziomie >= L w oknie
godzin"). Dawniej schowane dla Enyo (ENYO_ONLY_CHANGES.md)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QPushButton

import model.business_profile as bp
from model.shop_config import ShopConfig

_app = QApplication.instance() or QApplication([])


def _buttons(widget):
    return {button.text(): button for button in widget.findChildren(QPushButton)}


def test_config_dialog_profile_buttons_visible_on_enyo_channel():
    from ui.config_dialog import ConfigDialog

    shop = ShopConfig(2026, 10)
    shop.business_type = bp.DEFAULT_OCHRONA_PROFILE_KEY
    with patch.object(bp, "RELEASE_CHANNEL", "enyo"):
        dialog = ConfigDialog(None, shop)
    buttons = _buttons(dialog)
    for text in ("Nowy profil...", "Edytuj profil...", "Usuń profil..."):
        assert not buttons[text].isHidden(), text
    assert buttons["Edytuj profil..."].isEnabled()  # Ochrona to profil custom


def test_profile_picker_management_buttons_visible_on_enyo_channel():
    from ui.business_profile_picker import BusinessProfilePicker

    with patch.object(bp, "RELEASE_CHANNEL", "enyo"):
        picker = BusinessProfilePicker()
    buttons = _buttons(picker)
    assert not buttons["+ Nowa branża..."].isHidden()
    assert not buttons["Edytuj..."].isHidden()
    assert not buttons["Usuń..."].isHidden()
