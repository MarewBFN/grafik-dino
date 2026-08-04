"""Dane trybu uproszczonego (osobne od głównego grafiku i od DaySchedule)."""

CODES = ("", "1", "2", "W")


class SimpleModeData:
    """Przechowuje ręcznie wklikane kody (1 / 2 / W) dla (pracownik, dzień).

    Całkowicie niezależne od MonthSchedule/DaySchedule — nie wpływa na
    generator ani na sumy godzin w głównym grafiku.
    """

    def __init__(self):
        self._codes = {}  # (employee_id, day) -> "1" | "2" | "W"

    def get(self, employee, day):
        return self._codes.get((employee.id, day), "")

    def set(self, employee, day, code):
        if code:
            self._codes[(employee.id, day)] = code
        else:
            self._codes.pop((employee.id, day), None)

    def cycle(self, employee, day):
        """Ustawia kolejny kod z CODES i zwraca nową wartość."""
        current = self.get(employee, day)
        next_index = (CODES.index(current) + 1) % len(CODES) if current in CODES else 0
        new_code = CODES[next_index]
        self.set(employee, day, new_code)
        return new_code

    def to_dict(self):
        return {f"{emp_id}:{day}": code for (emp_id, day), code in self._codes.items()}

    @classmethod
    def from_dict(cls, data):
        instance = cls()
        for key, code in (data or {}).items():
            emp_id, day_str = key.rsplit(":", 1)
            instance._codes[(emp_id, int(day_str))] = code
        return instance
