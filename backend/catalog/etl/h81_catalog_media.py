"""Photo, diagrams, and sliced catalog PDFs for H8101…H8122 kits.

Hero photos: studio JPEGs extracted from the ball-valve catalog PDF.
Gallery crops from the same PDF:
  - overall dimensions (family-specific pages);
  - wiring / aux switches / DIP settings («Подключение и настройка»).
Instruction ProductFiles: inclusive page ranges per family pair (e.g. H8101/02 → 6–9).

Wrong ``.local-catalog/img_0020`` / ``img_0022`` gallery rows (butterfly / mixed
extractions previously attached to flanged kits) are unpublished on apply.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pypdfium2 as pdfium
from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image

from catalog.etl.manual_diagrams import (
    SORT_AUX_SWITCH,
    SORT_DIMENSIONS,
    SORT_PHOTO,
    SORT_SETTINGS,
    SORT_WIRING,
    DiagramCrop,
    DiagramKind,
    _pil_to_png_bytes,
    _upsert_diagram,
    center_cutout_on_canvas,
    punch_near_white_background,
    render_pdf_page,
)
from catalog.etl.series_copy_ball_valves import CATALOG_IMAGES_DIR, CATALOG_PDF_PATH
from catalog.etl.sku_variant import parse_sku_variant
from catalog.etl.webp import convert_bytes_to_webp
from catalog.models import SKU, ProductFile, ProductImage
from catalog.validators import MAX_PRODUCT_FILE_SIZE_BYTES

logger = logging.getLogger(__name__)

_H81_KIT_PREFIX = re.compile(
    r"(?i)^(?P<prefix>h81(?:01|02|03|04|05|06|07|08|21|22))-bv",
)

_SOURCE_URL = "https://hoocon.ru/.local-assets/h81-catalog/{prefix}-{kind}.webp"

# Previously attached mistaken embeds (butterfly / wrong crop) on flanged kits.
_LEGACY_LOCAL_CATALOG_URLS: Final[tuple[str, ...]] = (
    "https://hoocon.ru/.local-catalog/img_0020_xref135_p010.jpeg",
    "https://hoocon.ru/.local-catalog/img_0022_xref183_p018.jpeg",
)

_CATALOG_RENDER_SCALE = 2.5

# Default window when a family does not override left/right.
_DIMS_LEFT = 0.04
_DIMS_RIGHT = 0.915  # stop before the red vertical banner

# Shared «Подключение и настройка» page layout (same red title bands on p9/13/…).
# Bands skip section titles; right edge stays left of the red vertical banner.
_WIRING_PAGE_BANDS: Final[tuple[tuple[DiagramKind, str, int, float, float, float, float], ...]] = (
    ("wiring", "Схема подключения", SORT_WIRING, 0.105, 0.330, 0.04, 0.915),
    (
        "aux_switch",
        "Вспомогательные концевые выключатели",
        SORT_AUX_SWITCH,
        0.355,
        0.600,
        0.04,
        0.915,
    ),
    (
        "settings",
        "Настройка DIP-переключателей",
        SORT_SETTINGS,
        0.625,
        0.920,
        0.04,
        0.915,
    ),
)


@dataclass(frozen=True, slots=True)
class _FamilyMedia:
    """One H81xx family → photo + dims crop + instruction/wiring pages."""

    photo_file: str
    dims_page_index: int
    dims_top: float
    dims_bottom: float = 0.93
    dims_left: float = _DIMS_LEFT
    dims_right: float = _DIMS_RIGHT
    # Inclusive 1-based catalog pages for the sliced instruction PDF.
    instr_first_page: int = 0
    instr_last_page: int = 0
    # 0-based page with «Подключение и настройка» (wiring / aux / DIP).
    wiring_page_index: int = 0
    # Shared label for the pair (H8101/H8102 → «H8101/H8102»).
    pair_label: str = ""


# H8103/04 catalog embed (img_0020) is a lug/butterfly-looking shot — reuse the
# correct flanged ball photo from the H8121 page instead.
#
# dims_* fractions: ink bbox of the drawings + ~40px pad, equal L/R when the
# red vertical banner allows; no «Габаритные размеры» title in the crop.
_FAMILY_MEDIA: Final[dict[str, _FamilyMedia]] = {
    "H8101": _FamilyMedia(
        "img_0019_xref90_p006.jpeg",
        5,
        0.718,
        0.955,
        0.328,
        0.955,
        instr_first_page=6,
        instr_last_page=9,
        wiring_page_index=8,
        pair_label="H8101/H8102",
    ),
    "H8102": _FamilyMedia(
        "img_0019_xref90_p006.jpeg",
        5,
        0.718,
        0.955,
        0.328,
        0.955,
        instr_first_page=6,
        instr_last_page=9,
        wiring_page_index=8,
        pair_label="H8101/H8102",
    ),
    "H8103": _FamilyMedia(
        "img_0023_xref210_p022.jpeg",
        10,
        0.556,
        0.830,
        0.429,
        0.934,
        instr_first_page=10,
        instr_last_page=13,
        wiring_page_index=12,
        pair_label="H8103/H8104",
    ),
    "H8104": _FamilyMedia(
        "img_0023_xref210_p022.jpeg",
        10,
        0.556,
        0.830,
        0.429,
        0.934,
        instr_first_page=10,
        instr_last_page=13,
        wiring_page_index=12,
        pair_label="H8103/H8104",
    ),
    "H8105": _FamilyMedia(
        "img_0021_xref160_p014.jpeg",
        13,
        0.745,
        0.939,
        0.482,
        0.933,
        instr_first_page=14,
        instr_last_page=17,
        wiring_page_index=16,
        pair_label="H8105/H8106",
    ),
    "H8106": _FamilyMedia(
        "img_0021_xref160_p014.jpeg",
        13,
        0.745,
        0.939,
        0.482,
        0.933,
        instr_first_page=14,
        instr_last_page=17,
        wiring_page_index=16,
        pair_label="H8105/H8106",
    ),
    "H8107": _FamilyMedia(
        "img_0022_xref183_p018.jpeg",
        18,
        0.562,
        0.881,
        0.322,
        0.934,
        instr_first_page=18,
        instr_last_page=21,
        wiring_page_index=20,
        pair_label="H8107/H8108",
    ),
    "H8108": _FamilyMedia(
        "img_0022_xref183_p018.jpeg",
        18,
        0.562,
        0.881,
        0.322,
        0.934,
        instr_first_page=18,
        instr_last_page=21,
        wiring_page_index=20,
        pair_label="H8107/H8108",
    ),
    "H8121": _FamilyMedia(
        "img_0023_xref210_p022.jpeg",
        22,
        0.566,
        0.807,
        0.412,
        0.926,
        instr_first_page=22,
        instr_last_page=25,
        wiring_page_index=24,
        pair_label="H8121/H8122",
    ),
    "H8122": _FamilyMedia(
        "img_0023_xref210_p022.jpeg",
        22,
        0.566,
        0.807,
        0.412,
        0.926,
        instr_first_page=22,
        instr_last_page=25,
        wiring_page_index=24,
        pair_label="H8121/H8122",
    ),
}


def parse_h81_kit_prefix(sku_code: str) -> str | None:
    """Return ``H8101``…``H8122`` from a kit SKU, or ``None``."""
    match = _H81_KIT_PREFIX.match((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    return match.group("prefix").upper()


def source_url_for_h81(prefix: str, kind: str) -> str:
    """Stable ProductImage.source_url for photo / diagram upsert."""
    return _SOURCE_URL.format(prefix=prefix.casefold(), kind=kind)


def instruction_title_for_h81(pair_label: str, first_page: int, last_page: int) -> str:
    """Human ProductFile title for a sliced catalog instruction PDF."""
    return f"Инструкция {pair_label} (каталог 2026, стр. {first_page}–{last_page})"


def find_h81_catalog_pdf(*, pdf_path: Path | None = None) -> Path | None:
    """Resolve the 2026 ball-valve catalog PDF (instr. dir or sibling hoocon)."""
    if pdf_path is not None:
        path = pdf_path.resolve()
        return path if path.is_file() else None
    if CATALOG_PDF_PATH.is_file():
        return CATALOG_PDF_PATH
    sibling = (
        Path(__file__).resolve().parents[3]
        / ".."
        / "hoocon"
        / "data"
        / "catalog"
        / "каталог 2026 шаровые - hoocon.pdf"
    ).resolve()
    return sibling if sibling.is_file() else None


def find_h81_catalog_images_dir(*, images_dir: Path | None = None) -> Path | None:
    """Resolve directory with extracted catalog JPEGs."""
    root = (images_dir or CATALOG_IMAGES_DIR).resolve()
    return root if root.is_dir() else None


def extract_catalog_page_range_pdf(
    pdf_path: Path,
    *,
    first_page: int,
    last_page: int,
) -> bytes:
    """Slice inclusive 1-based catalog pages into a new PDF payload.

    Args:
        pdf_path: Full ball-valve catalog PDF.
        first_page: First page number (1-based, inclusive).
        last_page: Last page number (1-based, inclusive).

    Returns:
        PDF bytes for the page range.

    Raises:
        ValueError: Invalid range or empty result.
        OSError: PDF cannot be opened/saved.
    """
    if first_page < 1 or last_page < first_page:
        raise ValueError(f"Invalid page range {first_page}–{last_page}")
    src = pdfium.PdfDocument(str(pdf_path))
    try:
        page_count = len(src)
        if last_page > page_count:
            raise ValueError(f"Page {last_page} beyond catalog ({page_count} pages)")
        dest = pdfium.PdfDocument.new()
        try:
            # import_pages accepts 0-based indices.
            indices = list(range(first_page - 1, last_page))
            dest.import_pages(src, indices)
            buf = io.BytesIO()
            dest.save(buf)
            payload = buf.getvalue()
        finally:
            dest.close()
    finally:
        src.close()
    if not payload:
        raise ValueError("Empty PDF slice")
    return payload


def crop_h81_dimensions(
    page: Image.Image,
    *,
    top: float,
    bottom: float = 0.93,
    left: float = _DIMS_LEFT,
    right: float = _DIMS_RIGHT,
) -> Image.Image:
    """Crop a fractional band from a catalog page raster."""
    width, height = page.size
    box = (
        int(left * width),
        int(top * height),
        int(right * width),
        int(bottom * height),
    )
    return page.crop(box)


def _photo_image_from_file(path: Path) -> Image.Image | None:
    """Load a studio JPEG, punch near-white backdrop, center on shared canvas."""
    if not path.is_file():
        logger.warning("h81_catalog_photo_missing path=%s", path)
        return None
    try:
        image = Image.open(io.BytesIO(path.read_bytes())).convert("RGB")
    except OSError as exc:
        logger.warning("h81_catalog_photo_open_failed path=%s err=%s", path, type(exc).__name__)
        return None
    punched = punch_near_white_background(image)
    return center_cutout_on_canvas(punched)


def crops_for_h81_family(
    prefix: str,
    *,
    pdf_path: Path,
    images_dir: Path,
) -> list[DiagramCrop]:
    """Build photo + wiring/aux/settings + dimensions crops for one H81xx family."""
    media = _FAMILY_MEDIA.get(prefix.upper())
    if media is None:
        return []

    out: list[DiagramCrop] = []
    photo_img = _photo_image_from_file(images_dir / media.photo_file)
    if photo_img is not None:
        out.append(
            DiagramCrop(
                kind="photo",
                png_bytes=_pil_to_png_bytes(photo_img),
                alt=f"{prefix} | Фото комплекта шаровой кран + электропривод (каталог 2026)",
                sort_order=SORT_PHOTO,
                source_url=source_url_for_h81(prefix, "photo"),
            ),
        )

    wiring_page = render_pdf_page(
        pdf_path,
        media.wiring_page_index,
        scale=_CATALOG_RENDER_SCALE,
    )
    for kind, label, sort_order, top, bottom, left, right in _WIRING_PAGE_BANDS:
        band = crop_h81_dimensions(
            wiring_page,
            top=top,
            bottom=bottom,
            left=left,
            right=right,
        )
        out.append(
            DiagramCrop(
                kind=kind,
                png_bytes=_pil_to_png_bytes(band),
                alt=f"{prefix} | {label} (каталог 2026)",
                sort_order=sort_order,
                source_url=source_url_for_h81(prefix, kind),
            ),
        )

    dims_page = render_pdf_page(pdf_path, media.dims_page_index, scale=_CATALOG_RENDER_SCALE)
    dims_img = crop_h81_dimensions(
        dims_page,
        top=media.dims_top,
        bottom=media.dims_bottom,
        left=media.dims_left,
        right=media.dims_right,
    )
    out.append(
        DiagramCrop(
            kind="dimensions",
            png_bytes=_pil_to_png_bytes(dims_img),
            alt=f"{prefix} | Габаритные размеры (мм), чертёж из каталога 2026",
            sort_order=SORT_DIMENSIONS,
            source_url=source_url_for_h81(prefix, "dimensions"),
        ),
    )
    return out


def unpublish_legacy_h81_local_catalog(*, dry_run: bool = False) -> int:
    """Hide mistaken flanged-kit embeds from earlier local-catalog attach."""
    qs = ProductImage.objects.filter(
        sku__sku_code__iregex=r"(?i)^h81(?:01|02|03|04|05|06|07|08|21|22)-bv",
        source_url__in=_LEGACY_LOCAL_CATALOG_URLS,
        is_published=True,
    )
    count = qs.count()
    if dry_run or count == 0:
        return count
    return qs.update(is_published=False)


def apply_h81_catalog_media(
    *,
    dry_run: bool = False,
    prefixes: tuple[str, ...] | None = None,
    pdf_path: Path | None = None,
    images_dir: Path | None = None,
) -> dict[str, Any]:
    """Attach catalog photo + wiring/aux/settings + dimensions to H81 kit SKUs.

    Args:
        dry_run: Count create/update without writing files.
        prefixes: Optional filter like ``("H8101", "H8121")``.
        pdf_path: Override catalog PDF.
        images_dir: Override extracted JPEG directory.

    Returns:
        Counters: created, updated, skipped, unpublished_legacy, series, dry_run.
    """
    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "unpublished_legacy": 0,
        "unpublished_aux_plain": 0,
        "series": {},
        "dry_run": dry_run,
    }

    catalog_pdf = find_h81_catalog_pdf(pdf_path=pdf_path)
    images_root = find_h81_catalog_images_dir(images_dir=images_dir)
    if catalog_pdf is None or images_root is None:
        logger.info(
            "h81_catalog_media_missing pdf=%s images=%s",
            catalog_pdf is not None,
            images_root is not None,
        )
        return summary

    summary["unpublished_legacy"] = unpublish_legacy_h81_local_catalog(dry_run=dry_run)

    wanted = {p.upper() for p in prefixes} if prefixes else None
    crop_cache: dict[str, list[DiagramCrop] | None] = {}
    webp_cache: dict[str, bytes] = {}

    skus = list(
        SKU.objects.filter(
            sku_code__iregex=r"(?i)^h81(?:01|02|03|04|05|06|07|08|21|22)-bv",
        ).order_by("sku_code"),
    )
    for sku in skus:
        prefix = parse_h81_kit_prefix(sku.sku_code)
        if prefix is None:
            summary["skipped"] += 1
            continue
        if wanted is not None and prefix not in wanted:
            continue

        if prefix not in crop_cache:
            try:
                crop_cache[prefix] = crops_for_h81_family(
                    prefix,
                    pdf_path=catalog_pdf,
                    images_dir=images_root,
                )
            except Exception:
                logger.exception("h81_catalog_crop_failed prefix=%s", prefix)
                crop_cache[prefix] = None

        crops = crop_cache[prefix]
        if not crops:
            summary["skipped"] += 1
            continue

        variant = parse_sku_variant(sku.sku_code)
        has_aux = variant.aux_switch is True
        attach_crops = [c for c in crops if has_aux or c.kind != "aux_switch"]
        if not has_aux:
            aux_url = source_url_for_h81(prefix, "aux_switch")
            aux_qs = ProductImage.objects.filter(
                sku=sku,
                source_url=aux_url,
                is_published=True,
            )
            if dry_run:
                summary["unpublished_aux_plain"] += aux_qs.count()
            else:
                summary["unpublished_aux_plain"] += aux_qs.update(is_published=False)

        for crop in attach_crops:
            if crop.source_url not in webp_cache:
                webp_cache[crop.source_url] = convert_bytes_to_webp(
                    crop.png_bytes,
                    quality=92,
                    max_edge=1600,
                )

        series_stats = summary["series"].setdefault(
            prefix.casefold(),
            {"created": 0, "updated": 0, "skus": 0},
        )
        series_stats["skus"] += 1
        for crop in attach_crops:
            action = _upsert_diagram(
                sku,
                crop,
                dry_run=dry_run,
                webp_bytes=webp_cache[crop.source_url],
            )
            if action == "create":
                summary["created"] += 1
                series_stats["created"] += 1
            elif action == "update":
                summary["updated"] += 1
                series_stats["updated"] += 1

    return summary


def apply_h81_instruction_pdfs(
    *,
    dry_run: bool = False,
    prefixes: tuple[str, ...] | None = None,
    pdf_path: Path | None = None,
) -> dict[str, Any]:
    """Attach sliced catalog pages as DATASHEET ProductFiles on H81 kit SKUs.

    Args:
        dry_run: Count without writing.
        prefixes: Optional filter like ``("H8101",)``.
        pdf_path: Override catalog PDF.

    Returns:
        Counters: created, updated, skipped, warnings, by_pair, dry_run.
    """
    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "warnings": [],
        "by_pair": {},
        "dry_run": dry_run,
    }
    catalog_pdf = find_h81_catalog_pdf(pdf_path=pdf_path)
    if catalog_pdf is None:
        summary["warnings"].append("Catalog PDF not found")
        return summary

    # One PDF slice per pair_label (shared by two prefixes).
    pair_payload: dict[str, tuple[bytes, str, str]] = {}
    wanted = {p.upper() for p in prefixes} if prefixes else None
    for family_prefix, media in _FAMILY_MEDIA.items():
        if wanted is not None and family_prefix not in wanted:
            continue
        if media.pair_label in pair_payload:
            continue
        try:
            payload = extract_catalog_page_range_pdf(
                catalog_pdf,
                first_page=media.instr_first_page,
                last_page=media.instr_last_page,
            )
        except (OSError, ValueError) as exc:
            msg = f"{media.pair_label}: {exc}"
            summary["warnings"].append(msg)
            logger.warning("h81_instruction_slice_failed pair=%s err=%s", media.pair_label, exc)
            continue
        if len(payload) > MAX_PRODUCT_FILE_SIZE_BYTES:
            msg = f"{media.pair_label}: slice too large ({len(payload)} bytes)"
            summary["warnings"].append(msg)
            continue
        title = instruction_title_for_h81(
            media.pair_label,
            media.instr_first_page,
            media.instr_last_page,
        )
        basename = (
            f"instrukciya-{media.pair_label.casefold().replace('/', '-')}"
            f"-katalog-2026-p{media.instr_first_page}-{media.instr_last_page}.pdf"
        )
        pair_payload[media.pair_label] = (payload, title, basename)

    skus = list(
        SKU.objects.filter(
            sku_code__iregex=r"(?i)^h81(?:01|02|03|04|05|06|07|08|21|22)-bv",
        ).order_by("sku_code"),
    )
    with transaction.atomic():
        for sku in skus:
            prefix = parse_h81_kit_prefix(sku.sku_code)
            if prefix is None:
                summary["skipped"] += 1
                continue
            if wanted is not None and prefix not in wanted:
                continue
            family = _FAMILY_MEDIA.get(prefix)
            if family is None or family.pair_label not in pair_payload:
                summary["skipped"] += 1
                continue
            payload, title, basename = pair_payload[family.pair_label]
            pair_stats = summary["by_pair"].setdefault(
                family.pair_label,
                {"created": 0, "updated": 0, "skipped": 0, "skus": 0},
            )
            pair_stats["skus"] += 1
            existing = ProductFile.objects.filter(sku=sku, title=title).first()
            if dry_run:
                if existing is None:
                    summary["created"] += 1
                    pair_stats["created"] += 1
                else:
                    summary["updated"] += 1
                    pair_stats["updated"] += 1
                continue
            if existing is None:
                pf = ProductFile(
                    sku=sku,
                    title=title,
                    file_type=ProductFile.FileType.DATASHEET,
                    is_published=True,
                    sort_order=0,
                )
                pf.file.save(basename, ContentFile(payload), save=True)
                summary["created"] += 1
                pair_stats["created"] += 1
                logger.info(
                    "h81_instruction_attached sku=%s title=%s",
                    sku.sku_code,
                    title,
                )
            else:
                current_size = existing.file.size if existing.file else 0
                if current_size != len(payload):
                    existing.file.save(basename, ContentFile(payload), save=True)
                    existing.is_published = True
                    existing.save(update_fields=["is_published", "updated_at"])
                    summary["updated"] += 1
                    pair_stats["updated"] += 1
                else:
                    summary["skipped"] += 1
                    pair_stats["skipped"] += 1
        if dry_run:
            transaction.set_rollback(True)

    return summary
