import calendar
from PIL import Image, ImageDraw, ImageFont


def export_schedule_to_image(schedule, year, month, path):
    days = calendar.monthrange(year, month)[1]
    employees = schedule.employees

    NAME_COL_W = 200
    LBL_COL_W = 40
    CELL_W = 60
    CELL_H = 25
    HEADER_H = 120
    FOOTER_H = 180

    width = NAME_COL_W + LBL_COL_W + (days * CELL_W) + 20
    height = HEADER_H + (len(employees) * CELL_H * 3) + FOOTER_H

    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    try:
        font_r = ImageFont.truetype("arial.ttf", 14)
        font_b = ImageFont.truetype("arial.ttf", 16)
        font_sm = ImageFont.truetype("arial.ttf", 12)
    except:
        font_r = ImageFont.load_default()
        font_b = font_r
        font_sm = font_r

    C_GRID = (160, 160, 160)
    C_TEXT = (0, 0, 0)
    C_HEADER_BG = (245, 245, 245)
    C_WEEKEND_BG = (230, 230, 230)

    # HEADER
    draw.text((200, 30), f"Grafik planowany: {month:02d}/{year}", fill=C_TEXT, font=font_b)
    draw.rectangle([0, HEADER_H - 60, width, HEADER_H], fill=C_HEADER_BG, outline=C_GRID, width=1)
    draw.text((10, HEADER_H - 45), "Nazwisko i imię", fill=C_TEXT, font=font_b)

    for d in range(1, days + 1):
        x = NAME_COL_W + LBL_COL_W + (d - 1) * CELL_W
        wd = calendar.weekday(year, month, d)

        # weekend tylko w headerze (a nie cała kolumna)
        if wd >= 5:
            draw.rectangle([x, HEADER_H - 60, x + CELL_W, HEADER_H], fill=C_WEEKEND_BG)

        draw.rectangle([x, HEADER_H - 60, x + CELL_W, HEADER_H - 30], outline=C_GRID)
        draw.text((x + 20, HEADER_H - 55), str(d), fill=C_TEXT, font=font_b)

        draw.rectangle([x, HEADER_H - 30, x + CELL_W, HEADER_H], outline=C_GRID)
        draw.text((x + 12, HEADER_H - 25), ["Pn", "Wt", "Śr", "Cz", "Pt", "So", "Nd"][wd], fill=C_TEXT, font=font_r)

    total_m_hours = 0
    total_m_leave = 0

    y_off = HEADER_H

    for emp in employees:
        draw.rectangle([0, y_off, NAME_COL_W, y_off + 3 * CELL_H], outline=C_GRID)
        draw.text((10, y_off + CELL_H), emp.display_name(), fill=C_TEXT, font=font_b)

        for i, lbl in enumerate(["od", "do", "h"]):
            draw.rectangle(
                [NAME_COL_W, y_off + i * CELL_H, NAME_COL_W + LBL_COL_W, y_off + (i + 1) * CELL_H],
                outline=C_GRID
            )
            draw.text((NAME_COL_W + 10, y_off + i * CELL_H + 5), lbl, fill=C_TEXT, font=font_r)

        for d in range(1, days + 1):
            x = NAME_COL_W + LBL_COL_W + (d - 1) * CELL_W
            ds = schedule.get_day(emp, d)

            for i in range(3):
                draw.rectangle([x, y_off + i * CELL_H, x + CELL_W, y_off + (i + 1) * CELL_H], outline=C_GRID)

            if ds.is_leave:
                draw.text((x + 10, y_off + CELL_H), "URL", fill=(200, 0, 0), font=font_b)
                total_m_leave += emp.daily_hours  # tylko gdy faktycznie urlop

            elif not ds.is_empty():
                draw.text((x + 8, y_off + 5), str(ds.start), fill=C_TEXT, font=font_r)
                draw.text((x + 8, y_off + CELL_H + 5), str(ds.end), fill=C_TEXT, font=font_r)
                draw.text((x + 12, y_off + 2 * CELL_H + 5), ds.total_as_str(), fill=C_TEXT, font=font_r)

                total_m_hours += ds.total_duration().total_seconds() / 3600

        y_off += 3 * CELL_H

    # FOOTER
    draw.rectangle([0, y_off, width, y_off + FOOTER_H], fill=C_HEADER_BG, outline=C_GRID, width=1)

    f_labels = [
        "Godziny pracy",
        "Urlop wypoczynkowy",
        "Inne nieobecności",
        "RAZEM GODZINY"
    ]

    total_hours = int(total_m_hours)
    total_leave = int(total_m_leave)

    f_values = [
        f"{total_hours}:00",
        f"{total_leave}:00",
        "0:00",
        f"{total_hours + total_leave}:00"
    ]

    val_y = y_off + 20
    for i in range(4):
        draw.text((100, val_y), f_labels[i], fill=C_TEXT, font=font_b)
        draw.text((width // 2, val_y), f_values[i], fill=C_TEXT, font=font_r)
        val_y += 35

    img.save(path, "JPEG", quality=95)
    return True