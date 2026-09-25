import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from model.location import LocationConfig, format_open_hours_summary, normalize_night_shift
from model.shop_config import DEFAULT_LOCATION_KEY, ShopConfig
from model.employee import Employee
from model.month_schedule import MonthSchedule


def test_location_config_round_trips_through_dict():
    loc = LocationConfig(
        key="galeria_pn",
        name="Galeria Płn",
        open_hours={0: ("08:00", "20:00")},
        trade_sundays={7, 21},
        public_holidays={1},
        day_overrides={15: ("10:00", "18:00")},
        constraints={"min_open_staff": 2, "min_close_staff": 2, "max_consecutive_days": 5},
    )

    restored = LocationConfig.from_dict(loc.to_dict())

    assert restored.key == "galeria_pn"
    assert restored.name == "Galeria Płn"
    assert restored.open_hours == {0: ("08:00", "20:00")}
    assert restored.trade_sundays == {7, 21}
    assert restored.public_holidays == {1}
    assert restored.day_overrides == {15: ("10:00", "18:00")}
    assert restored.constraints == {"min_open_staff": 2, "min_close_staff": 2, "max_consecutive_days": 5}
    assert restored.is_24_7 is False
    # 08:00-20:00 doesn't touch 22:00-06:00 - no night shift for this location.
    assert restored.get_night_shift_hours() is None


# --- Auto-wykrywanie zmiany nocnej z godzin otwarcia (zastępuje ręczne pole) ---


def test_normalize_night_shift_accepts_empty_pair_as_no_window():
    assert normalize_night_shift(None, None) is None
    assert normalize_night_shift("", "") is None


def test_normalize_night_shift_rejects_a_single_missing_side():
    with pytest.raises(ValueError):
        normalize_night_shift("22:00", None)
    with pytest.raises(ValueError):
        normalize_night_shift(None, "06:00")


def test_normalize_night_shift_rejects_equal_start_and_end():
    with pytest.raises(ValueError):
        normalize_night_shift("22:00", "22:00")


def test_normalize_night_shift_allows_crossing_midnight():
    assert normalize_night_shift("22:00", "06:00") == {"start": "22:00", "end": "06:00"}


def test_location_config_detects_night_shift_from_default_open_hours():
    # Default open_hours (05:30-23:00/22:45) touch 22:00-06:00 on every day.
    loc = LocationConfig(key="obiekt_1", name="Obiekt 1")
    assert loc.get_night_shift_hours() == ("22:00", "06:00")


def test_location_config_no_night_shift_when_open_hours_never_touch_it():
    loc = LocationConfig(key="obiekt_1", name="Obiekt 1", open_hours={i: ("09:00", "17:00") for i in range(7)})
    assert loc.get_night_shift_hours() is None


def test_location_config_24_7_always_has_night_shift():
    loc = LocationConfig(key="obiekt_1", name="Obiekt 1", open_hours={i: ("09:00", "17:00") for i in range(7)})
    loc.set_24_7(True)
    assert loc.is_24_7 is True
    assert loc.open_hours == {i: ("00:00", "23:45") for i in range(7)}
    assert loc.get_night_shift_hours() == ("22:00", "06:00")

    loc.set_24_7(False)
    assert loc.is_24_7 is False
    # Turning 24/7 off does not restore the previous hours - open_hours stay
    # "cała doba" until the user edits them again (same as the UI's checkbox).
    assert loc.open_hours == {i: ("00:00", "23:45") for i in range(7)}


def test_location_config_ignores_legacy_night_shift_key_from_old_files():
    loc = LocationConfig(key="obiekt_1", name="Obiekt 1", open_hours={i: ("09:00", "17:00") for i in range(7)})
    data = loc.to_dict()
    data["night_shift"] = {"start": "10:00", "end": "14:00"}  # pre-migration file shape

    restored = LocationConfig.from_dict(data)
    assert not hasattr(restored, "night_shift")
    # Auto-detection from open_hours wins - the legacy manual field is ignored.
    assert restored.get_night_shift_hours() is None


