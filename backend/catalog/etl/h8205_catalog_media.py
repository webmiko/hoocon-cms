"""Photo, dimensions, wiring crops, and sliced PDF for H8205 LAV cards.

Catalog 2026 шаровые pages 26–29 (intro, dimensions, materials, wiring).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.core.files.base import ContentFile
from django.db import transaction

from catalog.etl.h81_catalog_media import (
    extract_catalog_page_range_pdf,
    find_h81_catalog_images_dir,
    find_h81_catalog_pdf,
)
from catalog.etl.manual_diagrams import (
    SORT_DIMENSIONS,
    SORT_PHOTO,
    SORT_WIRING,
    DiagramCrop,
    _pil_to_png_bytes,
    _upsert_diagram,
    center_cutout_on_canvas,
    punch_near_white_background,
    render_pdf_page,
)
from catalog.etl.series_copy_ball_valves import CATALOG_IMAGES_DIR
from catalog.etl.webp import convert_bytes_to_webp
from catalog.models import SKU, ProductFile
from catalog.validators import MAX_PRODUCT_FILE_SIZE_BYTES

logger = logging.getLogger(__name__)

_SOURCE_URL = "https://hoocon.ru/.local-assets/h8205-catalog/{kind}.webp"
_PHOTO_FILE = "img_0024_xref234_p026.jpeg"
_RENDER_SCALE = 2.5
# 0-based PDF page indices (catalog 1-based 26–29).
_DIMS_PAGE = 26
_WIRING_PAGE = 28
_INSTR_FIRST = 26
_INSTR_LAST = 29
_INSTR_TITLE = "Инструкция H8205 LAV (каталог 2026, стр. 26–29)"


def source_url_for_h8205(kind: str) -> str:
    """Stable ProductImage.source_url for H8205 photo / diagram upsert."""
    return _SOURCE_URL.format(kind=kind)


def crops_for_h8205(
    *,
    pdf_path: Path | None = None,
    images_dir: Path | None = None,
) -> list[DiagramCrop]:
    """Build photo + dimensions + wiring crops for the H8205 family."""
    catalog_pdf = find_h81_catalog_pdf(pdf_path=pdf_path)
    images_root = find_h81_catalog_images_dir(images_dir=images_dir)
    if catalog_pdf is None:
        return []

    out: list[DiagramCrop] = []
    root = images_root or CATALOG_IMAGES_DIR
    photo_path = (root / _PHOTO_FILE).resolve()
    if photo_path.is_file():
        raw = photo_path.read_bytes()
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(raw)).convert("RGB")
        img = center_cutout_on_canvas(punch_near_white_background(img))
        out.append(
            DiagramCrop(
                kind="photo",
                alt="H8205 LAV — общий вид",
                sort_order=SORT_PHOTO,
                source_url=source_url_for_h8205("photo"),
                png_bytes=_pil_to_png_bytes(img),
            ),
        )

    dims_page = render_pdf_page(catalog_pdf, _DIMS_PAGE, scale=_RENDER_SCALE)
    # Table of dimensions occupies the mid-page band under the red title.
    w, h = dims_page.size
    dims_crop = dims_page.crop(
        (int(0.04 * w), int(0.12 * h), int(0.92 * w), int(0.92 * h)),
    )
    out.append(
        DiagramCrop(
            kind="dimensions",
            alt="H8205 LAV — габаритные размеры",
            sort_order=SORT_DIMENSIONS,
            source_url=source_url_for_h8205("dimensions"),
            png_bytes=_pil_to_png_bytes(dims_crop),
        ),
    )

    wiring_page = render_pdf_page(catalog_pdf, _WIRING_PAGE, scale=_RENDER_SCALE)
    ww, wh = wiring_page.size
    wiring_crop = wiring_page.crop(
        (int(0.04 * ww), int(0.08 * wh), int(0.92 * ww), int(0.92 * wh)),
    )
    out.append(
        DiagramCrop(
            kind="wiring",
            alt="H8205 LAV — электрическое подключение",
            sort_order=SORT_WIRING,
            source_url=source_url_for_h8205("wiring"),
            png_bytes=_pil_to_png_bytes(wiring_crop),
        ),
    )
    return out


def apply_h8205_catalog_media(
    *,
    dry_run: bool = False,
    pdf_path: Path | None = None,
    images_dir: Path | None = None,
) -> dict[str, Any]:
    """Attach shared H8205 photo/dims/wiring WebP to every H8205 SKU.

    Args:
        dry_run: Count without writing.
        pdf_path: Override catalog PDF.
        images_dir: Override extracted JPEG directory.

    Returns:
        Counters ``created`` / ``updated`` / ``skipped`` / ``dry_run``.
    """
    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "dry_run": dry_run,
    }
    try:
        crops = crops_for_h8205(pdf_path=pdf_path, images_dir=images_dir)
    except Exception:
        logger.exception("h8205_catalog_crop_failed")
        return summary
    if not crops:
        summary["skipped"] = 1
        return summary

    webp_cache: dict[str, bytes] = {
        crop.source_url: convert_bytes_to_webp(crop.png_bytes, quality=92, max_edge=1600) for crop in crops
    }
    skus = list(
        SKU.objects.filter(sku_code__istartswith="H8205").order_by("sku_code"),
    )
    for sku in skus:
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

    catalog_pdf = find_h81_catalog_pdf(pdf_path=pdf_path)
    if catalog_pdf is not None and not dry_run:
        try:
            payload = extract_catalog_page_range_pdf(
                catalog_pdf,
                first_page=_INSTR_FIRST,
                last_page=_INSTR_LAST,
            )
        except (OSError, ValueError) as exc:
            logger.warning("h8205 instruction PDF slice failed: %s", exc)
            return summary
        if len(payload) <= MAX_PRODUCT_FILE_SIZE_BYTES:
            _attach_instruction_pdfs(skus, payload)
    return summary


def _attach_instruction_pdfs(skus: list[SKU], payload: bytes) -> int:
    """Attach sliced H8205 instruction PDF once per SKU (idempotent by title)."""
    created = 0
    for sku in skus:
        if ProductFile.objects.filter(
            sku=sku,
            title=_INSTR_TITLE,
            file_type=ProductFile.FileType.DATASHEET,
        ).exists():
            continue
        doc = ProductFile(
            sku=sku,
            title=_INSTR_TITLE,
            file_type=ProductFile.FileType.DATASHEET,
            is_published=True,
            sort_order=10,
        )
        with transaction.atomic():
            doc.file.save(
                f"{sku.sku_code.lower()}-h8205-instr.pdf",
                ContentFile(payload),
                save=False,
            )
            doc.full_clean()
            doc.save()
        created += 1
    return created
