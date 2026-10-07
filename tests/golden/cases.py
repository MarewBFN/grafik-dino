"""Projekty "golden" - punkt odniesienia dla migracji modelu kwalifikacji.

Każdy przypadek to `spec` w formacie tests/generator_audit_harness.py::
build_case (te same pola co GUI). tests/golden/record.py zapisuje z nich
pliki projektów w DZISIEJSZYM formacie (tests/golden/projects/*.json) i
wynik generatora (tests/golden/reference.json); test
tests/test_golden_schedules.py wczytuje te pliki tak, jak program wczytuje
projekt użytkownika, generuje grafik i porównuje wynik z punktem
odniesienia (walidator + wartość celu solvera - nie komórka po komórce,
bo CP-SAT bywa niedeterministyczny).

Pliki projektów są celowo zamrożone w starym formacie (pola is_opener,
is_meat, ... i custom_roles) - po migracji na Qualification ten sam test
sprawdza przy okazji, że stare pliki wczytują się bez utraty danych.

Profil custom "golden_sklep_custom" (reguły min_staff_with_role /
role_time_restriction) jest zdefiniowany tutaj w formacie pliku
custom_profiles.json i rejestrowany tylko w pamięci (nic nie trafia do
%LOCALAPPDATA%).
"""

DINO_HOURS = {0: ("05:30", "23:00"), **{wd: ("05:30", "22:45") for wd in range(1, 7)}}

GOLDEN_CUSTOM_PROFILE = {
    "key": "golden_sklep_custom",
    "display_name": "Golden: sklep (profil custom)",
    "roles": [
        {"key": "kasa", "label": "Kasa", "show_summary_row": True, "icon": ""},
        {"key": "dostawa", "label": "Przyjęcie dostawy", "show_summary_row": True, "icon": ""},
        {"key": "student", "label": "Student", "show_summary_row": False, "icon": ""},
    ],
    "rules": [
        {"id": "gold0001", "type": "min_staff_with_role", "role_key": "kasa",
         "policy": "MANDATORY", "weight": 1000, "params": {"min_count": 2, "scope": "any_shift"}},
        {"id": "gold0002", "type": "min_staff_with_role", "role_key": "dostawa",
         "policy": "PREFERRED", "weight": 1000, "params": {"min_count": 1, "scope": "open"}},
        {"id": "gold0003", "type": "role_time_restriction", "role_key": "student",
         "policy": "MANDATORY", "weight": 1000, "params": {"window_start_hour": 6, "window_end_hour": 12}},
    ],
    "enabled_summary_rows": ["open", "close"],
}


def register_golden_profiles():
    """Rejestruje profil custom golden w pamięci (idempotentne)."""
    from model.business_profile import get_custom_profile, register_custom_profile
    from model.custom_profile import CustomBusinessProfile

    if get_custom_profile(GOLDEN_CUSTOM_PROFILE["key"]) is None:
        register_custom_profile(CustomBusinessProfile.from_dict(GOLDEN_CUSTOM_PROFILE))


def _dino_team(n, openers=3, meat=3, meat_light=0, no_night=0, no_afternoon=0, location=None, fraction=None):
    team = []
    for i in range(n):
        emp = {"name": f"D{i:02d}", "opener": i < openers, "meat": i >= n - meat}
        if meat_light and not emp["meat"] and i >= n - meat - meat_light:
            emp["meat_light"] = True
        if i < no_night:
            emp["no_night"] = True
        if no_afternoon and n - meat - meat_light - no_afternoon <= i < n - meat - meat_light:
            emp["no_afternoon"] = True
        if location:
            emp["location"] = location
            emp["name"] = f"{location}{i:02d}"
        if fraction and i in fraction:
            emp["fraction"] = fraction[i]
        team.append(emp)
    return team


