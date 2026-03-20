class ScheduleController:
    def __init__(self, schedule, shop_config):
        self.schedule = schedule
        self.shop_config = shop_config
        self.history = []

    def snapshot(self):
        self.history.append(self.schedule.snapshot())

    def undo(self):
        if not self.history:
            return self.schedule
        self.schedule = self.history.pop()
        return self.schedule

    def set_day_free(self, emp, day):
        self.snapshot()
        self.schedule.set_day_free(emp, day)
        ds = self.schedule.get_day(emp, day)
        ds.is_locked = True

    def set_day_hours(self, emp, day, start, end):
        self.snapshot()
        self.schedule.set_day_hours(emp, day, start, end)
        ds = self.schedule.get_day(emp, day)
        ds.is_locked = True

    def set_day_leave(self, emp, day):
        self.snapshot()
        ds = self.schedule.get_day(emp, day)
        ds.set_leave()

    def add_employee(self, emp):
        self.snapshot()
        self.schedule.add_employee(emp)

    def replace_employee(self, old, new):
        self.snapshot()
        self.schedule.replace_employee(old, new)

    def get_day(self, emp, day):
        return self.schedule.get_day(emp, day)

    def generate_schedule(self):
        from logic.auto_generator import AutoScheduleGenerator
        generator = AutoScheduleGenerator(self.schedule, self.shop_config)
        return generator.generate()

    def set_shift(self, emp, day, shift_type, start=None, end=None):
        self.snapshot()

        ds = self.schedule.get_day(emp, day)

        if shift_type == "OFF":
            ds.start = None
            ds.end = None
            ds.is_leave = False

        elif shift_type == "LEAVE":
            ds.start = None
            ds.end = None
            ds.is_leave = True

        elif shift_type == "WORK":
            if start is not None and end is not None:
                ds.start = start
                ds.end = end
            else:
                hours = self.shop_config.get_open_hours_for_day(day)
                if hours:
                    ds.start, ds.end = hours

            ds.is_leave = False

        ds.is_locked = True

    def _calc_end_from_daily(self, start_str, hours):
        from datetime import datetime, timedelta

        fmt = "%H:%M"
        start = datetime.strptime(start_str, fmt)
        end = start + timedelta(hours=hours)
        return end.strftime(fmt)
    
    def remove_employee(self, employee):
        self.schedule.remove_employee(employee)