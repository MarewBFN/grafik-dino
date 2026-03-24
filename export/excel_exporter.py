import calendar
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

def export_schedule_to_excel(schedule, year, month, path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Grafik"

    days_in_month = calendar.monthrange(year, month)[1]
    weekdays = ["Pn", "Wt", "Śr", "Cz", "Pt", "So", "Nd"]

    # Style
    fill_weekend = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
    align_center = Alignment(horizontal="center", vertical="center")
    border_thin = Border(left=Side(style='thin'), right=Side(style='thin'),
                         top=Side(style='thin'), bottom=Side(style='thin'))

    # NAGŁÓWEK
    ws.merge_cells("A1:B2")
    ws.cell(row=1, column=1, value="Nazwisko i imię").alignment = align_center
    
    # Nagłówki dni
    for day in range(1, days_in_month + 1):
        col = day + 2
        wd = calendar.weekday(year, month, day)
        ws.cell(row=1, column=col, value=day).alignment = align_center
        ws.cell(row=2, column=col, value=weekdays[wd]).alignment = align_center
        if wd >= 5:
            ws.cell(row=1, column=col).fill = fill_weekend
            ws.cell(row=2, column=col).fill = fill_weekend

    # NAGŁÓWKI PODSUMOWANIA (ostatnie kolumny)
    sum_col_start = days_in_month + 3
    sum_labels = ["Godziny pracy", "Urlop", "Inne", "RAZEM"]
    for i, lbl in enumerate(sum_labels):
        col = sum_col_start + i
        ws.merge_cells(start_row=1, start_column=col, end_row=2, end_column=col)
        c = ws.cell(row=1, column=col, value=lbl)
        c.alignment = Alignment(textRotation=90, horizontal="center", vertical="center")
        c.font = Font(bold=True)

    # DANE PRACOWNIKÓW
    cur_row = 3
    for emp in schedule.employees:
        # Scalone nazwisko
        ws.merge_cells(start_row=cur_row, start_column=1, end_row=cur_row+2, end_column=1)
        name_cell = ws.cell(row=cur_row, column=1, value=emp.display_name())
        name_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        name_cell.font = Font(bold=True)

        for i, lbl in enumerate(["od", "do", "h"]):
            ws.cell(row=cur_row + i, column=2, value=lbl).alignment = align_center

        # Dni miesiąca
        for day in range(1, days_in_month + 1):
            col = day + 2
            ds = schedule.get_day(emp, day)
            wd = calendar.weekday(year, month, day)
            
            cells = [ws.cell(row=cur_row + i, column=col) for i in range(3)]
            for c in cells:
                c.alignment = align_center
                if wd >= 5: c.fill = fill_weekend

            if ds.is_leave:
                ws.merge_cells(start_row=cur_row, start_column=col, end_row=cur_row+2, end_column=col)
                cells[0].value = "URL"
            elif not ds.is_empty():
                cells[0].value = ds.start
                cells[1].value = ds.end
                cells[2].value = ds.total_as_str()

        # PODSUMOWANIE W WIERSZU (na prawo)
        # Godziny pracy (suma h)
        ws.merge_cells(start_row=cur_row, start_column=sum_col_start, end_row=cur_row+2, end_column=sum_col_start)
        ws.cell(row=cur_row, column=sum_col_start, value=schedule.total_hours_for_employee(emp)).alignment = align_center
        
        # Urlop
        ws.merge_cells(start_row=cur_row, start_column=sum_col_start+1, end_row=cur_row+2, end_column=sum_col_start+1)
        ws.cell(row=cur_row, column=sum_col_start+1, value=schedule.leave_hours_for_employee(emp)).alignment = align_center
        
        # Inne (na razie 0)
        ws.merge_cells(start_row=cur_row, start_column=sum_col_start+2, end_row=cur_row+2, end_column=sum_col_start+2)
        ws.cell(row=cur_row, column=sum_col_start+2, value="0").alignment = align_center
        
        # RAZEM
        ws.merge_cells(start_row=cur_row, start_column=sum_col_start+3, end_row=cur_row+2, end_column=sum_col_start+3)
        ws.cell(row=cur_row, column=sum_col_start+3, value=schedule.total_with_leave_for_employee(emp)).alignment = align_center

        cur_row += 3

    # Krawędzie i szerokości
    ws.column_dimensions["A"].width = 25
    ws.column_dimensions["B"].width = 5
    for col_idx in range(1, sum_col_start + 4):
        col_ltr = get_column_letter(col_idx)
        if col_idx > 2: ws.column_dimensions[col_ltr].width = 6
        for r_idx in range(1, cur_row):
            ws.cell(row=r_idx, column=col_idx).border = border_thin

    wb.save(path)