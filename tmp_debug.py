from tests.stress_test_generator import build_scenario
from logic.auto_generator import AutoScheduleGenerator
from model.constraints import ConstraintEngine

for emp_count in [3]:
    for seed in range(1):
        scenario, schedule, shop = build_scenario(emp_count, seed)
        gen = AutoScheduleGenerator(schedule, shop)
        res = gen.generate(trace_output_path=None)
        print('scenario', emp_count, seed, res['status'], res['success'], res['wall_time'])
        for emp in schedule.employees:
            total = schedule.total_hours_for_employee(emp)
            print(emp.display_name(), 'hours', total)
        print('violations', [v.type for v in ConstraintEngine.evaluate(schedule, shop)])
        print('---')
