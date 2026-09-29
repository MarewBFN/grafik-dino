"""Harness audytu generatora: konfiguracja -> generate -> validate -> record.

Buduje projekt (ShopConfig + MonthSchedule) z prostego słownika `spec`
dokładnie tymi polami, które ustawia GUI (Konfiguracja, Lokalizacje,
Pracownik, komórki grafiku, nagłówek dnia), uruchamia prawdziwy
AutoScheduleGenerator przez ScheduleController.generate_schedule() (ta sama
ścieżka co przycisk "Generuj grafik") i sprawdza wynik niezależnym
walidatorem (tests/schedule_validator.py).

Uruchomienie kampanii: python tests/generator_audit_harness.py [--quick]
"""

import contextlib
import copy
import io
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model.business_profile import DEFAULT_OCHRONA_PROFILE_KEY, get_custom_profile  # noqa: E402
from model.constraint_policy import ConstraintPolicy  # noqa: E402
from model.employee import Employee  # noqa: E402
from model.location import LocationConfig, normalize_duty_rotation  # noqa: E402
from model.month_schedule import MonthSchedule  # noqa: E402
from model.shop_config import ShopConfig  # noqa: E402
from tests.schedule_validator import evaluate, validate  # noqa: E402

DINO_DEFAULT_HOURS = {0: ("05:30", "23:00"), **{wd: ("05:30", "22:45") for wd in range(1, 7)}}


def duty_rotation_from_editor(start, split, prefer_24h=False):
    """Dokładnie to, co zapisuje ui/duty_rotation_editor.py::get_duty_rotation()."""
    return normalize_duty_rotation({
        "weekend_half_a": {"start": start, "end": split},
        "weekend_half_b": {"start": split, "end": start},
        "weekend_full": {"start": start},
        "only_12_24h": True,
        "prefer_24h": prefer_24h,
    })


def _build_from_project_file(spec):
    """Prawdziwy projekt z pliku (np. dane klienta) jako projekt Ochrony -
    dokładnie to, co robi wersja Enyo po zapisie okna Konfiguracja
    (profil przełączany na jedyny widoczny: Ochrona)."""
    from persistence.project_io import load_project

    schedule, shop = load_project(ROOT / spec["project_file"])
    if spec.get("as_ochrona", True):
        from logic.generator.custom_profile_wiring import default_policies
        shop.business_type = DEFAULT_OCHRONA_PROFILE_KEY
        for key, policy in default_policies(get_custom_profile(DEFAULT_OCHRONA_PROFILE_KEY)).items():
            shop.constraint_policies.setdefault(key, policy)
    if "year" in spec:
        shop.reset_for_new_month(spec["year"], spec["month"])
        fresh = MonthSchedule(spec["year"], spec["month"])
        for emp in schedule.employees:
            fresh.add_employee(emp)
        schedule = fresh
    shop.constraints.update(spec.get("constraints", {}))
    for name, value in spec.get("policies", {}).items():
        shop.constraint_policies[name] = ConstraintPolicy(value)
    employees = schedule.employees
    for cell in spec.get("cells", []):
        idx, day, kind = cell[0], cell[1], cell[2]
        ds = schedule.get_day(employees[idx % len(employees)], day)
        if kind == "leave":
            ds.set_leave()
        elif kind == "sick":
            ds.set_sick()
        ds.is_locked = True
    return schedule, shop


def build_case(spec):
    if "project_file" in spec:
        return _build_from_project_file(spec)
    year, month = spec.get("year", 2026), spec.get("month", 10)
    shop = ShopConfig(year, month)
    profile = spec.get("profile", "dino")

    if profile == "ochrona":
        # dokładnie to, co robi GUI przy tworzeniu nowego projektu Ochrony
        from logic.generator.custom_profile_wiring import apply_new_project_defaults
        shop.business_type = DEFAULT_OCHRONA_PROFILE_KEY
        apply_new_project_defaults(shop, get_custom_profile(DEFAULT_OCHRONA_PROFILE_KEY))
    elif profile != "dino":
        # zarejestrowany wcześniej profil custom (klucz)
        from logic.generator.custom_profile_wiring import default_policies
        shop.business_type = profile
        shop.constraint_policies.update(default_policies(get_custom_profile(profile)))

    shop.constraints.update(spec.get("constraints", {}))
    if "standard_daily_hours" in spec:
        shop.standard_daily_hours = spec["standard_daily_hours"]
    for name, value in spec.get("policies", {}).items():
        shop.constraint_policies[name] = ConstraintPolicy(value)
    shop.trade_sundays = set(spec.get("trade_sundays", []))
    shop.public_holidays = set(spec.get("public_holidays", []))

    locations = {}
    for loc_spec in spec.get("locations", [{"key": "glowna"}]):
        loc = LocationConfig(key=loc_spec["key"], name=loc_spec.get("name", loc_spec["key"]))
        hours = loc_spec.get("open_hours", DINO_DEFAULT_HOURS)
        if isinstance(hours, tuple):
            hours = {wd: hours for wd in range(7)}
        loc.open_hours = dict(hours)
        if "duty" in loc_spec:
            loc.set_24_7(True)
            start, split, prefer = loc_spec["duty"]
            loc.duty_rotation = duty_rotation_from_editor(start, split, prefer)
            loc.closed_on_public_holidays = loc_spec.get("closed_on_public_holidays", False)
        elif "duty_raw" in loc_spec:
            loc.set_24_7(True)
            loc.duty_rotation = normalize_duty_rotation(loc_spec["duty_raw"])
            loc.closed_on_public_holidays = loc_spec.get("closed_on_public_holidays", False)
        else:
            loc.closed_on_public_holidays = loc_spec.get("closed_on_public_holidays", True)
        # Zgodnie z ui/config_dialog.py::_save() (naprawa DINO_REGRESSION_
        # AUDIT.md punkt 2): "Niedziele handlowe" bez własnego wpisu per
        # placówka dziedziczy z pola projektowego, bo tam faktycznie zapisuje
        # je UI, gdy nie edytuje się konkretnej placówki.
        loc.trade_sundays = set(loc_spec.get("trade_sundays", spec.get("trade_sundays", [])))
        loc.public_holidays = set(loc_spec.get("public_holidays", []))
        loc.day_overrides = {int(d): tuple(v) for d, v in loc_spec.get("day_overrides", {}).items()}
        loc.constraints.update(loc_spec.get("constraints", {}))
        # Tryby zasad tej placówki (ustawienia zaawansowane są per placówka).
        for name, value in loc_spec.get("policies", {}).items():
            loc.constraint_policies[name] = ConstraintPolicy(value)
        loc.preferred_shifts_enabled = loc_spec.get("preferred_shifts_enabled", False)
        loc.preferred_shifts = list(loc_spec.get("preferred_shifts", []))
        locations[loc.key] = loc
    shop.locations = locations

    schedule = MonthSchedule(year, month)
    employees = []
    default_loc = next(iter(locations))
    for i, emp_spec in enumerate(spec.get("employees", [])):
        emp = Employee(
            last_name=emp_spec.get("name", f"P{i:02d}"),
            first_name="",
            is_opener=emp_spec.get("opener", False),
            is_meat=emp_spec.get("meat", False),
            is_meat_light=emp_spec.get("meat_light", False),
            is_manager=emp_spec.get("manager", False),
            no_night=emp_spec.get("no_night", False),
            no_afternoon=emp_spec.get("no_afternoon", False),
            employment_fraction=emp_spec.get("fraction", 1.0),
            custom_roles=dict(emp_spec.get("roles", {})),
            location_key=emp_spec.get("location", default_loc),
            availability=emp_spec.get("availability", {}),
        )
        schedule.add_employee(emp)
        employees.append(emp)

    for cell in spec.get("cells", []):
        idx, day, kind = cell[0], cell[1], cell[2]
        emp = employees[idx]
        ds = schedule.get_day(emp, day)
        if kind == "leave":
            ds.set_leave()
            ds.is_locked = True
        elif kind == "sick":
            ds.set_sick()
            ds.is_locked = True
        elif kind == "off":
            ds.set_free()
            ds.is_locked = True
        elif kind == "off_grid":
            # ścieżka ui/grid_view.py "OFF": czyści godziny + is_locked, bez is_day_off
            ds.start = None
            ds.end = None
            ds.is_locked = True
        elif kind == "hours":
            ds.set_hours(cell[3], cell[4])
            ds.is_locked = True
        elif kind == "full_day":
            ds.set_full_day_shift(cell[3])
            ds.is_locked = True
        elif kind == "class":
            ds.set_shift_class(cell[3])
        else:
            raise ValueError(kind)

    for idx, (end, crosses) in spec.get("prev_month", {}).items():
        schedule.set_previous_month_end_shift(employees[int(idx)], end, crosses)

    return schedule, shop