def test_shop_config_night_shift_set_get_and_round_trip():
    shop = ShopConfig(2026, 8)
    assert shop.get_night_shift_hours() is None

    shop.set_night_shift("22:00", "06:00")
    assert shop.get_night_shift_hours() == ("22:00", "06:00")

    restored = ShopConfig.from_dict(shop.to_dict())
    assert restored.get_night_shift_hours() == ("22:00", "06:00")


def test_shop_config_night_shift_defaults_none_for_old_data():
    shop = ShopConfig(2026, 8)
    data = shop.to_dict()
    del data["night_shift"]  # simulate a project saved before this field existed

    restored = ShopConfig.from_dict(data)
    assert restored.get_night_shift_hours() is None


def test_get_location_exposes_night_shift_hours_for_assigned_employee():
    shop = ShopConfig(2026, 8)
    # Project-level fallback (legacy, only used by employees without a
    # matching location - see get_location()).
    shop.set_night_shift("21:00", "05:00")

    loc = LocationConfig(key="obiekt_1", name="Obiekt 1")  # default hours -> auto night
    shop.locations["obiekt_1"] = loc

    emp = Employee(last_name="Kowalski", first_name="Jan", location_key="obiekt_1")
    assert shop.get_location(emp).get_night_shift_hours() == ("22:00", "06:00")

    emp_no_location = Employee(last_name="Nowak", first_name="Anna")
    assert shop.get_location(emp_no_location).get_night_shift_hours() == ("21:00", "05:00")


def test_location_config_open_hours_use_explicit_year_month_day():
    loc = LocationConfig(key="a", name="A", open_hours={0: ("08:00", "20:00")})
    # 2026-03-02 is a Monday.
    assert loc.get_open_hours_for_day(2026, 3, 2) == ("08:00", "20:00")


# --- uses_trade_calendar: Sunday must not silently close for profiles that
# don't use a trade calendar (Dino-era leftover: trade_sundays is empty by
# default, so every Sunday used to read as closed regardless of profile) ---


def test_sunday_is_open_when_profile_does_not_use_trade_calendar():
    loc = LocationConfig(key="a", name="A", open_hours={6: ("08:00", "20:00")})
    # 2026-03-01 is a Sunday. trade_sundays is empty (never explicitly marked).
    assert loc.is_trade_day(2026, 3, 1, uses_trade_calendar=False) is True
    assert loc.get_open_hours_for_day(2026, 3, 1, uses_trade_calendar=False) == ("08:00", "20:00")


def test_sunday_is_closed_by_default_when_profile_uses_trade_calendar():
    loc = LocationConfig(key="a", name="A", open_hours={6: ("08:00", "20:00")})
    assert loc.is_trade_day(2026, 3, 1, uses_trade_calendar=True) is False
    assert loc.get_open_hours_for_day(2026, 3, 1, uses_trade_calendar=True) is None


def test_sunday_open_hours_default_matches_the_old_trade_calendar_behavior():
    """uses_trade_calendar defaults to True (unspecified) - preserves
    behavior for any caller that doesn't know about business profiles."""
    loc = LocationConfig(key="a", name="A", open_hours={6: ("08:00", "20:00")})
    assert loc.get_open_hours_for_day(2026, 3, 1) is None


def test_public_holiday_is_ignored_when_profile_does_not_use_trade_calendar():
    loc = LocationConfig(key="a", name="A", open_hours={0: ("08:00", "20:00")}, public_holidays={2})
    # 2026-03-02 is a Monday, marked as a public holiday.
    assert loc.get_open_hours_for_day(2026, 3, 2, uses_trade_calendar=False) == ("08:00", "20:00")


