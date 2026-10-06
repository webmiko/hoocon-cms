"""Excel (.xlsx) spec import — ЛК-9, manager tool.

Менеджер грузит клиентскую спецификацию в Admin → парсим строки
(артикул + количество), резолвим наши SKU напрямую и через карту
аналогов (``catalog.services.resolve_position_code``) → черновик
заявки с позициями. Неопознанные артикулы складываем в ``LeadItem``
без SKU — менеджер разруливает вручную, как в обычной заявке.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import IO, Any

from django.db import transaction

from catalog.services import resolve_position_code
from leads.models import Lead

logger = logging.getLogger(__name__)

_MAX_ROWS = 500
_CODE_HEADER_HINTS = ("артикул", "арт", "код", "sku", "code", "модель", "article")
_QTY_HEADER_HINTS = ("кол", "qty", "шт", "количество", "count")


@dataclass
class ParsedSpecRow:
    """One parsed spec line before ORM persistence."""

    raw_code: str
    quantity: int
    sku: Any | None  # catalog.SKU
    via_analog: bool


class SpecParseError(Exception):
    """User-facing parse failure (битый файл, пустая таблица)."""


def _norm_header(value: Any) -> str:
    return str(value or "").strip().casefold()


def _find_columns(header_row: tuple[Any, ...]) -> tuple[int, int]:
    """Locate (code_col, qty_col) from a header row; -1 when not found."""
    code_col = qty_col = -1
    for idx, cell in enumerate(header_row):
        label = _norm_header(cell)
        if not label:
            continue
        if code_col == -1 and any(hint in label for hint in _CODE_HEADER_HINTS):
            code_col = idx
        elif qty_col == -1 and any(hint in label for hint in _QTY_HEADER_HINTS):
            qty_col = idx
    return code_col, qty_col


def parse_spec_xlsx(file_obj: IO[bytes]) -> list[ParsedSpecRow]:
    """Parse an .xlsx spec into rows; resolve each code against catalog.

    The first sheet is scanned for a header row containing an article
    column (артикул/sku/код/модель…); a quantity column is optional
    (defaults to 1). Up to ``_MAX_ROWS`` data rows are consumed.
    """
    import openpyxl

    try:
        wb = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
    except Exception as exc:
        raise SpecParseError("Не удалось прочитать файл — ожидается .xlsx.") from exc
    try:
        sheet = wb.worksheets[0]
        rows_iter = sheet.iter_rows(values_only=True)
        code_col = qty_col = -1
        header_found = False
        rows: list[ParsedSpecRow] = []
        for raw_row in rows_iter:
            if not header_found:
                code_col, qty_col = _find_columns(raw_row)
                if code_col != -1:
                    header_found = True
                continue
            if len(rows) >= _MAX_ROWS:
                break
            code = str(raw_row[code_col] if code_col < len(raw_row) else "").strip()
            if not code:
                continue
            qty = 1
            if qty_col != -1 and qty_col < len(raw_row):
                try:
                    qty = max(int(float(raw_row[qty_col])), 1)
                except (TypeError, ValueError):
                    qty = 1
            sku, analog = resolve_position_code(code)
            rows.append(
                ParsedSpecRow(
                    raw_code=code,
                    quantity=qty,
                    sku=sku,
                    via_analog=analog is not None,
                )
            )
        if not header_found:
            raise SpecParseError(
                "Не найдена колонка с артикулами (ожидаются заголовки: артикул / код / модель / sku)."
            )
        if not rows:
            raise SpecParseError("В файле нет строк с артикулами.")
        return rows
    finally:
        wb.close()


@transaction.atomic
def create_lead_from_spec_rows(
    rows: list[ParsedSpecRow],
    *,
    client: Any,  # crm.Client
    source_name: str,
) -> Lead:
    """Persist parsed rows as a draft RFQ lead on the client card.

    Неразрешённые артикулы идут в ``LeadItem.sku_code`` снимком — менеджер
    видит их в заявке и доразруливает; заменённые через аналог коды
    сохраняют исходник в ``sku_code`` (``sku`` уже наш).
    """
    lead = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name=client.name or client.email,
        email=client.email,
        phone=client.phone,
        company=client.company,
        client=client,
        message=f"Спецификация из файла «{source_name}»",
    )
    for idx, row in enumerate(rows):
        lead.items.create(
            sku=row.sku,
            sku_code=row.raw_code if row.sku is None or row.via_analog else (row.sku.sku_code),
            quantity=row.quantity,
            sort_order=idx,
        )
    logger.info(
        "spec_import_lead lead_id=%s rows=%s resolved=%s",
        lead.pk,
        len(rows),
        sum(1 for r in rows if r.sku is not None),
    )
    return lead