def run_case(spec, time_limit=None, quiet=True):
    from logic.schedule_controller import ScheduleController

    schedule, shop = build_case(spec)
    shop.constraints["solver_time_limit_seconds"] = time_limit or spec.get("time_limit", 10)
    before = schedule.snapshot()
    controller = ScheduleController(schedule, shop)

    buf = io.StringIO()
    started = time.time()
    with contextlib.redirect_stdout(buf) if quiet else contextlib.nullcontext():
        result = controller.generate_schedule(force=True)
    elapsed = time.time() - started

    success = bool(result and result.get("success"))
    report = validate(before, controller.schedule, shop, generation_succeeded=success)
    ev = evaluate(report, shop)
    return {
        "spec": spec,
        "success": success,
        "status": int(result.get("status")) if result else None,
        "reasons": result.get("infeasibility_reasons", []) if result else [],
        "elapsed": round(elapsed, 2),
        "report": report,
        "eval": ev,
        "schedule": controller.schedule,
        "shop": shop,
        "before": before,
    }


def audit_infeasible(spec, time_limit=10):
    """Czy "brak rozwiązania" jest prawdziwy? Uruchamia generator jeszcze raz
    z KAŻDĄ zasadą Wymaganą poluzowaną do Preferowanej i ocenia wynik
    względem ORYGINALNYCH zasad. Zero twardych naruszeń = istniał grafik
    spełniający wszystkie wymagania, a generator zwrócił brak rozwiązania
    (fałszywy "infeasible"). Naruszenia = wynik niejednoznaczny (zwykle
    prawdziwa niewykonalność)."""
    original_schedule, original_shop = build_case(spec)
    relaxed = copy.deepcopy(spec)
    relaxed["name"] = spec.get("name", "case") + "__relaxed"
    policies = dict(relaxed.get("policies", {}))
    for name, value in original_shop.constraint_policies.items():
        if getattr(value, "value", value) == "MANDATORY":
            policies[name] = "PREFERRED"
    relaxed["policies"] = policies
    for loc_spec in relaxed.get("locations", []):
        loc_spec["policies"] = {
            name: "PREFERRED" if value == "MANDATORY" else value
            for name, value in loc_spec.get("policies", {}).items()
        }
    outcome = run_case(relaxed, time_limit=time_limit)
    if not outcome["success"]:
        return {"verdict": "relaxed_also_infeasible"}
    report = validate(outcome["before"], outcome["schedule"], original_shop)
    ev = evaluate(report, original_shop)
    if not ev["hard"]:
        return {"verdict": "FALSE_INFEASIBLE"}
    return {"verdict": "genuine_or_unknown", "violated": sorted({v.rule for v in ev["hard"]})}


def summarize(outcome):
    ev = outcome["eval"]
    return {
        "name": outcome["spec"].get("name"),
        "success": outcome["success"],
        "status": outcome["status"],
        "elapsed": outcome["elapsed"],
        "hard": [v.as_dict() for v in ev["hard"]][:20],
        "hard_count": len(ev["hard"]),
        "soft_count": len(ev["soft"]),
        "soft_rules": sorted({v.rule for v in ev["soft"]}),
        "ignored_rules": sorted({v.rule for v in ev["ignored"]}),
        "input_conflicts": len(ev["input"]),
        "reasons": outcome["reasons"],
        "metrics": {k: v for k, v in outcome["report"].metrics.items() if k != "hours"},
    }


def save_reproducer(outcome, directory):
    from persistence.project_io import save_project

    Path(directory).mkdir(parents=True, exist_ok=True)
    name = outcome["spec"].get("name", "case").replace("/", "_").replace(" ", "_")
    save_project(Path(directory) / f"{name}_input.json", outcome["before"], outcome["shop"])
    save_project(Path(directory) / f"{name}_output.json", outcome["schedule"], outcome["shop"])
    with open(Path(directory) / f"{name}_spec.json", "w", encoding="utf-8") as f:
        json.dump(outcome["spec"], f, indent=2, ensure_ascii=False, default=str)


