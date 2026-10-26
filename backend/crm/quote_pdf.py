"""Quote PDF: letter layout (reportlab platypus + bundled DejaVu).

The font lives in ``backend/assets/fonts/`` so the Docker image renders
Cyrillic without system fonts. ``crm.quote_docs`` stores the file as the
client's ``ClientDocument(kind=quote_pdf)``.

Юридический каркас совпадает с публичной офертой на сайте: КП не оферта,
существенные условия — в счёте, акцепт — полная оплата счёта. Цена в
карточке уже включает НДС: в таблице она печатается как есть, налог
выделяется из суммы (ст. 168 НК РФ), а не начисляется сверху.
"""

from __future__ import annotations

import io
import re
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, cast
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone

from config.seller import (
    SELLER_ADDRESS,
    SELLER_EMAIL,
    SELLER_INN,
    SELLER_KPP,
    SELLER_NAME,
    SELLER_OGRN,
    SELLER_PHONE,
)
from config.warranty import warranty_duration

if TYPE_CHECKING:
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.platypus import BaseDocTemplate

    from catalog.models import SKU, Attribute
    from crm.models import Client, Company, Quote, QuoteItem

_FONTS_DIR = Path(settings.BASE_DIR) / "assets" / "fonts"
_KOPECK = Decimal("0.01")
_MOMENT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*Нм", re.IGNORECASE)

# Shared technical lines. Printed only when every line has the same value,
# so a mixed quote does not claim one IP or one voltage for all rows.
_SHARED_ATTRS: tuple[tuple[str, str], ...] = (
    ("control", "Управление"),
    ("ip-rating", "Степень защиты"),
    ("ambient-temp", "Температура окружающей среды"),
    ("protection-class", "Класс защиты"),
)


def vat_amount_rub(total: Decimal, rate: Decimal) -> Decimal:
    """VAT added on top of a net amount, half-up to kopecks (not banker's rounding)."""
    return (total * rate / 100).quantize(_KOPECK, rounding=ROUND_HALF_UP)


def vat_included_rub(gross: Decimal, rate: Decimal) -> Decimal:
    """VAT already inside a gross price: ``gross × rate / (100 + rate)``, half-up to kopecks.

    The quote stores the client price with VAT. The PDF must not add the rate again.
    """
    if not rate:
        return Decimal("0.00")
    return (gross * rate / (Decimal(100) + rate)).quantize(_KOPECK, rounding=ROUND_HALF_UP)


def vat_rate_label(rate: Decimal) -> str:
    """``22.00`` → ``22``, ``12.50`` → ``12.5`` (Decimal ``:g`` keeps the zeros)."""
    return format(Decimal(rate).normalize(), "f")


def quote_table_widths(usable: float, *, show_prices: bool) -> list[float]:
    """Column widths in points. They sum to ``usable`` so cells cannot spill.

    The name column takes whatever remains after the fixed columns. A
    non-positive remainder means the fixed columns no longer fit the page.
    """
    from reportlab.lib.units import mm

    number = 8 * mm
    article = 24 * mm
    moment = 16 * mm
    kind = 28 * mm
    qty = 12 * mm
    fixed = [number, article, moment, kind, qty]
    if show_prices:
        fixed.extend((24 * mm, 26 * mm))
    name = usable - sum(fixed)
    if name <= 20 * mm:
        raise ValueError("quote table columns do not fit the page")
    return [fixed[0], name, *fixed[1:]]


