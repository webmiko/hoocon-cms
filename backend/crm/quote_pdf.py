"""Quote PDF generation (ЛК-3): reportlab + bundled DejaVu (Cyrillic).

The font lives in ``backend/assets/fonts/`` so the Docker image renders
Cyrillic without system fonts. Output is small (<50 KB); ``crm.quote_docs``
stores it as the client's ``ClientDocument(kind=quote_pdf)``.
"""

from __future__ import annotations

import io
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, cast

from django.conf import settings
from django.utils import timezone

if TYPE_CHECKING:
    from crm.models import Client, Quote

_FONTS_DIR = Path(settings.BASE_DIR) / "assets" / "fonts"
_KOPECK = Decimal("0.01")


def vat_amount_rub(total: Decimal, rate: Decimal) -> Decimal:
    """VAT rounded to kopecks half-up, as accountants do (not banker's rounding)."""
    return (total * rate / 100).quantize(_KOPECK, rounding=ROUND_HALF_UP)


def vat_rate_label(rate: Decimal) -> str:
    """``22.00`` → ``22``, ``12.50`` → ``12.5`` (Decimal ``:g`` keeps the zeros)."""
    return format(Decimal(rate).normalize(), "f")


@lru_cache(maxsize=1)
def _register_fonts() -> tuple[str, str]:
    """Register DejaVu regular/bold once per process; return font names."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    pdfmetrics.registerFont(TTFont("DejaVu", str(_FONTS_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(_FONTS_DIR / "DejaVuSans-Bold.ttf")))
    return "DejaVu", "DejaVu-Bold"


def _wrap(text: str, width: int = 90) -> list[str]:
    """Naive word-wrap for plain-text table cells."""
    words = (text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + len(word) + 1 <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def render_quote_pdf(quote: Quote) -> io.BytesIO:
    """Render the quote as a one-page-ish PDF (A4) and return a buffer.

    Prices appear only when at least one item has ``unit_price`` set —
    matching the «цены только в счёте» decision: a priceless quote shows
    just positions and quantities.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    font, font_bold = _register_fonts()
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    x_margin = 20 * mm
    y = height - 20 * mm

    client = cast("Client", quote.client)
    pdf.setFont(font_bold, 16)
    pdf.drawString(x_margin, y, f"Коммерческое предложение {quote.number}")
    y -= 8 * mm
    pdf.setFont(font, 10)
    pdf.drawString(x_margin, y, f"Дата: {timezone.localtime(quote.created_at):%d.%m.%Y}")
    if quote.sent_at:
        pdf.drawString(x_margin + 60 * mm, y, f"Выдано: {timezone.localtime(quote.sent_at):%d.%m.%Y}")
    if quote.valid_until:
        pdf.drawString(x_margin + 110 * mm, y, f"Действует до: {quote.valid_until:%d.%m.%Y}")
    y -= 6 * mm
    pdf.drawString(x_margin, y, f"Клиент: {client.company or client.name or client.email}")
    y -= 6 * mm
    pdf.drawString(x_margin, y, f"Контакт: {client.name} · {client.email}")
    if client.phone:
        y -= 6 * mm
        pdf.drawString(x_margin, y, f"Телефон: {client.phone}")
    y -= 10 * mm

    items = list(quote.items.select_related("sku").order_by("sort_order", "id"))
    show_prices = any(item.unit_price is not None for item in items)

    # Table header
    pdf.setFont(font_bold, 9)
    pdf.drawString(x_margin, y, "№")
    pdf.drawString(x_margin + 10 * mm, y, "Позиция")
    pdf.drawString(x_margin + 120 * mm, y, "Кол-во")
    if show_prices:
        pdf.drawString(x_margin + 140 * mm, y, "Цена, ₽")
        pdf.drawString(x_margin + 162 * mm, y, "Сумма, ₽")
    y -= 2 * mm
    pdf.line(x_margin, y, width - x_margin, y)
    y -= 5 * mm

    pdf.setFont(font, 9)
    total = 0
    for idx, item in enumerate(items, start=1):
        item_sku = item.sku
        code = item.sku_code or (item_sku.sku_code if item_sku else "—")
        name = (item_sku.name if item_sku else "") or code
        line_total = (item.unit_price or 0) * item.quantity if item.unit_price else None
        if line_total:
            total += line_total
        for line_no, line in enumerate(_wrap(f"{code} — {name}", 68)):
            if y < 25 * mm:
                pdf.showPage()
                pdf.setFont(font, 9)
                y = height - 20 * mm
            if line_no == 0:
                pdf.drawString(x_margin, y, str(idx))
                pdf.drawString(x_margin + 120 * mm, y, str(item.quantity))
                if show_prices:
                    price_text = f"{item.unit_price:.2f}" if item.unit_price is not None else "—"
                    sum_text = f"{line_total:.2f}" if line_total is not None else "—"
                    pdf.drawString(x_margin + 140 * mm, y, price_text)
                    pdf.drawString(x_margin + 162 * mm, y, sum_text)
            pdf.drawString(x_margin + 10 * mm, y, line)
            y -= 4.5 * mm
        y -= 1.5 * mm

    if show_prices and total:
        y -= 2 * mm
        pdf.line(x_margin, y, width - x_margin, y)
        y -= 6 * mm
        vat_rate = quote.vat_rate
        if vat_rate:
            vat_amount = vat_amount_rub(Decimal(total), vat_rate)
            grand = total + vat_amount
            pdf.setFont(font, 9)
            pdf.drawRightString(width - x_margin, y, f"НДС {vat_rate_label(vat_rate)}%: {vat_amount:.2f} ₽")
            y -= 6 * mm
            pdf.setFont(font_bold, 10)
            pdf.drawRightString(width - x_margin, y, f"Итого с НДС: {grand:.2f} ₽")
        else:
            pdf.setFont(font_bold, 10)
            pdf.drawRightString(width - x_margin, y, f"Итого: {total:.2f} ₽")

    if quote.comment:
        y -= 10 * mm
        pdf.setFont(font_bold, 9)
        pdf.drawString(x_margin, y, "Условия:")
        y -= 5 * mm
        pdf.setFont(font, 9)
        for line in _wrap(quote.comment, 95):
            if y < 20 * mm:
                pdf.showPage()
                pdf.setFont(font, 9)
                y = height - 20 * mm
            pdf.drawString(x_margin, y, line)
            y -= 4.5 * mm

    pdf.setFont(font, 8)
    pdf.drawString(
        x_margin,
        12 * mm,
        "Документ сформирован автоматически в личном кабинете Hoocon.",
    )
    pdf.showPage()
    pdf.save()
    buf.seek(0)
    return buf