def dump_schedule(outcome, employees=None, days=None):
    schedule = outcome["schedule"]
    lines = []
    for emp in schedule.employees:
        if employees and emp.last_name not in employees:
            continue
        cells = []
        for day in days or range(1, schedule.days_in_month + 1):
            ds = schedule.get_day(emp, day)
            if ds.is_leave:
                cells.append(f"{day}:URL")
            elif ds.is_sick:
                cells.append(f"{day}:L4")
            elif ds.start:
                cells.append(f"{day}:{ds.start}-{'24h' if ds.is_full_day else ds.end}")
        lines.append(f"{emp.last_name} [{emp.location_key}]: " + " ".join(cells))
    return "\n".join(lines)


# ===========================================================================
# KAMPANIA: rodziny konfiguracji
# ===========================================================================

POLICY_MODES = ("MANDATORY", "PREFERRED", "DISABLED")

DINO_HOURS_SETS = {
    "0530-2245": {0: ("05:30", "23:00"), **{wd: ("05:30", "22:45") for wd in range(1, 7)}},
    "0600-2200": ("06:00", "22:00"),
    "0800-1600": ("08:00", "16:00"),
    "1000-1800": ("10:00", "18:00"),
    "0700-2100": ("07:00", "21:00"),
    "0000-2345": ("00:00", "23:45"),
    "1200-2000": ("12:00", "20:00"),
    "mixed_week": {0: ("06:00", "21:00"), 1: ("06:00", "21:00"), 2: ("07:00", "22:00"), 3: ("06:00", "21:00"),
                   4: ("06:00", "22:00"), 5: ("07:00", "15:00"), 6: (None, None)},
}

DUTY_SPLITS = [
    ("07:00", "15:00"),  # GZUK: 07-15 + 15->07
    ("06:00", "22:00"),  # 06-22 + 22->06 (noc)
    ("08:00", "20:00"),
    ("07:00", "19:00"),
    ("00:00", "12:00"),
    ("05:30", "22:45"),
    ("12:00", "23:45"),
    ("00:00", "08:00"),
    ("22:00", "23:00"),  # 22-23 + 23->22 (1h + 23h)
]

MONTHS = [(2026, 10), (2026, 11), (2026, 12), (2027, 1), (2027, 2), (2028, 2), (2026, 4), (2026, 5), (2026, 9)]


def _dino_team(n, openers=3, meat=3, meat_light=0, no_night=0, no_afternoon=0, location=None):
    team = []
    for i in range(n):
        emp = dict(opener=i < openers, meat=(i >= n - meat) if meat else False)
        if meat_light and not emp["meat"] and i >= n - meat - meat_light:
            emp["meat_light"] = True
        if i < no_night:
            emp["no_night"] = True
        if no_afternoon and n - meat - meat_light - no_afternoon <= i < n - meat - meat_light:
            emp["no_afternoon"] = True
        if location:
            emp["location"] = location
        team.append(emp)
    return team


def family_dino_policies():
    """Każda polityka Dino x MANDATORY/PREFERRED/DISABLED, przy ciasnej i luźnej obsadzie."""
    cases = []
    policies = ["rest_11h", "open", "close", "meat", "meat_coverage", "no_night", "no_afternoon",
                "max_consecutive", "monthly_hours", "balance"]
    for staffing, n in (("tight", 5), ("normal", 8)):
        for policy in policies:
            for mode in POLICY_MODES:
                if policy == "balance" and mode == "MANDATORY":
                    continue
                team = _dino_team(n, openers=2, meat=2, meat_light=1, no_night=1, no_afternoon=1)
                cases.append({
                    "name": f"dino_pol_{staffing}_{policy}_{mode}",
                    "profile": "dino",
                    "locations": [{"key": "glowna", "open_hours": ("06:00", "22:00")}],
                    "constraints": {"min_open_staff": 2, "min_close_staff": 2},
                    "policies": {policy: mode},
                    "employees": team,
                })
    return cases


def family_dino_min_staff():
    cases = []
    for m in range(0, 6):
        for n_delta in (-1, 0, 2, 5):
            n = max(1, 2 * m + n_delta)
            team = _dino_team(n, openers=min(n, max(1, m)), meat=min(n, max(1, m)))
            cases.append({
                "name": f"dino_min_{m}_{n}",
                "profile": "dino",
                "locations": [{"key": "glowna", "open_hours": ("06:00", "22:00")}],
                "constraints": {"min_open_staff": m, "min_close_staff": m},
                "policies": {"max_consecutive": "PREFERRED"},
                "employees": team,
            })
    # asymetryczne
    for mo, mc in ((1, 3), (3, 1), (4, 2), (2, 4)):
        cases.append({
            "name": f"dino_min_asym_{mo}_{mc}",
            "profile": "dino",
            "locations": [{"key": "glowna", "open_hours": ("06:00", "22:00")}],
            "constraints": {"min_open_staff": mo, "min_close_staff": mc},
            "employees": _dino_team(10, openers=4, meat=4),
        })
    return cases


def family_dino_hours():
    cases = []
    for hname, hours in DINO_HOURS_SETS.items():
        for (year, month) in ((2026, 10), (2026, 11), (2026, 12)):
            cases.append({
                "name": f"dino_hours_{hname}_{year}{month:02d}",
                "profile": "dino", "year": year, "month": month,
                "locations": [{"key": "glowna", "open_hours": hours}],
                "constraints": {"min_open_staff": 2, "min_close_staff": 2},
                "employees": _dino_team(9, openers=3, meat=3, no_night=1),
            })
    # nadpisania dni + niedziele handlowe na poziomie lokalizacji i projektu
    cases.append({
        "name": "dino_overrides",
        "profile": "dino", "year": 2026, "month": 12,
        "locations": [{"key": "glowna", "open_hours": ("06:00", "22:00"),
                       "day_overrides": {"7": [None, None], "8": ["08:00", "14:00"], "24": ["06:00", "14:00"]},
                       "trade_sundays": [20]}],
        "constraints": {"min_open_staff": 2, "min_close_staff": 2},
        "employees": _dino_team(9, openers=3, meat=3),
    })
    cases.append({
        "name": "dino_holidays_open",
        "profile": "dino", "year": 2026, "month": 11,
        "locations": [{"key": "glowna", "open_hours": ("06:00", "22:00"), "closed_on_public_holidays": False}],
        "constraints": {"min_open_staff": 2, "min_close_staff": 2},
        "employees": _dino_team(9, openers=3, meat=3),
    })
    return cases


