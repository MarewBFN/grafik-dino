from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from model.employee import Employee
from model.location import LocationConfig, normalize_duty_rotation
from model.shop_config import ShopConfig

VALID_ROTATION = {
    "weekday_long": {"start": "06:00", "end": "22:00"},
    "weekday_short": {"start": "22:00", "end": "06:00"},
    "weekend_full": {"start": "06:00"},
    "weekend_half_a": {"start": "06:00", "end": "18:00"},
    "weekend_half_b": {"start": "18:00", "end": "06:00"},
    "only_12_24h": False,
}


# --- normalize_duty_rotation ---


def test_normalize_duty_rotation_accepts_none_or_empty():
    assert normalize_duty_rotation(None) is None
    assert normalize_duty_rotation({}) is None


def test_normalize_duty_rotation_accepts_a_full_valid_config():
    assert normalize_duty_rotation(VALID_ROTATION) == VALID_ROTATION


def test_normalize_duty_rotation_drops_extra_keys_on_weekend_full():
    raw = dict(VALID_ROTATION)
    raw["weekend_full"] = {"start": "06:00", "end": "ignored, 24h is implicit"}
    assert normalize_duty_rotation(raw)["weekend_full"] == {"start": "06:00"}


def test_normalize_duty_rotation_only_12_24h_does_not_require_weekday_windows():
    raw = {
        "only_12_24h": True,
        "weekend_full": {"start": "06:00"},
        "weekend_half_a": {"start": "06:00", "end": "18:00"},
        "weekend_half_b": {"start": "18:00", "end": "06:00"},
    }
    result = normalize_duty_rotation(raw)
    assert result["only_12_24h"] is True
    assert "weekday_long" not in result
    assert "weekday_short" not in result


def test_normalize_duty_rotation_only_12_24h_still_requires_weekend_windows():
    raw = {"only_12_24h": True, "weekend_full": {"start": "06:00"}}
    with pytest.raises(ValueError):
        normalize_duty_rotation(raw)


def test_normalize_duty_rotation_only_12_24h_preserves_weekday_windows_if_present():
    """Jeśli ktoś i tak poda weekday_long/short razem z only_12_24h=True, są
    zachowane (nieużywane w tym trybie, ale nie zgubione) - inaczej toggle
    "Używaj tylko zmian 12/24h" nie dałoby się bezpiecznie przełączyć z
    powrotem na False bez osobnego UI do ponownego wpisania tych godzin."""
    raw = dict(VALID_ROTATION)
    raw["only_12_24h"] = True
    result = normalize_duty_rotation(raw)
    assert result["weekday_long"] == VALID_ROTATION["weekday_long"]
    assert result["weekday_short"] == VALID_ROTATION["weekday_short"]


def test_normalize_duty_rotation_requires_all_five_windows():
    required_keys = [k for k in VALID_ROTATION if k != "only_12_24h"]
    for missing_key in required_keys:
        raw = {k: v for k, v in VALID_ROTATION.items() if k != missing_key}
        with pytest.raises(ValueError):
            normalize_duty_rotation(raw)


def test_normalize_duty_rotation_rejects_equal_start_end_on_a_pair_window():
    raw = dict(VALID_ROTATION)
    raw["weekday_long"] = {"start": "06:00", "end": "06:00"}
    with pytest.raises(ValueError):
        normalize_duty_rotation(raw)


def test_normalize_duty_rotation_rejects_missing_side_on_a_pair_window():
    raw = dict(VALID_ROTATION)
    raw["weekend_half_a"] = {"start": "06:00"}
    with pytest.raises(ValueError):
        normalize_duty_rotation(raw)


def test_normalize_duty_rotation_rejects_weekend_full_without_start():
    raw = dict(VALID_ROTATION)
    raw["weekend_full"] = {}
    with pytest.raises(ValueError):
        normalize_duty_rotation(raw)


def test_normalize_duty_rotation_allows_crossing_midnight_pairs():
    # weekday_short (22:00-06:00) and weekend_half_b (18:00-06:00) already
    # cross midnight in VALID_ROTATION - this just makes that explicit.
    result = normalize_duty_rotation(VALID_ROTATION)
    assert result["weekday_short"] == {"start": "22:00", "end": "06:00"}
    assert result["weekend_half_b"] == {"start": "18:00", "end": "06:00"}


# --- LocationConfig ---


def test_location_config_duty_rotation_defaults_none():
    loc = LocationConfig(key="site1", name="Site 1")
    assert loc.get_duty_rotation() is None


def test_location_config_duty_rotation_set_get_and_round_trip():
    loc = LocationConfig(key="site1", name="Site 1")
    loc.set_duty_rotation(VALID_ROTATION)
    assert loc.get_duty_rotation() == VALID_ROTATION

    restored = LocationConfig.from_dict(loc.to_dict())
    assert restored.get_duty_rotation() == VALID_ROTATION

    loc.set_duty_rotation(None)
    assert loc.get_duty_rotation() is None


def test_location_config_duty_rotation_defaults_none_for_old_data():
    loc = LocationConfig(key="site1", name="Site 1")
    data = loc.to_dict()
    del data["duty_rotation"]  # simulate a project saved before this field existed

    restored = LocationConfig.from_dict(data)
    assert restored.get_duty_rotation() is None


# --- ShopConfig ---


def test_shop_config_duty_rotation_defaults_none():
    shop = ShopConfig(2026, 8)
    assert shop.get_duty_rotation() is None


def test_shop_config_duty_rotation_set_get_and_round_trip():
    shop = ShopConfig(2026, 8)
    shop.set_duty_rotation(VALID_ROTATION)
    assert shop.get_duty_rotation() == VALID_ROTATION

    restored = ShopConfig.from_dict(shop.to_dict())
    assert restored.get_duty_rotation() == VALID_ROTATION


def test_shop_config_duty_rotation_defaults_none_for_old_data():
    shop = ShopConfig(2026, 8)
    data = shop.to_dict()
    del data["duty_rotation"]  # simulate a project saved before this field existed

    restored = ShopConfig.from_dict(data)
    assert restored.get_duty_rotation() is None


def test_get_location_exposes_duty_rotation_for_assigned_employee():
    shop = ShopConfig(2026, 8)
    shop.set_duty_rotation({**VALID_ROTATION, "weekday_long": {"start": "00:00", "end": "01:00"}})

    loc = LocationConfig(key="site1", name="Site 1")
    loc.set_duty_rotation(VALID_ROTATION)
    shop.locations["site1"] = loc

    emp = Employee(last_name="Guard", first_name="A", location_key="site1")
    emp_no_location = Employee(last_name="Guard", first_name="B")

    assert shop.get_location(emp).get_duty_rotation() == VALID_ROTATION
    # Falls back to the project-level default when no location is assigned.
    assert shop.get_location(emp_no_location).get_duty_rotation()["weekday_long"] == {
        "start": "00:00", "end": "01:00",
    }
