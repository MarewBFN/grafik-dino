from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from update_checker import _is_newer, _parse_version


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


if __name__ == "__main__":
    unittest.main()