def family_dino_multiloc():
    cases = []
    combos = [
        (("06:00", "22:00"), ("06:00", "22:00")),
        (("06:00", "22:00"), ("08:00", "20:00")),
        (DINO_HOURS_SETS["0530-2245"], ("07:00", "21:00")),
    ]
    for i, (ha, hb) in enumerate(combos):
        for n_each in (5, 7):
            team = _dino_team(n_each, openers=2, meat=2, location="A") + _dino_team(n_each, openers=2, meat=2, location="B")
            cases.append({
                "name": f"dino_multiloc_{i}_{n_each}",
                "profile": "dino",
                "locations": [{"key": "A", "open_hours": ha}, {"key": "B", "open_hours": hb}],
                "constraints": {"min_open_staff": 2, "min_close_staff": 2},
                "employees": team,
            })
    return cases


def family_dino_manual(seed=11):
    rng = random.Random(seed)
    cases = []
    for k in range(12):
        team = _dino_team(8, openers=3, meat=3, no_night=1)
        cells = []
        for _ in range(rng.randint(3, 12)):
            idx, day = rng.randrange(8), rng.randint(1, 31)
            kind = rng.choice(["leave", "sick", "off", "off_grid", "hours_match", "hours_unmatched", "class1", "class2"])
            if kind == "hours_match":
                cells.append((idx, day, "hours", rng.choice(["06:00", "06:30", "07:00"]), rng.choice(["14:30", "15:00", "15:30"])))
            elif kind == "hours_unmatched":
                s = rng.choice(["10:00", "12:00", "13:00", "16:00"])
                cells.append((idx, day, "hours", s, rng.choice(["18:00", "20:00", "21:00", "21:30"])))
            elif kind == "class1":
                cells.append((idx, day, "class", "1"))
            elif kind == "class2":
                cells.append((idx, day, "class", "2"))
            else:
                cells.append((idx, day, kind))
        # unikalne (idx, day)
        seen, uniq = set(), []
        for c in cells:
            if (c[0], c[1]) not in seen and not (c[3:4] and c[3] >= c[4] if c[2] == "hours" else False):
                seen.add((c[0], c[1]))
                uniq.append(c)
        policies = {"rest_11h": "MANDATORY", "max_consecutive": rng.choice(POLICY_MODES)}
        cases.append({
            "name": f"dino_manual_{k}",
            "profile": "dino",
            "locations": [{"key": "glowna", "open_hours": ("06:00", "22:00")}],
            "constraints": {"min_open_staff": 2, "min_close_staff": 2},
            "policies": policies,
            "employees": team,
            "cells": uniq,
        })
    # kierowniczka w różnych godzinach otwarcia
    for hname in ("0530-2245", "0800-1600", "1000-1800"):
        team = _dino_team(8, openers=3, meat=3)
        team[4]["manager"] = True
        team[4]["fraction"] = 1.01
        cases.append({
            "name": f"dino_manager_{hname}",
            "profile": "dino",
            "locations": [{"key": "glowna", "open_hours": DINO_HOURS_SETS[hname]}],
            "constraints": {"min_open_staff": 2, "min_close_staff": 2},
            "employees": team,
        })
    return cases


def family_ochrona(seed=5, count=60):
    rng = random.Random(seed)
    cases = []
    # 1) pełna siatka kształtów rotacji x preferencja
    for start, split in DUTY_SPLITS:
        for prefer in (False, True):
            cases.append({
                "name": f"och_shape_{start}_{split}_{prefer}",
                "profile": "ochrona",
                "locations": [{"key": "o", "duty": (start, split, prefer)}],
                "employees": [dict(location="o") for _ in range(4)],
            })
    # 2) losowe kombinacje
    for k in range(count):
        start, split = rng.choice(DUTY_SPLITS)
        year, month = rng.choice(MONTHS)
        n = rng.randint(2, 7)
        emps = []
        for i in range(n):
            roles = {}
            if rng.random() < 0.3:
                roles["nie_chce_24h"] = True
            if rng.random() < 0.4:
                roles["umowa"] = True
            emps.append(dict(location="o", roles=roles))
        import calendar as _cal
        dim = _cal.monthrange(year, month)[1]
        cells = []
        for _ in range(rng.randint(0, 8)):
            idx, day = rng.randrange(n), rng.randint(1, dim)
            kind = rng.choice(["leave", "sick", "off", "off_grid", "match_a", "match_b", "full", "custom"])
            if kind == "match_a":
                cells.append((idx, day, "hours", start, split))
            elif kind == "match_b":
                cells.append((idx, day, "hours", split, start))
            elif kind == "full":
                cells.append((idx, day, "full_day", start))
            elif kind == "custom":
                s = rng.choice(["06:00", "07:00", "09:00", "10:00", "18:00", "19:00"])
                e = rng.choice(["14:00", "17:00", "19:00", "21:00", "02:00", "07:00"])
                if s != e:
                    cells.append((idx, day, "hours", s, e))
            else:
                cells.append((idx, day, kind))
        seen, uniq = set(), []
        for c in cells:
            if (c[0], c[1]) not in seen:
                seen.add((c[0], c[1]))
                uniq.append(c)
        overrides = {}
        if rng.random() < 0.3:
            overrides[str(rng.randint(1, dim))] = [None, None]
        policies = {
            "rest_11h": rng.choice(POLICY_MODES),
            "max_consecutive": rng.choice(POLICY_MODES),
            "monthly_hours": rng.choice(("PREFERRED", "DISABLED")),
            "hours_equalization": rng.choice(POLICY_MODES),
        }
        prev = {}
        if rng.random() < 0.4:
            prev[str(rng.randrange(n))] = (rng.choice(["07:00", "08:00", "15:00", "20:00", "22:00"]), rng.random() < 0.5)
        cases.append({
            "name": f"och_rand_{k}",
            "profile": "ochrona", "year": year, "month": month,
            "locations": [{"key": "o", "duty": (start, split, rng.random() < 0.5),
                           "closed_on_public_holidays": rng.random() < 0.3,
                           "day_overrides": overrides}],
            "policies": policies,
            "employees": emps,
            "cells": uniq,
            "prev_month": prev,
        })
    return cases


