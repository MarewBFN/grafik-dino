import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from model.business_profile import register_custom_profile
from model.constraint_policy import ConstraintPolicy
from model.custom_profile import (
    RULE_TYPE_MIN_STAFF_WITH_ROLE,
    CustomBusinessProfile,
    RoleDefinition,
    RuleInstance,
)
from ui.first_run_wizard import (
    STEP_BASICS,
    STEP_BRANCH,
    STEP_FEATURES,
    STEP_RULES,
    STEP_WELCOME,
    FirstRunWizardDialog,
)


def _advance_to_branch(wizard, name="Test Placówka"):
    wizard._go_next()  # welcome -> basics
    wizard.name_edit.setText(name)
    wizard._go_next()  # basics -> branch
    return wizard


def test_wizard_refuses_to_advance_past_basics_with_empty_name(monkeypatch):
    warned = []
    monkeypatch.setattr(
        "ui.first_run_wizard.QMessageBox.warning",
        lambda *a, **k: warned.append(True),
    )
    wizard = FirstRunWizardDialog(None)
    wizard._go_next()  # -> basics
    wizard.name_edit.setText("   ")
    wizard._go_next()
    assert wizard._step_index == STEP_BASICS
    assert warned


def test_wizard_dino_retail_feature_toggle_disables_meat_policy():
    wizard = _advance_to_branch(FirstRunWizardDialog(None))
    assert wizard._step_index == STEP_BRANCH
    wizard._go_next()  # -> features
    assert wizard._step_index == STEP_FEATURES
    assert "meat" in wizard._feature_checks

    wizard._feature_checks["meat"].setChecked(False)
    wizard._go_next()  # -> rules
    assert wizard._step_index == STEP_RULES
    assert wizard.result_policy_overrides["meat"] == ConstraintPolicy.DISABLED
    # The rules step's own selector reflects the toggle instead of the profile default.
    assert wizard._policy_selectors["meat"].currentData() == ConstraintPolicy.DISABLED

    wizard._go_next()  # Zakończ
    assert wizard.completed
    assert wizard.result_business_type == "dino_retail"
    assert wizard.result_name == "Test Placówka"
    assert wizard.result_policy_overrides["meat"] == ConstraintPolicy.DISABLED


def test_wizard_skip_rules_step_does_not_apply_rules_selectors():
    wizard = _advance_to_branch(FirstRunWizardDialog(None))
    wizard._go_next()  # -> features (untouched checkboxes still get recorded as-is)
    wizard._go_next()  # -> rules
    # Sabotage a selector so we can prove skipping never reads it.
    selector = wizard._policy_selectors["rest_11h"]
    selector.setCurrentIndex(selector.findData(ConstraintPolicy.DISABLED))

    wizard._finish(apply_rule_overrides=False)
    assert wizard.completed
    assert "rest_11h" not in wizard.result_policy_overrides


def test_wizard_custom_profile_with_rule_shows_no_feature_toggle_but_shows_rule_in_rules_step():
    rule = RuleInstance(
        type=RULE_TYPE_MIN_STAFF_WITH_ROLE, role_key="guard",
        policy="MANDATORY", params={"min_count": 2, "scope": "open"},
    )
    profile = CustomBusinessProfile(
        key="custom_test_wizard_rule",
        display_name="Ochrona Test Wizard",
        roles=[RoleDefinition(key="guard", label="Ochroniarz")],
        rules=[rule],
    )
    register_custom_profile(profile)

    wizard = _advance_to_branch(FirstRunWizardDialog(None))
    wizard.profile_picker._profile_radios["custom_test_wizard_rule"].setChecked(True)
    wizard._go_next()  # -> features
    assert wizard._feature_checks == {}  # no linked_policy roles on this profile

    wizard._go_next()  # -> rules
    rule_key = profile.rule_policy_key(rule)
    assert rule_key in wizard._policy_selectors


def test_wizard_cancel_leaves_result_incomplete():
    wizard = FirstRunWizardDialog(None)
    wizard.reject()
    assert wizard.completed is False
