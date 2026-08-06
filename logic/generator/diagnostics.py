"""Repeatable, human-readable diagnostics for the CP-SAT schedule generator.

The solver does not expose a "constraint changed this assignment" event.  This
module therefore solves progressively larger versions of the model and records
the difference between consecutive solutions.  The report deliberately calls
that a *stage impact*, rather than a proof of causality: CP-SAT may have several
equally good schedules.
"""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta
import io
import json
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

from ortools.sat.python import cp_model

from logic.utils.time_utils import get_effective_daily_hours
from model.constraint_policy import ConstraintPolicy


POLICY_STAGES = (
    "open",
    "close",
    "rest_11h",
    "balance",
    "availability",
    "no_night",
    "meat",
    "meat_coverage",
    "max_consecutive",
    "monthly_hours",
)


def _status_name(status: int) -> str:
    return {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.MODEL_INVALID: "MODEL_INVALID",
        cp_model.UNKNOWN: "UNKNOWN",
    }.get(status, str(status))


def _cell_value(day_state: Any) -> str:
    if day_state.is_leave:
        return "LEAVE"
    if getattr(day_state, "is_sick", False):
        return "SICK"
    if getattr(day_state, "is_day_off", False):
        return "DAY_OFF"
    if day_state.start and day_state.end:
        return f"{day_state.start}-{day_state.end}"
    if day_state.is_locked:
        return "LOCKED_OFF"
    return "OFF"


def schedule_snapshot(schedule) -> dict[str, dict[str, str]]:
    """Return an employee/day matrix that is easy to inspect in JSON."""
    return {
        employee.display_name(): {
            str(day): _cell_value(schedule.get_day(employee, day))
            for day in range(1, schedule.days_in_month + 1)
        }
        for employee in schedule.employees
    }


