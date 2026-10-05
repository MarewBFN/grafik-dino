"""Wniosek urlopowy (logic/leave_requests.py::LeaveRequest) jako strona A4 -
ten sam rysunek dla podglądu w oknie "Wnioski urlopowe"
(ui/leave_requests_dialog.py, render_leave_request_image) i dla zapisu do
PDF (export_leave_requests_to_pdf, jeden wniosek na stronę).

Układ strony:
- prawy górny róg: "<miejscowość>, dnia <data wygenerowania>" (miejscowość
  firmy pracownika, a bez niej - kropkowana linia),
- lewa strona, niżej: dane pracownika (imię i nazwisko, adres) z danych
  osobowych pracownika - brakujące pola jako kropkowana linia do wpisania
  ręcznie,
- prawa strona, niżej: dane firmy pracownika (Plik -> "Dane firmy",
  Employee.company_key) - bez przypisanej firmy kropkowane linie,
- treść wniosku z wcięciem na początku akapitu,
- prawa strona, na dole: kropkowana linia na podpis z podpisem
  "podpis pracownika" pod spodem."""

from datetime import date

from PySide6.QtCore import QMarginsF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen

# Liczba kropkowanych linii zamiast danych firmy, gdy pracownik nie ma
# przypisanej firmy (nazwa, adres, kod pocztowy i miejscowość).
_EMPTY_COMPANY_LINES = 3
_PLACE_DOTS = "." * 24

PAGE_WIDTH_MM = 210.0
PAGE_HEIGHT_MM = 297.0
_MARGIN_MM = 25.0
_RIGHT_COLUMN_MM = 115.0
_INDENT_MM = 12.5
_FONT_PT = 11.5
_SMALL_FONT_PT = 9.0
_PDF_DPI = 300


def format_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def leave_request_text(request) -> str:
    return (
        "Proszę o udzielenie urlopu wypoczynkowego od dnia "
        f"{format_date(request.start_date)} do dnia {format_date(request.end_date)}."
    )


def _employee_lines(employee) -> list[str | None]:
    """None = pole niepodane, rysowane jako kropkowana linia."""
    full_name = f"{employee.first_name} {employee.last_name}".strip()
    town = " ".join(part for part in (employee.postal_code, employee.city) if part)
    return [full_name or None, employee.street or None, town or None]


def company_for(request, companies):
    """Firma pracownika z wniosku albo None (brak przypisania/usunięta)."""
    if not companies:
        return None
    return companies.get(request.employee.company_key)


def _company_lines(company) -> list[str | None]:
    """Linie bloku firmy; None = kropkowana linia do wpisania ręcznie."""
    if company is None:
        return [None] * _EMPTY_COMPANY_LINES
    lines = [company.name, company.street or None, company.town() or None]
    if company.nip:
        lines.append(f"NIP: {company.nip}")
    if company.phone:
        lines.append(f"tel. {company.phone}")
    if company.email:
        lines.append(company.email)
    return lines


def _font(painter, point_size: float, bold: bool = False) -> QFont:
    font = QFont(painter.font())
    font.setPointSizeF(point_size)
    font.setBold(bold)
    return font


