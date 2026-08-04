from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.auto_generator import AutoScheduleGenerator
from logic.generator.trace import build_random_scenario
from model.employee import Employee
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig


if __name__ == "__main__":
    payload = build_random_scenario(seed=11, employee_count=8, days=7, output_path=ROOT / "trace_example.json")

    shop = ShopConfig(2026, 8)
    schedule = MonthSchedule(2026, 8)

    for item in payload["employees"]:
        emp = Employee(
            first_name=item["first_name"],
            last_name=item["last_name"],
            is_opener=item["is_opener"],
            is_meat=item["is_meat"],
            no_night=item["no_night"],
            monthly_target_hours=item["monthly_target_hours"],
            daily_hours=item["daily_hours"],
            employment_fraction=item["employment_fraction"],
        )
        schedule.add_employee(emp)

    generator = AutoScheduleGenerator(schedule, shop)
    result = generator.generate(trace_output_path=ROOT / "trace_output.json")
    print(result)