def snapshot_diff(before: dict[str, dict[str, str]] | None, after: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    if before is None:
        return []
    changes = []
    for employee, days in after.items():
        for day, value in days.items():
            old_value = before.get(employee, {}).get(day)
            if old_value != value:
                changes.append({"employee": employee, "day": day, "before": old_value, "after": value})
    return changes


def _minutes_between(end_day: int, end_time: str, next_day: int, next_time: str, year: int, month: int) -> int:
    fmt = "%Y-%m-%d %H:%M"
    end = datetime.strptime(f"{year}-{month:02d}-{end_day:02d} {end_time}", fmt)
    start = datetime.strptime(f"{year}-{month:02d}-{next_day:02d} {next_time}", fmt)
    return int((start - end).total_seconds() // 60)


def audit_schedule(schedule, shop) -> dict[str, Any]:
    """Independently verify the two most failure-prone rules after a solve."""
    nominal_minutes = shop.get_full_time_nominal_hours() * 60
    monthly = []
    rest_violations = []

    for employee in schedule.employees:
        effective_minutes = int(get_effective_daily_hours(employee, shop) * 60)
        leave_or_sick = sum(
            1
            for day in range(1, schedule.days_in_month + 1)
            if (ds := schedule.get_day(employee, day)).is_leave or getattr(ds, "is_sick", False)
        )
        target = int(nominal_minutes * employee.employment_fraction) - leave_or_sick * effective_minutes
        worked = 0
        for day in range(1, schedule.days_in_month + 1):
            duration = schedule.get_day(employee, day).total_duration()
            if duration:
                worked += int(duration.total_seconds() // 60)
        monthly.append({
            "employee": employee.display_name(),
            "worked_minutes": worked,
            "target_minutes": target,
            "difference_minutes": worked - target,
            "leave_or_sick_days": leave_or_sick,
        })

        for day in range(1, schedule.days_in_month):
            today = schedule.get_day(employee, day)
            tomorrow = schedule.get_day(employee, day + 1)
            if not (today.end and tomorrow.start):
                continue
            rest = _minutes_between(day, today.end, day + 1, tomorrow.start, schedule.year, schedule.month)
            if rest < 11 * 60:
                rest_violations.append({
                    "employee": employee.display_name(),
                    "days": f"{day}->{day + 1}",
                    "rest_minutes": rest,
                    "required_minutes": 660,
                    "shifts": f"{today.start}-{today.end} / {tomorrow.start}-{tomorrow.end}",
                })

    return {"monthly_hours": monthly, "rest_11h_violations": rest_violations}


def preflight_supply(schedule, shop) -> list[dict[str, Any]]:
    """Static input facts that commonly explain an infeasible staffing model."""
    report = []
    for day in range(1, schedule.days_in_month + 1):
        if not shop.is_trade_day(day):
            continue
        available = []
        locked = []
        for employee in schedule.employees:
            state = schedule.get_day(employee, day)
            if state.is_leave or getattr(state, "is_sick", False) or getattr(state, "is_day_off", False):
                continue
            available.append(employee)
            if state.is_locked:
                locked.append({
                    "employee": employee.display_name(),
                    "shift": _cell_value(state),
                })
        report.append({
            "day": day,
            "available_employees": len(available),
            "available_openers": sum(employee.is_opener for employee in available),
            "available_meat_staff": sum(employee.is_meat for employee in available),
            "available_meat_light_staff": sum(employee.is_meat_light for employee in available),
            "min_open_staff": shop.constraints.get("min_open_staff", 3),
            "min_close_staff": shop.constraints.get("min_close_staff", 3),
            "locked_assignments": locked,
        })
    return report


def build_infeasibility_summary(schedule, shop) -> list[str]:
    """Return client-readable causes that can be proven from the input data."""
    messages: list[str] = []
    policies = shop.constraint_policies
    min_open = shop.constraints.get("min_open_staff", 3)
    min_close = shop.constraints.get("min_close_staff", 3)

    def add(message: str) -> None:
        if message not in messages and len(messages) < 6:
            messages.append(message)

    for day in range(1, schedule.days_in_month + 1):
        if not shop.is_trade_day(day):
            continue
        hours = shop.get_open_hours_for_day(day)
        if not hours:
            continue

        open_time, close_time = hours
        for policy_name, target_time, required, label in (
            ("open", open_time, min_open, "otwarciu"),
            ("close", close_time, min_close, "zamknięciu"),
        ):
            if policies.get(policy_name) != ConstraintPolicy.MANDATORY:
                continue

            fixed = []
            possible = []
            for employee in schedule.employees:
                state = schedule.get_day(employee, day)
                if state.is_leave or getattr(state, "is_sick", False) or getattr(state, "is_day_off", False):
                    continue
                matches = state.start == target_time if policy_name == "open" else state.end == target_time
                if state.is_locked:
                    if matches:
                        fixed.append(employee)
                else:
                    possible.append(employee)

            if len(fixed) > required:
                add(
                    f"Dzień {day}: zablokowano {len(fixed)} osoby na {label}, "
                    f"a wymagane są dokładnie {required}."
                )
            elif len(fixed) + len(possible) < required:
                add(
                    f"Dzień {day}: za mało osób możliwych do pracy na {label} "
                    f"({len(fixed) + len(possible)} z wymaganych {required})."
                )
            elif not any(employee.is_opener for employee in fixed + possible):
                add(f"Dzień {day}: brak pracownika otwarcia możliwego do pracy na {label}.")
            elif not any(employee.is_meat or employee.is_meat_light for employee in fixed + possible):
                add(f"Dzień {day}: brak osoby z uprawnieniem mięso (ani zastępczej) możliwej do pracy na {label}.")

        if policies.get("meat_coverage") == ConstraintPolicy.MANDATORY:
            available_meat = [
                employee for employee in schedule.employees
                if (employee.is_meat or employee.is_meat_light)
                and not schedule.get_day(employee, day).is_leave
                and not getattr(schedule.get_day(employee, day), "is_sick", False)
                and not getattr(schedule.get_day(employee, day), "is_day_off", False)
            ]
            if not available_meat:
                add(f"Dzień {day}: brak dostępnej osoby z uprawnieniem mięso (ani zastępczej) na cały dzień.")

    if policies.get("rest_11h") == ConstraintPolicy.MANDATORY:
        fmt = "%H:%M"
        for employee in schedule.employees:
            for day in range(1, schedule.days_in_month):
                if not (shop.is_trade_day(day) and shop.is_trade_day(day + 1)):
                    continue
                today = schedule.get_day(employee, day)
                tomorrow = schedule.get_day(employee, day + 1)
                if not (today.is_locked and tomorrow.is_locked and today.end and tomorrow.start):
                    continue
                end = datetime.strptime(today.end, fmt)
                start = datetime.strptime(tomorrow.start, fmt)
                rest = start - end
                if rest.total_seconds() < 0:
                    rest += timedelta(days=1)
                if rest < timedelta(hours=11):
                    hours = rest.total_seconds() / 3600
                    add(
                        f"{employee.display_name()}, dni {day}–{day + 1}: "
                        f"zablokowana przerwa wynosi tylko {hours:.2f} h (wymagane 11 h)."
                    )

    if not messages:
        add(
            "Wymagane zasady są ze sobą sprzeczne. Sprawdź zablokowane zmiany, "
            "dostępność pracowników oraz wymagania dla danego dnia."
        )
    return messages


class GeneratorDiagnostics:
    """Run isolated stage solves and locate an irreducible hard-constraint set."""

    def __init__(self, schedule, shop, time_limit_seconds: float = 5):
        self.schedule = schedule
        self.shop = shop
        self.time_limit_seconds = time_limit_seconds

    @staticmethod
    def write_report(report: dict[str, Any], path: str | Path) -> None:
        Path(path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    def _run(self, enabled: Iterable[str]) -> tuple[dict[str, Any], Any]:
        """Solve a disposable copy with only selected policy constraints active."""
        from logic.auto_generator import AutoScheduleGenerator

        schedule = deepcopy(self.schedule)
        shop = deepcopy(self.shop)
        enabled = set(enabled)
        for name in POLICY_STAGES:
            if name not in enabled:
                shop.constraint_policies[name] = ConstraintPolicy.DISABLED

        # A single worker makes stage-to-stage output reproducible for a seed.
        with redirect_stdout(io.StringIO()):
            result = AutoScheduleGenerator(schedule, shop).generate(
                solver_time_limit_seconds=self.time_limit_seconds,
                solver_workers=1,
            )
        # OR-Tools 9.15 returns a CpSolverStatus enum, which json cannot encode.
        result = dict(result)
        result["status"] = int(result["status"])
        return result, schedule

    def _find_irreducible_conflict(self, active: list[str]) -> list[str]:
        """Deletion-based MUS approximation; every returned group is necessary."""
        conflict = list(active)
        for name in list(conflict):
            candidate = [item for item in conflict if item != name]
            result, _ = self._run(candidate)
            if not result["success"] and result["status"] == cp_model.INFEASIBLE:
                conflict = candidate
        return conflict

    def run(self) -> dict[str, Any]:
        original_policies = self.shop.constraint_policies
        active = [
            name for name in POLICY_STAGES
            if original_policies.get(name, ConstraintPolicy.DISABLED) != ConstraintPolicy.DISABLED
        ]

        base_result, base_schedule = self._run(())
        stages = []
        previous_snapshot = schedule_snapshot(base_schedule) if base_result["success"] else None
        first_infeasible_at = None
        enabled: list[str] = []

        stages.append({
            "stage": "core",
            "enabled_constraints": [],
            "contained_constraints": [
                "non_trade_day", "leave", "day_off", "manual_shift",
                "work_dependency", "one_shift_per_day",
            ],
            "status": _status_name(base_result["status"]),
            "solver": base_result,
            "schedule": previous_snapshot,
            "audit": audit_schedule(base_schedule, self.shop) if base_result["success"] else None,
            "changes_from_previous_stage": [],
        })
        if not base_result["success"]:
            first_infeasible_at = "core"

        for name in POLICY_STAGES:
            policy = original_policies.get(name, ConstraintPolicy.DISABLED)
            if policy == ConstraintPolicy.DISABLED:
                stages.append({"stage": name, "policy": policy.value, "status": "DISABLED"})
                continue
            enabled.append(name)
            result, solved_schedule = self._run(enabled)
            snapshot = schedule_snapshot(solved_schedule) if result["success"] else None
            stage = {
                "stage": name,
                "policy": policy.value,
                "enabled_constraints": list(enabled),
                "status": _status_name(result["status"]),
                "solver": result,
                "schedule": snapshot,
                "audit": audit_schedule(solved_schedule, self.shop) if result["success"] else None,
                "changes_from_previous_stage": snapshot_diff(previous_snapshot, snapshot) if snapshot else [],
            }
            stages.append(stage)
            if snapshot is not None:
                previous_snapshot = snapshot
            elif first_infeasible_at is None and result["status"] == cp_model.INFEASIBLE:
                first_infeasible_at = name
                break

        infeasibility = None
        if first_infeasible_at:
            if first_infeasible_at == "core":
                conflict = ["core"]
            else:
                conflict = self._find_irreducible_conflict(enabled)
            infeasibility = {
                "first_infeasible_stage": first_infeasible_at,
                "irreducible_constraint_groups": conflict,
                "interpretation": (
                    "Removing any listed group makes this staged model feasible. "
                    "The core group contains manual assignments, leave/day-off, "
                    "non-trade-day, one-shift and work-dependency constraints."
                ),
            }

        return {
            "format": "dingo-generator-diagnostics/v1",
            "note": (
                "changes_from_previous_stage shows the observable stage impact. "
                "It is not proof that a single constraint caused an assignment, because "
                "the model can have multiple optimal schedules."
            ),
            "scenario": {"schedule": self.schedule.to_dict(), "shop_config": self.shop.to_dict()},
            "active_policy_constraints": active,
            "preflight_supply": preflight_supply(self.schedule, self.shop),
            "stages": stages,
            "infeasibility": infeasibility,
        }
