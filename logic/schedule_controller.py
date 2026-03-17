class ScheduleController:
    """
    Warstwa pośrednia między UI a MonthSchedule.
    Zarządza operacjami oraz historią (undo).
    """

    def __init__(self, schedule, shop_config):
        self.schedule = schedule
        self.shop_config = shop_config
        self.history = []

    # ==================================================
    # UNDO
    # ==================================================

    def snapshot(self):
        self.history.append(self.schedule.snapshot())

    def undo(self):
        if not self.history:
            return self.schedule

        self.schedule = self.history.pop()
        return self.schedule

    # ==================================================
    # DAY OPERATIONS
    # ==================================================

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

    # ==================================================
    # EMPLOYEE OPERATIONS
    # ==================================================

    def add_employee(self, emp):
        self.snapshot()
        self.schedule.add_employee(emp)

    def replace_employee(self, old, new):
        self.snapshot()
        self.schedule.replace_employee(old, new)

    # ==================================================
    # READ
    # ==================================================

    def get_day(self, emp, day):
        return self.schedule.get_day(emp, day)

    # ==================================================
    # GENERATION
    # ==================================================

    def generate_schedule(self):
        from logic.auto_generator import AutoScheduleGenerator

        generator = AutoScheduleGenerator(
            self.schedule,
            self.shop_config
        )
        generator.generate()

    def clear_schedule(self):
        self.snapshot()
        self.schedule.clear_all_days()