"""Urlop wypoczynkowy: automatyczne odejmowanie zaznaczonego urlopu od
Employee.vacation_days_left oraz wnioski urlopowe (menu Plik -> "Wnioski
urlopowe...", ui/leave_requests_dialog.py, PDF w
export/leave_request_exporter.py).

Liczą się wyłącznie dni ręcznie oznaczone przez użytkownika jako urlop
(DaySchedule.is_leave - generator nigdy go nie ustawia) i wyłącznie dni
robocze w rozumieniu Kodeksu pracy: poniedziałek-piątek, z wyłączeniem
świąt ustawowo wolnych od pracy. Urlop zaznaczony w sobotę/niedzielę/święto
nie zmniejsza puli i nie tworzy osobnego wniosku.

Jeden dzień urlopu kosztuje tyle dni, ile wynosi dzienny wymiar pracownika
podzielony przez 8h (8h -> 1 dzień, 4h -> 0,5 dnia, 24h -> 3 dni),
zaokrąglone do 0,5 dnia, minimum 0,5 dnia."""

import calendar
from dataclasses import dataclass
from datetime import date

from logic.utils.holidays_pl import polish_public_holiday_days
from logic.utils.time_utils import get_effective_daily_hours

HOURS_PER_LEAVE_DAY = 8
MIN_LEAVE_DAY_VALUE = 0.5


def leave_day_value(employee, shop) -> float:
    """Ile dni urlopu zużywa jeden dzień urlopu tego pracownika."""
    hours = get_effective_daily_hours(employee, shop)
    halves = int(hours / HOURS_PER_LEAVE_DAY * 2 + 0.5)
    return max(MIN_LEAVE_DAY_VALUE, halves / 2)


def is_leave_working_day(year: int, month: int, day: int) -> bool:
    """Czy urlop w tym dniu liczy się do puli (pon-pt, poza świętami)."""
    if calendar.weekday(year, month, day) >= 5:
        return False
    return day not in polish_public_holiday_days(year, month)


def _counted_leave_days(schedule, employee) -> list[int]:
    return [
        day for day in range(1, schedule.days_in_month + 1)
        if schedule.get_day(employee, day).is_leave
        and is_leave_working_day(schedule.year, schedule.month, day)
    ]


def leave_days_used(schedule, shop, employee) -> float:
    """Dni urlopu zużyte przez pracownika w tym miesiącu."""
    return len(_counted_leave_days(schedule, employee)) * leave_day_value(employee, shop)


def sync_vacation_balances(schedule, shop) -> list[tuple]:
    """Dopasowuje Employee.vacation_days_left do urlopu zaznaczonego w
    grafiku: odejmuje dopiero co dodany urlop, oddaje usunięty. Bezpieczne do
    wołania po każdej zmianie (bez zmian w urlopie nic nie robi). Zwraca
    listę (pracownik, zmiana_puli) dla pracowników, których pula się
    zmieniła - zmiana ujemna = urlop odjęty."""
    changes = []
    for employee in list(schedule.employees):
        used = leave_days_used(schedule, shop, employee)
        charged = schedule.leave_days_charged.get(employee)
        if charged is None:
            # Pierwsze liczenie (projekt sprzed tej funkcji) - zakładamy, że
            # wpisana ręcznie pula uwzględnia już urlop obecny w grafiku.
            schedule.leave_days_charged[employee] = used
            continue
        delta = used - charged
        if delta == 0:
            continue
        new_balance = employee.vacation_days_left - delta
        employee = schedule.set_employee_vacation_days(employee, new_balance)
        schedule.leave_days_charged[employee] = used
        changes.append((employee, -delta))
    return changes


@dataclass(frozen=True)
class LeaveRequest:
    """Jeden wniosek urlopowy - ciągły okres urlopu jednego pracownika."""

    employee: object
    year: int
    month: int
    start_day: int
    end_day: int
    days: float
    printed: bool

    @property
    def start_date(self) -> date:
        return date(self.year, self.month, self.start_day)

    @property
    def end_date(self) -> date:
        return date(self.year, self.month, self.end_day)

    @property
    def key(self) -> tuple[int, int]:
        return self.start_day, self.end_day


def _leave_periods(schedule, employee) -> list[tuple[int, int]]:
    """Ciągłe okresy urlopu. Dni wolne od pracy (weekend/święto) bez
    zaznaczonego urlopu nie przerywają okresu (urlop pt + pon = jeden
    wniosek), ale okres nie zaczyna się ani nie kończy na takim dniu."""
    counted = _counted_leave_days(schedule, employee)
    periods = []
    for day in counted:
        if periods and all(
            schedule.get_day(employee, between).is_leave
            or not is_leave_working_day(schedule.year, schedule.month, between)
            for between in range(periods[-1][1] + 1, day)
        ):
            periods[-1][1] = day
        else:
            periods.append([day, day])
    return [(start, end) for start, end in periods]


def build_leave_requests(schedule, shop, location_key: str | None = None) -> list[LeaveRequest]:
    """Wnioski urlopowe na ten miesiąc - dla pracowników jednej placówki
    (`location_key`, puste/None = wszyscy), w kolejności pracowników z
    grafiku i dat."""
    requests = []
    for employee in schedule.employees:
        if location_key and employee.location_key != location_key:
            continue
        value = leave_day_value(employee, shop)
        printed = schedule.printed_leave_requests.get(employee, set())
        for start, end in _leave_periods(schedule, employee):
            days = sum(
                value for day in range(start, end + 1)
                if schedule.get_day(employee, day).is_leave
                and is_leave_working_day(schedule.year, schedule.month, day)
            )
            requests.append(LeaveRequest(
                employee=employee,
                year=schedule.year,
                month=schedule.month,
                start_day=start,
                end_day=end,
                days=days,
                printed=(start, end) in printed,
            ))
    return requests


def pending_leave_requests_count(schedule, shop, location_key: str | None = None) -> int:
    return sum(1 for request in build_leave_requests(schedule, shop, location_key) if not request.printed)


def mark_leave_requests_printed(schedule, requests) -> None:
    for request in requests:
        schedule.printed_leave_requests.setdefault(request.employee, set()).add(request.key)


def format_days(days: float) -> str:
    """1 -> "1", 1.5 -> "1,5" (polski przecinek dziesiętny)."""
    if float(days).is_integer():
        return str(int(days))
    return f"{days:.1f}".replace(".", ",")


def days_noun(days: float) -> str:
    """"1 dzień", "2,5 dnia", "5 dni" (także dla wartości ujemnych)."""
    if not float(days).is_integer():
        return "dnia"
    return "dzień" if abs(days) == 1 else "dni"


def _plural_form(count: int) -> int:
    """Polska odmiana liczebnika: 0 = "1 wniosek", 1 = "2-4 wnioski",
    2 = "5+ wniosków" (także 12-14, 22-24 -> "wnioski")."""
    if count == 1:
        return 0
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return 1
    return 2


def requests_noun(count: int) -> str:
    return ("wniosek", "wnioski", "wniosków")[_plural_form(count)]


def pending_requests_text(count: int) -> str:
    """Tekst paska pod grafikiem, z polską odmianą liczebnika."""
    form = _plural_form(count)
    verb = ("Istnieje", "Istnieją", "Istnieje")[form]
    rest = ("oczekujący", "oczekujące", "oczekujących")[form]
    return f"{verb} {count} {requests_noun(count)} {rest} na wydruk"


def generate_button_text(count: int) -> str:
    return "Wygeneruj wniosek" if count == 1 else "Wygeneruj wnioski"
