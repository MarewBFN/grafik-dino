import calendar
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

CODE_LABELS = {
    "1": "1",
    "2": "2",
    "W": "W",
}

CODE_FILL = {
    "1": (219, 234, 254),
    "2": (237, 233, 254),
    "W": (221, 228, 238),
}


class SimpleModeImageExporter:
    def __init__(self, schedule, simple_data, year, month):
        self.schedule = schedule
        self.simple_data = simple_data
        self.year = year
        self.month = month

        self.days = calendar.monthrange(year, month)[1]
        self.employees = schedule.employees

        self.NAME_W = 220
        self.CELL_W = 32
        self.CELL_H = 26

        self.HEADER_H = 90
        self.FOOTER_H = 40

        self.width = self.NAME_W + self.days * self.CELL_W
        self.height = self.HEADER_H + len(self.employees) * self.CELL_H + self.FOOTER_H

        self.img = Image.new("RGB", (self.width, self.height), "white")
        self.draw = ImageDraw.Draw(self.img)

        try:
            self.font = ImageFont.truetype("arial.ttf", 13)
            self.font_b = ImageFont.truetype("arial.ttf", 18)
        except OSError:
            self.font = ImageFont.load_default()
            self.font_b = self.font

        self.GRID = (0, 0, 0)
        self.SATURDAY = (225, 225, 225)
        self.SUNDAY = (200, 200, 200)

    def export(self, path):
        self._draw_header()
        self._draw_table()
        self.img.save(path, "JPEG", quality=95)

    def _draw_header(self):
        self.draw.text(
            (20, 15),
            f"Grafik uproszczony {self.month:02d}/{self.year}",
            fill=(0, 0, 0),
            font=self.font_b,
        )
        self.draw.text(
            (20, 45),
            f"Wygenerowany w Dingo, {datetime.now().strftime('%d/%m/%Y')}",
            fill=(0, 0, 0),
            font=self.font,
        )

    def _draw_table(self):
        y = self.HEADER_H

        for d in range(1, self.days + 1):
            x = self.NAME_W + (d - 1) * self.CELL_W
            wd = calendar.weekday(self.year, self.month, d)
            color = self.SUNDAY if wd == 6 else self.SATURDAY if wd == 5 else None

            table_bottom = y + len(self.employees) * self.CELL_H
            if color:
                self.draw.rectangle([x, y, x + self.CELL_W, table_bottom], fill=color)

            self.draw.rectangle([x, y - 20, x + self.CELL_W, y], outline=self.GRID)
            self.draw.text((x + self.CELL_W // 2, y - 10), str(d), fill=(0, 0, 0), font=self.font, anchor="mm")

        for row, emp in enumerate(self.employees):
            row_y = y + row * self.CELL_H
            self.draw.rectangle([0, row_y, self.NAME_W, row_y + self.CELL_H], outline=self.GRID)
            self._draw_centered_text(self.NAME_W // 2, row_y + self.CELL_H // 2, emp.display_name(), self.font)

            for d in range(1, self.days + 1):
                x = self.NAME_W + (d - 1) * self.CELL_W
                code = self.simple_data.get(emp, d)
                fill = CODE_FILL.get(code)
                if fill:
                    self.draw.rectangle([x, row_y, x + self.CELL_W, row_y + self.CELL_H], fill=fill)
                self.draw.rectangle([x, row_y, x + self.CELL_W, row_y + self.CELL_H], outline=self.GRID)
                if code:
                    self._draw_centered_text(
                        x + self.CELL_W // 2, row_y + self.CELL_H // 2, CODE_LABELS.get(code, code), self.font_b
                    )

    def _draw_centered_text(self, x, y, text, font):
        bbox = self.draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        self.draw.text((x - w // 2, y - h // 2), text, fill=(0, 0, 0), font=font)


def export_simple_schedule_to_image(schedule, simple_data, year, month, path):
    exporter = SimpleModeImageExporter(schedule, simple_data, year, month)
    exporter.export(path)
    return True
