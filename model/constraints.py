from dataclasses import dataclass
from typing import List
from model.business_profile import DEFAULT_BUSINESS_TYPE
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from model.constraint_policy import ConstraintPolicy
from model.qualification import is_full_meat_on, is_light_meat_on, is_opener_on


# ==========================================
# RESULT
# ==========================================

@dataclass
class ConstraintViolation:
    type: str          # np. "max_consecutive_days"
    employee: object   # Employee lub None (jeśli globalne)
    day: int | None
    message: str
    # Wiersz podsumowania nad tabelą, który to naruszenie koloruje (np.
    # "role:kasa" dla reguły profilu custom) - None = wg `type`.
    row_key: str | None = None
    # Ostrzeżenie (żółty, zasada Preferowana) zamiast błędu (czerwony).
    warning: bool = False


# ==========================================
# ENGINE
# ==========================================

# ==========================================
# RULE BASE
# ==========================================

class Rule:
    def apply(self, schedule: MonthSchedule, shop: ShopConfig) -> List[ConstraintViolation]:
        raise NotImplementedError


# ==========================================
# RULES
# ==========================================

class MaxConsecutiveDaysRule(Rule):

    def __init__(self, default_limit: int):
        self.default_limit = default_limit

    def apply(self, schedule, shop):
        results = []

        for emp in schedule.employees:
            # Resolve per the employee's location the same way the real
            # generator does (logic/generator/base_specs.py::_build_max_consecutive)
            # - without a location assigned this is just self.default_limit,
            # identical to before per-location overrides existed.
            limit = shop.get_location(emp).constraints.get("max_consecutive_days", self.default_limit)
            streak = 0

            for day in range(1, schedule.days_in_month + 1):

                ds = schedule.get_day(emp, day)

                if not ds.is_empty():
                    streak += 1
                else:
                    streak = 0

                if streak > limit:
                    results.append(
                        ConstraintViolation(
                            type="max_consecutive_days",
                            employee=emp,
                            day=day,
                            message=f"Więcej niż {limit} dni pracy pod rząd"
                        )
                    )

        return results


class MinStaffRule(Rule):

    def __init__(self, minimum: int, mode: str):
        self.minimum = minimum
        self.mode = mode  # "open" | "close"

    def apply(self, schedule, shop):
        results = []

        for day in range(1, schedule.days_in_month + 1):

            stats = opening_closing_stats(schedule, shop, day, self.mode)

            if stats["count"] < self.minimum:

                results.append(
                    ConstraintViolation(
                        type=f"min_{self.mode}_staff",
                        employee=None,
                        day=day,
                        message=(
                            f"Za mało osób na "
                            f"{'otwarciu' if self.mode == 'open' else 'zamknięciu'} "
                            f"(min {self.minimum})"
                        )
                    )
                )

        return results


class Rest11hRule(Rule):

    def apply(self, schedule, shop):
        from datetime import datetime, timedelta

        results = []
        fmt = "%H:%M"

        for emp in schedule.employees:

            for day in range(1, schedule.days_in_month):

                today = schedule.get_day(emp, day)
                next_day = schedule.get_day(emp, day + 1)

                if today.is_empty() or next_day.is_empty():
                    continue

                end_today = datetime.strptime(today.end, fmt)
                if today.crosses_midnight():
                    # Zmiana nocna (plan zmian nocnych) kończy się w
                    # kolejnej dobie kalendarzowej z definicji - bez tego
                    # ta reguła liczyłaby odpoczynek o 24h za dużo i nigdy
                    # nie wykryłaby realnego naruszenia po zmianie nocnej.
                    end_today += timedelta(days=1)
                start_next = datetime.strptime(next_day.start, fmt)
                start_next += timedelta(days=1)

                rest = start_next - end_today
                hours = rest.total_seconds() / 3600

                if hours < 11:
                    results.append(
                        ConstraintViolation(
                            type="rest_11h",
                            employee=emp,
                            day=day + 1,
                            message=f"Przerwa tylko {round(hours,2)}h (min 11h)"
                        )
                    )

        return results