def _och(n, location, nie_chce=(), umowa=(), prefix=None):
    return [
        {
            "name": f"{prefix or location}{i:02d}",
            "location": location,
            "roles": {
                **({"nie_chce_24h": True} if i in nie_chce else {}),
                **({"umowa": True} if i in umowa else {}),
            },
        }
        for i in range(n)
    ]


DINO_CASES = [
    {
        "name": "dino_01_basic_2026_10",
        "profile": "dino", "year": 2026, "month": 10,
        "locations": [{"key": "glowna", "open_hours": DINO_HOURS}],
        "employees": _dino_team(10, openers=3, meat=3),
    },
    {
        "name": "dino_02_december_trade_sundays",
        "profile": "dino", "year": 2026, "month": 12,
        "trade_sundays": [13, 20],
        "locations": [{"key": "glowna", "open_hours": DINO_HOURS}],
        "employees": _dino_team(10, openers=3, meat=3, no_night=1),
    },
    {
        "name": "dino_03_november_leaves_sick",
        "profile": "dino", "year": 2026, "month": 11,
        "locations": [{"key": "glowna", "open_hours": DINO_HOURS}],
        "employees": _dino_team(10, openers=3, meat=3),
        "cells": [(0, 3, "leave"), (0, 4, "leave"), (0, 5, "leave"), (4, 16, "sick"), (4, 17, "sick"),
                  (7, 23, "leave"), (9, 9, "off")],
    },
    {
        "name": "dino_04_manager",
        "profile": "dino", "year": 2027, "month": 1,
        "locations": [{"key": "glowna", "open_hours": DINO_HOURS}],
        "employees": [{"name": "Kierowniczka", "manager": True, "opener": True, "fraction": 1.01}]
                     + _dino_team(9, openers=2, meat=3),
    },
    {
        "name": "dino_05_meat_light",
        "profile": "dino", "year": 2026, "month": 10,
        "locations": [{"key": "glowna", "open_hours": ("06:00", "22:00")}],
        "constraints": {"min_open_staff": 2, "min_close_staff": 2},
        "employees": _dino_team(8, openers=2, meat=2, meat_light=2),
    },
    {
        "name": "dino_06_no_night_no_afternoon",
        "profile": "dino", "year": 2026, "month": 9,
        "locations": [{"key": "glowna", "open_hours": DINO_HOURS}],
        "employees": _dino_team(10, openers=3, meat=3, no_night=2, no_afternoon=2),
    },
    {
        "name": "dino_07_part_time",
        "profile": "dino", "year": 2026, "month": 10,
        "locations": [{"key": "glowna", "open_hours": ("06:00", "22:00")}],
        "constraints": {"min_open_staff": 2, "min_close_staff": 2},
        "employees": _dino_team(9, openers=3, meat=3, fraction={1: 0.5, 4: 0.75, 6: 0.5}),
    },
    {
        "name": "dino_08_feb_leap_manual_classes",
        "profile": "dino", "year": 2028, "month": 2,
        "locations": [{"key": "glowna", "open_hours": ("06:00", "22:00")}],
        "constraints": {"min_open_staff": 2, "min_close_staff": 2},
        "employees": _dino_team(8, openers=3, meat=3),
        "cells": [(0, 2, "hours", "06:00", "14:30"), (1, 3, "class", "1"), (2, 3, "class", "2"),
                  (2, 10, "hours", "13:30", "22:00"), (5, 14, "off"), (6, 20, "class", "2")],
    },
    {
        "name": "dino_09_prev_month_memory",
        "profile": "dino", "year": 2026, "month": 11,
        "locations": [{"key": "glowna", "open_hours": DINO_HOURS}],
        "employees": _dino_team(9, openers=3, meat=3),
        "prev_month": {"0": ("22:45", False), "1": ("22:45", False), "4": ("14:00", False)},
    },
    {
        "name": "dino_10_policies_strict",
        "profile": "dino", "year": 2026, "month": 10,
        "locations": [{"key": "glowna", "open_hours": ("06:00", "22:00")}],
        "constraints": {"min_open_staff": 2, "min_close_staff": 2},
        "policies": {"meat": "MANDATORY", "meat_coverage": "MANDATORY", "max_consecutive": "MANDATORY",
                     "no_night": "MANDATORY", "no_afternoon": "MANDATORY"},
        "employees": _dino_team(9, openers=3, meat=4, no_night=1, no_afternoon=1),
    },
    {
        "name": "dino_11_rest_simplified",
        "profile": "dino", "year": 2027, "month": 2,
        "locations": [{"key": "glowna", "open_hours": DINO_HOURS}],
        "constraints": {"rest_11h_mode": "simplified"},
        "employees": _dino_team(10, openers=3, meat=3),
    },
    {
        "name": "dino_12_small_team",
        "profile": "dino", "year": 2026, "month": 4,
        "locations": [{"key": "glowna", "open_hours": ("07:00", "21:00")}],
        "constraints": {"min_open_staff": 2, "min_close_staff": 2, "max_consecutive_days": 5},
        "employees": _dino_team(6, openers=2, meat=2),
    },
    {
        "name": "dino_13_multiloc",
        "profile": "dino", "year": 2026, "month": 10,
        "locations": [{"key": "A", "open_hours": ("06:00", "22:00")}, {"key": "B", "open_hours": ("07:00", "21:00")}],
        "constraints": {"min_open_staff": 2, "min_close_staff": 2},
        "employees": _dino_team(6, openers=2, meat=2, location="A") + _dino_team(6, openers=2, meat=2, location="B"),
    },
    {
        "name": "dino_14_availability_overrides",
        "profile": "dino", "year": 2026, "month": 12,
        "locations": [{"key": "glowna", "open_hours": ("06:00", "22:00"),
                       "day_overrides": {"8": ["08:00", "14:00"], "24": ["06:00", "14:00"]},
                       "trade_sundays": [20]}],
        "constraints": {"min_open_staff": 2, "min_close_staff": 2},
        "employees": [
            {**emp, "availability": {0: [{"start": "06:00", "end": "15:00", "mode": "hard"}]}} if i == 2 else emp
            for i, emp in enumerate(_dino_team(9, openers=3, meat=3))
        ],
    },
]

