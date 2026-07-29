"""Attach series-8100 brass PDF + dimension/wiring crops to ``8100-bv*`` SKUs.

Source::

    ``_инструкции-pdf/шаровые краны серии 8100.pdf`` (6 pages, ~3 MiB)

- ProductFile datasheet on every published brass body SKU.
- ProductImage tiles: габариты (стр.4) + схема подключения привода (стр.5).
- Optional ТТХ fill for empty size attrs from the page-4 table (no silent overwrite).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image

from catalog.etl.attr_write import set_sku_attribute
from catalog.etl.h81_catalog_media import crop_h81_dimensions
from catalog.etl.manual_diagrams import (
    SORT_DIMENSIONS,
    SORT_WIRING,
    DiagramCrop,
    _pil_to_png_bytes,
    _upsert_diagram,
    render_pdf_page,
)
from catalog.etl.manual_pdfs import default_manuals_dir
from catalog.etl.webp import convert_bytes_to_webp
from catalog.models import SKU, AttributeValue, ProductFile
from catalog.validators import MAX_PRODUCT_FILE_SIZE_BYTES

logger = logging.getLogger(__name__)

PDF_FILENAME: Final[str] = "шаровые краны серии 8100.pdf"
PDF_TITLE: Final[str] = "Паспорт серии 8100 (шаровые краны)"
PDF_SORT: Final[int] = 40
_SOURCE_URL = "https://hoocon.ru/.local-assets/8100-series/{stem}-{kind}.webp"
_RENDER_SCALE = 2.5
_SKU_BODY_RE = re.compile(r"(?i)^(?:8100-)?bv(?P<num>\d{3,4})(?P<ed>[a-e])?$")

# Page index 3 = «Габаритные размеры» table + threaded drawing.
_DIMS_PAGE = 3
_DIMS_BAND = (0.50, 0.72, 0.03, 0.97)  # top, bottom, left, right

# Page index 4 = «Схема подключения» (right column).
_WIRING_PAGE = 4
_WIRING_BAND = (0.10, 0.98, 0.48, 0.98)


@dataclass(frozen=True, slots=True)
class _BrassDims:
    """Overall dimensions from PDF page 4 (mm; G = thread label)."""

    g: str
    h: str
    h1: str
    length: str
    s: str
    d: str | None = None  # 3-way center-to-edge when present


# From «Габаритные размеры» table (PDF стр.4). H→height-actuator, H1→height-stem,
# L→valve-length, S→valve-od, D→center-to-edge (3-way only).
_BRASS_DIMS: Final[dict[str, _BrassDims]] = {
    "BV215": _BrassDims("G1/2", "142", "39", "60", "25"),
    "BV220": _BrassDims("G3/4", "146", "43", "68", "32"),
    "BV225": _BrassDims("G1", "150", "47", "89", "39"),
    "BV232": _BrassDims("G1-1/4", "155", "52", "102,5", "48"),
    "BV240": _BrassDims("G1-1/2", "160", "57", "113", "56"),
    "BV250": _BrassDims("G2", "165", "62", "127", "70"),
    "BV315": _BrassDims("G1/2", "142", "39", "60", "25", "30"),
    "BV320": _BrassDims("G3/4", "146", "43", "67", "32", "33"),
    "BV325": _BrassDims("G1", "150", "47", "89", "39"),
    "BV332": _BrassDims("G1-1/4", "155", "52", "98", "48"),
    "BV340": _BrassDims("G1-1/2", "160", "57", "106,5", "55"),
    "BV350": _BrassDims("G2", "165", "62", "122,5", "70"),
}


def find_8100_series_pdf(*, pdf_path: Path | None = None) -> Path | None:
    """Resolve the series-8100 brass PDF under ``_инструкции-pdf``."""
    if pdf_path is not None:
        return pdf_path if pdf_path.is_file() else None
    candidate = default_manuals_dir() / PDF_FILENAME
    return candidate if candidate.is_file() else None


def brass_body_code_from_sku(sku_code: str) -> str | None:
    """``8100-bv215a`` → ``BV215``."""
    match = _SKU_BODY_RE.fullmatch((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    return f"BV{match.group('num')}"


def source_url_for_8100(stem: str, kind: str) -> str:
    """Stable ProductImage.source_url for upsert."""
    return _SOURCE_URL.format(stem=stem.casefold(), kind=kind)


def _normalize_mm(value: str) -> str:
    """Compare size strings ignoring comma/dot and spaces."""
    return (value or "").strip().replace(",", ".").replace(" ", "").casefold()


def attach_8100_series_pdf(
    sku: SKU,
    *,
    pdf_path: Path,
    dry_run: bool = False,
) -> str:
    """Attach series PDF as datasheet. Returns create / update / skip / too_large."""
    existing = ProductFile.objects.filter(
        sku=sku,
        title=PDF_TITLE,
        file_type=ProductFile.FileType.DATASHEET,
    ).first()
    size = pdf_path.stat().st_size
    if size > MAX_PRODUCT_FILE_SIZE_BYTES:
        logger.warning(
            "8100 series PDF too large (%s > %s) — skip %s",
            size,
            MAX_PRODUCT_FILE_SIZE_BYTES,
            sku.sku_code,
        )
        return "too_large"
    if dry_run:
        return "update" if existing else "create"

    data = pdf_path.read_bytes()
    filename = "seria-8100-sharovye-krany.pdf"
    with transaction.atomic():
        if existing is None:
            doc = ProductFile(
                sku=sku,
                title=PDF_TITLE,
                file_type=ProductFile.FileType.DATASHEET,
                is_published=True,
                sort_order=PDF_SORT,
            )
            doc.file.save(filename, ContentFile(data), save=False)
            doc.full_clean()
            doc.save()
            return "create"
        existing.is_published = True
        existing.sort_order = PDF_SORT
        existing.file.save(filename, ContentFile(data), save=False)
        existing.full_clean()
        existing.save()
        return "update"


def _crop_band(page: Image.Image, band: tuple[float, float, float, float]) -> Image.Image:
    top, bottom, left, right = band
    return crop_h81_dimensions(page, top=top, bottom=bottom, left=left, right=right)


def build_8100_diagram_crops(pdf_path: Path) -> list[DiagramCrop]:
    """Rasterize page 4–5 bands into dimensions + wiring crops."""
    dims_page = render_pdf_page(pdf_path, _DIMS_PAGE, scale=_RENDER_SCALE)
    wiring_page = render_pdf_page(pdf_path, _WIRING_PAGE, scale=_RENDER_SCALE)
    dims_img = _crop_band(dims_page, _DIMS_BAND)
    wiring_img = _crop_band(wiring_page, _WIRING_BAND)
    return [
        DiagramCrop(
            kind="dimensions",
            png_bytes=_pil_to_png_bytes(dims_img),
            alt="Серия 8100 | Габаритные размеры (мм), чертёж из паспорта серии",
            sort_order=SORT_DIMENSIONS,
            source_url=source_url_for_8100("brass", "dimensions"),
        ),
        DiagramCrop(
            kind="wiring",
            png_bytes=_pil_to_png_bytes(wiring_img),
            alt="Серия 8100 | Схема подключения электропривода (паспорт серии)",
            sort_order=SORT_WIRING,
            source_url=source_url_for_8100("brass", "wiring"),
        ),
    ]


def _attr_value(sku: SKU, slug: str) -> str | None:
    row = AttributeValue.objects.filter(sku=sku, attribute__slug=slug).values_list("value", flat=True).first()
    if row is None:
        return None
    text = str(row).strip()
    return text or None


def sync_brass_dims_from_pdf(
    sku: SKU,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, int]:
    """Fill empty size attrs from PDF table; warn on mismatch unless ``force``.

    Returns counters: filled, mismatched, skipped.
    """
    stats = {"filled": 0, "mismatched": 0, "skipped": 0}
    body = brass_body_code_from_sku(sku.sku_code or "")
    if body is None or body not in _BRASS_DIMS:
        stats["skipped"] += 1
        return stats
    dims = _BRASS_DIMS[body]
    pairs: list[tuple[str, str, str, str]] = [
        ("Высота до верхнего края привода", "height-actuator", "мм", dims.h),
        ("Высота до верхнего края штока", "height-stem", "мм", dims.h1),
        ("Длина крана", "valve-length", "мм", dims.length),
        ("Внешний диаметр крана", "valve-od", "мм", dims.s),
    ]
    if dims.d:
        pairs.append(
            ("Длина от центра до края крана", "center-to-edge", "мм", dims.d),
        )

    for name, slug, unit, expected in pairs:
        current = _attr_value(sku, slug)
        if current is None:
            stats["filled"] += 1
            if not dry_run:
                set_sku_attribute(sku, slug=slug, value=expected, name=name, unit=unit)
            continue
        if _normalize_mm(current) == _normalize_mm(expected):
            continue
        stats["mismatched"] += 1
        logger.warning(
            "8100 dims mismatch %s %s: db=%r pdf=%r",
            sku.sku_code,
            slug,
            current,
            expected,
        )
        if force and not dry_run:
            set_sku_attribute(sku, slug=slug, value=expected, name=name, unit=unit)
            stats["filled"] += 1
    return stats


def apply_8100_catalog_media(
    *,
    dry_run: bool = False,
    pdf_path: Path | None = None,
    force_attrs: bool = False,
) -> dict[str, Any]:
    """Attach series PDF + diagrams to published ``8100-bv*`` SKUs."""
    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "pdf_created": 0,
        "pdf_updated": 0,
        "pdf_skipped": 0,
        "attrs_filled": 0,
        "attrs_mismatched": 0,
        "skipped": 0,
        "dry_run": dry_run,
        "pdf": "",
    }
    catalog = find_8100_series_pdf(pdf_path=pdf_path)
    if catalog is None:
        summary["skipped"] = 1
        logger.warning("8100 series PDF not found")
        return summary
    summary["pdf"] = str(catalog)

    skus = list(
        SKU.objects.filter(
            sku_code__istartswith="8100-bv",
            is_published=True,
        ).order_by("sku_code"),
    )
    if not skus:
        summary["skipped"] = 1
        return summary

    crops = build_8100_diagram_crops(catalog)
    webp_cache: dict[str, bytes] = {
        crop.source_url: convert_bytes_to_webp(crop.png_bytes, quality=92, max_edge=1600) for crop in crops
    }

    for sku in skus:
        pdf_action = attach_8100_series_pdf(sku, pdf_path=catalog, dry_run=dry_run)
        if pdf_action == "create":
            summary["pdf_created"] += 1
        elif pdf_action == "update":
            summary["pdf_updated"] += 1
        else:
            summary["pdf_skipped"] += 1

        for crop in crops:
            action = _upsert_diagram(
                sku,
                crop,
                dry_run=dry_run,
                webp_bytes=webp_cache[crop.source_url],
            )
            if action == "create":
                summary["created"] += 1
            elif action == "update":
                summary["updated"] += 1

        attr_stats = sync_brass_dims_from_pdf(
            sku,
            dry_run=dry_run,
            force=force_attrs,
        )
        summary["attrs_filled"] += attr_stats["filled"]
        summary["attrs_mismatched"] += attr_stats["mismatched"]
        logger.info(
            "8100_catalog_media %s pdf=%s diagrams=%s attrs_filled=%s",
            sku.sku_code,
            pdf_action,
            len(crops),
            attr_stats["filled"],
        )

    return summary
