"""Eksport całego grafiku (cała załoga) do PDF - jedna strona.

Celowo bez własnego layoutu: korzysta z tego samego renderowania co JPG
(`export/export_style.py::render_schedule_image` - `ImageScheduleExporter`
dla Dino, `SecurityScheduleImageExporter` dla pozostałych profili, ten sam
podział co `export_schedule_to_image`), tylko zapisuje gotowy obraz jako
PDF zamiast JPEG. Pillow robi to natywnie, więc nie ma tu żadnej nowej
logiki rysowania do utrzymania - zmiana wyglądu JPG automatycznie zmienia
wygląd PDF.
"""

from export.export_style import render_schedule_image


def export_schedule_to_pdf(schedule, year, month, path, shop=None, employees=None):
    image = render_schedule_image(schedule, year, month, shop=shop, employees=employees)
    image.save(path, "PDF", resolution=150.0)
    return True
