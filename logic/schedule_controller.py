from copy import deepcopy


class ScheduleController:
    def __init__(self, schedule, shop_config):
        self.schedule = schedule
        self.shop_config = shop_config
        self.history = []
        self.future = []

    def snapshot(self):
        # Schedule and shop configuration change together from the user's point
        # of view (e.g. a day override can make a day non-working).
        self.history.append((self.schedule.snapshot(), deepcopy(self.shop_config)))
        self.future.clear()

    def undo(self):
        if not self.history:
            return self.schedule

        self.future.append((self.schedule.snapshot(), deepcopy(self.shop_config)))
        self.schedule, self.shop_config = self.history.pop()
        return self.schedule

    def set_day_free(self, emp, day):
        ds = self.schedule.get_day(emp, day)

        if ds.start is None and ds.end is None and not ds.is_leave and not ds.is_sick and not ds.shift_class:
            return

        self.snapshot()
        self.schedule.set_day_free(emp, day)
        ds.is_locked = True
        ds.shift_class = None

    def set_day_hours(self, emp, day, start, end):
        from datetime import datetime

        fmt = "%H:%M"

        try:
            start_dt = datetime.strptime(start, fmt)
            end_dt = datetime.strptime(end, fmt)
        except:
            return  # nieprawidłowy format → ignoruj

        # ❌ BLOKADA: koniec <= start, chyba że to dokładnie skonfigurowana
        # zmiana nocna tej lokalizacji (Etap D planu zmian nocnych) - inne
        # dowolne zakresy przez północ i tak nie są rozpoznawane przez
        # generator (logic/generator/night_shift_constraint.py), więc
        # przepuszczanie ich tutaj tylko tworzyłoby martwe, niezrozumiałe
        # dla generatora wpisy.
        if end_dt <= start_dt:
            night_hours = self.shop_config.get_location(emp).get_night_shift_hours()
            if night_hours != (start, end):
                return

        ds = self.schedule.get_day(emp, day)

        if ds.start == start and ds.end == end and not ds.is_leave and not ds.is_sick:
            return

        self.snapshot()
        self.schedule.set_day_hours(emp, day, start, end)
        ds.is_locked = True
        ds.shift_class = None

    def set_day_preset(self, emp, day, preset):
        """Zastosuj przedział zdefiniowany w "Ustawieniach trybu szybkiego"
        (Konfiguracja -> Ustawienia trybu szybkiego). W odróżnieniu od
        set_day_hours ufa przedziałowi bez sprawdzania go względem zmiany
        nocnej lokalizacji - użytkownik zdefiniował go świadomie w
        konfiguracji (a nie wpisał przypadkowo w locie), i normalize_quick_mode_presets
        już zagwarantowało, że godziny są sensowne."""
        ds = self.schedule.get_day(emp, day)
        full_day = bool(preset.get("full_day"))
        start = preset["start"]
        end = preset.get("end")

        # is_locked musi być częścią porównania: komórka może już mieć te
        # same godziny "przypadkiem" (np. wygenerowane automatycznie przez
        # generator) bez bycia zablokowaną ręcznie - kliknięcie presetu ma
        # wtedy nadal skutek (zablokowanie), więc nie może się skrócić do
        # no-opa tylko dlatego, że start/end się zgadzają.
        if full_day:
            if ds.is_locked and ds.is_full_day and ds.start == start:
                return
        elif (
            ds.is_locked and ds.start == start and ds.end == end
            and not ds.is_full_day and not ds.is_leave and not ds.is_sick
        ):
            return

        self.snapshot()

        if full_day:
            self.schedule.set_day_full_day_shift(emp, day, start)
        else:
            self.schedule.set_day_hours(emp, day, start, end)

        ds.is_locked = True
        ds.shift_class = None

    def copy_day_snapshot(self, emp, day) -> dict:
        """Pełny, kopiowalny stan dnia (do wklejenia gdzie indziej przez
        paste_day_snapshot) - w odróżnieniu od samych start/end, obejmuje też
        urlop/L4/zmianę pełnodobową (24h)/zablokowany typ zmiany (rano/
        popołudnie), których set_day_hours nie umie odtworzyć."""
        ds = self.schedule.get_day(emp, day)
        return {
            "start": ds.start,
            "end": ds.end,
            "is_leave": ds.is_leave,
            "is_sick": getattr(ds, "is_sick", False),
            "is_full_day": getattr(ds, "is_full_day", False),
            "shift_class": ds.shift_class,
        }

    def paste_day_snapshot(self, emp, day, snapshot: dict) -> None:
        """Wklej stan dnia skopiowany przez copy_day_snapshot(). Deleguje do
        istniejących set_day_*() (snapshot/undo, is_locked, ważność godzin
        nocnych itd. - patrz set_day_hours) zamiast nadpisywać dane wprost,
        więc każdy typ dnia dostaje dokładnie taką walidację, jaką miałby
        wpisany ręcznie."""
        if snapshot.get("is_leave"):
            self.set_day_leave(emp, day)
        elif snapshot.get("is_sick"):
            self.set_day_sick(emp, day)
        elif snapshot.get("shift_class"):
            self.set_shift_class(emp, day, snapshot["shift_class"])
        elif snapshot.get("is_full_day"):
            self.set_day_full_day_shift(emp, day, snapshot["start"])
        elif snapshot.get("start") is None or snapshot.get("end") is None:
            self.set_day_free(emp, day)
        else:
            self.set_day_hours(emp, day, snapshot["start"], snapshot["end"])

    def set_day_full_day_shift(self, emp, day, start):
        ds = self.schedule.get_day(emp, day)

        if ds.is_locked and ds.is_full_day and ds.start == start:
            return

        self.snapshot()
        self.schedule.set_day_full_day_shift(emp, day, start)
        ds.is_locked = True
        ds.shift_class = None

    def set_day_leave(self, emp, day):
        ds = self.schedule.get_day(emp, day)

        if ds.is_leave:
            return

        self.snapshot()
        ds.set_leave()
        ds.is_locked = True
        ds.shift_class = None

    def set_shift_class(self, emp, day, code):
        if code not in ("1", "2"):
            return

        if not self.shop_config.is_trade_day(day):
            return

        ds = self.schedule.get_day(emp, day)

        if ds.shift_class == code:
            return

        self.snapshot()
        ds.set_shift_class(code)

    def add_employee(self, emp):
        self.snapshot()
        self.schedule.add_employee(emp)
        self._apply_manager_schedule_if_needed(emp)

    def replace_employee(self, old, new):
        self.snapshot()
        self.schedule.replace_employee(old, new)
        self._apply_manager_schedule_if_needed(new)

    def _apply_manager_schedule_if_needed(self, emp):
        if not getattr(emp, "is_manager", False):
            return
        from logic.manager_schedule import apply_manager_schedule
        apply_manager_schedule(self.schedule, self.shop_config, emp)

    def get_day(self, emp, day):
        return self.schedule.get_day(emp, day)

    def generate_schedule(self, force=False):
        from logic.auto_generator import AutoScheduleGenerator

        # Keep an undo entry only when generation actually changes the schedule.
        schedule_before_generation = self.schedule.snapshot()
        shop_before_generation = deepcopy(self.shop_config)
        generator = AutoScheduleGenerator(self.schedule, self.shop_config)
        
        is_fix = getattr(self.schedule, "is_generated", False) and not force
        time_limit = self.shop_config.constraints.get("solver_time_limit_seconds", 60)
        result = generator.generate(is_fix=is_fix, solver_time_limit_seconds=time_limit)
        
        if result and result.get("success"):
            self.history.append((schedule_before_generation, shop_before_generation))
            self.future.clear()
            self.schedule.is_generated = True
            
        return result

    def set_shift(self, emp, day, shift_type, start=None, end=None):
        ds = self.schedule.get_day(emp, day)

        # --- BLOKADA DUPLIKATÓW ---
        if shift_type == "OFF":
            if ds.start is None and ds.end is None and not ds.is_leave and not ds.is_sick and not ds.shift_class:
                return

        elif shift_type == "LEAVE":
            if ds.is_leave:
                return

        elif shift_type == "WORK":
            if start is not None and end is not None:
                if ds.start == start and ds.end == end and not ds.is_leave and not ds.is_sick:
                    return

        self.snapshot()

        if shift_type == "OFF":
            ds.start = None
            ds.end = None
            ds.is_leave = False
            ds.is_sick = False

        elif shift_type == "LEAVE":
            ds.start = None
            ds.end = None
            ds.is_leave = True
            ds.is_sick = False

        elif shift_type == "WORK":
            from datetime import datetime

            fmt = "%H:%M"

            if start is not None and end is not None:
                try:
                    start_dt = datetime.strptime(start, fmt)
                    end_dt = datetime.strptime(end, fmt)
                except:
                    return

                if end_dt <= start_dt:
                    night_hours = self.shop_config.get_location(emp).get_night_shift_hours()
                    if night_hours != (start, end):
                        return

                ds.start = start
                ds.end = end
            else:
                hours = self.shop_config.get_location(emp).get_open_hours_for_day(day)
                if hours:
                    ds.start, ds.end = hours

            ds.is_leave = False
            ds.is_sick = False

        ds.is_locked = True
        ds.shift_class = None

    def _calc_end_from_daily(self, start_str, hours):
        from datetime import datetime, timedelta

        fmt = "%H:%M"
        start = datetime.strptime(start_str, fmt)
        end = start + timedelta(hours=hours)
        return end.strftime(fmt)
    
    def remove_employee(self, employee):
        self.snapshot()
        self.schedule.remove_employee(employee)

    def set_day_sick(self, emp, day):
        ds = self.schedule.get_day(emp, day)

        if ds.is_sick:
            return

        self.snapshot()
        ds.set_sick()
        ds.is_locked = True
        ds.shift_class = None

    def redo(self):
        if not self.future:
            return self.schedule

        self.history.append((self.schedule.snapshot(), deepcopy(self.shop_config)))
        self.schedule, self.shop_config = self.future.pop()
        return self.schedule
