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
zaokrąglone do 0,5 dnia, minimum 0,5 dnia. Pół dnia urlopu
(DaySchedule.is_half_leave, "0,5 urlopu") kosztuje połowę tego dziennego
wymiaru, liczoną tak samo (8h -> 0,5 dnia, 24h -> 1,5 dnia)."""

import calendar
from dataclasses import dataclass, replace
from datetime import date

from logic.utils.holidays_pl import polish_public_holiday_days
from logic.utils.time_utils import get_effective_daily_hours

HOURS_PER_LEAVE_DAY = 8
MIN_LEAVE_DAY_VALUE = 0.5


def leave_day_value(employee, shop, fraction: float = 1.0) -> float:
    """Ile dni urlopu zużywa jeden dzień urlopu tego pracownika (`fraction`
    0,5 - pół dnia urlopu, patrz DaySchedule.leave_fraction())."""
    hours = get_effective_daily_hours(employee, shop) * fraction
    halves = int(hours / HOURS_PER_LEAVE_DAY * 2 + 0.5)
    return max(MIN_LEAVE_DAY_VALUE, halves / 2)


def _day_cost(schedule, shop, employee, day: int) -> float:
    fraction = schedule.get_day(employee, day).leave_fraction()
    return leave_day_value(employee, shop, fraction)


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
    return sum(_day_cost(schedule, shop, employee, day) for day in _counted_leave_days(schedule, employee))


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


def share_vacation_balances(project, schedule) -> None:
    """Pula urlopu jest jedna na pracownika, a każdy miesiąc projektu
    (model/monthly_project.py) trzyma własne kopie pracowników - przepisuje
    Employee.vacation_days_left z `schedule` do tych samych pracowników we
    wszystkich pozostałych miesiącach. Bez tego urlop zaznaczony w jednym
    miesiącu nie zmniejszał puli widocznej w innym, a po powrocie do
    tamtego miesiąca kolejny urlop odejmował się od nieaktualnej puli."""
    balances = {employee: employee.vacation_days_left for employee in schedule.employees}
    for key, (other, _shop) in project.months.items():
        # Po klucz miesiąca, nie po tożsamości - po cofnij/ponów
        # self.schedule jest nowym obiektem, a kontener trzyma jeszcze stary.
        if key == (schedule.year, schedule.month):
            continue
        for employee in list(other.employees):
            balance = balances.get(employee)
            if balance is not None and employee.vacation_days_left != balance:
                other.set_employee_vacation_days(employee, balance)


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
    def key(self) -> tuple[int, int, float]:
        """Zakres dni i liczba przydzielanych dni - zmiana samej liczby dni
        (np. urlop -> 0,5 urlopu w tym samym okresie) daje nowy wniosek,
        oczekujący na wydruk."""
        return self.start_day, self.end_day, self.days

    def is_printed_in(self, printed) -> bool:
        # (start, koniec) bez liczby dni - zapis sprzed tej zmiany; taki
        # wniosek dalej uznajemy za zapisany, bez względu na liczbę dni.
        return self.key in printed or (self.start_day, self.end_day) in printed


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
        printed = schedule.printed_leave_requests.get(employee, set())
        for start, end in _leave_periods(schedule, employee):
            days = sum(
                _day_cost(schedule, shop, employee, day) for day in range(start, end + 1)
                if schedule.get_day(employee, day).is_leave
                and is_leave_working_day(schedule.year, schedule.month, day)
            )
            request = LeaveRequest(
                employee=employee,
                year=schedule.year,
                month=schedule.month,
                start_day=start,
                end_day=end,
                days=days,
                printed=False,
            )
            requests.append(replace(request, printed=request.is_printed_in(printed)))
    return requests


def pending_leave_requests_count(schedule, shop, location_key: str | None = None) -> int:
    return sum(1 for request in build_leave_requests(schedule, shop, location_key) if not request.printed)


def mark_leave_requests_printed(schedule, requests) -> None:
    for request in requests:
        printed = schedule.printed_leave_requests.setdefault(request.employee, set())
        # Para bez liczby dni (stary zapis) pasowałaby do każdej liczby dni -
        # po ponownym zapisie zostaje już tylko pełny klucz.
        printed.discard((request.start_day, request.end_day))
        printed.add(request.key)


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