def test_shop_get_location_resolves_uses_trade_calendar_from_the_profile():
    from model.business_profile import register_custom_profile
    from model.custom_profile import CustomBusinessProfile

    profile = CustomBusinessProfile(
        key="custom_test_sunday_not_closed", display_name="Test", roles=[], rules=[],
    )
    register_custom_profile(profile)

    shop = ShopConfig(2026, 3)
    shop.business_type = profile.key
    loc = LocationConfig(key="site1", name="Site 1", open_hours={6: ("08:00", "20:00")})
    shop.locations["site1"] = loc
    emp = Employee(last_name="Kowalski", first_name="Jan", location_key="site1")

    # 2026-03-01 is a Sunday - must stay open for a profile without a trade calendar.
    assert shop.get_location(emp).get_open_hours_for_day(1) == ("08:00", "20:00")


# --- format_open_hours_summary (pasek nad tabelą grafiku) ---


def test_format_open_hours_summary_24_7():
    loc = LocationConfig(key="a", name="A")
    loc.set_24_7(True)
    assert format_open_hours_summary(loc) == "24/7"


def test_format_open_hours_summary_identical_every_day():
    loc = LocationConfig(key="a", name="A", open_hours={i: ("08:00", "20:00") for i in range(7)})
    assert format_open_hours_summary(loc) == "Godziny pracy: 08:00 - 20:00"


def test_format_open_hours_summary_weekday_vs_shared_weekend():
    hours = {i: ("08:00", "20:00") for i in range(5)}
    hours[5] = ("10:00", "18:00")
    hours[6] = ("10:00", "18:00")
    loc = LocationConfig(key="a", name="A", open_hours=hours)
    assert format_open_hours_summary(loc) == "Pon-Pt 08:00-20:00, Sob-Nd 10:00-18:00"


def test_format_open_hours_summary_weekday_vs_separate_weekend_days():
    hours = {i: ("08:00", "20:00") for i in range(5)}
    hours[5] = ("10:00", "16:00")
    hours[6] = ("10:00", "14:00")
    loc = LocationConfig(key="a", name="A", open_hours=hours)
    assert format_open_hours_summary(loc) == "Pon-Pt 08:00-20:00, Sob 10:00-16:00, Nd 10:00-14:00"


def test_format_open_hours_summary_falls_back_for_mixed_patterns():
    hours = {i: ("08:00", "20:00") for i in range(7)}
    hours[2] = ("09:00", "18:00")  # one weekday differs from the rest
    loc = LocationConfig(key="a", name="A", open_hours=hours)
    assert format_open_hours_summary(loc) == "Niestandardowe godziny pracy"


def test_format_open_hours_summary_falls_back_when_a_day_is_closed():
    hours = {i: ("08:00", "20:00") for i in range(7)}
    hours[6] = None
    loc = LocationConfig(key="a", name="A", open_hours=hours)
    assert format_open_hours_summary(loc) == "Niestandardowe godziny pracy"


# --- ShopConfig.locations: zawsze co najmniej jedna lokalizacja ---


def test_shop_config_always_has_a_default_location():
    shop = ShopConfig(2026, 3)
    assert set(shop.locations.keys()) == {DEFAULT_LOCATION_KEY}
    assert shop.locations[DEFAULT_LOCATION_KEY].name == "Placówka główna"

    shop.locations["main"] = LocationConfig(key="main", name="Główna")
    data = shop.to_dict()
    restored = ShopConfig.from_dict(data)

    assert set(restored.locations.keys()) == {DEFAULT_LOCATION_KEY, "main"}
    assert restored.locations["main"].name == "Główna"


def test_old_project_without_locations_field_migrates_to_one_default_location():
    shop = ShopConfig(2026, 3)
    shop.open_hours = {i: ("07:00", "19:00") for i in range(7)}
    data = shop.to_dict()
    del data["locations"]  # simulate a project file saved before this field existed

    restored = ShopConfig.from_dict(data)
    assert set(restored.locations.keys()) == {DEFAULT_LOCATION_KEY}
    assert restored.locations[DEFAULT_LOCATION_KEY].open_hours == restored.open_hours
    assert restored._migrated_default_location is True


