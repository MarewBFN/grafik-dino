import calendar
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont


class ImageScheduleExporter:
    def __init__(self, schedule, year, month):
        self.schedule = schedule
        self.year = year
        self.month = month

        self.days = calendar.monthrange(year, month)[1]
        self.employees = schedule.employees

        self.NAME_W = 220
        self.LABEL_W = 40
        self.CELL_W = 55
        self.CELL_H = 22

        self.HEADER_H = 140
        self.FOOTER_H = 100

        self.width = self.NAME_W + self.LABEL_W + self.days * self.CELL_W + 4 * 80
        self.height = self.HEADER_H + len(self.employees) * 3 * self.CELL_H + self.FOOTER_H

        self.img = Image.new("RGB", (self.width, self.height), "white")
        self.draw = ImageDraw.Draw(self.img)

        try:
            self.font = ImageFont.truetype("arial.ttf", 14)
            self.font_b = ImageFont.truetype("arial.ttf", 20)  # +2
        except:
            self.font = ImageFont.load_default()
            self.font_b = self.font

        self.GRID = (0, 0, 0)
        self.SATURDAY = (225, 225, 225)
        self.SUNDAY = (200, 200, 200)

    def export(self, path):
        self._draw_header()
        self._draw_table()
        self.img.save(path, "JPEG", quality=95)

    # ================= HEADER =================

    def _draw_header(self):
        x_base = int(self.width * 0.25)

        self.draw.text(
            (x_base, 20),
            f"Grafik planowany {self.month:02d}/{self.year}",
            fill=(0, 0, 0),
            font=self.font_b
        )

        self.draw.text(
            (x_base + 300, 20),
            f"Komórka:",
            fill=(0, 0, 0),
            font=self.font_b
        )

        right_x = self.width - 260

        self.draw.text((right_x, 10), "Wydruk wewnętrzny", fill=(0, 0, 0), font=self.font_b)
        self.draw.text((right_x, 35), f"Data: {datetime.now().strftime('%d/%m/%Y')}", fill=(0, 0, 0), font=self.font_b)
        self.draw.text((right_x, 60), "Wygenerowany w Dingo", fill=(0, 0, 0), font=self.font)

    # ================= TABLE =================

    def _draw_table(self):
        y = self.HEADER_H
        start_x = self.NAME_W + self.LABEL_W

        center = start_x + (self.days * self.CELL_W) // 2
        self._draw_centered_text(center, y - 60, "Dni miesiąca", self.font_b)

        table_bottom = self.HEADER_H + len(self.employees) * 3 * self.CELL_H

        for d in range(1, self.days + 1):
            x = start_x + (d - 1) * self.CELL_W
            wd = calendar.weekday(self.year, self.month, d)

            color = self.SUNDAY if wd == 6 else self.SATURDAY if wd == 5 else None
            if color:
                self.draw.rectangle([x, y - 40, x + self.CELL_W, table_bottom], fill=color)

            self.draw.rectangle([x, y - 40, x + self.CELL_W, y - 20], outline=self.GRID)
            self.draw.text((x + self.CELL_W // 2, y - 30), str(d), fill=(0, 0, 0), font=self.font, anchor="mm")

            self.draw.rectangle([x, y - 20, x + self.CELL_W, y], outline=self.GRID)
            self.draw.text(
                (x + self.CELL_W // 2, y - 10),
                ["Pn", "Wt", "Śr", "Cz", "Pt", "S", "N"][wd],
                fill=(0, 0, 0),
                font=self.font,
                anchor="mm"
            )

        summary_x = start_x + self.days * self.CELL_W
        headers = ["Godziny", "Urlop", "L4", "Razem"]

        for i, h in enumerate(headers):
            x = summary_x + i * 80
            self._draw_centered_text(x + 40, y - 40, h, self.font)

        for emp in self.employees:
            self._draw_employee(emp, y)
            y += 3 * self.CELL_H

    # ================= EMPLOYEE =================

    def _draw_employee(self, emp, y):
        self.draw.rectangle([0, y, self.NAME_W, y + 3 * self.CELL_H], outline=self.GRID)
        self._draw_centered_text(self.NAME_W // 2, y + self.CELL_H, emp.display_name(), self.font)

        for i, txt in enumerate(["od", "do", "h"]):
            self.draw.rectangle(
                [self.NAME_W, y + i * self.CELL_H, self.NAME_W + self.LABEL_W, y + (i + 1) * self.CELL_H],
                outline=self.GRID
            )
            self._draw_centered_text(self.NAME_W + self.LABEL_W // 2, y + i * self.CELL_H + 5, txt, self.font)

        for d in range(1, self.days + 1):
            x = self.NAME_W + self.LABEL_W + (d - 1) * self.CELL_W
            ds = self.schedule.get_day(emp, d)

            if ds.is_leave:
                self.draw.rectangle([x, y, x + self.CELL_W, y + 3 * self.CELL_H], outline=self.GRID)
                self._draw_centered_text(x + self.CELL_W // 2, y + self.CELL_H, "URL", self.font_b)
                continue

            if getattr(ds, "is_sick", False):
                self.draw.rectangle([x, y, x + self.CELL_W, y + 3 * self.CELL_H], outline=self.GRID)
                self._draw_centered_text(x + self.CELL_W // 2, y + self.CELL_H, "L4", self.font_b)
                continue

            self.draw.rectangle([x, y, x + self.CELL_W, y + 3 * self.CELL_H], outline=self.GRID)

            if not ds.is_empty():
                mid_y = y + 2 * self.CELL_H
                self.draw.line([x + 10, mid_y, x + self.CELL_W - 10, mid_y], fill=self.GRID)

                self.draw.text((x + self.CELL_W // 2, y + self.CELL_H // 2), self._format_hour(ds.start), fill=(0, 0, 0), font=self.font, anchor="mm")
                self.draw.text((x + self.CELL_W // 2, y + self.CELL_H + self.CELL_H // 2), self._format_hour(ds.end), fill=(0, 0, 0), font=self.font, anchor="mm")
                self.draw.text((x + self.CELL_W // 2, y + 2 * self.CELL_H + self.CELL_H // 2), ds.total_as_str(), fill=(0, 0, 0), font=self.font, anchor="mm")

        summary_x = self.NAME_W + self.LABEL_W + self.days * self.CELL_W

        total = self.schedule.total_hours_for_employee(emp)
        leave = self.schedule.leave_hours_for_employee(emp)
        sick = self.schedule.sick_hours_for_employee(emp)
        sum_all = self.schedule.total_with_leave_and_sick_for_employee(emp)

        values = [total, leave, sick, sum_all]

        for i, val in enumerate(values):
            x = summary_x + i * 80
            self.draw.rectangle([x, y, x + 80, y + 3 * self.CELL_H], outline=self.GRID)
            self._draw_centered_text(x + 40, y + self.CELL_H, str(val), self.font)

    # ================= UTILS =================

    def _format_hour(self, time_str):
        if not time_str:
            return ""
        if time_str.endswith(":00"):
            return str(int(time_str.split(":")[0]))
        return time_str

    def _draw_centered_text(self, x, y, text, font):
        bbox = self.draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        self.draw.text((x - w // 2, y - h // 2), text, fill=(0, 0, 0), font=font)


def export_schedule_to_image(schedule, year, month, path):
    exporter = ImageScheduleExporter(schedule, year, month)
    exporter.export(path)
    return True