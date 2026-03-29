class ScheduleController:
    def __init__(self, schedule, shop_config):
        self.schedule = schedule
        self.shop_config = shop_config
        self.history = []
        self.future = []

    def snapshot(self):
        self.history.append(self.schedule.snapshot())
        self.future.clear()

    def undo(self):
        if not self.history:
            return self.schedule

        self.future.append(self.schedule.snapshot())
        self.schedule = self.history.pop()
        return self.schedule

    def set_day_free(self, emp, day):
        ds = self.schedule.get_day(emp, day)

        if ds.start is None and ds.end is None and not ds.is_leave and not ds.is_sick:
            return

        self.snapshot()
        self.schedule.set_day_free(emp, day)
        ds.is_locked = True

    def set_day_hours(self, emp, day, start, end):
        ds = self.schedule.get_day(emp, day)

        if ds.start == start and ds.end == end and not ds.is_leave and not ds.is_sick:
            return

        self.snapshot()
        self.schedule.set_day_hours(emp, day, start, end)
        ds.is_locked = True

    def set_day_leave(self, emp, day):
        ds = self.schedule.get_day(emp, day)

        if ds.is_leave:
            return

        self.snapshot()
        ds.set_leave()
        ds.is_locked = True

    def add_employee(self, emp):
        self.snapshot()
        self.schedule.add_employee(emp)

    def replace_employee(self, old, new):
        self.snapshot()
        self.schedule.replace_employee(old, new)

    def get_day(self, emp, day):
        return self.schedule.get_day(emp, day)

    def generate_schedule(self, force=False):
        from logic.auto_generator import AutoScheduleGenerator
        generator = AutoScheduleGenerator(self.schedule, self.shop_config)
        
        is_fix = getattr(self.schedule, "is_generated", False) and not force
        result = generator.generate(is_fix=is_fix)
        
        if result and result.get("success"):
            self.schedule.is_generated = True
            
        return result

    def set_shift(self, emp, day, shift_type, start=None, end=None):
        ds = self.schedule.get_day(emp, day)

        # --- BLOKADA DUPLIKATÓW ---
        if shift_type == "OFF":
            if ds.start is None and ds.end is None and not ds.is_leave and not ds.is_sick:
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
            if start is not None and end is not None:
                ds.start = start
                ds.end = end
            else:
                hours = self.shop_config.get_open_hours_for_day(day)
                if hours:
                    ds.start, ds.end = hours

            ds.is_leave = False
            ds.is_sick = False

        ds.is_locked = True

    def _calc_end_from_daily(self, start_str, hours):
        from datetime import datetime, timedelta

        fmt = "%H:%M"
        start = datetime.strptime(start_str, fmt)
        end = start + timedelta(hours=hours)
        return end.strftime(fmt)
    
    def remove_employee(self, employee):
        self.schedule.remove_employee(employee)

    def set_day_sick(self, emp, day):
        ds = self.schedule.get_day(emp, day)

        if ds.is_sick:
            return

        self.snapshot()
        ds.set_sick()
        ds.is_locked = True

    def redo(self):
        if not self.future:
            return self.schedule

        self.history.append(self.schedule.snapshot())
        self.schedule = self.future.pop()
        return self.schedule