OCHRONA_CASES = [
    {
        "name": "och_01_duty_24h",
        "profile": "ochrona", "year": 2026, "month": 10,
        "locations": [{"key": "pge", "duty": ("08:00", "20:00", True)}],
        "employees": _och(4, "pge", umowa=(0, 1)),
    },
    {
        "name": "och_02_duty_split_no24h",
        "profile": "ochrona", "year": 2026, "month": 11,
        "locations": [{"key": "ubojnia", "duty": ("08:00", "20:00", False)}],
        "employees": _och(6, "ubojnia", nie_chce=(0, 1, 2), umowa=(3,)),
    },
    {
        "name": "och_03_duty_leaves_manual",
        "profile": "ochrona", "year": 2026, "month": 12,
        "locations": [{"key": "o", "duty": ("07:00", "15:00", False), "closed_on_public_holidays": True}],
        "employees": _och(5, "o", nie_chce=(4,), umowa=(0, 2)),
        "cells": [(0, 5, "leave"), (0, 6, "leave"), (1, 12, "sick"), (2, 3, "hours", "07:00", "15:00"),
                  (3, 18, "full_day", "07:00"), (1, 20, "hours", "10:00", "19:00"), (4, 27, "class", "W")],
    },
    {
        "name": "och_04_regular_gzuk",
        "profile": "ochrona", "year": 2026, "month": 10,
        "locations": [{"key": "gzuk", "open_hours": {**{wd: ("15:00", "07:00") for wd in range(5)},
                                                      5: ("00:00", "23:45"), 6: ("00:00", "23:45")}}],
        "employees": _och(5, "gzuk", nie_chce=(0,), umowa=(1, 2)),
    },
    {
        "name": "och_05_regular_preferred_shifts",
        "profile": "ochrona", "year": 2027, "month": 1,
        "locations": [{"key": "brico", "open_hours": ("07:00", "22:00"), "preferred_shifts_enabled": True,
                       "preferred_shifts": [{"start": "07:00", "end": "15:00"}, {"start": "15:00", "end": "22:00"}]}],
        "employees": _och(4, "brico", umowa=(0,)),
    },
    {
        "name": "och_06_multiloc_mixed",
        "profile": "ochrona", "year": 2026, "month": 11,
        "locations": [
            {"key": "gzuk", "duty": ("07:00", "15:00", False), "closed_on_public_holidays": True},
            {"key": "pge", "duty": ("08:00", "20:00", True)},
            {"key": "biuro", "open_hours": ("08:00", "16:00")},
        ],
        "employees": _och(4, "gzuk", nie_chce=(1,)) + _och(4, "pge", umowa=(0,)) + _och(2, "biuro"),
    },
    {
        "name": "och_07_max_staff_two",
        "profile": "ochrona", "year": 2026, "month": 10,
        "locations": [{"key": "p", "open_hours": ("06:00", "22:00"), "constraints": {"max_staff_at_once": 2}}],
        "employees": _och(5, "p", umowa=(0, 1, 2)),
    },
    {
        "name": "och_08_regular_doba_weekend_prev_month",
        "profile": "ochrona", "year": 2027, "month": 2,
        "locations": [{"key": "p", "open_hours": {**{wd: ("08:00", "16:00") for wd in range(5)},
                                                   5: ("00:00", "23:45"), 6: ("00:00", "23:45")}}],
        "employees": _och(5, "p", nie_chce=(2,)),
        "prev_month": {"0": ("23:00", False), "1": ("08:00", True)},
    },
    {
        "name": "och_09_policies_strict",
        "profile": "ochrona", "year": 2026, "month": 9,
        "locations": [{"key": "o", "duty": ("06:00", "18:00", True)}],
        "policies": {"max_consecutive": "MANDATORY", "hours_equalization": "PREFERRED"},
        "employees": _och(5, "o", nie_chce=(0, 1), umowa=(2,)),
    },
    {
        "name": "och_10_client_data",
        "project_file": "test_data/dane_klienta_ochrona.json", "year": 2026, "month": 10,
        "time_limit": 60,
    },
]