# --- from_dict() musi odrzucić duty_rotation osierocone bez is_24_7
# (zgłoszenie użytkownika 2026-09-25: test_data/dane_klienta_ochrona.json ma
# lokalizacje z is_24_7=False i skonfigurowanymi konkretnymi godzinami
# pracy, ale z osieroconym duty_rotation z dawnych danych testowych (sprzed
# scalenia checkboxa "Rotacja służby 24/7" z "Działalność całodobowa
# (24/7)") - generator mimo to przydzielał zmiany 24h/12h+12h, bo
# get_duty_rotation() samo w sobie jest celowo niezależne od is_24_7 (patrz
# jej docstring - generator/testy legalnie konstruują lokalizacje z
# duty_rotation bez is_24_7). Obie ścieżki zapisu (LocationsDialog,
# ConfigDialog) zawsze trzymają te dwa pola w parze, więc jedyne miejsce,
# gdzie mogą się faktycznie rozjechać, to wczytanie pliku - tam (nie w
# get_duty_rotation()) ma to być naprawione. ---


def test_from_dict_drops_orphaned_duty_rotation_when_24_7_is_off():
    rotation = {
        "weekend_half_a": {"start": "08:00", "end": "20:00"},
        "weekend_half_b": {"start": "20:00", "end": "08:00"},
        "weekend_full": {"start": "08:00"},
        "only_12_24h": True,
    }
    loc = LocationConfig(key="a", name="A", open_hours={i: ("08:00", "20:00") for i in range(7)})
    loc.duty_rotation = dict(rotation)  # np. z demo/install_*.py albo starego projektu
    assert loc.is_24_7 is False

    restored = LocationConfig.from_dict(loc.to_dict())

    assert restored.is_24_7 is False
    assert restored.get_duty_rotation() is None
    assert restored.open_hours == {i: ("08:00", "20:00") for i in range(7)}


def test_from_dict_keeps_duty_rotation_when_24_7_is_on():
    rotation = {
        "weekend_half_a": {"start": "08:00", "end": "20:00"},
        "weekend_half_b": {"start": "20:00", "end": "08:00"},
        "weekend_full": {"start": "08:00"},
        "only_12_24h": True,
    }
    loc = LocationConfig(key="a", name="A")
    loc.is_24_7 = True
    loc.duty_rotation = dict(rotation)

    restored = LocationConfig.from_dict(loc.to_dict())

    assert restored.get_duty_rotation() == rotation


def test_get_duty_rotation_is_independent_of_is_24_7_for_in_memory_objects():
    """Generator/testy tworzą lokalizacje z duty_rotation bezpośrednio (bez
    is_24_7) - to jest jedyny mechanizm, o którym duty_rotation w ogóle wie,
    godziny otwarcia/is_24_7 są dla niego bez znaczenia. Spójność z is_24_7
    jest egzekwowana wyłącznie przy wczytywaniu z dysku (patrz testy
    from_dict wyżej), nie tutaj."""
    rotation = {
        "weekend_half_a": {"start": "08:00", "end": "20:00"},
        "weekend_half_b": {"start": "20:00", "end": "08:00"},
        "weekend_full": {"start": "08:00"},
        "only_12_24h": True,
    }
    loc = LocationConfig(key="a", name="A")
    loc.set_duty_rotation(rotation)
    assert loc.is_24_7 is False

    assert loc.get_duty_rotation() == rotation


# --- closed_on_public_holidays: automatyczne zamknięcie w polskie święta
# ustawowe (biblioteka `holidays`, patrz logic/utils/holidays_pl.py) -
# zgłoszenie użytkownika (2026-09-25): program dotąd liczył nominalny czas
# pracy/otwarcie lokalizacji tylko przez ręcznie zaznaczane public_holidays ---


def test_is_closed_for_public_holiday_true_by_default_on_a_real_holiday():
    loc = LocationConfig(key="a", name="A")
    assert loc.closed_on_public_holidays is True
    # 2026-01-01 to Nowy Rok - trwałe, ustawowe święto.
    assert loc.is_closed_for_public_holiday(2026, 1, 1) is True