@lru_cache(maxsize=1)
def _register_fonts() -> tuple[str, str]:
    """Register DejaVu regular/bold once per process; return font names."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    pdfmetrics.registerFont(TTFont("DejaVu", str(_FONTS_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(_FONTS_DIR / "DejaVuSans-Bold.ttf")))
    return "DejaVu", "DejaVu-Bold"


def _para(text: str, style: ParagraphStyle) -> object:
    """Paragraph with escaped text. Newlines become breaks, not overlapping draws."""
    from reportlab.platypus import Paragraph

    safe = escape(text or "").replace("\n", "<br/>")
    return Paragraph(safe or "—", style)


def _breakable_code(code: str) -> str:
    """Escape an article and allow a wrap after a hyphen or every 10 characters."""
    chunks: list[str] = []
    run = 0
    for char in code:
        chunks.append(escape(char))
        run += 1
        if char in "-_/" or run >= 10:
            chunks.append("\u200b")
            run = 0
    return "".join(chunks) or "—"


def _attr_map(sku: SKU | None) -> dict[str, str]:
    if sku is None:
        return {}
    found: dict[str, str] = {}
    for row in sku.attribute_values.all():
        attribute = cast("Attribute", row.attribute)
        found[attribute.slug] = (row.value or "").strip()
    return found


def _item_name(item: QuoteItem) -> str:
    sku = item.sku
    raw = ((sku.name if sku is not None else "") or item.sku_code or "—").strip()
    if " | " in raw:
        raw = raw.split(" | ", 1)[1].strip() or raw
    return raw


def _item_code(item: QuoteItem) -> str:
    sku = item.sku
    return (item.sku_code or (sku.sku_code if sku is not None else "") or "—").strip() or "—"


def _moment(attrs: dict[str, str], name: str) -> str:
    raw = attrs.get("moment", "").strip()
    if raw:
        return raw if "нм" in raw.casefold() else f"{raw} Нм"
    match = _MOMENT_RE.search(name)
    if match is None:
        return "—"
    return f"{match.group(1).replace(',', '.')} Нм"


def _drive_kind(name: str) -> str:
    folded = name.casefold()
    if "без возвратн" in folded or "без пружин" in folded:
        return "Без возвратной пружины"
    if "пружин" in folded:
        return "С пружинным возвратом"
    return "—"


def _shared_lines(maps: list[dict[str, str]]) -> list[str]:
    if not maps:
        return []
    lines: list[str] = []
    for slug, label in _SHARED_ATTRS:
        values = [row.get(slug, "") for row in maps]
        if all(values) and len(set(values)) == 1:
            lines.append(f"{label}: {values[0]}")
    return lines


def _voltage_note(maps: list[dict[str, str]]) -> str:
    if not maps:
        return ""
    values = [row.get("voltage", "") for row in maps]
    if all(values) and len(set(values)) == 1:
        return f"Примечание: все позиции рассчитаны на напряжение {values[0]}."
    return ""


def _greeting(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned or "@" in cleaned or cleaned.casefold().startswith(("ооо", "ип ", "зао", "ао ")):
        return "Здравствуйте!"
    first = cleaned.split()[0]
    if len(first) < 2:
        return "Здравствуйте!"
    return f"Здравствуйте, {first}!"


def _styles(font: str, font_bold: str) -> dict[str, ParagraphStyle]:
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle

    def make(name: str, **kwargs: object) -> ParagraphStyle:
        base: dict[str, object] = {
            "fontName": font,
            "fontSize": 9,
            "leading": 12,
            "alignment": TA_LEFT,
            "textColor": "black",
            "spaceBefore": 0,
            "spaceAfter": 0,
        }
        base.update(kwargs)
        return ParagraphStyle(name, **base)

    return {
        "title": make("qp-title", fontName=font_bold, fontSize=16, leading=20, spaceAfter=2),
        "seller": make("qp-seller", fontSize=8, leading=11, spaceAfter=1),
        "meta": make("qp-meta", fontSize=9, leading=12, spaceBefore=6, spaceAfter=2),
        "h": make("qp-h", fontName=font_bold, fontSize=11, leading=13, spaceBefore=6, spaceAfter=2),
        "body": make("qp-body", fontSize=9, leading=12, spaceAfter=2),
        "small": make("qp-small", fontSize=8, leading=11, spaceAfter=2),
        "right": make("qp-right", fontSize=9, leading=12, alignment=TA_RIGHT, spaceBefore=2),
        "right-bold": make(
            "qp-right-bold",
            fontName=font_bold,
            fontSize=10,
            leading=13,
            alignment=TA_RIGHT,
            spaceBefore=1,
        ),
        "th": make("qp-th", fontName=font_bold, fontSize=7, leading=9, alignment=TA_CENTER),
        "td": make("qp-td", fontSize=7.5, leading=9),
        "td-right": make("qp-td-right", fontSize=7.5, leading=9, alignment=TA_RIGHT),
        "td-center": make("qp-td-center", fontSize=7.5, leading=9, alignment=TA_CENTER),
        "code": make("qp-code", fontSize=7, leading=9),
    }


def _footer(canvas: Canvas, doc: BaseDocTemplate, font: str) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    canvas.saveState()
    canvas.setFont(font, 7)
    y = 8 * mm
    canvas.drawString(doc.leftMargin, y, f"{SELLER_NAME}. Документ не является офертой.")
    canvas.drawRightString(A4[0] - doc.rightMargin, y, str(doc.page))
    canvas.restoreState()


def render_quote_pdf(quote: Quote, *, include_prices: bool | None = None) -> io.BytesIO:
    """Render the quote as an A4 letter and return a buffer.

    Prices appear only when at least one item has ``unit_price`` set.
    ``include_prices=False`` hides them anyway: the cabinet flag
    ``CABINET_SHOW_PRICES`` must cover ``/api/account/*``, including this PDF.
    ``None`` keeps the stored-document behaviour (show a price that is set).

    Flowables (paragraphs and a table) are stacked by reportlab, so a long
    name wraps inside its cell instead of drawing over the next column.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Spacer

    font, font_bold = _register_fonts()
    styles = _styles(font, font_bold)
    client = cast("Client", quote.client)
    org = cast("Company | None", client.company_ref)
    items = list(
        quote.items.select_related("sku")
        .prefetch_related("sku__attribute_values__attribute")
        .order_by("sort_order", "id")
    )
    priced = any(item.unit_price is not None for item in items)
    show_prices = priced if include_prices is None else bool(include_prices) and priced

    story: list[object] = [
        _para("КОММЕРЧЕСКОЕ ПРЕДЛОЖЕНИЕ", styles["title"]),
        _para(SELLER_NAME, styles["seller"]),
        _para(f"ИНН {SELLER_INN}, КПП {SELLER_KPP}, ОГРН {SELLER_OGRN}", styles["seller"]),
        _para(SELLER_ADDRESS, styles["seller"]),
        _para(f"Тел.: {SELLER_PHONE} · {SELLER_EMAIL}", styles["seller"]),
    ]

    issued = timezone.localtime(quote.created_at)
    meta = f"{quote.number or 'КП'} от {issued:%d.%m.%Y}"
    if quote.sent_at:
        meta += f". Выдано: {timezone.localtime(quote.sent_at):%d.%m.%Y}"
    if quote.valid_until:
        meta += f". Действует до: {quote.valid_until:%d.%m.%Y}"
    story.append(_para(meta, styles["meta"]))

    company = (client.company or "").strip() or (org.name if org is not None else "") or client.name or client.email
    story.append(_para(f"Для {company}", styles["h"]))
    if org is not None and (org.legal_address or "").strip():
        story.append(_para(org.legal_address.strip(), styles["small"]))
    org_bits = []
    if org is not None and (org.phone or "").strip() and org.phone.strip() != (client.phone or "").strip():
        org_bits.append(f"Тел.: {org.phone.strip()}")
    if org is not None and (org.email or "").strip() and org.email.strip().casefold() != client.email.casefold():
        org_bits.append(org.email.strip())
    if org is not None and (org.website or "").strip():
        org_bits.append(org.website.strip())
    if org_bits:
        story.append(_para(" · ".join(org_bits), styles["small"]))

    story.append(_para("Получатель", styles["h"]))
    if (client.name or "").strip():
        story.append(_para(client.name.strip(), styles["body"]))
    story.append(_para(f"Email: {client.email}", styles["small"]))
    if (client.phone or "").strip():
        story.append(_para(f"Тел.: {client.phone.strip()}", styles["small"]))

    story.append(Spacer(1, 4))
    story.append(_para(_greeting(client.name), styles["body"]))
    if show_prices and quote.vat_rate:
        story.append(
            _para(
                f"Направляем спецификацию. Цены указаны с НДС {vat_rate_label(quote.vat_rate)}%.",
                styles["body"],
            )
        )
    elif show_prices:
        story.append(_para("Направляем спецификацию. Цены указаны без НДС.", styles["body"]))
    else:
        story.append(_para("Направляем спецификацию. Цены в этом экземпляре не показаны.", styles["body"]))

    story.append(_para("СПЕЦИФИКАЦИЯ И ЦЕНЫ", styles["h"]))
    maps = [_attr_map(item.sku) for item in items]
    story.extend(_spec_table(items, maps, styles, show_prices=show_prices))
    note = _voltage_note(maps)
    if note:
        story.append(Spacer(1, 4))
        story.append(_para(note, styles["small"]))
    if show_prices:
        story.extend(_totals(items, quote.vat_rate, styles))

    shared = _shared_lines(maps)
    if shared:
        story.append(_para("ТЕХНИЧЕСКИЕ ХАРАКТЕРИСТИКИ", styles["h"]))
        story.extend(_para(line, styles["body"]) for line in shared)
        story.append(
            _para(
                "Строка выше — только то, что совпало у всех позиций. Различающиеся параметры в общее не сводятся.",
                styles["small"],
            )
        )

    story.append(_para("УСЛОВИЯ", styles["h"]))
    story.append(
        _para(
            "Срок и адрес поставки указываются в счёте. До выставления счёта наличие и срок отгрузки уточняются.",
            styles["body"],
        )
    )
    story.append(
        _para(
            "Оплата по счёту: 100% либо, если счёт это указывает, 50% предоплата "
            "и 50% по факту прибытия партии в РФ. Договор заключается поступлением "
            f"оплаты по счёту на расчётный счёт {SELLER_NAME}, а не этим документом.",
            styles["body"],
        )
    )
    story.append(
        _para(
            f"Гарантия на электроприводы — {warranty_duration()}, если иное не указано в счёте.",
            styles["body"],
        )
    )
    story.append(
        _para(
            "Настоящее коммерческое предложение не является офертой (ст. 435 ГК РФ) "
            "и публичной офертой (ст. 437 ГК РФ). Наименование, количество, цена и срок "
            "поставки становятся обязательными в счёте.",
            styles["body"],
        )
    )
    extra = (quote.comment or "").strip()
    if extra:
        story.append(_para("Дополнительно", styles["h"]))
        story.append(_para(extra, styles["body"]))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=16 * mm,
        title=f"Коммерческое предложение {quote.number}",
        author=SELLER_NAME,
    )

    def _paint(canvas: Canvas, document: BaseDocTemplate) -> None:
        _footer(canvas, document, font)

    doc.build(story, onFirstPage=_paint, onLaterPages=_paint)  # type: ignore[arg-type]
    buf.seek(0)
    return buf


def _totals(
    items: list[QuoteItem],
    vat_rate: Decimal,
    styles: dict[str, ParagraphStyle],
) -> list[object]:
    from reportlab.platypus import Spacer

    total = sum(
        ((item.unit_price or Decimal(0)) * item.quantity for item in items if item.unit_price is not None),
        Decimal(0),
    )
    block: list[object] = [Spacer(1, 4)]
    if vat_rate:
        included = vat_included_rub(total, vat_rate)
        block.append(_para(f"В том числе НДС {vat_rate_label(vat_rate)}%: {included:.2f} ₽", styles["right"]))
    block.append(_para(f"Итого: {total:.2f} ₽", styles["right-bold"]))
    return block


def _spec_table(
    items: list[QuoteItem],
    maps: list[dict[str, str]],
    styles: dict[str, ParagraphStyle],
    *,
    show_prices: bool,
) -> list[object]:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Table, TableStyle

    usable = A4[0] - 28 * mm
    widths = quote_table_widths(usable, show_prices=show_prices)
    headers = ["№", "Наименование", "Артикул", "Момент", "Тип привода", "Кол-во"]
    if show_prices:
        headers.extend(("Цена, ₽", "Сумма, ₽"))
    rows: list[list[object]] = [[_para(label, styles["th"]) for label in headers]]
    if not items:
        empty = ["—", "Позиции не указаны", "—", "—", "—", "—"]
        if show_prices:
            empty.extend(("—", "—"))
        rows.append([_para(cell, styles["td"]) for cell in empty])
    for idx, (item, attrs) in enumerate(zip(items, maps, strict=True), start=1):
        name = _item_name(item)
        full_name = (item.sku.name if item.sku is not None else "") or name
        code = _item_code(item)
        line: list[object] = [
            _para(str(idx), styles["td-center"]),
            _para(name, styles["td"]),
            Paragraph(_breakable_code(code), styles["code"]),
            _para(_moment(attrs, full_name), styles["td"]),
            _para(_drive_kind(full_name), styles["td"]),
            _para(str(item.quantity), styles["td-right"]),
        ]
        if show_prices:
            if item.unit_price is None:
                line.extend((_para("—", styles["td-right"]), _para("—", styles["td-right"])))
            else:
                line_total = item.unit_price * item.quantity
                line.append(_para(f"{item.unit_price:.2f}", styles["td-right"]))
                line.append(_para(f"{line_total:.2f}", styles["td-right"]))
        rows.append(line)
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.93, 0.93, 0.93)),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.Color(0.7, 0.7, 0.7)),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return [table]
