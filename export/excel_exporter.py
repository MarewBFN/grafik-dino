from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
import calendar


def export_schedule_to_excel(schedule, year, month, path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Grafik"

    days_in_month = calendar.monthrange(year, month)[1]
    weekdays = ["Pn", "Wt", "Śr", "Cz", "Pt", "So", "Nd"]

    # =========================
    # NAGŁÓWEK
    # =========================
    ws.cell(row=1, column=1, value="Pracownik")

    for day in range(1, days_in_month + 1):
        wd = calendar.weekday(year, month, day)
        ws.cell(
            row=1,
            column=day + 1,
            value=f"{weekdays[wd]} {day}"
        )

    ws.cell(row=1, column=days_in_month + 2, value="H")

    # style nagłówka
    for col in range(1, days_in_month + 3):
        c = ws.cell(row=1, column=col)
        c.font = Font(bold=True)
        c.alignment = Alignment(horizontal="center")

    # =========================
    # DANE
    # =========================
    start_row = 2

    for r, emp in enumerate(schedule.employees):
        row = start_row + r
        ws.cell(row=row, column=1, value=emp.display_name())

        for day in range(1, days_in_month + 1):
            ds = schedule.get_day(emp, day)
            s, e, t = ds.as_rows()

            ws.cell(row=row, column=day + 1, value=f"{s}\n{e}\n{t}")
            ws.cell(row=row, column=day + 1).alignment = Alignment(wrap_text=True)

        ws.cell(
            row=row,
            column=days_in_month + 2,
            value=schedule.total_hours_for_employee(emp)
        )

    # =========================
    # SIZING
    # =========================
    ws.column_dimensions["A"].width = 22

    for col in range(2, days_in_month + 3):
        ws.column_dimensions[get_column_letter(col)].width = 12

    wb.save(path)