def family_ochrona_policies():
    cases = []
    for policy in ("duty_rotation_coverage", "duty_rotation_no24h", "rest_11h", "max_consecutive", "monthly_hours"):
        for mode in POLICY_MODES:
            for n in (2, 4):
                emps = [dict(location="o", roles={"nie_chce_24h": i % 2 == 0}) for i in range(n)]
                cases.append({
                    "name": f"och_pol_{policy}_{mode}_{n}",
                    "profile": "ochrona",
                    "locations": [{"key": "o", "duty": ("08:00", "20:00", True)}],
                    "policies": {policy: mode},
                    "employees": emps,
                })
    return cases


def family_mixed_ochrona_multiloc():
    cases = []
    for k, closed in enumerate((False, True)):
        cases.append({
            "name": f"och_multiloc_{k}",
            "profile": "ochrona", "year": 2026, "month": 11,
            "locations": [
                {"key": "gzuk", "duty": ("07:00", "15:00", False), "closed_on_public_holidays": closed},
                {"key": "pge", "duty": ("08:00", "20:00", True)},
                {"key": "zwykla", "open_hours": ("08:00", "16:00")},
            ],
            "employees": [dict(location="gzuk") for _ in range(4)] + [dict(location="pge") for _ in range(4)]
                         + [dict(location="zwykla") for _ in range(2)],
        })
    return cases


def family_ochrona_legacy():
    """Starszy schemat rotacji (osobny tydzień: zmiana długa/krótka) - edytor
    już go nie tworzy, ale generator nadal go obsługuje dla starych projektów."""
    cases = []
    schemas = [
        {"weekday_long": {"start": "06:00", "end": "22:00"}, "weekday_short": {"start": "22:00", "end": "06:00"},
         "weekend_half_a": {"start": "06:00", "end": "18:00"}, "weekend_half_b": {"start": "18:00", "end": "06:00"},
         "weekend_full": {"start": "06:00"}},
        {"weekday_long": {"start": "07:00", "end": "23:00"}, "weekday_short": {"start": "23:00", "end": "07:00"},
         "weekend_half_a": {"start": "08:00", "end": "20:00"}, "weekend_half_b": {"start": "20:00", "end": "08:00"},
         "weekend_full": {"start": "08:00"}},
    ]
    for i, raw in enumerate(schemas):
        for n in (3, 5):
            cases.append({
                "name": f"och_legacy_{i}_{n}",
                "profile": "ochrona",
                "locations": [{"key": "o", "duty_raw": raw}],
                "employees": [dict(location="o") for _ in range(n)],
            })
    return cases


OCHRONA_REGULAR_HOURS = {
    "0530-2245": DINO_HOURS_SETS["0530-2245"],
    "0600-2200": ("06:00", "22:00"),
    "0800-1600": ("08:00", "16:00"),
    "1000-1800": ("10:00", "18:00"),
    "0600-2300": ("06:00", "23:00"),
    "0000-2345": ("00:00", "23:45"),
    "doba_weekend": {**{wd: ("08:00", "16:00") for wd in range(5)}, 5: ("00:00", "23:45"), 6: ("00:00", "23:45")},
    "doba_mixed": {0: ("00:00", "23:45"), 1: ("06:00", "22:00"), 2: ("00:00", "23:45"), 3: (None, None),
                   4: ("07:00", "19:00"), 5: ("00:00", "23:45"), 6: ("10:00", "18:00")},
    "0700-1500": ("07:00", "15:00"),
}


def family_ochrona_regular(seed=23, count=45):
    """Placówki Ochrony BEZ rotacji 24/7 (model godzin otwarcia)."""
    rng = random.Random(seed)
    cases = []
    for hname, hours in OCHRONA_REGULAR_HOURS.items():
        for n in (3, 6):
            cases.append({
                "name": f"och_reg_{hname}_{n}",
                "profile": "ochrona",
                "locations": [{"key": "p", "open_hours": hours}],
                "employees": [dict(location="p") for _ in range(n)],
            })
    import calendar as _cal
    for k in range(count):
        hname = rng.choice(list(OCHRONA_REGULAR_HOURS))
        year, month = rng.choice(MONTHS)
        dim = _cal.monthrange(year, month)[1]
        n = rng.randint(2, 8)
        emps = [dict(location="p", roles={"umowa": True} if rng.random() < 0.4 else {},
                     fraction=rng.choice((1.0, 1.0, 1.0, 0.5, 0.75))) for _ in range(n)]
        cells = []
        for _ in range(rng.randint(0, 10)):
            idx, day = rng.randrange(n), rng.randint(1, dim)
            kind = rng.choice(["leave", "sick", "off", "off_grid", "hours", "hours", "night", "class1", "class2"])
            if kind == "hours":
                s = rng.choice(["06:00", "07:00", "08:00", "12:00", "14:00", "16:00"])
                e = rng.choice(["14:00", "15:00", "16:00", "20:00", "22:00", "23:00"])
                if s < e:
                    cells.append((idx, day, "hours", s, e))
            elif kind == "night":
                cells.append((idx, day, "hours", "22:00", "06:00"))
            elif kind == "class1":
                cells.append((idx, day, "class", "1"))
            elif kind == "class2":
                cells.append((idx, day, "class", "2"))
            else:
                cells.append((idx, day, kind))
        seen, uniq = set(), []
        for c in cells:
            if (c[0], c[1]) not in seen:
                seen.add((c[0], c[1]))
                uniq.append(c)
        overrides = {}
        if rng.random() < 0.3:
            overrides[str(rng.randint(1, dim))] = [None, None]
        if rng.random() < 0.3:
            overrides[str(rng.randint(1, dim))] = ["09:00", "13:00"]
        policies = {
            "rest_11h": rng.choice(POLICY_MODES),
            "max_consecutive": rng.choice(POLICY_MODES),
            "opening_hours_coverage": rng.choice(("MANDATORY", "MANDATORY", "PREFERRED", "DISABLED")),
            "monthly_hours": rng.choice(("PREFERRED", "DISABLED")),
        }
        constraints = {}
        if rng.random() < 0.3:
            constraints["force_fulltime_845"] = True  # istniejący projekt sprzed zmiany
        prev = {}
        if rng.random() < 0.4:
            prev[str(rng.randrange(n))] = (rng.choice(["20:00", "22:00", "23:00", "06:00"]), rng.random() < 0.5)
        cases.append({
            "name": f"och_reg_rand_{k}",
            "profile": "ochrona", "year": year, "month": month,
            "locations": [{"key": "p", "open_hours": OCHRONA_REGULAR_HOURS[hname],
                           "closed_on_public_holidays": rng.random() < 0.7,
                           "day_overrides": overrides}],
            "policies": policies,
            "constraints": constraints,
            "employees": emps,
            "cells": uniq,
            "prev_month": prev,
        })
    # placówka rotacji + placówka z godzinami w jednym projekcie
    cases.append({
        "name": "och_reg_with_duty",
        "profile": "ochrona", "year": 2026, "month": 11,
        "locations": [{"key": "d", "duty": ("07:00", "19:00", False)},
                      {"key": "p", "open_hours": OCHRONA_REGULAR_HOURS["doba_weekend"]}],
        "employees": [dict(location="d") for _ in range(4)] + [dict(location="p") for _ in range(6)],
    })
    return cases


