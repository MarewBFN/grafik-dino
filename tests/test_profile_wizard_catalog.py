"""Kreator profilu: reguła "min. N osób z kwalifikacją" może wskazać
kwalifikację z katalogu projektu; przy zapisie trafia ona do profilu jako
rola (Krok 2.2) - każdy projekt z tym profilem ma ją wtedy w katalogu."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from model.business_profile import get_custom_profile
from model.month_schedule import MonthSchedule
from model.monthly_project import MonthlyProject
from model.qualification import Qualification
from model.shop_config import ShopConfig
from ui.profile_wizard_dialog import ProfileWizardDialog

_app = QApplication.instance() or QApplication([])

CATALOG = {
    "kasa": Qualification(id="kasa", name="Kasa"),
    "wozek": Qualification(id="wozek", name="Wózek widłowy", icon="📦"),
    "otwarcie": Qualification(id="otwarcie", name="Otwarcie", icon="builtin:open"),
}


def _wizard(monkeypatch, name, catalog=CATALOG):
    monkeypatch.setattr("ui.profile_wizard_dialog.save_custom_profile", lambda profile: None)
    wizard = ProfileWizardDialog(None, qualifications=catalog)
    wizard.name_edit.setText(name)
    wizard._role_rows[0].label_edit.setText("Kasa")
    return wizard


def _rule_choices(row):
    return [(row.role_combo.itemData(i), row.role_combo.itemText(i)) for i in range(row.role_combo.count())]


def test_rule_offers_profile_roles_then_catalog(monkeypatch):
    wizard = _wizard(monkeypatch, "Test katalog lista")
    wizard._add_rule_row()
    # "Kasa" z katalogu pokrywa się z rolą profilu - nie jest powtórzona.
    assert _rule_choices(wizard._rule_rows[0]) == [
        ("kasa", "Kasa"),
        ("wozek", "Wózek widłowy (z katalogu projektu)"),
        ("otwarcie", "Otwarcie (z katalogu projektu)"),
    ]


def test_catalog_qualification_used_in_rule_is_added_to_profile(monkeypatch):
    wizard = _wizard(monkeypatch, "Test katalog zapis")
    wizard._add_rule_row()
    row = wizard._rule_rows[0]
    row.role_combo.setCurrentIndex(row.role_combo.findData("wozek"))
    wizard._save()

    profile = get_custom_profile(wizard.new_profile_key)
    assert [(r.key, r.label, r.icon) for r in profile.roles] == [
        (profile.roles[0].key, "Kasa", ""),
        ("wozek", "Wózek widłowy", "📦"),
    ]
    assert [r.qualification_key for r in profile.rules] == ["wozek"]

    # Nowy projekt z tym profilem ma kwalifikację w katalogu - reguła nie
    # żąda osób, których nikt nie może mieć.
    project = MonthlyProject()
    shop = ShopConfig(2026, 10)
    shop.business_type = profile.key
    project.put(2026, 10, MonthSchedule(2026, 10), shop)
    project.ensure_qualification_catalog()
    assert project.qualifications["wozek"].name == "Wózek widłowy"


def test_builtin_icon_is_not_copied_to_profile_role(monkeypatch):
    wizard = _wizard(monkeypatch, "Test katalog ikona")
    wizard._add_rule_row()
    row = wizard._rule_rows[0]
    row.role_combo.setCurrentIndex(row.role_combo.findData("otwarcie"))
    wizard._save()
    role = next(r for r in get_custom_profile(wizard.new_profile_key).roles if r.key == "otwarcie")
    assert role.icon == ""


def test_unused_catalog_qualifications_are_not_added(monkeypatch):
    wizard = _wizard(monkeypatch, "Test katalog bez reguł")
    wizard._save()
    assert [r.label for r in get_custom_profile(wizard.new_profile_key).roles] == ["Kasa"]


def test_wizard_without_project_catalog_lists_only_roles(monkeypatch):
    wizard = _wizard(monkeypatch, "Test bez katalogu", catalog=None)
    wizard._add_rule_row()
    assert [key for key, _ in _rule_choices(wizard._rule_rows[0])] == [wizard._current_role_labels()[0][0]]


def test_editing_profile_keeps_each_rule_on_its_own_qualification(monkeypatch):
    """Dawniej każda reguła w edytowanym profilu pokazywała pierwszą rolę, a
    "Zapisz zmiany" przepisywało ją na nią po cichu."""
    from tests.golden.cases import GOLDEN_CUSTOM_PROFILE
    from model.custom_profile import CustomBusinessProfile

    monkeypatch.setattr("ui.profile_wizard_dialog.save_custom_profile", lambda profile: None)
    existing = CustomBusinessProfile.from_dict({**GOLDEN_CUSTOM_PROFILE, "key": "custom_test_wizard_roundtrip"})
    wizard = ProfileWizardDialog(None, existing=existing)

    assert [row.role_combo.currentData() for row in wizard._rule_rows] == ["kasa", "dostawa", "student"]

    wizard._save()
    saved = get_custom_profile("custom_test_wizard_roundtrip")
    assert [(r.qualification_key, r.id) for r in saved.rules] == [(r.qualification_key, r.id) for r in existing.rules]