def _wrap(text: str, metrics: QFontMetricsF, first_width: float, width: float) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        limit = first_width if not lines else width
        if current and metrics.horizontalAdvance(candidate) > limit:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def draw_leave_request(painter: QPainter, request, generated_on: date, unit: float, company=None) -> None:
    """Rysuje cały wniosek; `unit` = liczba jednostek urządzenia na 1 mm,
    `company` - firma pracownika (model.company.Company) albo None."""

    def mm(value: float) -> float:
        return value * unit

    left = mm(_MARGIN_MM)
    right = mm(PAGE_WIDTH_MM - _MARGIN_MM)
    right_column = mm(_RIGHT_COLUMN_MM)
    text_pen = QPen(QColor("black"))
    dotted_pen = QPen(QColor("black"), max(1.0, mm(0.25)), Qt.DotLine)

    painter.setFont(_font(painter, _FONT_PT))
    metrics = QFontMetricsF(painter.font())
    line_height = metrics.height() * 1.35

    def dotted_line(x1: float, x2: float, baseline: float) -> None:
        painter.setPen(dotted_pen)
        painter.drawLine(QPointF(x1, baseline), QPointF(x2, baseline))
        painter.setPen(text_pen)

    painter.setPen(text_pen)

    # Miejscowość i data - prawy górny róg.
    top = mm(_MARGIN_MM)
    painter.drawText(
        QRectF(left, top, right - left, line_height),
        Qt.AlignRight | Qt.AlignVCenter,
        f"{(company.city if company is not None else '') or _PLACE_DOTS}, dnia {format_date(generated_on)}",
    )

    # Dane pracownika - lewa strona, poniżej daty.
    y = top + line_height * 2.5
    for line in _employee_lines(request.employee):
        if line is None:
            dotted_line(left, left + mm(70), y + line_height * 0.8)
        else:
            painter.drawText(QRectF(left, y, right_column - left, line_height), Qt.AlignLeft | Qt.AlignVCenter, line)
        y += line_height

    # Dane firmy - prawa strona, niżej.
    y += line_height * 1.5
    for line in _company_lines(company):
        if line is None:
            dotted_line(right_column, right, y + line_height * 0.8)
            y += line_height
            continue
        # Długa nazwa/adres firmy nie mieści się w prawej kolumnie - zawijamy.
        for part in _wrap(line, metrics, right - right_column, right - right_column):
            painter.drawText(QRectF(right_column, y, right - right_column, line_height), Qt.AlignLeft | Qt.AlignVCenter, part)
            y += line_height

    # Treść wniosku, z wcięciem pierwszego wiersza.
    y += line_height * 3
    width = right - left
    for index, line in enumerate(_wrap(leave_request_text(request), metrics, width - mm(_INDENT_MM), width)):
        x = left + (mm(_INDENT_MM) if index == 0 else 0)
        painter.drawText(QRectF(x, y, right - x, line_height), Qt.AlignLeft | Qt.AlignVCenter, line)
        y += line_height

    # Podpis - wycentrowany w prawej kolumnie.
    y += line_height * 4
    signature_width = mm(60)
    signature_left = right_column + ((right - right_column) - signature_width) / 2
    dotted_line(signature_left, signature_left + signature_width, y)
    painter.setFont(_font(painter, _SMALL_FONT_PT))
    painter.drawText(
        QRectF(right_column, y + mm(1), right - right_column, line_height),
        Qt.AlignHCenter | Qt.AlignTop,
        "podpis pracownika",
    )


def render_leave_request_image(request, generated_on: date, width_px: int = 620, companies=None) -> QImage:
    """Podgląd wniosku jako obraz strony A4 o szerokości `width_px`."""
    height_px = round(width_px * PAGE_HEIGHT_MM / PAGE_WIDTH_MM)
    image = QImage(width_px, height_px, QImage.Format_RGB32)
    # DPI obrazu dobrane do szerokości strony - dzięki temu rozmiary czcionek
    # w punktach wychodzą w tych samych proporcjach co w PDF.
    dots_per_meter = round(width_px / (PAGE_WIDTH_MM / 1000))
    image.setDotsPerMeterX(dots_per_meter)
    image.setDotsPerMeterY(dots_per_meter)
    image.fill(QColor("white"))

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    draw_leave_request(painter, request, generated_on, width_px / PAGE_WIDTH_MM, company_for(request, companies))
    painter.end()
    return image


def export_leave_requests_to_pdf(requests, path: str, generated_on: date, companies=None) -> bool:
    """Zapisuje wnioski do jednego pliku PDF, każdy na osobnej stronie A4."""
    if not requests:
        return False

    writer = QPdfWriter(path)
    writer.setResolution(_PDF_DPI)
    writer.setPageLayout(QPageLayout(
        QPageSize(QPageSize.A4), QPageLayout.Portrait, QMarginsF(0, 0, 0, 0), QPageLayout.Millimeter,
    ))
    writer.setTitle("Wnioski urlopowe")

    painter = QPainter(writer)
    if not painter.isActive():
        return False
    unit = _PDF_DPI / 25.4
    for index, request in enumerate(requests):
        if index:
            writer.newPage()
        draw_leave_request(painter, request, generated_on, unit, company_for(request, companies))
    painter.end()
    return True