WEIRD_HOURS = {
    "gzuk": {**{wd: ("15:00", "07:00") for wd in range(5)}, 5: ("00:00", "23:45"), 6: ("00:00", "23:45")},
    "2200-0600": ("22:00", "06:00"),
    "1800-0600": ("18:00", "06:00"),
    "2300-0700": ("23:00", "07:00"),
    "1500-0700": ("15:00", "07:00"),
    "0000-0000": ("00:00", "00:00"),
    "0700-0700": ("07:00", "07:00"),
    "noc_tydzien_dzien_weekend": {**{wd: ("20:00", "08:00") for wd in range(5)}, 5: ("08:00", "20:00"), 6: ("08:00", "20:00")},
    "rano_tydzien_doba_weekend": {**{wd: ("06:00", "14:00") for wd in range(5)}, 5: ("00:00", "23:45"), 6: ("00:00", "23:45")},
    "doba_pt_do_pn": {**{wd: ("16:00", "08:00") for wd in range(4)}, 4: ("00:00", "23:45"), 5: ("00:00", "23:45"), 6: ("00:00", "23:45")},
    "mieszane_przez_polnoc": {0: ("22:00", "06:00"), 1: ("15:00", "07:00"), 2: (None, None), 3: ("00:00", "23:45"),
                              4: ("18:00", "02:00"), 5: ("00:00", "23:45"), 6: ("10:00", "04:00")},
}


def family_weird_hours(seed=31, count=70):
    """Placówki Ochrony z godzinami przez północ i dobą 24h obok nocek (GZUK,
    zgłoszenie użytkownika 2026-09-28): obłożenie kwadrans po kwadransie,
    „Maks. obsada naraz”, „Nie chce 24h”, typy zmian, ręczne wpisy, pamięć
    poprzedniego miesiąca, święta, profil klienta (inny klucz niż
    custom_ochrona, ta sama rola „Nie chce 24h”)."""
    from demo.install_client_sample_data import build_profile
    from model.business_profile import register_custom_profile

    client = build_profile()
    register_custom_profile(client)
    rng = random.Random(seed)
    cases = []
    for hname, hours in WEIRD_HOURS.items():
        for n in (4, 6):
            cases.append({
                "name": f"weird_{hname}_{n}",
                "profile": "ochrona",
                "locations": [{"key": "p", "open_hours": hours}],
                "employees": [dict(location="p") for _ in range(n)],
            })
    import calendar as _cal
    for k in range(count):
        hname = rng.choice(list(WEIRD_HOURS))
        year, month = rng.choice(MONTHS)
        dim = _cal.monthrange(year, month)[1]
        n = rng.randint(3, 8)
        emps = []
        for _ in range(n):
            roles = {}
            if rng.random() < 0.3:
                roles["umowa"] = True
            if rng.random() < 0.25:
                roles["nie_chce_24h"] = True
            emps.append(dict(location="p", roles=roles, fraction=rng.choice((1.0, 1.0, 0.5, 0.75)),
                             no_night=rng.random() < 0.08, no_afternoon=rng.random() < 0.05))
        cells = []
        for _ in range(rng.randint(0, 10)):
            idx, day = rng.randrange(n), rng.randint(1, dim)
            kind = rng.choice(["leave", "sick", "off", "off_grid", "hours", "hours", "full_day", "W", "class1", "class2"])
            if kind == "hours":
                s_, e_ = rng.choice([("15:00", "23:00"), ("23:00", "07:00"), ("07:00", "19:00"), ("19:00", "07:00"),
                                     ("15:00", "07:00"), ("22:00", "06:00"), ("08:00", "16:00")])
                cells.append((idx, day, "hours", s_, e_))
            elif kind == "full_day":
                cells.append((idx, day, "full_day", rng.choice(["07:00", "00:00", "08:00"])))
            elif kind == "W":
                cells.append((idx, day, "class", "W"))
            elif kind == "class1":
                cells.append((idx, day, "class", "1"))
            elif kind == "class2":
                cells.append((idx, day, "class", "2"))
            else:
                cells.append((idx, day, kind))
        seen, uniq = set(), []
        for c in cells:
            if (c[0], c[1]) not in seen:
                seen.add((c[0], c[1]))
                uniq.append(c)
        overrides = {}
        if rng.random() < 0.25:
            overrides[str(rng.randint(1, dim))] = [None, None]
        if rng.random() < 0.25:
            overrides[str(rng.randint(1, dim))] = rng.choice([["00:00", "23:45"], ["18:00", "06:00"], ["09:00", "13:00"]])
        policies = {
            "rest_11h": rng.choice(("MANDATORY", "MANDATORY", "PREFERRED")),
            "max_consecutive": rng.choice(POLICY_MODES),
            "opening_hours_coverage": rng.choice(("MANDATORY", "MANDATORY", "PREFERRED", "DISABLED")),
            "max_staff_at_once": rng.choice(POLICY_MODES),
            "monthly_hours": rng.choice(("PREFERRED", "DISABLED", "DISABLED")),
            "duty_rotation_no24h": rng.choice(("MANDATORY", "MANDATORY", "PREFERRED")),
            "no_night": rng.choice(("MANDATORY", "PREFERRED")),
        }
        constraints = {"max_staff_at_once": rng.choice((1, 1, 1, 2))}
        if rng.random() < 0.3:
            constraints["rest_11h_mode"] = "simplified"
        prev = {}
        if rng.random() < 0.4:
            prev[str(rng.randrange(n))] = (rng.choice(["07:00", "06:00", "23:00", "08:00"]), rng.random() < 0.6)
        cases.append({
            "name": f"weird_rand_{k}",
            "profile": rng.choice(("ochrona", "ochrona", client.key)),
            "year": year, "month": month,
            "time_limit": 20,
            "locations": [{"key": "p", "open_hours": WEIRD_HOURS[hname],
                           "closed_on_public_holidays": rng.random() < 0.5,
                           "day_overrides": overrides}],
            "policies": policies,
            "constraints": constraints,
            "employees": emps,
            "cells": uniq,
            "prev_month": prev,
        })
    return cases


