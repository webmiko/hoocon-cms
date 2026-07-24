"""Photo + overall-dimensions gallery for H8101…H8122 kits from the 2026 catalog.

Hero photos: studio JPEGs extracted from the ball-valve catalog PDF.
Dimension drawings: cropped from the same PDF (family-specific pages).

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

from PIL import Image

from catalog.etl.manual_diagrams import (
    SORT_DIMENSIONS,
    SORT_PHOTO,
    DiagramCrop,
    _pil_to_png_bytes,
    _upsert_diagram,
    punch_near_white_background,
    render_pdf_page,
)
from catalog.etl.series_copy_ball_valves import CATALOG_IMAGES_DIR, CATALOG_PDF_PATH
from catalog.etl.webp import convert_bytes_to_webp
from catalog.models import SKU, ProductImage

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


@dataclass(frozen=True, slots=True)
class _FamilyMedia:
    """One H81xx family → photo file + PDF dimensions page crop."""

    photo_file: str
    dims_page_index: int
    dims_top: float
    dims_bottom: float = 0.93
    dims_left: float = _DIMS_LEFT
    dims_right: float = _DIMS_RIGHT


# H8103/04 catalog embed (img_0020) is a lug/butterfly-looking shot — reuse the
# correct flanged ball photo from the H8121 page instead.
#
# dims_* fractions: skip «Габаритные размеры» / tables above the drawings;
# right edge stays left of the red banner so H/H1 ticks are not clipped.
# H8101/H8102 (catalog page 6): tight box around S/G/L1 + H/H1/L drawings.
_FAMILY_MEDIA: Final[dict[str, _FamilyMedia]] = {
    "H8101": _FamilyMedia("img_0019_xref90_p006.jpeg", 5, 0.718, 0.950, 0.150, 0.920),
    "H8102": _FamilyMedia("img_0019_xref90_p006.jpeg", 5, 0.718, 0.950, 0.150, 0.920),
    "H8103": _FamilyMedia("img_0023_xref210_p022.jpeg", 10, 0.575, 0.895, 0.30, 0.928),
    "H8104": _FamilyMedia("img_0023_xref210_p022.jpeg", 10, 0.575, 0.895, 0.30, 0.928),
    "H8105": _FamilyMedia("img_0021_xref160_p014.jpeg", 13, 0.745, 0.928, 0.08, 0.918),
    "H8106": _FamilyMedia("img_0021_xref160_p014.jpeg", 13, 0.745, 0.928, 0.08, 0.918),
    "H8107": _FamilyMedia("img_0022_xref183_p018.jpeg", 18, 0.545, 0.875, 0.28, 0.928),
    "H8108": _FamilyMedia("img_0022_xref183_p018.jpeg", 18, 0.545, 0.875, 0.28, 0.928),
    "H8121": _FamilyMedia("img_0023_xref210_p022.jpeg", 22, 0.545, 0.875, 0.35, 0.928),
    "H8122": _FamilyMedia("img_0023_xref210_p022.jpeg", 22, 0.545, 0.875, 0.35, 0.928),
}


def parse_h81_kit_prefix(sku_code: str) -> str | None:
    """Return ``H8101``…``H8122`` from a kit SKU, or ``None``."""
    match = _H81_KIT_PREFIX.match((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    return match.group("prefix").upper()


def source_url_for_h81(prefix: str, kind: str) -> str:
    """Stable ProductImage.source_url for photo / dimensions upsert."""
    return _SOURCE_URL.format(prefix=prefix.casefold(), kind=kind)


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


def crop_h81_dimensions(
    page: Image.Image,
    *,
    top: float,
    bottom: float = 0.93,
    left: float = _DIMS_LEFT,
    right: float = _DIMS_RIGHT,
) -> Image.Image:
    """Crop the overall-dimensions drawings band from a catalog page raster."""
    width, height = page.size
    box = (
        int(left * width),
        int(top * height),
        int(right * width),
        int(bottom * height),
    )
    return page.crop(box)


def _photo_image_from_file(path: Path) -> Image.Image | None:
    """Load a studio JPEG and punch near-white backdrop."""
    if not path.is_file():
        logger.warning("h81_catalog_photo_missing path=%s", path)
        return None
    try:
        image = Image.open(io.BytesIO(path.read_bytes())).convert("RGB")
    except OSError as exc:
        logger.warning("h81_catalog_photo_open_failed path=%s err=%s", path, type(exc).__name__)
        return None
    return punch_near_white_background(image)


def crops_for_h81_family(
    prefix: str,
    *,
    pdf_path: Path,
    images_dir: Path,
) -> list[DiagramCrop]:
    """Build photo + dimensions DiagramCrop rows for one H81xx family."""
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

    page = render_pdf_page(pdf_path, media.dims_page_index, scale=_CATALOG_RENDER_SCALE)
    dims_img = crop_h81_dimensions(
        page,
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
    """Attach catalog photo + dimensions to every H8101…H8122 kit SKU.

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

        for crop in crops:
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
        for crop in crops:
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
