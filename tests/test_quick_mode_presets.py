from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model.shop_config import ShopConfig, normalize_quick_mode_presets


class NormalizeQuickModePresetsTests(unittest.TestCase):
    """Presety trybu szybkiego (Konfiguracja -> "Ustawienia trybu szybkiego"),
    prośba klienta 2026-09-17: zastępują ręczne wpisywanie godzin nazwanymi
    przedziałami czasowymi."""

    def test_none_or_empty_returns_empty_list(self):
        self.assertEqual(normalize_quick_mode_presets(None), [])
        self.assertEqual(normalize_quick_mode_presets([]), [])

    def test_normal_preset_round_trips(self):
        raw = [{"name": "Zmiana 16h", "start": "06:00", "end": "22:00", "full_day": False}]
        result = normalize_quick_mode_presets(raw)
        self.assertEqual(result, raw)

    def test_overnight_preset_is_allowed(self):
        raw = [{"name": "Nocka", "start": "22:00", "end": "06:00"}]
        result = normalize_quick_mode_presets(raw)
        self.assertEqual(result[0]["start"], "22:00")
        self.assertEqual(result[0]["end"], "06:00")
        self.assertFalse(result[0]["full_day"])

    def test_full_day_preset_drops_end(self):
        raw = [{"name": "Doba 24h", "start": "06:00", "end": "06:00", "full_day": True}]
        result = normalize_quick_mode_presets(raw)
        self.assertEqual(result, [{"name": "Doba 24h", "start": "06:00", "end": None, "full_day": True}])

    def test_empty_name_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_quick_mode_presets([{"name": "  ", "start": "06:00", "end": "14:00"}])

    def test_duplicate_names_are_rejected(self):
        raw = [
            {"name": "Zmiana", "start": "06:00", "end": "14:00"},
            {"name": "Zmiana", "start": "14:00", "end": "22:00"},
        ]
        with self.assertRaises(ValueError):
            normalize_quick_mode_presets(raw)

    def test_equal_start_and_end_without_full_day_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_quick_mode_presets([{"name": "Zmiana", "start": "06:00", "end": "06:00"}])

    def test_missing_end_without_full_day_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_quick_mode_presets([{"name": "Zmiana", "start": "06:00"}])


class ShopConfigQuickModePresetsTests(unittest.TestCase):
    def test_defaults_to_empty_list(self):
        shop = ShopConfig(2026, 9)
        self.assertEqual(shop.quick_mode_presets, [])

    def test_set_quick_mode_presets_validates(self):
        shop = ShopConfig(2026, 9)
        with self.assertRaises(ValueError):
            shop.set_quick_mode_presets([{"name": "", "start": "06:00", "end": "14:00"}])

    def test_survives_to_dict_from_dict_round_trip(self):
        shop = ShopConfig(2026, 9)
        shop.set_quick_mode_presets([
            {"name": "Zmiana 16h", "start": "06:00", "end": "22:00", "full_day": False},
            {"name": "Doba 24h", "start": "06:00", "end": None, "full_day": True},
        ])

        restored = ShopConfig.from_dict(shop.to_dict())

        self.assertEqual(restored.quick_mode_presets, shop.quick_mode_presets)

    def test_corrupted_saved_presets_fall_back_to_empty_list(self):
        data = ShopConfig(2026, 9).to_dict()
        data["quick_mode_presets"] = [{"name": "Dup", "start": "06:00", "end": "14:00"},
                                       {"name": "Dup", "start": "14:00", "end": "22:00"}]

        restored = ShopConfig.from_dict(data)

        self.assertEqual(restored.quick_mode_presets, [])


if __name__ == "__main__":
    unittest.main()
