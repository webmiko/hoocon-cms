"""Attach HV dimension drawings cropped from the RU 2025 product catalog.

Source::

    _инструкции-pdf/RU/2025 каталог-2.2.3.pdf
    (landscape spreads: PDF page N → catalog pages ``2*(N-1)`` | ``2*(N-1)+1``)

Envelope families (H×W×D) share one crop::

    5 / 5Q              → 144,1 × 71,1 × 62,1   (catalog p.39)
    10 / 10Q / 5QX/10QX → 167,8 × 86,2 × 68     (catalog p.41)
    20 / 20Q / 20QX     → 191,8 × 103,4 × 68    (catalog p.43)
    40 / 40Q / 40QX     → 198,6 × 110,2 × 68    (catalog p.45)

Replaces stale ``hva-catalog`` / ``hvd-catalog`` razmer tiles that no longer
match the catalog ТТХ.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Final

import pypdfium2 as pdfium
from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image, ImageChops

from catalog.etl.manual_pdfs import default_manuals_dir
from catalog.etl.webp import DEFAULT_WEBP_QUALITY, MAX_EDGE_PX, convert_bytes_to_webp
from catalog.models import SKU, ProductImage

logger = logging.getLogger(__name__)

SORT_DIMENSIONS: Final[int] = 6
_CATALOG_NAME: Final[str] = "2025 каталог-2.2.3.pdf"
_RENDER_SCALE: Final[float] = 2.5
_SOURCE = "https://hoocon.ru/.local-assets/hv-catalog/{stem}-dimensions.webp"

# Catalog page (left column of spread) → PDF 1-based page.
# PDF page P holds catalog pages 2*(P-1) and 2*(P-1)+1.
_ENVELOPE_CATALOG_PAGE: Final[dict[str, int]] = {
    "hv-5": 39,
    "hv-10": 41,
    "hv-20": 43,
    "hv-40": 45,
}

_SKU_RE = re.compile(
    r"(?i)^(?P<brand>hv[ad])(?:24|230)s?-(?P<nm>\d+)(?P<sfx>qx|q)?$",
)
_DIMS_URL_HINT = re.compile(r"(?i)dimension|razmer|габарит|hv-catalog/")
_DIMS_ALT_HINT = re.compile(r"(?i)габарит|размер|dimension|razmer")


def default_hv_ru_catalog_pdf() -> Path | None:
    """Resolve the RU 2025 catalog PDF under ``_инструкции-pdf``."""
    manuals = default_manuals_dir()
    for candidate in (
        manuals / "RU" / _CATALOG_NAME,
        manuals / _CATALOG_NAME,
    ):
        if candidate.is_file():
            return candidate
    return None


def envelope_stem_for_sku(sku_code: str) -> str | None:
    """Map an HVA/HVD edition code to a shared dimension envelope stem."""
    match = _SKU_RE.match((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    nm = int(match.group("nm"))
    sfx = (match.group("sfx") or "").lower()
    if sfx == "qx" and nm in {5, 10}:
        return "hv-10"
    if nm in {5, 10, 20, 40}:
        return f"hv-{nm}"
    return None


def _pdf_page_for_catalog_page(catalog_page: int) -> int:
    """0-based PDF page index for a catalog page number."""
    return catalog_page // 2


def _trim_whitespace(image: Image.Image, *, pad: int = 8) -> Image.Image:
    """Crop near-white margins from a catalog band."""
    rgb = image.convert("RGB")
    bg = Image.new("RGB", rgb.size, (255, 255, 255))
    diff = ImageChops.difference(rgb, bg)
    bbox = diff.getbbox()
    if bbox is None:
        return rgb
    left, top, right, bottom = bbox
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(rgb.size[0], right + pad)
    bottom = min(rgb.size[1], bottom + pad)
    return rgb.crop((left, top, right, bottom))


def _find_red_heading_y(half: Image.Image, *, search_from_frac: float = 0.55) -> int | None:
    """Y of the red «Размеры привода» title in a page half, or None."""
    width, height = half.size
    y0 = int(search_from_frac * height)
    for y in range(y0, height - 40):
        red = 0
        for x in range(0, width, 4):
            pixel = half.getpixel((x, y))
            if not isinstance(pixel, tuple) or len(pixel) < 3:
                continue
            r, g, b = int(pixel[0]), int(pixel[1]), int(pixel[2])
            if r > 150 and g < 100 and b < 100:
                red += 1
                if red > 20:
                    return y
    return None


def crop_hv_catalog_dimensions(
    page_image: Image.Image,
    *,
    left_page: bool = True,
) -> Image.Image:
    """Crop the «Размеры привода» drawing block from one half of a spread."""
    width, height = page_image.size
    mid = width // 2
    if left_page:
        half = page_image.crop((0, 0, mid, height))
    else:
        half = page_image.crop((mid, 0, width, height))
    # Anchor on the red heading so ТТХ table rows above are excluded.
    heading_y = _find_red_heading_y(half)
    top = max(0, (heading_y - 6) if heading_y is not None else int(0.735 * height))
    band = half.crop(
        (
            int(0.02 * half.size[0]),
            top,
            int(0.98 * half.size[0]),
            height - 48,
        ),
    )
    return _trim_whitespace(band)


def render_envelope_crop(catalog_pdf: Path, stem: str) -> Image.Image:
    """Render and crop the dimension drawing for one envelope stem."""
    catalog_page = _ENVELOPE_CATALOG_PAGE[stem]
    pdf_index = _pdf_page_for_catalog_page(catalog_page)
    document = pdfium.PdfDocument(str(catalog_pdf))
    try:
        page = document[pdf_index]
        page_image = page.render(scale=_RENDER_SCALE).to_pil().convert("RGB")
    finally:
        document.close()
    # Odd catalog pages sit on the RIGHT half of the landscape spread
    # (PDF page P = catalog ``2*(P-1)`` | ``2*(P-1)+1``).
    left_page = catalog_page % 2 == 0
    return crop_hv_catalog_dimensions(page_image, left_page=left_page)


def _demote_other_dimension_tiles(sku: SKU, *, keep_pk: int) -> int:
    """Unpublish competing dimension drawings on the SKU."""
    demoted = 0
    for other in ProductImage.objects.filter(sku=sku).exclude(pk=keep_pk):
        alt = other.alt or ""
        url = other.source_url or ""
        if not (_DIMS_URL_HINT.search(url) or _DIMS_ALT_HINT.search(alt)):
            continue
        if not other.is_published and other.sort_order != SORT_DIMENSIONS:
            continue
        other.is_published = False
        if other.sort_order == SORT_DIMENSIONS:
            other.sort_order = 16
        other.save(update_fields=["is_published", "sort_order", "updated_at"])
        demoted += 1
    return demoted


def _upsert_dimensions(
    sku: SKU,
    *,
    stem: str,
    webp: bytes,
    alt: str,
    dry_run: bool,
) -> tuple[str, int]:
    """Create/update the catalog dimensions tile; return (action, demoted)."""
    source_url = _SOURCE.format(stem=stem)
    existing = ProductImage.objects.filter(sku=sku, source_url=source_url).first()
    if dry_run:
        return ("update" if existing else "create"), 0
    filename = f"{stem}-dimensions.webp"
    with transaction.atomic():
        if existing is None:
            image = ProductImage(
                sku=sku,
                alt=alt[:300],
                source_url=source_url,
                sort_order=SORT_DIMENSIONS,
                is_published=True,
            )
            image.image.save(filename, ContentFile(webp), save=False)
            image.full_clean()
            image.save()
            keep_pk = image.pk
            action = "create"
        else:
            existing.alt = alt[:300]
            existing.sort_order = SORT_DIMENSIONS
            existing.is_published = True
            existing.image.save(filename, ContentFile(webp), save=False)
            existing.full_clean()
            existing.save()
            keep_pk = existing.pk
            action = "update"
        demoted = _demote_other_dimension_tiles(sku, keep_pk=keep_pk)
    return action, demoted


def apply_hv_catalog_dimensions(
    *,
    dry_run: bool = False,
    catalog_pdf: Path | None = None,
) -> dict[str, Any]:
    """Crop RU catalog dimension drawings and attach to published HVA/HVD SKUs."""
    pdf_path = catalog_pdf if catalog_pdf is not None else default_hv_ru_catalog_pdf()
    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "demoted": 0,
        "dry_run": dry_run,
        "catalog": str(pdf_path) if pdf_path else "",
        "envelopes": {},
    }
    if pdf_path is None or not pdf_path.is_file():
        summary["skipped"] = 1
        summary["error"] = "catalog PDF not found"
        return summary

    webp_by_stem: dict[str, bytes] = {}
    for envelope_stem in _ENVELOPE_CATALOG_PAGE:
        try:
            crop = render_envelope_crop(pdf_path, envelope_stem)
            if dry_run:
                webp_by_stem[envelope_stem] = b""
            else:
                from io import BytesIO

                buf = BytesIO()
                crop.save(buf, format="PNG")
                webp_by_stem[envelope_stem] = convert_bytes_to_webp(
                    buf.getvalue(),
                    quality=DEFAULT_WEBP_QUALITY,
                    max_edge=MAX_EDGE_PX,
                    flatten_white=True,
                )
            summary["envelopes"][envelope_stem] = {
                "catalog_page": _ENVELOPE_CATALOG_PAGE[envelope_stem],
                "size": list(crop.size),
            }
        except (OSError, ValueError, KeyError) as exc:
            logger.warning("hv_catalog_dimensions crop %s failed: %s", envelope_stem, exc)
            summary["envelopes"][envelope_stem] = {"error": str(exc)}

    for sku in SKU.objects.filter(sku_code__iregex=r"(?i)^hv[ad]", is_published=True).order_by(
        "sku_code",
    ):
        code = (sku.sku_code or "").strip().upper()
        stem = envelope_stem_for_sku(code)
        if stem is None or stem not in webp_by_stem:
            summary["skipped"] += 1
            continue
        brand = "HVA" if code.startswith("HVA") else "HVD"
        match = _SKU_RE.match(code)
        nm = match.group("nm") if match else "?"
        sfx = (match.group("sfx") or "").upper() if match else ""
        alt = f"{brand}-{nm}{sfx} | Габаритные размеры (мм)"
        action, demoted = _upsert_dimensions(
            sku,
            stem=stem,
            webp=webp_by_stem[stem],
            alt=alt,
            dry_run=dry_run,
        )
        summary["demoted"] += demoted
        if action == "create":
            summary["created"] += 1
        else:
            summary["updated"] += 1
    summary["attached"] = summary["created"] + summary["updated"]
    return summary
