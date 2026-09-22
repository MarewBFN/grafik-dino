"""Eksport JPG dla profili innych niż Dino (np. "Ochrona") - zbudowany od
zera, niezależnie od `export/image_exporter.py`, żeby przyszłe zmiany w
wyglądzie Ochrony nigdy nie ruszały wyglądu Dino (i odwrotnie).

To jest na razie prosty, działający układ tabeli (dni miesiąca w
kolumnach, pracownicy w wierszach - jedyny sensowny układ dla
MonthSchedule/DaySchedule, niezależny od profilu), bez brandingu Dino.
Docelowy wygląd dla Ochrony (per-posterunek, rotacja 24/7...) czeka na
wymagania klienta - patrz "plan profil ochrona (analiza specyfikacji
klienta).md".
"""

import calendar
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

from logic.monthly_hours_status import monthly_hours_status

_OVERTIME_COLOR = (204, 0, 0)


class SecurityScheduleImageExporter:
    def __init__(self, schedule, year, month, shop=None, employees=None):
        self.schedule = schedule
        self.year = year
        self.month = month
        self.shop = shop

        self.days = calendar.monthrange(year, month)[1]
        self.employees = employees if employees is not None else schedule.employees

        self.NAME_W = 220
        self.LABEL_W = 40
        self.CELL_W = 55
        self.CELL_H = 22

        self.HEADER_H = 100
        self.FOOTER_H = 60

        self.width = self.NAME_W + self.LABEL_W + self.days * self.CELL_W + 5 * 80
        self.height = self.HEADER_H + len(self.employees) * 3 * self.CELL_H + self.FOOTER_H

        self.img = Image.new("RGB", (self.width, self.height), "white")
        self.draw = ImageDraw.Draw(self.img)

        try:
            self.font = ImageFont.truetype("arial.ttf", 14)
            self.font_b = ImageFont.truetype("arial.ttf", 20)
        except Exception:
            self.font = ImageFont.load_default()
            self.font_b = self.font

        self.GRID = (0, 0, 0)
        self.SATURDAY = (225, 225, 225)
        self.SUNDAY = (200, 200, 200)

    def render(self):
        """Rysuje grafik i zwraca gotowy obraz - bez zapisu, żeby ten sam
        render mógł posłużyć zarówno JPG (`export`), jak i PDF
        (`export/pdf_exporter.py`) bez powielania logiki rysowania."""
        self._draw_header()
        self._draw_table()
        return self.img

    def export(self, path):
        self.render()
        self.img.save(path, "JPEG", quality=95)

    # ================= HEADER =================

    def _draw_header(self):
        name = self.shop.name if self.shop is not None and getattr(self.shop, "name", "") else ""
        title = f"Grafik {self.month:02d}/{self.year}" + (f" - {name}" if name else "")

        self.draw.text((20, 15), title, fill=(0, 0, 0), font=self.font_b)

        right_x = self.width - 220
        self.draw.text(
            (right_x, 15),
            f"Data wydruku: {datetime.now().strftime('%d/%m/%Y')}",
            fill=(0, 0, 0),
            font=self.font,
        )

    # ================= TABLE =================

    def _draw_table(self):
        y = self.HEADER_H
        start_x = self.NAME_W + self.LABEL_W

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
                anchor="mm",
            )

        summary_x = start_x + self.days * self.CELL_W
        headers = ["Godziny", "Urlop", "L4", "Razem", "Nadgodziny"]

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
                outline=self.GRID,
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

                # Bez znacznika "+1" dla zmian nocnych - usunięty całkiem na
                # życzenie użytkownika.
                end_text = self._format_hour(ds.end)

                self.draw.text((x + self.CELL_W // 2, y + self.CELL_H // 2), self._format_hour(ds.start), fill=(0, 0, 0), font=self.font, anchor="mm")
                self.draw.text((x + self.CELL_W // 2, y + self.CELL_H + self.CELL_H // 2), end_text, fill=(0, 0, 0), font=self.font, anchor="mm")
                self.draw.text((x + self.CELL_W // 2, y + 2 * self.CELL_H + self.CELL_H // 2), ds.total_as_str(), fill=(0, 0, 0), font=self.font, anchor="mm")

        summary_x = self.NAME_W + self.LABEL_W + self.days * self.CELL_W

        total = self.schedule.total_hours_for_employee(emp)
        leave = self.schedule.leave_hours_for_employee(emp)
        sick = self.schedule.sick_hours_for_employee(emp)
        sum_all = self.schedule.total_with_leave_and_sick_for_employee(emp)

        hours_status = self.shop is not None and monthly_hours_status(self.schedule, self.shop, emp)
        is_over = bool(hours_status and hours_status["is_over"])
        over_minutes = hours_status["over_minutes"] if hours_status else 0
        overtime_str = f"{over_minutes // 60}:{over_minutes % 60:02d}"

        values = [total, leave, sick, sum_all, overtime_str]

        for i, val in enumerate(values):
            x = summary_x + i * 80
            self.draw.rectangle([x, y, x + 80, y + 3 * self.CELL_H], outline=self.GRID)
            fill = _OVERTIME_COLOR if (i in (0, 4) and is_over) else (0, 0, 0)
            self._draw_centered_text(x + 40, y + self.CELL_H, str(val), self.font, fill=fill)

    # ================= UTILS =================

    def _format_hour(self, time_str):
        if not time_str:
            return ""
        if time_str.endswith(":00"):
            return str(int(time_str.split(":")[0]))
        return time_str

    def _draw_centered_text(self, x, y, text, font, fill=(0, 0, 0)):
        bbox = self.draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        self.draw.text((x - w // 2, y - h // 2), text, fill=fill, font=font)


def export_security_schedule_to_image(schedule, year, month, path, shop=None, employees=None):
    exporter = SecurityScheduleImageExporter(schedule, year, month, shop=shop, employees=employees)
    exporter.export(path)
    return True