class MeatCoverageRule(Rule):

    def apply(self, schedule, shop):
        results = []

        for day in range(1, schedule.days_in_month + 1):

            result = meat_coverage(schedule, shop, day)

            if not result["ok"]:

                if result["gap"] is None:
                    msg = "Brak mięsa przez cały dzień"
                else:
                    start, end = result["gap"]
                    msg = f"Brak mięsa od {start} do {end}"

                results.append(
                    ConstraintViolation(
                        type="meat_coverage",
                        employee=None,
                        day=day,
                        message=msg
                    )
                )

            elif result["light_ranges"]:
                msg = "; ".join(
                    f"mięsiara tymczasowa między {start} a {end}"
                    for start, end in result["light_ranges"]
                )
                results.append(
                    ConstraintViolation(
                        type="meat_light_coverage",
                        employee=None,
                        day=day,
                        message=msg
                    )
                )

        return results


class CustomStaffRule(Rule):
    """Reguły profilu custom "min. N osób z kwalifikacją X" - ta sama
    definicja co w generatorze (model/staffing_rules.py). Zasada Wymagana -
    błąd, Preferowana - ostrzeżenie, Wyłączona (albo bez wpisu w projekcie,
    jak w generatorze) - pomijana. Koloruje wiersz kwalifikacji "role:<klucz>"."""

    def __init__(self, custom):
        self.custom = custom

    def apply(self, schedule, shop):
        from model.custom_profile import RULE_TYPE_MIN_STAFF_WITH_ROLE
        from model.staffing_rules import check_min_staff

        results = []
        for rule in self.custom.rules:
            if rule.type != RULE_TYPE_MIN_STAFF_WITH_ROLE:
                continue
            rule_key = self.custom.rule_policy_key(rule)
            policy = shop.constraint_policies.get(rule_key)
            if policy not in (ConstraintPolicy.MANDATORY, ConstraintPolicy.PREFERRED):
                continue
            label = self.custom.rule_label(rule)
            for day, detail in check_min_staff(schedule, shop, rule_key, rule.qualification_key, rule.params):
                results.append(ConstraintViolation(
                    type="custom_min_staff",
                    employee=None,
                    day=day,
                    message=f"{label} – {detail}",
                    row_key=f"role:{rule.qualification_key}",
                    warning=policy == ConstraintPolicy.PREFERRED,
                ))
        return results


# ==========================================
# ENGINE
# ==========================================

class ConstraintEngine:

    @staticmethod
    def evaluate(schedule: MonthSchedule,
                 shop: ShopConfig) -> List[ConstraintViolation]:

        cfg = shop.constraints
        rules: List[Rule] = []

        if "max_consecutive_days" in cfg:
            rules.append(
                MaxConsecutiveDaysRule(cfg["max_consecutive_days"])
            )

        if cfg.get("enforce_11h_rest", False):
            rules.append(Rest11hRule())

        # min_open_staff/min_close_staff/meat coverage are dino_retail-only
        # concepts (see logic/generator/dino_retail_profile.py) - shop.constraints
        # always carries min_open_staff/min_close_staff defaults regardless of
        # business_type, so without this guard every custom profile's grid
        # would get validated against Dino's own staffing numbers instead of
        # its actual rules (which live in model.custom_profile.RuleInstance,
        # not shop.constraints - checked below by CustomStaffRule).
        if shop.business_type == DEFAULT_BUSINESS_TYPE:
            if "min_open_staff" in cfg:
                rules.append(
                    MinStaffRule(cfg["min_open_staff"], "open")
                )

            if "min_close_staff" in cfg:
                rules.append(
                    MinStaffRule(cfg["min_close_staff"], "close")
                )

            meat_policy = shop.constraint_policies.get("meat_coverage", ConstraintPolicy.MANDATORY)
            if meat_policy != ConstraintPolicy.DISABLED or cfg.get("enforce_meat_coverage", False):
                rules.append(MeatCoverageRule())

        from model.business_profile import get_custom_profile

        custom = get_custom_profile(shop.business_type)
        if custom is not None:
            rules.append(CustomStaffRule(custom))

        violations: List[ConstraintViolation] = []

        for rule in rules:
            violations.extend(rule.apply(schedule, shop))

        return violations

def opening_closing_stats(
    schedule: MonthSchedule,
    shop: ShopConfig,
    day: int,
    mode: str  # "open" | "close"
) -> dict:
    open_hours = shop.get_open_hours_for_day(day)
    if not open_hours:
        return {"count": 0, "has_opener": False}

    target_time = open_hours[0] if mode == "open" else open_hours[1]

    count = 0
    has_opener = False

    for emp in schedule.employees:
        ds = schedule.get_day(emp, day)
        if ds.is_empty():
            continue

        time = ds.start if mode == "open" else ds.end
        if time == target_time:
            count += 1
            if is_opener_on(emp, schedule.year, schedule.month, day):
                has_opener = True

    return {"count": count, "has_opener": has_opener}