CUSTOM_CASES = [
    {
        "name": "custom_01_min_staff_role",
        "profile": GOLDEN_CUSTOM_PROFILE["key"], "year": 2026, "month": 10,
        "locations": [{"key": "s", "open_hours": ("07:00", "21:00")}],
        "employees": [
            {"name": f"C{i:02d}", "location": "s",
             "roles": {"kasa": i < 5, "dostawa": i in (2, 6), "student": i in (7, 8)}}
            for i in range(9)
        ],
    },
    {
        "name": "custom_02_rule_override_per_location",
        "profile": GOLDEN_CUSTOM_PROFILE["key"], "year": 2026, "month": 11,
        "locations": [
            {"key": "a", "open_hours": ("07:00", "21:00"), "constraints": {"rule:gold0001": 1}},
            {"key": "b", "open_hours": ("08:00", "20:00")},
        ],
        "employees": [
            {"name": f"A{i:02d}", "location": "a", "roles": {"kasa": i < 3, "dostawa": i == 3, "student": i == 4}}
            for i in range(6)
        ] + [
            {"name": f"B{i:02d}", "location": "b", "roles": {"kasa": i < 4, "dostawa": i == 0}}
            for i in range(6)
        ],
        "cells": [(0, 10, "leave"), (6, 15, "sick")],
    },
]

GOLDEN_CASES = DINO_CASES + OCHRONA_CASES + CUSTOM_CASES
