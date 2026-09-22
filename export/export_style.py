"""Wybór wyglądu eksportu/wydruku wg profilu działalności projektu.

Dino ma dziś jedyny, w pełni dopracowany wygląd eksportu
(`export/image_exporter.py`, `export/excel_exporter.py`) - dla każdego
innego profilu (np. "Ochrona") używamy osobnego, budowanego od zera
modułu (`export/security_image_exporter.py`,
`export/security_excel_exporter.py`), żeby zmiany w jednym wyglądzie
nigdy nie ruszały drugiego. Wybór jest w pełni automatyczny wg
`ShopConfig.business_type` - ten sam podział co istniejący `is_retail`
w `ui/main_window.py` (Rano/Popo widoczne tylko dla Dino), tylko
wydzielony do jednego miejsca zamiast kopiowany w każdym eksporterze.
"""

from model.business_profile import DEFAULT_BUSINESS_TYPE


def is_dino_style(shop) -> bool:
    """`shop` bywa `None` (część wywołań eksportu, głównie w testach, nie
    przekazuje ShopConfig) - liczy się wtedy jak Dino, tak jak działało to
    zanim ten mechanizm istniał."""
    business_type = shop.business_type if shop is not None else DEFAULT_BUSINESS_TYPE
    return business_type == DEFAULT_BUSINESS_TYPE


def render_schedule_image(schedule, year, month, shop=None, employees=None):
    """Renderuje grafik do obrazu (PIL Image), bez zapisu do pliku - ten
    sam wybór stylu co `is_dino_style()`. Współdzielone przez
    `export_schedule_to_image`/`export_schedule_to_pdf` (oba tylko
    zapisują ten gotowy obraz w innym formacie) oraz przez podgląd przed
    eksportem (`ui/export_preview_dialog.py`), żeby podgląd był dokładnie
    tym, co trafi do pliku."""
    from export.image_exporter import ImageScheduleExporter
    from export.security_image_exporter import SecurityScheduleImageExporter

    exporter_cls = ImageScheduleExporter if is_dino_style(shop) else SecurityScheduleImageExporter
    return exporter_cls(schedule, year, month, shop=shop, employees=employees).render()
