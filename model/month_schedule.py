import calendar
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Dict

from model.day_schedule import DaySchedule
from model.employee import PERSONAL_DATA_FIELDS, Employee

# Odkryte z powrotem (2026-09-21) przy okazji pamięci wielu miesięcy - diagnostyka
# INFEASIBLE (ENYO_ONLY_CHANGES.md, "Naprawiony bug: infeasible bez
# wyjaśnienia...") była już gotowa, więc nic nie stało na przeszkodzie.
# Sprawdzane w:
# - ui/main_window.py (przejęcie automatyczne przy zmianie miesiąca +
#   pozycja menu Edycja -> "Godziny zakończenia z poprzedniego miesiąca..."),
# - logic/generator/base_specs.py::_build_rest_11h (wpływ na generator),
# - ui/grid_view.py::_previous_month_last_day_if_shown (kolumna w gridzie).
PREVIOUS_MONTH_MEMORY_ENABLED = True


@dataclass(frozen=True)
class PreviousMonthShiftEnd:
    """"Pamięć poprzedniego miesiąca" (tego samego projektu) - koniec
    ostatniej zmiany jednego pracownika w ostatnim dniu miesiąca
    poprzedzającego ten MonthSchedule. Przejmowane automatycznie przy
    zmianie miesiąca w tym samym projekcie (patrz
    ui/main_window.py::_save_date_clicked) albo wpisywane ręcznie, gdy
    nie ma czego przejąć (nowy projekt / brak poprzedniego miesiąca w
    tej sesji).

    `crosses_midnight` jednoznacznie umieszcza `end` na osi czasu
    względem dnia 1 tego miesiąca - dokładnie ten sam wzorzec co
    DaySchedule.crosses_midnight(): True = zmiana wchodzi już w dzień 1,
    False = zmiana kończy się jeszcze w (nieistniejącym w tym projekcie)
    ostatnim dniu poprzedniego miesiąca. Bez tej flagi sam `end` byłby
    niejednoznaczny (np. "06:00" mogłoby oznaczać zarówno "skończył o
    6 rano tuż przed dniem 1", jak i "skończył o 6 rano W dniu 1")."""

    end: str  # "HH:MM"
    crosses_midnight: bool


