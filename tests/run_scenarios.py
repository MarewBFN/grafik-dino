import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from logic.auto_generator import AutoScheduleGenerator
from logic.generator.custom_profile_wiring import default_policies
from model.business_profile import register_custom_profile
from model.constraint_policy import ConstraintPolicy
from model.custom_profile import (
    RULE_TYPE_MIN_STAFF_WITH_ROLE,
    CustomBusinessProfile,
    RoleDefinition,
    RuleInstance,
)
from model.employee import Employee
from model.location import LocationConfig
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

# Etap G planu zmian nocnych: profil 24/7 (bez OPEN/CLOSE) z lokalizacją
# posiadającą night_shift i regułą "min. 2 ochroniarzy w nocy" - sprawdza
# feasibility i brak nakładających się zmian dla scenariusza, który jest
# powodem całej tej pracy (klient z firmy ochroniarskiej).
_night_rule = RuleInstance(
    type=RULE_TYPE_MIN_STAFF_WITH_ROLE, role_key='guard',
    policy='MANDATORY', params={'min_count': 2, 'scope': 'night'},
)
_night_profile = CustomBusinessProfile(
    key='run_scenarios_night_24_7',
    display_name='Ochrona 24/7 (run_scenarios.py)',
    roles=[RoleDefinition(key='guard', label='Ochroniarz')],
    rules=[_night_rule],
)
register_custom_profile(_night_profile)
_night_rule_key = _night_profile.rule_policy_key(_night_rule)

night_shop = ShopConfig(2026, 8)
night_shop.business_type = _night_profile.key
night_shop.constraint_policies.update(default_policies(_night_profile))
night_shop.constraint_policies[_night_rule_key] = ConstraintPolicy.MANDATORY

night_loc = LocationConfig(key='site1', name='Obiekt 24/7')
night_loc.set_night_shift('22:00', '06:00')
night_shop.locations = {'site1': night_loc}

night_schedule = MonthSchedule(2026, 8)
night_employees = [
    Employee(f'Guard{i}', 'A', location_key='site1', custom_roles={'guard': True})
    for i in range(4)
]
for emp in night_employees:
    night_schedule.add_employee(emp)

night_result = AutoScheduleGenerator(night_schedule, night_shop).generate(
    trace_output_path='trace_night_shift_24_7.json'
)
print('night_shift_24_7', night_result)
for emp in night_employees:
    nights = sum(
        1 for day in range(1, night_schedule.days_in_month + 1)
        if night_schedule.get_day(emp, day).crosses_midnight()
    )
    print(' ', emp.display_name(), night_schedule.total_hours_for_employee(emp), f'({nights} zmian nocnych)')
print()