def family_rest_modes():
    """Tryb liczenia odpoczynku 11h (Konfiguracja -> Zasady generatora):
    standardowy i uproszczony, dla Dino i placówki Ochrony bez rotacji."""
    cases = []
    for mode in ("standard", "simplified"):
        for hname in ("0600-2200", "0800-1600", "mixed_week"):
            cases.append({
                "name": f"dino_rest_{mode}_{hname}",
                "profile": "dino",
                "locations": [{"key": "glowna", "open_hours": DINO_HOURS_SETS[hname]}],
                "constraints": {"min_open_staff": 2, "min_close_staff": 2, "rest_11h_mode": mode},
                "employees": _dino_team(7, openers=3, meat=3),
                "prev_month": {"0": ("23:00", False), "1": ("02:00", True)},
            })
        for hname in ("0600-2300", "doba_mixed"):
            cases.append({
                "name": f"och_rest_{mode}_{hname}",
                "profile": "ochrona",
                "locations": [{"key": "p", "open_hours": OCHRONA_REGULAR_HOURS[hname]}],
                "constraints": {"rest_11h_mode": mode},
                "employees": [dict(location="p") for _ in range(6)],
                "prev_month": {"0": ("23:00", False), "1": ("02:00", True)},
            })
    return cases


def family_ochrona_client(seed=77):
    """Dane klienta (6 placówek, 25 osób) jako projekt Ochrony, kilka
    miesięcy (święta: listopad/grudzień/styczeń), z losowymi urlopami/L4."""
    rng = random.Random(seed)
    cases = []
    for year, month in ((2026, 10), (2026, 11), (2026, 12), (2027, 1), (2027, 2)):
        for variant in ("plain", "leaves", "balance_preferred"):
            spec = {"name": f"och_client_{year}{month:02d}_{variant}",
                    "project_file": "test_data/dane_klienta_ochrona.json", "year": year, "month": month,
                    "time_limit": 30}
            if variant == "leaves":
                spec["cells"] = [(rng.randrange(25), rng.randint(1, 28), rng.choice(("leave", "sick"))) for _ in range(12)]
            if variant == "balance_preferred":
                spec["policies"] = {"balance": "PREFERRED", "monthly_hours": "PREFERRED"}
            cases.append(spec)
    return cases


FAMILIES = {
    "weird_hours": family_weird_hours,
    "ochrona_client": family_ochrona_client,
    "ochrona_final": lambda: [dict(c, name=c["name"].replace("och_", "ochF_")) for c in family_ochrona(seed=101, count=80)],
    "ochrona_regular_final": lambda: [dict(c, name=c["name"].replace("och_", "ochF_")) for c in family_ochrona_regular(seed=202, count=60)],
    "rest_modes": family_rest_modes,
    "ochrona_regular": family_ochrona_regular,
    "ochrona_legacy": family_ochrona_legacy,
    "dino_policies": family_dino_policies,
    "dino_min_staff": family_dino_min_staff,
    "dino_hours": family_dino_hours,
    "dino_multiloc": family_dino_multiloc,
    "dino_manual": family_dino_manual,
    "ochrona": family_ochrona,
    "ochrona_policies": family_ochrona_policies,
    "ochrona_multiloc": family_mixed_ochrona_multiloc,
}


# ===========================================================================
# TESTY RÓŻNICOWE: zmień jedno ustawienie -> porównaj rzeczywisty wynik
# ===========================================================================

def _open_close_counts(outcome):
    per_day = outcome["report"].metrics.get("open_close_per_day", {})
    opens = [v[0] for day in per_day.values() for v in day.values()]
    closes = [v[1] for day in per_day.values() for v in day.values()]
    return (min(opens, default=None), max(opens, default=None)), (min(closes, default=None), max(closes, default=None))


def _max_streak(outcome):
    from tests.schedule_validator import cell_interval

    schedule = outcome["schedule"]
    best = 0
    for emp in schedule.employees:
        streak = 0
        for day in range(1, schedule.days_in_month + 1):
            streak = streak + 1 if cell_interval(schedule.get_day(emp, day), day) else 0
            best = max(best, streak)
    return best


def _count(outcome, rule):
    return len([v for v in outcome["report"].violations if v.rule == rule and v.source == "generator"])