class MonthSchedule:
    def __init__(self, year: int, month: int, employees=None):
        self.year = year
        self.month = month
        self.days_in_month = calendar.monthrange(year, month)[1]
        self.is_generated = False

        self.employees: list[Employee] = []
        self._data: Dict[Employee, Dict[int, DaySchedule]] = {}

        # Docelowa liczba minut w miesiącu per pracownik (funkcja "Okres
        # rozliczeniowy") — None/brak wpisu oznacza brak ustalonego celu.
        self.settlement_targets: Dict[Employee, int] = {}

        # "Pamięć poprzedniego miesiąca" - patrz PreviousMonthShiftEnd.
        # Brak wpisu = brak danych (świeży projekt, albo pracownik dodany
        # dopiero w tym miesiącu) - generator wtedy po prostu nie dokłada
        # żadnego dodatkowego ograniczenia na dzień 1 dla tego pracownika.
        self.previous_month_end_shifts: Dict[Employee, PreviousMonthShiftEnd] = {}

        # Wnioski urlopowe (logic/leave_requests.py):
        # - leave_days_charged: ile dni urlopu z tego miesiąca jest już
        #   odjęte od Employee.vacation_days_left - różnica względem urlopu
        #   faktycznie zaznaczonego w grafiku to kwota do odjęcia/oddania przy
        #   następnej synchronizacji (sync_vacation_balances). Brak wpisu =
        #   jeszcze nie liczone (np. projekt sprzed tej funkcji) - pierwsza
        #   synchronizacja przyjmuje wtedy bieżący urlop za już rozliczony.
        # - printed_leave_requests: zakresy dni (start, koniec) wniosków już
        #   zapisanych do PDF - okno "Wnioski urlopowe" domyślnie ich nie
        #   zaznacza, a pasek pod grafikiem ich nie liczy.
        self.leave_days_charged: Dict[Employee, float] = {}
        self.printed_leave_requests: Dict[Employee, set[tuple[int, int]]] = {}

        if employees:
            for emp in employees:
                self.add_employee(emp)

    def add_employee(self, employee: Employee) -> None:
        employee.validate()
        if employee in self._data:
            raise ValueError("Ten pracownik już istnieje w grafiku")

        self.employees.append(employee)
        self.employees.sort(key=self._employee_sort_key)
        self._data[employee] = {
            day: DaySchedule()
            for day in range(1, self.days_in_month + 1)
        }

    def remove_employee(self, employee: Employee) -> None:
        if employee not in self._data:
            return
        self.employees.remove(employee)
        del self._data[employee]
        self.settlement_targets.pop(employee, None)
        self.previous_month_end_shifts.pop(employee, None)
        self.leave_days_charged.pop(employee, None)
        self.printed_leave_requests.pop(employee, None)

    def _per_employee_dicts(self) -> list[dict]:
        return [
            self._data,
            self.settlement_targets,
            self.previous_month_end_shifts,
            self.leave_days_charged,
            self.printed_leave_requests,
        ]

    def set_employee_vacation_days(self, employee: Employee, days: float) -> Employee:
        """Zmienia Employee.vacation_days_left w miejscu (Employee jest
        frozen, więc podmienia obiekt na kopię z nową wartością, zachowując
        wszystkie dane z nim związane). Zwraca nowy obiekt pracownika."""
        new = replace(employee, vacation_days_left=days)
        self.employees[self.employees.index(employee)] = new
        # dict[new] = dict.pop(old): samo przypisanie zostawiłoby stary obiekt
        # jako klucz (new == old, bo równość/hash liczy się tylko z nazwiska).
        for mapping in self._per_employee_dicts():
            if employee in mapping:
                mapping[new] = mapping.pop(employee)
        return new

    def get_settlement_target(self, employee: Employee) -> int | None:
        return self.settlement_targets.get(employee)

    def set_settlement_target(self, employee: Employee, minutes: int | None) -> None:
        if minutes is None:
            self.settlement_targets.pop(employee, None)
        else:
            self.settlement_targets[employee] = minutes

    def get_previous_month_end_shift(self, employee: Employee) -> PreviousMonthShiftEnd | None:
        return self.previous_month_end_shifts.get(employee)

    def set_previous_month_end_shift(
        self, employee: Employee, end: str | None, crosses_midnight: bool = False
    ) -> None:
        if end is None:
            self.previous_month_end_shifts.pop(employee, None)
        else:
            self.previous_month_end_shifts[employee] = PreviousMonthShiftEnd(end, crosses_midnight)

    def get_day(self, employee: Employee, day: int) -> DaySchedule:
        self._validate_day(day)
        return self._data[employee][day]

    def set_day_hours(self, employee: Employee, day: int, start: str, end: str) -> None:
        self._validate_day(day)
        self._data[employee][day].set_hours(start, end)

    def set_day_full_day_shift(self, employee: Employee, day: int, start: str) -> None:
        self._validate_day(day)
        self._data[employee][day].set_full_day_shift(start)

    def set_day_free(self, employee: Employee, day: int) -> None:
        self._validate_day(day)
        self._data[employee][day].set_free()

    def copy_day(self, employee: Employee, day: int) -> None:
        self._validate_day(day)
        self._clipboard = deepcopy(self._data[employee][day])

    def paste_day(self, employee: Employee, day: int) -> None:
        if self._clipboard is None:
            return
        self._validate_day(day)
        self._data[employee][day] = deepcopy(self._clipboard)

    def total_hours_for_employee(self, employee: Employee) -> str:
        total_minutes = self.total_minutes_for_employee(employee)
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours}:{minutes:02d}"

    def total_minutes_for_employee(self, employee: Employee) -> int:
        """To samo co total_hours_for_employee, ale jako int minut zamiast
        sformatowanego stringa - do obliczeń (np. podświetlanie przekroczenia
        miesięcznego limitu godzin, logic/monthly_hours_status.py), gdzie
        liczy się dokładna wartość, nie tekst do wyświetlenia w siatce.
        """
        total_minutes = 0
        for day in range(1, self.days_in_month + 1):
            ds = self._data[employee][day]

            if ds.is_leave or getattr(ds, "is_sick", False):
                continue

            duration = ds.total_duration()
            if duration:
                total_minutes += int(duration.total_seconds() // 60)

        return total_minutes

    def leave_hours_for_employee(self, employee: Employee) -> str:
        total_minutes = 0
        for day in range(1, self.days_in_month + 1):
            ds = self._data[employee][day]
            if ds.is_leave:
                total_minutes += int(
                    employee.daily_hours *
                    (1.0 if employee.employment_fraction >= 1.0 else employee.employment_fraction)
                    * 60
                )
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours}:{minutes:02d}"

    def sick_hours_for_employee(self, employee):
        total_minutes = 0
        for day in range(1, self.days_in_month + 1):
            ds = self._data[employee][day]
            if getattr(ds, "is_sick", False):
                total_minutes += int(
                    employee.daily_hours *
                    (1.0 if employee.employment_fraction >= 1.0 else employee.employment_fraction)
                    * 60
                )
        return f"{total_minutes // 60}:{total_minutes % 60:02d}"

    def total_with_leave_for_employee(self, employee: Employee) -> str:
        total_minutes = 0
        for day in range(1, self.days_in_month + 1):
            ds = self._data[employee][day]

            if not getattr(ds, "is_sick", False):
                duration = ds.total_duration()
                if duration:
                    total_minutes += int(duration.total_seconds() // 60)

            if ds.is_leave:
                total_minutes += int(
                    employee.daily_hours *
                    (1.0 if employee.employment_fraction >= 1.0 else employee.employment_fraction)
                    * 60
                )

        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours}:{minutes:02d}"

    def total_with_leave_and_sick_minutes_for_employee(self, employee) -> int:
        """To samo co total_with_leave_and_sick_for_employee, ale jako int
        minut zamiast sformatowanego stringa — do obliczeń (np. okres
        rozliczeniowy), gdzie liczy się dokładna wartość, nie tekst do
        wyświetlenia w siatce.
        """
        total_minutes = 0
        for day in range(1, self.days_in_month + 1):
            ds = self._data[employee][day]

            if not getattr(ds, "is_sick", False):
                duration = ds.total_duration()
                if duration:
                    total_minutes += int(duration.total_seconds() // 60)

            if ds.is_leave:
                total_minutes += int(
                    employee.daily_hours *
                    (1.0 if employee.employment_fraction >= 1.0 else employee.employment_fraction)
                    * 60
                )

            if getattr(ds, "is_sick", False):
                total_minutes += int(
                    employee.daily_hours *
                    (1.0 if employee.employment_fraction >= 1.0 else employee.employment_fraction)
                    * 60
                )

        return total_minutes

    def total_with_leave_and_sick_for_employee(self, employee):
        total_minutes = self.total_with_leave_and_sick_minutes_for_employee(employee)
        return f"{total_minutes // 60}:{total_minutes % 60:02d}"

    def total_hours_for_day(self, day: int) -> int:
        self._validate_day(day)
        count = 0
        for emp in self.employees:
            if not self._data[emp][day].is_empty():
                count += 1
        return count

    def snapshot(self) -> "MonthSchedule":
        return deepcopy(self)

    def restore(self, snapshot: "MonthSchedule") -> None:
        """Restore a previously captured state without replacing this schedule object."""
        self.year = snapshot.year
        self.month = snapshot.month
        self.days_in_month = snapshot.days_in_month
        self.is_generated = snapshot.is_generated
        self.employees = snapshot.employees
        self._data = snapshot._data
        self.settlement_targets = snapshot.settlement_targets
        self.previous_month_end_shifts = snapshot.previous_month_end_shifts
        self.leave_days_charged = snapshot.leave_days_charged
        self.printed_leave_requests = snapshot.printed_leave_requests

    def _validate_day(self, day: int) -> None:
        if day < 1 or day > self.days_in_month:
            raise ValueError("Nieprawidłowy dzień miesiąca")

    def to_dict(self):
        return {
            "year": self.year,
            "month": self.month,
            "is_generated": getattr(self, "is_generated", False),
            "employees": [
                {
                    "first_name": e.first_name,
                    "last_name": e.last_name,
                    "is_opener": e.is_opener,
                    "is_meat": e.is_meat,
                    "is_meat_light": e.is_meat_light,
                    "is_manager": e.is_manager,
                    "no_night": e.no_night,
                    "no_afternoon": e.no_afternoon,
                    "custom_roles": e.custom_roles,
                    "location_key": e.location_key,
                    "monthly_target_hours": e.monthly_target_hours,
                    "daily_hours": e.daily_hours,
                    "employment_fraction": e.employment_fraction,
                    "availability": e.availability,
                    "vacation_days_left": e.vacation_days_left,
                    "leave_days_charged": self.leave_days_charged.get(e),
                    "printed_leave_requests": sorted(
                        [start, end] for start, end in self.printed_leave_requests.get(e, ())
                    ),
                    **e.personal_data(),
                    "settlement_target_minutes": self.settlement_targets.get(e),
                    "previous_month_shift_end": (
                        self.previous_month_end_shifts[e].end
                        if e in self.previous_month_end_shifts else None
                    ),
                    "previous_month_shift_crosses_midnight": (
                        self.previous_month_end_shifts[e].crosses_midnight
                        if e in self.previous_month_end_shifts else None
                    ),
                    "days": {
                        day: {
                            "start": ds.start,
                            "end": ds.end,
                            "is_leave": ds.is_leave,
                            "is_locked": ds.is_locked,
                            "is_sick": ds.is_sick,
                            "is_day_off": ds.is_day_off,
                            "shift_class": ds.shift_class,
                            "is_full_day": ds.is_full_day,
                        }
                        for day in range(1, self.days_in_month + 1)
                        if (
                            not (ds := self.get_day(e, day)).is_empty()
                            or ds.is_leave
                            or getattr(ds, "is_sick", False)
                            or getattr(ds, "is_locked", False)
                            or getattr(ds, "shift_class", None)
                        )
                    },
                }
                for e in self.employees
            ],
        }

    @classmethod
    def from_dict(cls, data):
        sched = cls(data["year"], data["month"])
        sched.is_generated = data.get("is_generated", False)

        for ed in data["employees"]:
            emp = Employee(
                last_name=ed["last_name"],
                first_name=ed["first_name"],
                is_opener=ed.get("is_opener", False),
                is_meat=ed.get("is_meat", False),
                is_meat_light=ed.get("is_meat_light", False),
                is_manager=ed.get("is_manager", False),
                no_night=ed.get("no_night", False),
                no_afternoon=ed.get("no_afternoon", False),
                custom_roles=dict(ed.get("custom_roles", {})),
                location_key=ed.get("location_key", ""),
                monthly_target_hours=ed.get("monthly_target_hours", 160),
                daily_hours=ed.get("daily_hours", 8),
                employment_fraction=ed.get("employment_fraction", 1.0),
                availability={int(k): v for k, v in ed.get("availability", {}).items()},
                vacation_days_left=ed.get("vacation_days_left", 0),
                **{name: ed.get(name) or "" for name in PERSONAL_DATA_FIELDS},
            )
            sched.add_employee(emp)

            target_minutes = ed.get("settlement_target_minutes")
            if target_minutes is not None:
                sched.set_settlement_target(emp, target_minutes)

            charged = ed.get("leave_days_charged")
            if charged is not None:
                sched.leave_days_charged[emp] = charged
            printed = ed.get("printed_leave_requests") or []
            if printed:
                sched.printed_leave_requests[emp] = {(int(start), int(end)) for start, end in printed}

            prev_end = ed.get("previous_month_shift_end")
            if prev_end is not None:
                sched.set_previous_month_end_shift(
                    emp, prev_end, ed.get("previous_month_shift_crosses_midnight", False)
                )

            for day in range(1, sched.days_in_month + 1):
                ds = sched.get_day(emp, day)
                ds.start = None
                ds.end = None
                ds.is_leave = False
                ds.is_full_day = False

            for day, dd in ed.get("days", {}).items():
                ds = sched.get_day(emp, int(day))
                ds.start = dd.get("start")
                ds.end = dd.get("end")
                ds.is_leave = dd.get("is_leave", False)
                ds.is_sick = dd.get("is_sick", False)
                ds.is_locked = dd.get("is_locked", False)
                ds.is_day_off = dd.get("is_day_off", False)
                ds.shift_class = dd.get("shift_class")
                ds.is_full_day = dd.get("is_full_day", False)

        sched.employees.sort(key=cls._employee_sort_key)
        return sched

    @staticmethod
    def _employee_sort_key(employee: Employee) -> tuple[str, str]:
        """Alphabetical order independent of uppercase/lowercase letters."""
        return employee.last_name.casefold(), employee.first_name.casefold()

    def replace_employee(self, old, new):
        if old not in self._data:
            return
        # Wszystko, co jest przypisane do pracownika (dni, cel okresu
        # rozliczeniowego, pamięć poprzedniego miesiąca, rozliczony urlop,
        # zapisane wnioski) przechodzi na nowy obiekt - także przy zmianie
        # nazwiska, po którym liczy się klucz słowników.
        carried = [mapping.get(old) for mapping in self._per_employee_dicts()]
        self.remove_employee(old)
        self.add_employee(new)
        for mapping, value in zip(self._per_employee_dicts(), carried):
            if value is not None:
                mapping[new] = value

    def clear_unlocked_days(self, employees=None):
        """Domyślnie czyści WSZYSTKICH pracowników - `employees` (podzbiór
        self.employees) pozwala ograniczyć czyszczenie do wybranej grupy, np.
        tylko pracowników jednej lokalizacji przy generowaniu grafiku dla
        pojedynczej placówki (patrz AutoScheduleGenerator.generate()) - bez
        tego generowanie dla jednej placówki kasowałoby też niezablokowane
        dni WSZYSTKICH pozostałych placówek."""
        for emp in (employees if employees is not None else self.employees):
            for d in range(1, self.days_in_month + 1):
                day_data = self.get_day(emp, d)

                if not day_data.is_locked:
                    day_data.start = None
                    day_data.end = None
                    day_data.is_full_day = False
                    if hasattr(day_data, "is_day_off"):
                        day_data.is_day_off = False

    def clear_generated_days(self):
        for emp in self.employees:
            for d in range(1, self.days_in_month + 1):
                ds = self.get_day(emp, d)

                if ds.is_locked:
                    continue

                ds.start = None
                ds.end = None
                ds.is_leave = False
                ds.is_sick = False
                ds.is_full_day = False

                if hasattr(ds, "is_day_off"):
                    ds.is_day_off = False
