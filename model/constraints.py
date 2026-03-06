from dataclasses import dataclass
from typing import List
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig


# ==========================================
# RESULT
# ==========================================

@dataclass
class ConstraintViolation:
    type: str          # np. "max_consecutive_days"
    employee: object   # Employee lub None (jeśli globalne)
    day: int | None
    message: str


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

    def __init__(self, limit: int):
        self.limit = limit

    def apply(self, schedule, shop):
        results = []

        for emp in schedule.employees:
            streak = 0

            for day in range(1, schedule.days_in_month + 1):

                ds = schedule.get_day(emp, day)

                if not ds.is_empty():
                    streak += 1
                else:
                    streak = 0

                if streak > self.limit:
                    results.append(
                        ConstraintViolation(
                            type="max_consecutive_days",
                            employee=emp,
                            day=day,
                            message=f"Więcej niż {self.limit} dni pracy pod rząd"
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

        if "min_open_staff" in cfg:
            rules.append(
                MinStaffRule(cfg["min_open_staff"], "open")
            )

        if "min_close_staff" in cfg:
            rules.append(
                MinStaffRule(cfg["min_close_staff"], "close")
            )

        if cfg.get("enforce_11h_rest", False):
            rules.append(Rest11hRule())

        if cfg.get("enforce_meat_coverage", False):
            rules.append(MeatCoverageRule())

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
            if emp.is_opener:
                has_opener = True

    return {"count": count, "has_opener": has_opener}


# ==================================================
# MIĘSO
# ==================================================
from datetime import datetime

FMT = "%H:%M"


def meat_coverage(schedule, shop, day: int) -> dict:
    """
    Sprawdza czy mięso jest pokryte przez cały dzień.
    Wersja zoptymalizowana – analiza przedziałowa.
    """

    open_hours = shop.get_open_hours_for_day(day)
    if not open_hours:
        return {"ok": True, "gap": None}

    open_t = datetime.strptime(open_hours[0], FMT)
    close_t = datetime.strptime(open_hours[1], FMT)

    intervals = []

    # 🔹 zbierz przedziały tylko dla pracowników z mięsem
    for emp in schedule.employees:
        if not emp.is_meat:
            continue

        ds = schedule.get_day(emp, day)
        if ds.is_empty():
            continue

        start = datetime.strptime(ds.start, FMT)
        end = datetime.strptime(ds.end, FMT)

        # ignorujemy błędne zakresy
        if start >= end:
            continue

        intervals.append((start, end))

    if not intervals:
        return {
            "ok": False,
            "gap": (open_t.strftime(FMT), close_t.strftime(FMT))
        }

    # 🔹 sortujemy po czasie rozpoczęcia
    intervals.sort(key=lambda x: x[0])

    current = open_t

    for start, end in intervals:

        # luka przed kolejnym przedziałem
        if start > current:
            return {
                "ok": False,
                "gap": (current.strftime(FMT), start.strftime(FMT))
            }

        # rozszerzamy pokrycie
        if end > current:
            current = end

        if current >= close_t:
            return {"ok": True, "gap": None}

    # jeśli po przejściu wszystkich nadal nie pokryliśmy
    if current < close_t:
        return {
            "ok": False,
            "gap": (current.strftime(FMT), close_t.strftime(FMT))
        }

    return {"ok": True, "gap": None}


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
    start_next = datetime.strptime(next_day.start, fmt)

    # 🔥 uwzględnij przejście do kolejnego dnia
    start_next += timedelta(days=1)

    rest = start_next - end_today
    hours = rest.total_seconds() / 3600

    return {
        "violation": hours < 11,
        "rest_hours": round(hours, 2)
    }