def differential_cases():
    """(nazwa, [(etykieta, spec)], funkcja pomiaru, funkcja oceny)."""
    dino_base = {
        "profile": "dino",
        "locations": [{"key": "glowna", "open_hours": ("06:00", "22:00")}],
        "employees": _dino_team(10, openers=4, meat=4),
        "policies": {"max_consecutive": "PREFERRED"},
    }
    och_reg = {
        "profile": "ochrona",
        "locations": [{"key": "p", "open_hours": ("06:00", "22:00")}],
        "employees": [dict(location="p") for _ in range(5)],
    }
    och_duty = {
        "profile": "ochrona",
        "employees": [dict(location="o") for _ in range(4)],
    }
    return [
        (
            "A/B: min_open 2 -> 3 (Dino)",
            [("min=2", dict(dino_base, constraints={"min_open_staff": 2, "min_close_staff": 2})),
             ("min=3", dict(dino_base, constraints={"min_open_staff": 3, "min_close_staff": 3}))],
            _open_close_counts,
            lambda r: r[0][1] == ((2, 2), (2, 2)) and r[1][1] == ((3, 3), (3, 3)),
        ),
        (
            "C/D: max_consecutive MANDATORY <-> DISABLED (Ochrona, placówka z godzinami, 3 osoby)",
            [("MANDATORY", dict(och_reg, employees=och_reg["employees"][:3], policies={"max_consecutive": "MANDATORY"})),
             ("DISABLED", dict(och_reg, employees=och_reg["employees"][:3], policies={"max_consecutive": "DISABLED"})),
             ("MANDATORY again", dict(och_reg, employees=och_reg["employees"][:3], policies={"max_consecutive": "MANDATORY"}))],
            _max_streak,
            lambda r: (not r[0][0]["success"] or r[0][1] <= 4) and r[1][1] > 4 and (not r[2][0]["success"] or r[2][1] <= 4),
        ),
        (
            "C/D: obłożenie godzin otwarcia MANDATORY <-> DISABLED (Ochrona, 2 osoby na 16 h)",
            [("MANDATORY", dict(och_reg, employees=och_reg["employees"][:2])),
             ("DISABLED", dict(och_reg, employees=och_reg["employees"][:2], policies={"opening_hours_coverage": "DISABLED"}))],
            lambda o: _count(o, "opening_hours_coverage"),
            lambda r: r[0][1] == 0 and r[1][1] > 0,
        ),
        (
            "C: rest_11h MANDATORY -> DISABLED (Ochrona 24/7, 2 osoby, bez 24 h)",
            [("MANDATORY", dict(och_duty, employees=[dict(location="o", roles={"nie_chce_24h": True}) for _ in range(2)],
                                locations=[{"key": "o", "duty": ("08:00", "20:00", False)}])),
             ("DISABLED", dict(och_duty, employees=[dict(location="o", roles={"nie_chce_24h": True}) for _ in range(2)],
                               locations=[{"key": "o", "duty": ("08:00", "20:00", False)}], policies={"rest_11h": "DISABLED"}))],
            lambda o: (_count(o, "rest_11h"), o["report"].metrics.get("duty_coverage")),
            lambda r: r[0][1][0] == 0,
        ),
        (
            "E: godziny 06:00-22:00 -> rotacja 15:00->07:00 (GZUK) -> 22:00->06:00",
            [("06:00-22:00 (godziny)", och_reg),
             ("07:00/15:00 (15->07)", dict(och_duty, locations=[{"key": "o", "duty": ("07:00", "15:00", False)}])),
             ("06:00/22:00 (22->06)", dict(och_duty, locations=[{"key": "o", "duty": ("06:00", "22:00", False)}]))],
            lambda o: (sorted({(o["schedule"].get_day(e, d).start, o["schedule"].get_day(e, d).end if not o["schedule"].get_day(e, d).is_full_day else "24h")
                               for e in o["schedule"].employees for d in range(1, 8) if o["schedule"].get_day(e, d).start}),
                       o["report"].metrics.get("duty_coverage") or o["report"].metrics.get("opening_coverage")),
            lambda r: all(not o["eval"]["hard"] for o, _m in r),
        ),
        (
            "PREFERRED vs MANDATORY: Preferuj 24h (prefer_24h) off -> on",
            [("prefer_24h=False", dict(och_duty, locations=[{"key": "o", "duty": ("08:00", "20:00", False)}])),
             ("prefer_24h=True", dict(och_duty, locations=[{"key": "o", "duty": ("08:00", "20:00", True)}]))],
            lambda o: sum(1 for e in o["schedule"].employees for d in range(1, o["schedule"].days_in_month + 1)
                          if o["schedule"].get_day(e, d).is_full_day),
            lambda r: r[1][1] > r[0][1],
        ),
    ]


def run_differential(time_limit=10):
    results = []
    for name, variants, measure, judge in differential_cases():
        rows = []
        for label, spec in variants:
            outcome = run_case(dict(spec, name=f"diff_{label}"), time_limit=time_limit)
            rows.append((outcome, measure(outcome)))
        ok = judge(rows)
        results.append((name, ok, [(label, o["success"], m, sorted({v.rule for v in o["eval"]["hard"]}))
                                   for (label, _s), (o, m) in zip(variants, rows)]))
        print(f"[{'OK' if ok else 'FAIL'}] {name}", file=sys.stderr)
        for label, success, m, hard in results[-1][2]:
            print(f"     {label}: success={success} pomiar={m} twarde={hard}", file=sys.stderr)
    return results


def main(argv):
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("families", nargs="*", default=list(FAMILIES))
    parser.add_argument("--out", default="Output/audit")
    parser.add_argument("--time-limit", type=int, default=10)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--audit-infeasible", action="store_true")
    parser.add_argument("--differential", action="store_true")
    parser.add_argument("--only-profile", default=None, help="np. ochrona - pomija przypadki innych profili")
    args = parser.parse_args(argv)

    if args.differential:
        run_differential(time_limit=args.time_limit)
        return

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for family in args.families:
        cases = FAMILIES[family]()
        if args.only_profile:
            cases = [c for c in cases if c.get("profile", "ochrona" if "project_file" in c else "dino") == args.only_profile]
        if args.limit:
            cases = cases[: args.limit]
        path = out / f"{family}.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for spec in cases:
                try:
                    outcome = run_case(spec, time_limit=spec.get("time_limit", args.time_limit))
                except Exception as exc:  # noqa: BLE001 - wynik kampanii ma zapisać każdy wyjątek
                    row = {"name": spec.get("name"), "exception": repr(exc)}
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    f.flush()
                    print(f"[{family}] {spec.get('name')}: EXCEPTION {exc!r}", file=sys.stderr)
                    continue
                row = summarize(outcome)
                if not outcome["success"] and args.audit_infeasible:
                    row["infeasible_audit"] = audit_infeasible(spec, time_limit=args.time_limit)
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                f.flush()
                if row["hard_count"]:
                    save_reproducer(outcome, out / "reproducers")
                print(
                    f"[{family}] {row['name']}: success={row['success']} hard={row['hard_count']} "
                    f"rules={sorted({v['rule'] for v in row['hard']})} soft={row['soft_rules']} t={row['elapsed']}"
                    + (f" infeasible_audit={row['infeasible_audit']}" if "infeasible_audit" in row else ""),
                    file=sys.stderr,
                )


if __name__ == "__main__":
    main(sys.argv[1:])
