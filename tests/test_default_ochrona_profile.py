"""model/business_profile.py::_ensure_default_ochrona_profile() - Enyo-only
auto-provisioning of the "Ochrona" custom profile (branch integration/
enyo-only). %LOCALAPPDATA%\\GrafikDino\\custom_profiles.json is per-machine
state, not shipped with the installer - a genuinely fresh client machine
starts with nothing registered there, and profile-management UI is hidden
for this build, so without this the first-run wizard would have no usable
profile to offer. Also must repair a stale/incorrect existing registration
(found on the dev machine during testing: a leftover "Obłożenie"
per-employee role from before LocationConfig.duty_rotation existed)."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import model.business_profile as bp
from model.custom_profile import CustomBusinessProfile, RoleDefinition


class BuildDefaultOchronaProfileTests(unittest.TestCase):
    def test_canonical_profile_has_umowa_and_nie_chce_24h_only(self):
        profile = bp.build_default_ochrona_profile()

        self.assertEqual(profile.key, bp.DEFAULT_OCHRONA_PROFILE_KEY)
        self.assertEqual(profile.display_name, "Ochrona")
        role_keys = [r.key for r in profile.roles]
        self.assertEqual(role_keys, ["umowa", "nie_chce_24h"])

    def test_canonical_profile_has_no_generic_rules(self):
        """Obłożenie/pokrycie 24/7 is computed entirely from LocationConfig.
        duty_rotation, not from a min_staff_with_role rule."""
        profile = bp.build_default_ochrona_profile()
        self.assertEqual(profile.rules, [])

    def test_canonical_profile_roles_do_not_show_their_own_summary_row(self):
        profile = bp.build_default_ochrona_profile()
        self.assertTrue(all(not r.show_summary_row for r in profile.roles))


class EnsureDefaultOchronaProfileTests(unittest.TestCase):
    def setUp(self):
        self._saved_custom = dict(bp.CUSTOM_PROFILES)
        self._saved_business = dict(bp.BUSINESS_PROFILES)

    def tearDown(self):
        bp.CUSTOM_PROFILES.clear()
        bp.CUSTOM_PROFILES.update(self._saved_custom)
        bp.BUSINESS_PROFILES.clear()
        bp.BUSINESS_PROFILES.update(self._saved_business)

    def test_missing_profile_gets_registered(self):
        bp.CUSTOM_PROFILES.pop(bp.DEFAULT_OCHRONA_PROFILE_KEY, None)
        bp.BUSINESS_PROFILES.pop(bp.DEFAULT_OCHRONA_PROFILE_KEY, None)

        with patch("model.custom_profile_store.save_custom_profile"):
            bp._ensure_default_ochrona_profile()

        registered = bp.get_custom_profile(bp.DEFAULT_OCHRONA_PROFILE_KEY)
        self.assertIsNotNone(registered)
        self.assertEqual([r.key for r in registered.roles], ["umowa", "nie_chce_24h"])

    def test_stale_registered_profile_gets_repaired(self):
        stale = CustomBusinessProfile(
            key=bp.DEFAULT_OCHRONA_PROFILE_KEY,
            display_name="Ochrona",
            roles=[RoleDefinition(key="ob_o_enie", label="Obłożenie")],
            rules=[],
        )
        bp.CUSTOM_PROFILES[stale.key] = stale

        with patch("model.custom_profile_store.save_custom_profile") as mock_save:
            bp._ensure_default_ochrona_profile()

        mock_save.assert_called_once()
        registered = bp.get_custom_profile(bp.DEFAULT_OCHRONA_PROFILE_KEY)
        self.assertEqual([r.key for r in registered.roles], ["umowa", "nie_chce_24h"])

    def test_already_correct_profile_is_not_rewritten(self):
        bp.CUSTOM_PROFILES[bp.DEFAULT_OCHRONA_PROFILE_KEY] = bp.build_default_ochrona_profile()

        with patch("model.custom_profile_store.save_custom_profile") as mock_save:
            bp._ensure_default_ochrona_profile()

        mock_save.assert_not_called()

    def test_visible_profiles_includes_ochrona_after_ensuring(self):
        bp.CUSTOM_PROFILES.pop(bp.DEFAULT_OCHRONA_PROFILE_KEY, None)
        bp.BUSINESS_PROFILES.pop(bp.DEFAULT_OCHRONA_PROFILE_KEY, None)

        with patch("model.custom_profile_store.save_custom_profile"):
            bp._ensure_default_ochrona_profile()

        visible_keys = [p.key for p in bp.visible_profiles()]
        self.assertIn(bp.DEFAULT_OCHRONA_PROFILE_KEY, visible_keys)
        self.assertNotIn(bp.DEFAULT_BUSINESS_TYPE, visible_keys)

    def test_broken_app_data_location_does_not_raise(self):
        bp.CUSTOM_PROFILES.pop(bp.DEFAULT_OCHRONA_PROFILE_KEY, None)
        bp.BUSINESS_PROFILES.pop(bp.DEFAULT_OCHRONA_PROFILE_KEY, None)

        with patch("model.custom_profile_store.save_custom_profile", side_effect=OSError("no LOCALAPPDATA")):
            bp._ensure_default_ochrona_profile()  # must not raise

        # Still usable for this run even though persisting to disk failed.
        self.assertIsNotNone(bp.get_custom_profile(bp.DEFAULT_OCHRONA_PROFILE_KEY))


if __name__ == "__main__":
    unittest.main()
