"""Eksport całego grafiku (cała załoga) do PDF - jedna strona.

Celowo bez własnego layoutu: korzysta z tego samego renderowania co JPG
(`export/image_exporter.py::ImageScheduleExporter` dla Dino,
`export/security_image_exporter.py::SecurityScheduleImageExporter` dla
pozostałych profili - ten sam podział co `export_schedule_to_image`),
tylko zapisuje gotowy obraz jako PDF zamiast JPEG. Pillow robi to
natywnie, więc nie ma tu żadnej nowej logiki rysowania do utrzymania -
zmiana wyglądu JPG automatycznie zmienia wygląd PDF.
"""

from export.export_style import is_dino_style
from export.image_exporter import ImageScheduleExporter
from export.security_image_exporter import SecurityScheduleImageExporter


def export_schedule_to_pdf(schedule, year, month, path, shop=None, employees=None):
    exporter_cls = ImageScheduleExporter if is_dino_style(shop) else SecurityScheduleImageExporter
    exporter = exporter_cls(schedule, year, month, shop=shop, employees=employees)
    image = exporter.render()
    image.save(path, "PDF", resolution=150.0)
    return True
