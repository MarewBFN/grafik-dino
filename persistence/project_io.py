import json
from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig


def save_project(path, schedule: MonthSchedule, shop_config: ShopConfig):
    data = {
        "schedule": schedule.to_dict(),
        "shop_config": shop_config.to_dict()
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_project(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    schedule = MonthSchedule.from_dict(data["schedule"])
    shop_config = ShopConfig.from_dict(data["shop_config"])

    return schedule, shop_config
