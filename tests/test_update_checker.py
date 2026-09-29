from pathlib import Path
from unittest.mock import Mock, patch
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import update_checker
from update_checker import _is_newer, _manifest_url, _parse_version, check_for_updates


class ParseVersionTests(unittest.TestCase):
    def test_parses_simple_version(self):
        self.assertEqual(_parse_version("1.1"), (1, 1))

    def test_strips_leading_v_prefix(self):
        self.assertEqual(_parse_version("v1.2.3"), (1, 2, 3))

    def test_ignores_non_digit_suffix(self):
        self.assertEqual(_parse_version("1.2.3-beta"), (1, 2, 3))


class IsNewerTests(unittest.TestCase):
    def test_equal_versions_are_not_newer(self):
        self.assertFalse(_is_newer("1.1", "1.1"))

    def test_equal_versions_with_different_segment_counts_are_not_newer(self):
        self.assertFalse(_is_newer("1.1", "1.1.0"))
        self.assertFalse(_is_newer("1.1.0", "1.1"))

    def test_higher_minor_is_newer(self):
        self.assertTrue(_is_newer("1.2", "1.1"))

    def test_lower_version_is_not_newer(self):
        self.assertFalse(_is_newer("1.0", "1.1"))

    def test_v_prefix_does_not_affect_comparison(self):
        self.assertTrue(_is_newer("v1.2.0", "1.1"))

    def test_higher_patch_with_extra_segment_is_newer(self):
        self.assertTrue(_is_newer("1.1.1", "1.1"))


class ManifestUrlTests(unittest.TestCase):
    def test_manifest_url_uses_channel_specific_raw_github_path(self):
        with patch.object(update_checker, "RELEASE_CHANNEL", "dino"):
            self.assertEqual(
                _manifest_url(),
                "https://raw.githubusercontent.com/MarewBFN/grafik-dino/main/releases/dino.json",
            )

        with patch.object(update_checker, "RELEASE_CHANNEL", "enyo"):
            self.assertEqual(
                _manifest_url(),
                "https://raw.githubusercontent.com/MarewBFN/grafik-dino/main/releases/enyo.json",
            )


class CheckForUpdatesTests(unittest.TestCase):
    def _mock_response(self, status_code=200, json_data=None):
        response = Mock()
        response.status_code = status_code
        response.json.return_value = json_data or {}
        response.raise_for_status = Mock()
        return response

    def test_fetches_manifest_for_current_channel(self):
        response = self._mock_response(json_data={
            "latest_version": "99.0.0",
            "download_url": "https://example.com/setup.exe",
            "changelog": "notatki",
        })
        with patch.object(update_checker, "RELEASE_CHANNEL", "enyo"), \
                patch.object(update_checker.requests, "get", return_value=response) as get_mock:
            result = check_for_updates()

        get_mock.assert_called_once()
        called_url = get_mock.call_args[0][0]
        self.assertTrue(called_url.endswith("/releases/enyo.json"))
        self.assertEqual(result, {
            "available": True,
            "version": "99.0.0",
            "url": "https://example.com/setup.exe",
            "notes": "notatki",
        })

    def test_no_update_when_manifest_version_is_not_newer(self):
        response = self._mock_response(json_data={
            "latest_version": update_checker.APP_VERSION,
            "download_url": "https://example.com/setup.exe",
        })
        with patch.object(update_checker.requests, "get", return_value=response):
            result = check_for_updates()

        self.assertEqual(result, {"available": False})

    def test_missing_manifest_returns_not_available(self):
        response = self._mock_response(status_code=404)
        with patch.object(update_checker.requests, "get", return_value=response):
            result = check_for_updates()

        self.assertEqual(result, {"available": False})

    def test_network_error_reports_error(self):
        with patch.object(update_checker.requests, "get", side_effect=OSError("boom")):
            result = check_for_updates()

        self.assertFalse(result["available"])
        self.assertIn("boom", result["error"])

    def test_missing_download_url_returns_not_available(self):
        response = self._mock_response(json_data={"latest_version": "99.0.0"})
        with patch.object(update_checker.requests, "get", return_value=response):
            result = check_for_updates()

        self.assertEqual(result, {"available": False})


class DefaultReleaseChannelTests(unittest.TestCase):
    def test_committed_default_channel_is_dino(self):
        content = (ROOT / "release_channel.py").read_text(encoding="utf-8")
        match = re.search(r'RELEASE_CHANNEL\s*=\s*"([^"]*)"', content)
        self.assertIsNotNone(match, "release_channel.py nie zawiera RELEASE_CHANNEL")
        self.assertEqual(
            match.group(1),
            "dino",
            "release_channel.py w repo musi miec RELEASE_CHANNEL = \"dino\" - "
            "wyglada na to, ze pozostala niezacommitowana zmiana z builda dla innego klienta.",
        )


if __name__ == "__main__":
    unittest.main()