def test_is_closed_for_public_holiday_false_when_toggle_off():
    loc = LocationConfig(key="a", name="A", closed_on_public_holidays=False)
    assert loc.is_closed_for_public_holiday(2026, 1, 1) is False


def test_is_closed_for_public_holiday_false_on_a_regular_day():
    loc = LocationConfig(key="a", name="A")
    assert loc.is_closed_for_public_holiday(2026, 1, 2) is False


def test_day_override_wins_over_automatic_public_holiday_closure():
    loc = LocationConfig(key="a", name="A")
    loc.day_overrides[1] = ("08:00", "16:00")  # 2026-01-01, jawne nadpisanie
    assert loc.is_closed_for_public_holiday(2026, 1, 1) is False
    assert loc.get_open_hours_for_day(2026, 1, 1) == ("08:00", "16:00")


def test_get_open_hours_for_day_returns_none_on_a_public_holiday():
    loc = LocationConfig(key="a", name="A", open_hours={3: ("08:00", "20:00")})  # Czwartek
    # 2026-01-01 to czwartek.
    assert loc.get_open_hours_for_day(2026, 1, 1) is None


def test_get_open_hours_for_day_unaffected_when_toggle_off():
    loc = LocationConfig(
        key="a", name="A", open_hours={3: ("08:00", "20:00")}, closed_on_public_holidays=False,
    )
    assert loc.get_open_hours_for_day(2026, 1, 1) == ("08:00", "20:00")


def test_closed_on_public_holidays_round_trips_and_defaults_true_for_old_files():
    loc = LocationConfig(key="a", name="A", closed_on_public_holidays=False)
    restored = LocationConfig.from_dict(loc.to_dict())
    assert restored.closed_on_public_holidays is False

    data = LocationConfig(key="a", name="A").to_dict()
    del data["closed_on_public_holidays"]  # symuluje projekt zapisany przed tym polem
    restored_old = LocationConfig.from_dict(data)
    assert restored_old.closed_on_public_holidays is True


# --- ShopConfig.get_full_time_nominal_hours(): liczone automatycznie z
# biblioteki `holidays` zamiast tylko ręcznie zaznaczanych public_holidays ---


def test_nominal_hours_subtracts_automatically_detected_weekday_holidays():
    # Styczeń 2026: 22 dni robocze (pon-pt), z czego 2 to święta (1 i 6
    # stycznia) - (22-2)*8 = 160.
    shop = ShopConfig(2026, 1)
    assert shop.get_full_time_nominal_hours() == 160.0


def test_nominal_hours_manual_public_holidays_still_subtract_too():
    # Unia automatycznych i ręcznie zaznaczonych - dzień spoza kalendarza
    # krajowego (np. lokalny/firmowy) nadal się odejmuje.
    shop = ShopConfig(2026, 1)
    shop.public_holidays = {2}  # 2026-01-02, piątek, nie jest świętem PL
    assert shop.get_full_time_nominal_hours() == 152.0


def test_nominal_hours_uses_standard_daily_hours_not_hardcoded_8():
    shop = ShopConfig(2026, 1)
    shop.standard_daily_hours = 7.5
    assert shop.get_full_time_nominal_hours() == 20 * 7.5


def test_nominal_hours_month_without_any_weekday_holiday_is_unaffected():
    # Marzec 2026 nie ma żadnego polskiego święta ustawowego.
    shop = ShopConfig(2026, 3)
    import calendar
    workdays = sum(1 for d in range(1, 32) if calendar.weekday(2026, 3, d) < 5)
    assert shop.get_full_time_nominal_hours() == workdays * 8


def test_employee_location_key_defaults_empty_and_round_trips():
    emp = Employee(last_name="Kowalski", first_name="Jan")
    assert emp.location_key == ""

    schedule = MonthSchedule(2026, 3)
    emp2 = Employee(last_name="Nowak", first_name="Anna", location_key="galeria_pn")
    schedule.add_employee(emp2)

    restored = MonthSchedule.from_dict(schedule.to_dict())
    assert restored.employees[0].location_key == "galeria_pn"
