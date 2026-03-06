from dataclasses import dataclass
from datetime import datetime, timedelta


_TIME_FORMAT = "%H:%M"


def _parse_time(value: str) -> datetime:
    return datetime.strptime(value, _TIME_FORMAT)


@dataclass
class DaySchedule:
    """
    Jedna komórka grafiku (jeden dzień, jeden pracownik).

    Przechowuje:
    - start pracy
    - koniec pracy
    - flagę urlopu
    """

    start: str | None = None
    end: str | None = None
    is_leave: bool = False   # ← DODANE
    is_locked: bool = False


    def is_empty(self) -> bool:
        """Czy dzień jest pusty (wolne)."""
        return self.start is None and self.end is None

    def set_free(self) -> None:
        """Ustawia dzień jako wolny."""
        self.start = None
        self.end = None
        self.is_leave = False   # ← DODANE

    def set_leave(self) -> None:
        """Ustawia dzień jako urlop."""
        self.start = None
        self.end = None
        self.is_leave = True

    def set_hours(self, start: str, end: str) -> None:
        """
        Ustawia godziny pracy.
        Format: 'HH:MM'
        """
        start_dt = _parse_time(start)
        end_dt = _parse_time(end)

        if end_dt <= start_dt:
            raise ValueError("Godzina zakończenia musi być późniejsza niż rozpoczęcia")

        self.start = start
        self.end = end
        self.is_leave = False   # ← DODANE (godziny kasują urlop)

    def total_duration(self) -> timedelta | None:
        """
        Zwraca czas pracy jako timedelta.
        """
        if self.is_empty() or self.is_leave:
            return None

        start_dt = _parse_time(self.start)
        end_dt = _parse_time(self.end)

        return end_dt - start_dt

    def total_as_str(self) -> str | None:
        """
        Zwraca sumę godzin w formacie HH:MM.
        """
        duration = self.total_duration()
        if duration is None:
            return None

        total_minutes = int(duration.total_seconds() // 60)
        hours = total_minutes // 60
        minutes = total_minutes % 60

        return f"{hours}:{minutes:02d}"

    def as_rows(self) -> tuple[str, str, str]:
        """
        Zwraca dane dokładnie pod GUI:
        (start, end, suma)

        Jeśli wolne → puste stringi
        Jeśli urlop → 🌴 w pierwszej linii
        """
        if self.is_leave:
            return "🌴", "", ""

        if self.is_empty():
            return "", "", ""

        return (
            self.start or "",
            self.end or "",
            self.total_as_str() or "",
        )