# ==================================================
# MIĘSO
# ==================================================
from datetime import datetime

FMT = "%H:%M"


def _merge_intervals(intervals):
    if not intervals:
        return []
    intervals = sorted(intervals)
    merged = [list(intervals[0])]
    for start, end in intervals[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def _covered_by(intervals, moment) -> bool:
    return any(start <= moment < end for start, end in intervals)


def meat_coverage(schedule, shop, day: int) -> dict:
    """
    Sprawdza czy mięso jest pokryte przez cały dzień.

    Rozróżnia pokrycie przez pełnoprawnych "mięsiarzy" (Mięso poziom 2) od
    pokrycia zastępczego przez osoby z Mięsem na poziomie 1 ("pomocniczo") -
    to drugie liczy się jako pokrycie, ale jest zwracane osobno w
    "light_ranges", żeby UI mogło to zaznaczyć jako ostrzeżenie, nie sukces.
    """

    open_hours = shop.get_open_hours_for_day(day)
    if not open_hours:
        return {"ok": True, "gap": None, "light_ranges": []}

    open_t = datetime.strptime(open_hours[0], FMT)
    close_t = datetime.strptime(open_hours[1], FMT)

    real_intervals = []
    light_intervals = []

    for emp in schedule.employees:
        full_meat = is_full_meat_on(emp, schedule.year, schedule.month, day)
        if not (full_meat or is_light_meat_on(emp, schedule.year, schedule.month, day)):
            continue

        ds = schedule.get_day(emp, day)
        if ds.is_empty():
            continue

        start = datetime.strptime(ds.start, FMT)
        end = datetime.strptime(ds.end, FMT)

        # ignorujemy błędne zakresy
        if start >= end:
            continue

        (real_intervals if full_meat else light_intervals).append((start, end))

    real_merged = _merge_intervals(real_intervals)
    light_merged = _merge_intervals(light_intervals)

    boundaries = {open_t, close_t}
    for start, end in real_merged + light_merged:
        if open_t < start < close_t:
            boundaries.add(start)
        if open_t < end < close_t:
            boundaries.add(end)
    points = sorted(boundaries)

    gap_start = None
    gap = None
    light_start = None
    light_ranges = []

    for seg_start, seg_end in zip(points, points[1:]):
        mid = seg_start + (seg_end - seg_start) / 2
        real_cov = _covered_by(real_merged, mid)
        light_cov = _covered_by(light_merged, mid)

        if not real_cov and not light_cov:
            if gap_start is None:
                gap_start = seg_start
            if light_start is not None:
                light_ranges.append((light_start.strftime(FMT), seg_start.strftime(FMT)))
                light_start = None
            continue

        # segment pokryty - zamykamy ewentualną otwartą lukę
        if gap_start is not None and gap is None:
            gap = (gap_start.strftime(FMT), seg_start.strftime(FMT))

        if not real_cov and light_cov:
            if light_start is None:
                light_start = seg_start
        elif light_start is not None:
            light_ranges.append((light_start.strftime(FMT), seg_start.strftime(FMT)))
            light_start = None

    if gap_start is not None and gap is None:
        gap = (gap_start.strftime(FMT), close_t.strftime(FMT))
    if light_start is not None:
        light_ranges.append((light_start.strftime(FMT), close_t.strftime(FMT)))

    return {"ok": gap is None, "gap": gap, "light_ranges": light_ranges}


def rest_11h_violation(schedule: MonthSchedule, emp, day: int):
    """
    Zwraca:
    {
        "violation": bool,
        "rest_hours": float | None
    }
    """
    if day < 1 or day >= schedule.days_in_month:
        return {"violation": False, "rest_hours": None}

    today = schedule.get_day(emp, day)
    next_day = schedule.get_day(emp, day + 1)

    if today.is_empty() or next_day.is_empty():
        return {"violation": False, "rest_hours": None}

    from datetime import datetime, timedelta

    fmt = "%H:%M"

    end_today = datetime.strptime(today.end, fmt)
    if today.crosses_midnight():
        # Zmiana nocna kończy się w kolejnej dobie kalendarzowej z definicji.
        end_today += timedelta(days=1)
    start_next = datetime.strptime(next_day.start, fmt)

    # 🔥 uwzględnij przejście do kolejnego dnia
    start_next += timedelta(days=1)

    rest = start_next - end_today
    hours = rest.total_seconds() / 3600

    return {
        "violation": hours < 11,
        "rest_hours": round(hours, 2)
    }
