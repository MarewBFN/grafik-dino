import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from logic.auto_generator import AutoScheduleGenerator
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig

scenarios = [
    ('base', [], [], []),
    ('one_leave', [2], [], []),
    ('leave_sick', [2], [3], []),
    ('many_off', [2, 4, 6], [3, 5], [1, 7]),
]

for name, leave_days, sick_days, locked_days in scenarios:
    shop = ShopConfig(2026, 8)
    schedule = MonthSchedule(2026, 8)
    employees = [
        Employee('Kowalski', 'Jan', is_opener=True, is_meat=True, monthly_target_hours=160, daily_hours=8),
        Employee('Nowak', 'Anna', is_opener=False, is_meat=False, monthly_target_hours=160, daily_hours=8),
        Employee('Wiśniewska', 'Maria', is_opener=False, is_meat=True, monthly_target_hours=160, daily_hours=8),
        Employee('Kaczmarek', 'Piotr', is_opener=False, is_meat=False, monthly_target_hours=160, daily_hours=8),
    ]
    for emp in employees:
        schedule.add_employee(emp)
    for day in leave_days:
        schedule.get_day(employees[0], day).set_leave()
    for day in sick_days:
        schedule.get_day(employees[1], day).set_sick()
    for day in locked_days:
        ds = schedule.get_day(employees[2], day)
        ds.is_locked = True
        ds.start = '05:30'
        ds.end = '13:30'
    generator = AutoScheduleGenerator(schedule, shop)
    result = generator.generate(trace_output_path=f'trace_{name}.json')
    print(name, result)
    for emp in employees:
        print(' ', emp.display_name(), schedule.total_hours_for_employee(emp))
    print()
