"""Crop wiring + overall-dimensions diagrams from instruction PDFs / catalog.

D/DS manuals (4 pages): diagrams on page 3 (stacked).
A/AS manuals (2 pages, landscape): diagrams in the right column of page 2.
SA..FU manuals (2 pages, landscape): wiring + dimensions in the right column of page 2.
HVA: dimensions from the Russian Illustrator catalog (``.ai``, PDF-compatible).

Source PDFs: attached ``ProductFile`` rows, with fallback to ``_инструкции-pdf``.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, cast

import pypdfium2 as pdfium
from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image, ImageDraw, ImageFont

from catalog.etl.manual_pdfs import (
    default_manuals_dir,
    normalize_manual_stem,
    parse_manual_stem,
    parse_safu_manual_stem,
)
from catalog.etl.sku_variant import parse_sku_variant
from catalog.etl.webp import convert_bytes_to_webp
from catalog.models import SKU, ProductFile, ProductImage

logger = logging.getLogger(__name__)

DiagramKind = Literal["wiring", "dimensions", "photo", "photo_thermal"]
Edition = Literal["on_off", "modulating_24"]

_DAFU_CODE = re.compile(r"(?i)^da(?P<nm>\d+)fu")
_SAFU_CODE = re.compile(r"(?i)^sa(?P<nm>\d+)fu")
_RENDER_SCALE = 3.0

# Idempotent CDN-style keys (URLField-valid); files are local media, not fetched.
_SOURCE_URL = "https://hoocon.ru/.local-assets/manual-diagrams/{series}-{edition}-{kind}.webp"
_SAFU_SOURCE_URL = "https://hoocon.ru/.local-assets/manual-diagrams/sa{nm}fu-ds-{kind}.webp"

SORT_PHOTO = 0
SORT_WIRING = 5
SORT_DIMENSIONS = 6

# Small spring-return bodies without a dedicated PDF reuse DA5 drawings for now.
_PDF_FALLBACK_NM: Final[dict[int, int]] = {
    3: 5,
}
# SA20 has no manual yet — reuse SA15 wiring/dimensions crops.
_SAFU_PDF_FALLBACK_NM: Final[dict[int, int]] = {
    20: 15,
}
# SAMU: map Nm → PDF Nm when a series reuses another family's manual (like SAFU).
_SAMU_PDF_FALLBACK_NM: Final[dict[int, int]] = {}

_LEGACY_COMBINED_ALT = "размеры и способ подключения"
_LEGACY_DIMENSION_URL = "https://hoocon.ru/.local-assets/dafu-dimensions-98x156x84.webp"


@dataclass(frozen=True, slots=True)
class DiagramCrop:
    """One cropped diagram ready to attach."""

    kind: DiagramKind
    png_bytes: bytes
    alt: str
    sort_order: int
    source_url: str


def parse_dafu_series_nm(sku_code: str) -> int | None:
    """Return torque family number from ``da10fu24-d`` → ``10``."""
    match = _DAFU_CODE.match((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    return int(match.group("nm"))


def edition_for_sku(sku_code: str) -> Edition | None:
    """Map SKU suffix to manual edition (D/DS vs A/AS)."""
    variant = parse_sku_variant(sku_code)
    if variant.control == "modulating":
        return "modulating_24"
    if variant.control == "on_off":
        return "on_off"
    return None


def source_url_for(series_nm: int, edition: Edition, kind: DiagramKind) -> str:
    """Stable ProductImage.source_url for upsert."""
    edition_key = "aas" if edition == "modulating_24" else "dds"
    return _SOURCE_URL.format(
        series=f"da{series_nm}fu",
        edition=edition_key,
        kind=kind,
    )


def _pil_to_png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def punch_near_white_background(
    image: Image.Image,
    *,
    luma_min: int = 220,
) -> Image.Image:
    """Make edge-connected near-white pixels transparent (studio cutout).

    Flood-fills from the image border so white dials / labels on the product
    face stay opaque. Soft grey vignette from PDF pages is treated as backdrop
    when luminance is high enough and connected to the edge.

    Args:
        image: RGB/RGBA crop.
        luma_min: Minimum average channel value to treat as backdrop.

    Returns:
        RGBA image with transparent backdrop.
    """
    from collections import deque

    rgba = image.convert("RGBA")
    pixels = cast(Any, rgba.load())
    width, height = rgba.size
    if width < 2 or height < 2 or pixels is None:
        return rgba

    def is_backdrop(x: int, y: int) -> bool:
        r, g, b, a = pixels[x, y]
        if a < 16:
            return True
        return (r + g + b) / 3 >= luma_min and min(r, g, b) >= luma_min - 15

    seen = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def try_enqueue(x: int, y: int) -> None:
        if x < 0 or y < 0 or x >= width or y >= height:
            return
        index = y * width + x
        if seen[index]:
            return
        if not is_backdrop(x, y):
            return
        seen[index] = 1
        queue.append((x, y))

    for x in range(width):
        try_enqueue(x, 0)
        try_enqueue(x, height - 1)
    for y in range(height):
        try_enqueue(0, y)
        try_enqueue(width - 1, y)

    while queue:
        x, y = queue.popleft()
        pixels[x, y] = (255, 255, 255, 0)
        try_enqueue(x + 1, y)
        try_enqueue(x - 1, y)
        try_enqueue(x, y + 1)
        try_enqueue(x, y - 1)

    return rgba


def crop_on_off_diagrams(page: Image.Image) -> tuple[Image.Image, Image.Image]:
    """Crop wiring and dimensions from a D/DS page-3 raster.

    Skips HOOCON chrome and the black section titles («Схема подключения»,
    «Габаритные размеры…») so only the drawings remain.
    """
    width, height = page.size
    # Below black «Схема подключения» bar (~0.12–0.15), above dims title (~0.34).
    wiring = page.crop((30, int(0.15 * height), width - 30, int(0.34 * height)))
    # Below black «Габаритные размеры…» bar (~0.34–0.38).
    dimensions = page.crop((30, int(0.38 * height), width - 30, int(0.64 * height)))
    return wiring, dimensions


def crop_modulating_diagrams(page: Image.Image) -> tuple[Image.Image, Image.Image]:
    """Crop wiring + dimensions from the right column of an A/AS page-2 raster.

    Same vertical cuts as D/DS: drop logo and black section titles.
    """
    width, height = page.size
    left = int(width * 0.48)
    wiring = page.crop((left, int(0.15 * height), width - 20, int(0.34 * height)))
    dimensions = page.crop((left, int(0.38 * height), width - 20, int(0.62 * height)))
    return wiring, dimensions


def crop_safu_diagrams(page: Image.Image) -> tuple[Image.Image, Image.Image]:
    """Crop wiring + dimensions from the right column of an SA..FU page-2 raster.

    Layout (landscape): left = ТТХ table; right = Wiring → Dimensions → Thermal.
    Black section titles sit near y≈0.10, 0.34, 0.65 — crop content between them.
    """
    width, height = page.size
    left = int(width * 0.48)
    wiring = page.crop((left, int(0.12 * height), width - 10, int(0.335 * height)))
    dimensions = page.crop((left, int(0.37 * height), width - 10, int(0.645 * height)))
    return wiring, dimensions


def render_pdf_page(pdf_path: Path, page_index: int, *, scale: float = _RENDER_SCALE) -> Image.Image:
    """Rasterize a zero-based PDF page to RGB."""
    document = pdfium.PdfDocument(str(pdf_path))
    try:
        page = document[page_index]
        return page.render(scale=scale).to_pil().convert("RGB")
    finally:
        document.close()


def diagrams_from_pdf(
    pdf_path: Path,
    *,
    edition: Edition,
    series_nm: int,
) -> list[DiagramCrop]:
    """Build wiring + dimensions crops from a series manual PDF.

    Args:
        pdf_path: Local PDF path.
        edition: ``on_off`` (D/DS) or ``modulating_24`` (A/AS).
        series_nm: Torque family (5 / 10 / 15 / 20).

    Returns:
        Two ``DiagramCrop`` rows (wiring, dimensions).
    """
    if edition == "on_off":
        page = render_pdf_page(pdf_path, 2)
        wiring_img, dims_img = crop_on_off_diagrams(page)
    else:
        page = render_pdf_page(pdf_path, 1)
        wiring_img, dims_img = crop_modulating_diagrams(page)

    series = f"DA{series_nm}FU"
    return [
        DiagramCrop(
            kind="wiring",
            png_bytes=_pil_to_png_bytes(wiring_img),
            alt=f"{series} | Схема подключения из инструкции",
            sort_order=SORT_WIRING,
            source_url=source_url_for(series_nm, edition, "wiring"),
        ),
        DiagramCrop(
            kind="dimensions",
            png_bytes=_pil_to_png_bytes(dims_img),
            alt=f"{series} | Габаритные размеры привода (мм), чертёж из инструкции",
            sort_order=SORT_DIMENSIONS,
            source_url=source_url_for(series_nm, edition, "dimensions"),
        ),
    ]


def pdf_source_series_nm(series_nm: int) -> int:
    """Series whose PDF to crop when this family has no dedicated manual yet."""
    return _PDF_FALLBACK_NM.get(series_nm, series_nm)


def safu_pdf_source_series_nm(series_nm: int) -> int:
    """SAFU series whose PDF to crop when this family has no dedicated manual."""
    return _SAFU_PDF_FALLBACK_NM.get(series_nm, series_nm)


def parse_safu_series_nm(sku_code: str) -> int | None:
    """Return torque family number from ``sa10fu24-ds`` → ``10``."""
    match = _SAFU_CODE.match((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    return int(match.group("nm"))


def source_url_for_safu(series_nm: int, kind: DiagramKind) -> str:
    """Stable local-asset key for a SAFU diagram row."""
    return _SAFU_SOURCE_URL.format(nm=series_nm, kind=kind)


def diagrams_from_safu_pdf(pdf_path: Path, *, series_nm: int) -> list[DiagramCrop]:
    """Build wiring + dimensions crops from an SA..FU manual PDF (page 2)."""
    page = render_pdf_page(pdf_path, 1)
    wiring_img, dims_img = crop_safu_diagrams(page)
    series = f"SA{series_nm}FU"
    return [
        DiagramCrop(
            kind="wiring",
            png_bytes=_pil_to_png_bytes(wiring_img),
            alt=f"{series} | Схема подключения из инструкции",
            sort_order=SORT_WIRING,
            source_url=source_url_for_safu(series_nm, "wiring"),
        ),
        DiagramCrop(
            kind="dimensions",
            png_bytes=_pil_to_png_bytes(dims_img),
            alt=f"{series} | Габаритные размеры привода (мм), чертёж из инструкции",
            sort_order=SORT_DIMENSIONS,
            source_url=source_url_for_safu(series_nm, "dimensions"),
        ),
    ]


def relabel_safu_diagram_crops(
    crops: list[DiagramCrop],
    *,
    series_nm: int,
) -> list[DiagramCrop]:
    """Retarget crop alts / source_url to the SKU series (e.g. SA20 borrowing SA15)."""
    series = f"SA{series_nm}FU"
    out: list[DiagramCrop] = []
    for crop in crops:
        if crop.kind == "wiring":
            alt = f"{series} | Схема подключения из инструкции"
        else:
            alt = f"{series} | Габаритные размеры привода (мм), чертёж из инструкции"
        out.append(
            DiagramCrop(
                kind=crop.kind,
                png_bytes=crop.png_bytes,
                alt=alt,
                sort_order=crop.sort_order,
                source_url=source_url_for_safu(series_nm, crop.kind),
            ),
        )
    return out


def find_safu_manual_pdf(
    *,
    series_nm: int,
    manuals_dir: Path | None = None,
) -> Path | None:
    """Locate an SA..FU manual PDF for the series (with fallback Nm)."""
    pdf_nm = safu_pdf_source_series_nm(series_nm)
    file_qs = ProductFile.objects.filter(
        is_published=True,
        sku__sku_code__iregex=rf"(?i)^sa{pdf_nm}fu",
        title__icontains="Инструкция SA",
    ).exclude(file="")
    for product_file in file_qs.select_related("sku")[:8]:
        path = Path(product_file.file.path)
        if path.is_file():
            return path

    root = manuals_dir or default_manuals_dir()
    if not root.is_dir():
        return None
    for path in sorted(root.iterdir()):
        if path.suffix.casefold() != ".pdf":
            continue
        nm = parse_safu_manual_stem(normalize_manual_stem(path.name))
        if nm == pdf_nm:
            return path.resolve()
    return None


def relabel_diagram_crops(
    crops: list[DiagramCrop],
    *,
    series_nm: int,
    edition: Edition,
) -> list[DiagramCrop]:
    """Retarget crop alts / source_url to the SKU series (e.g. DA3 borrowing DA5)."""
    series = f"DA{series_nm}FU"
    out: list[DiagramCrop] = []
    for crop in crops:
        if crop.kind == "wiring":
            alt = f"{series} | Схема подключения из инструкции"
        else:
            alt = f"{series} | Габаритные размеры привода (мм), чертёж из инструкции"
        out.append(
            DiagramCrop(
                kind=crop.kind,
                png_bytes=crop.png_bytes,
                alt=alt,
                sort_order=crop.sort_order,
                source_url=source_url_for(series_nm, edition, crop.kind),
            ),
        )
    return out


def find_manual_pdf(
    *,
    series_nm: int,
    edition: Edition,
    manuals_dir: Path | None = None,
) -> Path | None:
    """Locate a DAFU manual PDF for the series edition.

    Prefers an already-attached ``ProductFile``, then ``_инструкции-pdf``.
    Resolves ``_PDF_FALLBACK_NM`` (DA3 → DA5) when the series has no PDF yet.
    """
    pdf_nm = pdf_source_series_nm(series_nm)
    if edition == "modulating_24":
        file_qs = ProductFile.objects.filter(
            is_published=True,
            sku__sku_code__iregex=rf"(?i)^da{pdf_nm}fu24-a",
        ).exclude(file="")
    else:
        file_qs = ProductFile.objects.filter(
            is_published=True,
            sku__sku_code__iregex=rf"(?i)^da{pdf_nm}fu.*-d(s)?$",
        ).exclude(file="")

    for product_file in file_qs.select_related("sku")[:8]:
        path = Path(product_file.file.path)
        if path.is_file():
            return path

    root = manuals_dir or default_manuals_dir()
    if not root.is_dir():
        return None
    wanted_kind = "modulating_24" if edition == "modulating_24" else "on_off"
    for path in sorted(root.iterdir()):
        if path.suffix.casefold() != ".pdf":
            continue
        parsed = parse_manual_stem(normalize_manual_stem(path.name))
        if parsed is None:
            continue
        nm, kind = parsed
        if nm == pdf_nm and kind == wanted_kind:
            return path.resolve()
    return None


def unpublish_legacy_combined_photos(*, dry_run: bool = False) -> int:
    """Hide Tilda «Размеры и способ подключения» shots superseded by PDF crops."""
    qs = ProductImage.objects.filter(
        sku__sku_code__iregex=r"(?i)^da\d+fu",
        alt__icontains=_LEGACY_COMBINED_ALT,
        is_published=True,
    )
    count = qs.count()
    if dry_run or count == 0:
        return count
    return qs.update(is_published=False)


def unpublish_legacy_static_dimension(*, dry_run: bool = False) -> int:
    """Hide the earlier single DA5 static dimensions asset (replaced per series)."""
    qs = ProductImage.objects.filter(source_url=_LEGACY_DIMENSION_URL, is_published=True)
    count = qs.count()
    if dry_run or count == 0:
        return count
    return qs.update(is_published=False)


def _upsert_diagram(
    sku: SKU,
    crop: DiagramCrop,
    *,
    dry_run: bool,
    webp_bytes: bytes | None = None,
) -> str:
    """Create or refresh one diagram image. Returns ``create`` / ``update`` / ``skip``."""
    webp = (
        webp_bytes
        if webp_bytes is not None
        else convert_bytes_to_webp(
            crop.png_bytes,
            quality=92,
            max_edge=1600,
        )
    )
    existing = ProductImage.objects.filter(sku=sku, source_url=crop.source_url).first()
    if dry_run:
        return "update" if existing else "create"

    filename = f"{sku.sku_code.lower()}-{crop.kind}.webp"
    with transaction.atomic():
        if existing is None:
            image = ProductImage(
                sku=sku,
                alt=crop.alt[:300],
                source_url=crop.source_url,
                sort_order=crop.sort_order,
                is_published=True,
            )
            image.image.save(filename, ContentFile(webp), save=False)
            image.full_clean()
            image.save()
            return "create"

        existing.alt = crop.alt[:300]
        existing.sort_order = crop.sort_order
        existing.is_published = True
        existing.image.save(filename, ContentFile(webp), save=False)
        existing.full_clean()
        existing.save()
        return "update"


def apply_manual_diagrams(*, dry_run: bool = False) -> dict[str, Any]:
    """Attach wiring + dimensions diagrams for every DAFU SKU that has a manual PDF.

    Returns:
        Counters: created, updated, unpublished, skipped, series.
    """
    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "unpublished_combined": 0,
        "unpublished_static": 0,
        "skipped": 0,
        "series": {},
        "dry_run": dry_run,
    }

    summary["unpublished_combined"] = unpublish_legacy_combined_photos(dry_run=dry_run)
    summary["unpublished_static"] = unpublish_legacy_static_dimension(dry_run=dry_run)

    skus = list(
        SKU.objects.filter(sku_code__iregex=r"(?i)^da\d+fu").order_by("sku_code"),
    )
    crop_cache: dict[tuple[int, Edition], list[DiagramCrop] | None] = {}

    for sku in skus:
        series_nm = parse_dafu_series_nm(sku.sku_code)
        edition = edition_for_sku(sku.sku_code)
        if series_nm is None or edition is None:
            summary["skipped"] += 1
            continue

        pdf_nm = pdf_source_series_nm(series_nm)
        cache_key = (pdf_nm, edition)
        if cache_key not in crop_cache:
            pdf_path = find_manual_pdf(series_nm=series_nm, edition=edition)
            if pdf_path is None:
                logger.info(
                    "manual_diagram_pdf_missing series=%s edition=%s pdf_nm=%s",
                    series_nm,
                    edition,
                    pdf_nm,
                )
                crop_cache[cache_key] = None
            else:
                try:
                    crop_cache[cache_key] = diagrams_from_pdf(
                        pdf_path,
                        edition=edition,
                        series_nm=pdf_nm,
                    )
                except Exception as exc:
                    logger.exception(
                        "manual_diagram_crop_failed pdf=%s series=%s edition=%s err_type=%s",
                        pdf_path,
                        series_nm,
                        edition,
                        type(exc).__name__,
                    )
                    crop_cache[cache_key] = None

        raw_crops = crop_cache[cache_key]
        if not raw_crops:
            summary["skipped"] += 1
            continue

        crops = relabel_diagram_crops(
            raw_crops,
            series_nm=series_nm,
            edition=edition,
        )

        series_key = f"da{series_nm}fu-{edition}"
        series_stats = summary["series"].setdefault(
            series_key,
            {"created": 0, "updated": 0, "skus": 0},
        )
        series_stats["skus"] += 1
        for crop in crops:
            action = _upsert_diagram(sku, crop, dry_run=dry_run)
            if action == "create":
                summary["created"] += 1
                series_stats["created"] += 1
            elif action == "update":
                summary["updated"] += 1
                series_stats["updated"] += 1

    return summary


def apply_safu_manual_diagrams(*, dry_run: bool = False) -> dict[str, Any]:
    """Attach wiring + dimensions diagrams for every SA..FU SKU with a manual PDF.

    Returns:
        Counters: created, updated, skipped, series.
    """
    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "series": {},
        "dry_run": dry_run,
    }

    skus = list(
        SKU.objects.filter(sku_code__iregex=r"(?i)^sa\d+fu").order_by("sku_code"),
    )
    crop_cache: dict[int, list[DiagramCrop] | None] = {}

    for sku in skus:
        series_nm = parse_safu_series_nm(sku.sku_code)
        if series_nm is None:
            summary["skipped"] += 1
            continue

        pdf_nm = safu_pdf_source_series_nm(series_nm)
        if pdf_nm not in crop_cache:
            pdf_path = find_safu_manual_pdf(series_nm=series_nm)
            if pdf_path is None:
                logger.info(
                    "safu_manual_diagram_pdf_missing series=%s pdf_nm=%s",
                    series_nm,
                    pdf_nm,
                )
                crop_cache[pdf_nm] = None
            else:
                try:
                    crop_cache[pdf_nm] = diagrams_from_safu_pdf(
                        pdf_path,
                        series_nm=pdf_nm,
                    )
                except Exception as exc:
                    logger.exception(
                        "safu_manual_diagram_crop_failed pdf=%s series=%s err_type=%s",
                        pdf_path,
                        series_nm,
                        type(exc).__name__,
                    )
                    crop_cache[pdf_nm] = None

        raw_crops = crop_cache[pdf_nm]
        if not raw_crops:
            summary["skipped"] += 1
            continue

        crops = relabel_safu_diagram_crops(raw_crops, series_nm=series_nm)

        series_key = f"sa{series_nm}fu"
        series_stats = summary["series"].setdefault(
            series_key,
            {"created": 0, "updated": 0, "skus": 0},
        )
        series_stats["skus"] += 1
        for crop in crops:
            action = _upsert_diagram(sku, crop, dry_run=dry_run)
            if action == "create":
                summary["created"] += 1
                series_stats["created"] += 1
            elif action == "update":
                summary["updated"] += 1
                series_stats["updated"] += 1

    return summary


_DAMU_CODE = re.compile(r"(?i)^da(?P<nm>\d+)mu(?!q)")
_DAMU_SOURCE_URL = "https://hoocon.ru/.local-assets/manual-diagrams/da{nm}mu-{edition}-{kind}.webp"


def parse_damu_series_nm(sku_code: str) -> int | None:
    """Return torque family from ``DA8MU24-D`` → ``8``."""
    match = _DAMU_CODE.match((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    return int(match.group("nm"))


def _right_column_black_bands(
    page: Image.Image,
    *,
    left: int,
    dark_thresh: int = 45,
    row_frac: float = 0.65,
    min_band_px: int = 8,
) -> list[tuple[int, int]]:
    """Return ``(y0, y1)`` spans of black section titles in the right column.

    Args:
        page: Full-page RGB raster.
        left: Left X of the right-hand content column.
        dark_thresh: Max RGB channel value treated as black.
        row_frac: Minimum fraction of dark samples to mark a row as a bar.
        min_band_px: Ignore thinner noise bands.

    Returns:
        Merged top→bottom black bars as inclusive pixel ranges.
    """
    width, height = page.size
    column = page.crop((left, 0, max(left + 1, width - 4), height))
    col_w, col_h = column.size
    pixels = cast(Any, column.load())
    dark_rows: list[int] = []
    step = max(1, col_w // 120)
    for y in range(col_h):
        dark = 0
        samples = 0
        for x in range(0, col_w, step):
            red, green, blue = pixels[x, y][:3]
            samples += 1
            if red < dark_thresh and green < dark_thresh and blue < dark_thresh:
                dark += 1
        if samples and dark / samples >= row_frac:
            dark_rows.append(y)
    raw: list[tuple[int, int]] = []
    if dark_rows:
        start = prev = dark_rows[0]
        for y in dark_rows[1:]:
            if y <= prev + 3:
                prev = y
            else:
                raw.append((start, prev))
                start = prev = y
        raw.append((start, prev))
    raw = [(a, b) for a, b in raw if (b - a) >= min_band_px]
    merge_gap = max(8, int(0.025 * height))
    merged: list[list[int]] = []
    for start, end in raw:
        if merged and start - merged[-1][1] < merge_gap:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return [(a, b) for a, b in merged]


def crop_damu_diagrams(page: Image.Image) -> tuple[Image.Image, Image.Image]:
    """Crop wiring + dimensions from DAMU English manual page 2 (landscape).

    Layout: left = photo + ТТХ; right = Wiring → Dimensions → (optional extras).
    Black section titles are detected and excluded so crops keep only drawings.
    """
    width, height = page.size
    left = int(width * 0.48)
    bands = _right_column_black_bands(page, left=left)
    if len(bands) >= 2:
        wiring_top = bands[0][1] + 6
        wiring_bot = max(wiring_top + 40, bands[1][0] - 4)
        dims_top = bands[1][1] + 6
        if len(bands) >= 3:
            dims_bot = max(dims_top + 40, bands[2][0] - 4)
        else:
            dims_bot = int(0.65 * height)
        wiring = page.crop((left, wiring_top, width - 10, wiring_bot))
        dimensions = page.crop((left, dims_top, width - 10, dims_bot))
        return wiring, dimensions

    # Fallback when bars are not detected (same cuts as SA..FU manuals).
    wiring = page.crop((left, int(0.125 * height), width - 10, int(0.335 * height)))
    dimensions = page.crop((left, int(0.375 * height), width - 10, int(0.645 * height)))
    return wiring, dimensions


def source_url_for_damu(series_nm: int, edition: Edition, kind: DiagramKind) -> str:
    """Stable local-asset key for a DAMU diagram row."""
    edition_key = "aas" if edition == "modulating_24" else "dds"
    return _DAMU_SOURCE_URL.format(nm=series_nm, edition=edition_key, kind=kind)


_SHAFT_LABEL_FONTS: Final[tuple[str, ...]] = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


def _load_shaft_label_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Best-effort sans font for diagram label patches."""
    for path in _SHAFT_LABEL_FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


# Relative boxes over PDF caption ``6...16mm`` (right of ○/◇ icons).
# English manuals print 6…16; catalog ТТХ for DA2/4/6MU use 8…16 mm.
_SHAFT_LABEL_6_TO_8_REGION: Final[dict[int, tuple[float, float, float, float]]] = {
    2: (0.261, 0.040, 0.369, 0.088),
    4: (0.250, 0.080, 0.340, 0.140),
    6: (0.250, 0.080, 0.340, 0.140),
}


def patch_damu_dimensions_shaft_label(
    image: Image.Image,
    *,
    series_nm: int,
) -> Image.Image:
    """Replace PDF label ``6...16mm`` with catalog value ``8...16mm``.

    Applies to DA2MU / DA4MU / DA6MU dimension crops from English manuals.
    """
    rel = _SHAFT_LABEL_6_TO_8_REGION.get(series_nm)
    if rel is None:
        return image
    width, height = image.size
    region = (
        int(rel[0] * width),
        int(rel[1] * height),
        int(rel[2] * width),
        int(rel[3] * height),
    )
    patched = image.copy()
    draw = ImageDraw.Draw(patched)
    draw.rectangle(region, fill=(255, 255, 255))
    font_size = max(12, int(0.030 * height))
    font = _load_shaft_label_font(font_size)
    label = "8...16mm"
    text_box = draw.textbbox((0, 0), label, font=font)
    text_h = text_box[3] - text_box[1]
    x = region[0] + 2
    y = region[1] + max(0, ((region[3] - region[1]) - text_h) // 2) - 1
    draw.text((x, y), label, fill=(20, 20, 20), font=font)
    return patched


def patch_da2mu_dimensions_shaft_label(image: Image.Image) -> Image.Image:
    """Backward-compatible alias for DA2MU shaft-label patch."""
    return patch_damu_dimensions_shaft_label(image, series_nm=2)


# Belimo RU glossary: docs/tech-copy-belimo-ru.md (Wiring Diagram section).
_WIRING_LABEL_ACTUATOR_RU: Final[str] = "Привод"
_WIRING_LABEL_AUX_RU: Final[str] = "Вспомогательный переключатель"
# English "Actuator" ≈ 98 px; "Auxiliary switch" ≈ 176 px at render scale 3.
_WIRING_ACTUATOR_MAX_WIDTH_FRAC: Final[float] = 0.12


def _wiring_title_ink_spans(
    image: Image.Image,
    *,
    ink_thr: int = 140,
) -> list[tuple[int, int, int, int]]:
    """Detect dark title spans in the top band of a wiring crop.

    Returns:
        List of ``(x0, y0, x1, y1)`` boxes for contiguous ink runs wide enough
        to be section titles (not terminal digits).
    """
    width, height = image.size
    y_lo = max(0, int(0.08 * height))
    y_hi = min(height, int(0.18 * height))
    if y_hi <= y_lo:
        return []

    pixels = cast(Any, image.convert("RGB").load())
    col_hits = [0] * width
    for y in range(y_lo, y_hi):
        for x in range(width):
            r, g, b = pixels[x, y]
            if (r + g + b) // 3 < ink_thr:
                col_hits[x] += 1

    raw_spans: list[tuple[int, int]] = []
    in_span = False
    start = 0
    for x, hits in enumerate(col_hits):
        if hits >= 2 and not in_span:
            start = x
            in_span = True
        elif hits < 2 and in_span:
            raw_spans.append((start, x))
            in_span = False
    if in_span:
        raw_spans.append((start, width))

    merged: list[tuple[int, int]] = []
    for x0, x1 in raw_spans:
        if merged and x0 - merged[-1][1] < 10:
            merged[-1] = (merged[-1][0], x1)
        else:
            merged.append((x0, x1))

    boxes: list[tuple[int, int, int, int]] = []
    min_width = max(40, int(0.04 * width))
    for x0, x1 in merged:
        if x1 - x0 < min_width:
            continue
        ys: list[int] = []
        for y in range(y_lo, y_hi):
            for x in range(x0, x1):
                r, g, b = pixels[x, y]
                if (r + g + b) // 3 < ink_thr:
                    ys.append(y)
                    break
        if not ys:
            continue
        boxes.append((x0, min(ys), x1, max(ys) + 1))
    return boxes


def patch_damu_wiring_labels_ru(image: Image.Image) -> Image.Image:
    """Replace English wiring titles with Belimo RU terms on DAMU crops.

    Patches ``Actuator`` → ``Привод`` and ``Auxiliary switch`` →
    ``Вспомогательный переключатель``. Voltage legends (AC/DC 24V, …) stay
    as printed — same style as Belimo RU manuals.
    """
    width, height = image.size
    boxes = _wiring_title_ink_spans(image)
    if not boxes:
        return image

    patched = image.copy()
    draw = ImageDraw.Draw(patched)
    font_size = max(14, int(0.045 * height))
    font = _load_shaft_label_font(font_size)
    actuator_max_w = int(_WIRING_ACTUATOR_MAX_WIDTH_FRAC * width)

    for x0, y0, x1, y1 in boxes:
        label = _WIRING_LABEL_ACTUATOR_RU if (x1 - x0) <= actuator_max_w else _WIRING_LABEL_AUX_RU
        pad = 4
        region = (
            max(0, x0 - pad),
            max(0, y0 - pad),
            min(width, x1 + pad),
            min(height, y1 + pad),
        )
        draw.rectangle(region, fill=(255, 255, 255))
        text_box = draw.textbbox((0, 0), label, font=font)
        text_w = text_box[2] - text_box[0]
        text_h = text_box[3] - text_box[1]
        if text_w > (region[2] - region[0]):
            cx = (region[0] + region[2]) // 2
            half = text_w // 2 + 8
            region = cast(
                tuple[int, int, int, int],
                (
                    max(0, cx - half),
                    region[1],
                    min(width, cx + half),
                    min(height, region[3] + 2),
                ),
            )
            draw.rectangle(region, fill=(255, 255, 255))
        tx = (region[0] + region[2] - text_w) // 2
        ty = (region[1] + region[3] - text_h) // 2 - 1
        draw.text((tx, ty), label, fill=(20, 20, 20), font=font)
    return patched


def diagrams_from_damu_pdf(
    pdf_path: Path,
    *,
    series_nm: int,
    edition: Edition,
) -> list[DiagramCrop]:
    """Build wiring + dimensions crops from a DA..MU English manual PDF."""
    page = render_pdf_page(pdf_path, 1)
    wiring_img, dims_img = crop_damu_diagrams(page)
    wiring_img = patch_damu_wiring_labels_ru(wiring_img)
    dims_img = patch_damu_dimensions_shaft_label(dims_img, series_nm=series_nm)
    series = f"DA{series_nm}MU"
    return [
        DiagramCrop(
            kind="wiring",
            png_bytes=_pil_to_png_bytes(wiring_img),
            alt=f"{series} | Схема подключения из инструкции",
            sort_order=SORT_WIRING,
            source_url=source_url_for_damu(series_nm, edition, "wiring"),
        ),
        DiagramCrop(
            kind="dimensions",
            png_bytes=_pil_to_png_bytes(dims_img),
            alt=f"{series} | Габаритные размеры привода (мм), чертёж из инструкции",
            sort_order=SORT_DIMENSIONS,
            source_url=source_url_for_damu(series_nm, edition, "dimensions"),
        ),
    ]


def find_damu_manual_pdf(
    *,
    series_nm: int,
    edition: Edition,
    manuals_dir: Path | None = None,
) -> Path | None:
    """Locate a DAMU English manual for the series edition."""
    from catalog.etl.manual_pdfs import parse_damu_manual_stem

    manuals_dir = manuals_dir or default_manuals_dir()
    wanted_kind = "a_as" if edition == "modulating_24" else "d_ds"

    if edition == "modulating_24":
        file_qs = ProductFile.objects.filter(
            is_published=True,
            sku__sku_code__iregex=rf"(?i)^da{series_nm}mu\d*-a",
            title__icontains="Инструкция",
        ).exclude(file="")
    else:
        file_qs = ProductFile.objects.filter(
            is_published=True,
            sku__sku_code__iregex=rf"(?i)^da{series_nm}mu\d*-d",
            title__icontains="Инструкция",
        ).exclude(file="")
    for pf in file_qs.select_related("sku")[:3]:
        if pf.file and Path(pf.file.path).is_file():
            return Path(pf.file.path)

    if not manuals_dir.is_dir():
        return None
    for path in sorted(manuals_dir.glob("*.pdf")):
        parsed = parse_damu_manual_stem(path.name)
        if parsed is None:
            continue
        nms, kind, _volt = parsed
        if series_nm in nms and kind == wanted_kind:
            return path
    return None


def apply_damu_manual_diagrams(*, dry_run: bool = False) -> dict[str, Any]:
    """Attach wiring + dimensions diagrams for every DA..MU SKU with a manual PDF."""
    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "series": {},
        "dry_run": dry_run,
    }

    skus = list(
        SKU.objects.filter(sku_code__iregex=r"(?i)^da[0-9]+mu")
        .exclude(sku_code__iregex=r"(?i)^da[0-9]+mqu")
        .order_by("sku_code"),
    )
    crop_cache: dict[tuple[int, Edition], list[DiagramCrop] | None] = {}

    for sku in skus:
        series_nm = parse_damu_series_nm(sku.sku_code)
        edition = edition_for_sku(sku.sku_code)
        if series_nm is None or edition is None:
            summary["skipped"] += 1
            continue

        cache_key = (series_nm, edition)
        if cache_key not in crop_cache:
            pdf_path = find_damu_manual_pdf(series_nm=series_nm, edition=edition)
            if pdf_path is None:
                logger.info(
                    "damu_manual_diagram_pdf_missing series=%s edition=%s",
                    series_nm,
                    edition,
                )
                crop_cache[cache_key] = None
            else:
                try:
                    crop_cache[cache_key] = diagrams_from_damu_pdf(
                        pdf_path,
                        series_nm=series_nm,
                        edition=edition,
                    )
                except Exception as exc:
                    logger.exception(
                        "damu_manual_diagram_crop_failed pdf=%s series=%s err_type=%s",
                        pdf_path,
                        series_nm,
                        type(exc).__name__,
                    )
                    crop_cache[cache_key] = None

        crops = crop_cache[cache_key]
        if not crops:
            summary["skipped"] += 1
            continue

        series_key = f"da{series_nm}mu-{edition}"
        series_stats = summary["series"].setdefault(
            series_key,
            {"created": 0, "updated": 0, "skus": 0},
        )
        series_stats["skus"] += 1
        for crop in crops:
            action = _upsert_diagram(sku, crop, dry_run=dry_run)
            if action == "create":
                summary["created"] += 1
                series_stats["created"] += 1
            elif action == "update":
                summary["updated"] += 1
                series_stats["updated"] += 1

    return summary


_SAMU_CODE = re.compile(r"(?i)^sa(?P<nm>\d+)mu")
_SAMU_SOURCE_URL = "https://hoocon.ru/.local-assets/manual-diagrams/sa{nm}mu-ds-{kind}.webp"


def parse_samu_series_nm(sku_code: str) -> int | None:
    """Return torque from ``SA10MU24-DS`` → ``10``."""
    match = _SAMU_CODE.match((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    return int(match.group("nm"))


def samu_pdf_source_series_nm(series_nm: int) -> int:
    """SAMU series whose PDF to crop when this family has no dedicated manual."""
    return _SAMU_PDF_FALLBACK_NM.get(series_nm, series_nm)


def source_url_for_samu(series_nm: int, kind: DiagramKind) -> str:
    """Stable local-asset key for a SAMU diagram row."""
    return _SAMU_SOURCE_URL.format(nm=series_nm, kind=kind)


def diagrams_from_samu_pdf(pdf_path: Path, *, series_nm: int) -> list[DiagramCrop]:
    """Build wiring + dimensions crops from an SA..MU manual (page 2, SAFU-like)."""
    page = render_pdf_page(pdf_path, 1)
    wiring_img, dims_img = crop_safu_diagrams(page)
    series = f"SA{series_nm}MU"
    return [
        DiagramCrop(
            kind="wiring",
            png_bytes=_pil_to_png_bytes(wiring_img),
            alt=f"{series} | Схема подключения из инструкции",
            sort_order=SORT_WIRING,
            source_url=source_url_for_samu(series_nm, "wiring"),
        ),
        DiagramCrop(
            kind="dimensions",
            png_bytes=_pil_to_png_bytes(dims_img),
            alt=f"{series} | Габаритные размеры привода (мм), чертёж из инструкции",
            sort_order=SORT_DIMENSIONS,
            source_url=source_url_for_samu(series_nm, "dimensions"),
        ),
    ]


def relabel_samu_diagram_crops(
    crops: list[DiagramCrop],
    *,
    series_nm: int,
) -> list[DiagramCrop]:
    """Retarget crop alts / source_url to the SKU series (e.g. SA20 borrowing SA15)."""
    series = f"SA{series_nm}MU"
    out: list[DiagramCrop] = []
    for crop in crops:
        if crop.kind == "wiring":
            alt = f"{series} | Схема подключения из инструкции"
        else:
            alt = f"{series} | Габаритные размеры привода (мм), чертёж из инструкции"
        out.append(
            DiagramCrop(
                kind=crop.kind,
                png_bytes=crop.png_bytes,
                alt=alt,
                sort_order=crop.sort_order,
                source_url=source_url_for_samu(series_nm, crop.kind),
            ),
        )
    return out


def find_samu_manual_pdf(*, series_nm: int, manuals_dir: Path | None = None) -> Path | None:
    """Locate a SAMU English manual PDF for the series (with fallback Nm)."""
    from catalog.etl.manual_pdfs import parse_samu_manual_stem

    pdf_nm = samu_pdf_source_series_nm(series_nm)
    manuals_dir = manuals_dir or default_manuals_dir()
    file_qs = ProductFile.objects.filter(
        is_published=True,
        sku__sku_code__iregex=rf"(?i)^sa{pdf_nm}mu",
        title__icontains="Инструкция",
    ).exclude(file="")
    for pf in file_qs.select_related("sku")[:3]:
        if pf.file and Path(pf.file.path).is_file():
            return Path(pf.file.path)
    if not manuals_dir.is_dir():
        return None
    for path in sorted(manuals_dir.glob("*.pdf")):
        nm = parse_samu_manual_stem(path.name)
        if nm == pdf_nm:
            return path
    return None


def apply_samu_manual_diagrams(*, dry_run: bool = False) -> dict[str, Any]:
    """Attach wiring + dimensions for every SA..MU SKU with a manual PDF."""
    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "series": {},
        "dry_run": dry_run,
    }
    skus = list(SKU.objects.filter(sku_code__iregex=r"(?i)^sa\d+mu").order_by("sku_code"))
    crop_cache: dict[int, list[DiagramCrop] | None] = {}
    for sku in skus:
        series_nm = parse_samu_series_nm(sku.sku_code)
        if series_nm is None:
            summary["skipped"] += 1
            continue
        pdf_nm = samu_pdf_source_series_nm(series_nm)
        if pdf_nm not in crop_cache:
            pdf_path = find_samu_manual_pdf(series_nm=series_nm)
            if pdf_path is None:
                logger.info(
                    "samu_manual_diagram_pdf_missing series=%s pdf_nm=%s",
                    series_nm,
                    pdf_nm,
                )
                crop_cache[pdf_nm] = None
            else:
                try:
                    crop_cache[pdf_nm] = diagrams_from_samu_pdf(
                        pdf_path,
                        series_nm=pdf_nm,
                    )
                except Exception as exc:
                    logger.exception(
                        "samu_manual_diagram_crop_failed pdf=%s series=%s err_type=%s",
                        pdf_path,
                        series_nm,
                        type(exc).__name__,
                    )
                    crop_cache[pdf_nm] = None
        raw_crops = crop_cache[pdf_nm]
        if not raw_crops:
            summary["skipped"] += 1
            continue
        crops = relabel_samu_diagram_crops(raw_crops, series_nm=series_nm)
        series_key = f"sa{series_nm}mu"
        series_stats = summary["series"].setdefault(
            series_key,
            {"created": 0, "updated": 0, "skus": 0},
        )
        series_stats["skus"] += 1
        for crop in crops:
            action = _upsert_diagram(sku, crop, dry_run=dry_run)
            if action == "create":
                summary["created"] += 1
                series_stats["created"] += 1
            elif action == "update":
                summary["updated"] += 1
                series_stats["updated"] += 1
    return summary


_HVDF_CODE = re.compile(r"(?i)^hvd(?:24|230)st?-(?P<nm>\d+)f$")
_HVDF_SOURCE_URL = "https://hoocon.ru/.local-assets/manual-diagrams/hvd-{nm}f-{kind}.webp"


def parse_hvdf_series_nm(sku_code: str) -> int | None:
    """Return torque from ``HVD24ST-3F`` → ``3``."""
    match = _HVDF_CODE.fullmatch((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    return int(match.group("nm"))


def source_url_for_hvdf(series_nm: int, kind: DiagramKind) -> str:
    """Stable local-asset key for an HVD-…F gallery row."""
    return _HVDF_SOURCE_URL.format(nm=series_nm, kind=kind)


def crop_hvdf_product_photos(page: Image.Image) -> tuple[Image.Image, Image.Image]:
    """Crop actuator-only and actuator+SAF72 photos from HVD-…F page 2 (index 1).

    Page layout (English manual): product shot top-left, feature bullets to the
    right (~0.21×), «Technical specification» table from ~0.27× height. Crops must
    stay above the table and left of the bullets so gallery photos are hardware-only.

    Both outputs share the same pixel size so S (no sensor) and ST (with SAF72)
    render the actuator at the same visual scale in catalog cards / PDP.
    """
    width, height = page.size
    left = int(0.042 * width)
    top = int(0.085 * height)
    bottom = int(0.264 * height)
    # Actuator body ends before the orange SAF72 (~0.149…0.169×).
    body_right = int(0.140 * width)
    # Include SAF72; stop before the «3Nm ON/OFF» title (~0.21×).
    frame_right = int(0.200 * width)

    with_sensor = page.crop((left, top, frame_right, bottom))
    body_tight = page.crop((left, top, body_right, bottom))
    # Same canvas as ST: pad the right (sensor) column with white → punched later.
    body = Image.new("RGB", with_sensor.size, (255, 255, 255))
    body.paste(body_tight, (0, 0))
    return body, with_sensor


def diagrams_from_hvdf_pdf(pdf_path: Path, *, series_nm: int) -> list[DiagramCrop]:
    """Build photo + wiring + dimensions crops from an HVD-…F English manual."""
    page = render_pdf_page(pdf_path, 1)
    body_img, thermal_img = crop_hvdf_product_photos(page)
    # Opaque PDF studio white + grey vignette → transparent cutout so PDP/catalog
    # PhotoWash purpose gradient (smoke) shows through instead of sampled grey.
    body_img = punch_near_white_background(body_img)
    thermal_img = punch_near_white_background(thermal_img)
    wiring_img, dims_img = crop_safu_diagrams(page)
    series = f"HVD-{series_nm}F"
    s_code = f"HVD24S-{series_nm}F"
    st_code = f"HVD24ST-{series_nm}F"
    return [
        DiagramCrop(
            kind="photo",
            png_bytes=_pil_to_png_bytes(body_img),
            alt=f"{series} | Привод дымового клапана с пружинным возвратом ({s_code})",
            sort_order=SORT_PHOTO,
            source_url=source_url_for_hvdf(series_nm, "photo"),
        ),
        DiagramCrop(
            kind="photo_thermal",
            png_bytes=_pil_to_png_bytes(thermal_img),
            alt=(f"{series} | Привод с термодатчиком SAF72 72 °C ({st_code})"),
            sort_order=SORT_PHOTO,
            source_url=source_url_for_hvdf(series_nm, "photo_thermal"),
        ),
        DiagramCrop(
            kind="wiring",
            png_bytes=_pil_to_png_bytes(wiring_img),
            alt=f"{series} | Схема подключения из инструкции",
            sort_order=SORT_WIRING,
            source_url=source_url_for_hvdf(series_nm, "wiring"),
        ),
        DiagramCrop(
            kind="dimensions",
            png_bytes=_pil_to_png_bytes(dims_img),
            alt=f"{series} | Габаритные размеры привода (мм), чертёж из инструкции",
            sort_order=SORT_DIMENSIONS,
            source_url=source_url_for_hvdf(series_nm, "dimensions"),
        ),
    ]


def find_hvdf_manual_pdf(*, series_nm: int, manuals_dir: Path | None = None) -> Path | None:
    """Locate ``hvd-{nm}f-s_st.pdf`` from ProductFile or manuals dir."""
    from catalog.etl.manual_pdfs import parse_hvd_f_manual_stem

    manuals_dir = manuals_dir or default_manuals_dir()
    file_qs = ProductFile.objects.filter(
        is_published=True,
        sku__sku_code__iregex=rf"(?i)^hvd(24|230)st?-{series_nm}f$",
        title__icontains="Инструкция",
    ).exclude(file="")
    for pf in file_qs.select_related("sku")[:3]:
        if pf.file and Path(pf.file.path).is_file():
            return Path(pf.file.path)
    if not manuals_dir.is_dir():
        return None
    for path in sorted(manuals_dir.glob("hvd-*.pdf")):
        nm = parse_hvd_f_manual_stem(path.name)
        if nm == series_nm:
            return path
    return None


def apply_hvdf_manual_diagrams(*, dry_run: bool = False) -> dict[str, Any]:
    """Attach photos + wiring + dimensions for every HVD-…F SKU."""
    from catalog.etl.sku_variant import sku_code_is_thermal

    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "series": {},
        "dry_run": dry_run,
    }
    skus = list(
        SKU.objects.filter(sku_code__iregex=r"(?i)^hvd(24|230)st?-\d+f$").order_by(
            "sku_code",
        ),
    )
    crop_cache: dict[int, list[DiagramCrop] | None] = {}
    for sku in skus:
        series_nm = parse_hvdf_series_nm(sku.sku_code)
        if series_nm is None:
            summary["skipped"] += 1
            continue
        if series_nm not in crop_cache:
            pdf_path = find_hvdf_manual_pdf(series_nm=series_nm)
            if pdf_path is None:
                crop_cache[series_nm] = None
            else:
                try:
                    crop_cache[series_nm] = diagrams_from_hvdf_pdf(
                        pdf_path,
                        series_nm=series_nm,
                    )
                except Exception as exc:
                    logger.exception(
                        "hvdf_manual_diagram_crop_failed pdf=%s err_type=%s",
                        pdf_path,
                        type(exc).__name__,
                    )
                    crop_cache[series_nm] = None
        crops = crop_cache[series_nm]
        if not crops:
            summary["skipped"] += 1
            continue
        thermal = sku_code_is_thermal(sku.sku_code)
        filtered: list[DiagramCrop] = []
        for crop in crops:
            if crop.kind == "photo_thermal" and not thermal:
                continue
            if crop.kind == "photo" and thermal:
                continue
            filtered.append(crop)
        series_key = f"hvd-{series_nm}f"
        series_stats = summary["series"].setdefault(
            series_key,
            {"created": 0, "updated": 0, "skus": 0},
        )
        series_stats["skus"] += 1
        for crop in filtered:
            action = _upsert_diagram(sku, crop, dry_run=dry_run)
            if action == "create":
                summary["created"] += 1
                series_stats["created"] += 1
            elif action == "update":
                summary["updated"] += 1
                series_stats["updated"] += 1
    return summary


# ── HVA: dimensions from Russian Illustrator catalog (PDF-compatible .ai) ──

_HVA_CODE = re.compile(
    r"(?i)^hva(?:24|230)s?-(?P<nm>\d+)(?P<fast>q)?(?:x)?$",
)
_HVA_CATALOG_NAME = "浒江2022俄文画册3.ai"
_HVA_SOURCE_URL = "https://hoocon.ru/.local-assets/manual-diagrams/hva{nm}{fast}-{kind}.webp"
# Page index in the catalog spread (left column = this family).
_HVA_CATALOG_PAGE: Final[dict[tuple[int, bool], int]] = {
    (5, False): 0,
    (10, False): 1,
    (20, False): 2,
    (40, False): 3,
    (5, True): 4,
    (10, True): 5,
    (20, True): 6,
    (40, True): 7,
}
# Envelope W × H × D from left-column «Размеры привода» drawings.
_HVA_ENVELOPE_MM: Final[dict[tuple[int, bool], str]] = {
    (5, False): "71,1 × 144,1 × 62,1 мм",
    (5, True): "71,1 × 144,1 × 62,1 мм",  # same body family until proven otherwise
}
_HVA_DIMS_TITLE = "Размеры привода(mm)"
_HVA_CATALOG_SCALE: Final[float] = 2.5


def parse_hva_series(sku_code: str) -> tuple[int, bool] | None:
    """Return ``(nm, is_fast_q)`` from ``HVA24S-5Q`` → ``(5, True)``."""
    match = _HVA_CODE.match((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    return int(match.group("nm")), bool(match.group("fast"))


def find_hva_catalog_ai(*, manuals_dir: Path | None = None) -> Path | None:
    """Locate the HOOCON Russian Illustrator catalog with HVA drawings."""
    manuals_dir = manuals_dir or default_manuals_dir()
    path = manuals_dir / _HVA_CATALOG_NAME
    if path.is_file():
        return path
    # Fallback: any .ai in manuals dir.
    if manuals_dir.is_dir():
        for candidate in sorted(manuals_dir.glob("*.ai")):
            return candidate
    return None


def _hva_dims_title_boxes(
    page: pdfium.PdfPage,
) -> list[tuple[float, float, float, float]]:
    """PDF boxes ``(x0, y0, x1, y1)`` for each «Размеры привода(mm)» title."""
    text_page = page.get_textpage()
    boxes: list[tuple[str, tuple[float, float, float, float]]] = []
    for index in range(text_page.count_chars()):
        char = text_page.get_text_range(index, 1)
        if char:
            boxes.append((char, text_page.get_charbox(index)))
    joined = "".join(char for char, _ in boxes)
    found: list[tuple[float, float, float, float]] = []
    start = 0
    needle = _HVA_DIMS_TITLE
    while True:
        pos = joined.find(needle, start)
        if pos < 0:
            break
        xs: list[float] = []
        ys: list[float] = []
        for _, box in boxes[pos : pos + len(needle)]:
            xs.extend((box[0], box[2]))
            ys.extend((box[1], box[3]))
        found.append((min(xs), min(ys), max(xs), max(ys)))
        start = pos + 1
    return found


def crop_hva_catalog_dimensions(
    page_image: Image.Image,
    page: pdfium.PdfPage,
    *,
    scale: float = _HVA_CATALOG_SCALE,
) -> Image.Image:
    """Crop left-column actuator dimensions under «Размеры привода(mm)»."""
    titles = _hva_dims_title_boxes(page)
    if not titles:
        # Fallback: bottom half of the left column.
        width, height = page_image.size
        return page_image.crop((0, int(0.58 * height), int(0.52 * width), height - 8))

    left_title = min(titles, key=lambda box: box[0])
    page_height = float(page.get_height())
    crop_top = int((page_height - left_title[1]) * scale) + 2
    crop_left = max(0, int(left_title[0] * scale) - 20)
    crop_right = int(0.52 * page_image.size[0])
    crop_bottom = page_image.size[1] - 8
    if crop_right <= crop_left or crop_bottom <= crop_top:
        width, height = page_image.size
        return page_image.crop((0, int(0.58 * height), int(0.52 * width), height - 8))
    return page_image.crop((crop_left, crop_top, crop_right, crop_bottom))


def source_url_for_hva(series_nm: int, *, fast: bool, kind: DiagramKind) -> str:
    """Stable local-asset key for an HVA diagram row."""
    fast_key = "q" if fast else ""
    return _HVA_SOURCE_URL.format(nm=series_nm, fast=fast_key, kind=kind)


def diagrams_from_hva_catalog(
    catalog_path: Path,
    *,
    series_nm: int,
    fast: bool,
) -> list[DiagramCrop]:
    """Build dimensions crop from the HVA catalog page for one torque family."""
    page_index = _HVA_CATALOG_PAGE.get((series_nm, fast))
    if page_index is None:
        return []
    document = pdfium.PdfDocument(str(catalog_path))
    try:
        page = document[page_index]
        page_image = page.render(scale=_HVA_CATALOG_SCALE).to_pil().convert("RGB")
        dims_img = crop_hva_catalog_dimensions(page_image, page)
    finally:
        document.close()

    label = f"HVA-{series_nm}{'Q' if fast else ''}"
    return [
        DiagramCrop(
            kind="dimensions",
            png_bytes=_pil_to_png_bytes(dims_img),
            alt=f"{label} | Габаритные размеры привода (мм), чертёж из каталога",
            sort_order=SORT_DIMENSIONS,
            source_url=source_url_for_hva(series_nm, fast=fast, kind="dimensions"),
        ),
    ]


def apply_hva_manual_diagrams(*, dry_run: bool = False) -> dict[str, Any]:
    """Attach HVA dimensions crops from the Illustrator catalog to galleries.

    Also backfills ``dimensions`` ТТХ when the envelope is known from the drawing.
    """
    from catalog.etl.attr_write import set_sku_attribute

    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "series": {},
        "dry_run": dry_run,
    }
    catalog = find_hva_catalog_ai()
    if catalog is None:
        logger.info("hva_catalog_ai_missing")
        return summary

    crop_cache: dict[tuple[int, bool], list[DiagramCrop] | None] = {}
    skus = list(SKU.objects.filter(sku_code__istartswith="HVA").order_by("sku_code"))
    for sku in skus:
        parsed = parse_hva_series(sku.sku_code)
        if parsed is None:
            summary["skipped"] += 1
            continue
        series_nm, fast = parsed
        cache_key = (series_nm, fast)
        if cache_key not in crop_cache:
            if cache_key not in _HVA_CATALOG_PAGE:
                crop_cache[cache_key] = None
            else:
                try:
                    crop_cache[cache_key] = diagrams_from_hva_catalog(
                        catalog,
                        series_nm=series_nm,
                        fast=fast,
                    )
                except Exception as exc:
                    logger.exception(
                        "hva_catalog_diagram_crop_failed nm=%s fast=%s err_type=%s",
                        series_nm,
                        fast,
                        type(exc).__name__,
                    )
                    crop_cache[cache_key] = None

        crops = crop_cache[cache_key]
        if not crops:
            summary["skipped"] += 1
            continue

        series_key = f"hva-{series_nm}{'q' if fast else ''}"
        series_stats = summary["series"].setdefault(
            series_key,
            {"created": 0, "updated": 0, "skus": 0},
        )
        series_stats["skus"] += 1
        for crop in crops:
            action = _upsert_diagram(sku, crop, dry_run=dry_run)
            if action == "create":
                summary["created"] += 1
                series_stats["created"] += 1
            elif action == "update":
                summary["updated"] += 1
                series_stats["updated"] += 1

        envelope = _HVA_ENVELOPE_MM.get(cache_key)
        if envelope and not dry_run:
            set_sku_attribute(
                sku,
                slug="dimensions",
                value=envelope,
                name="Габаритные размеры",
                unit="мм",
            )
    return summary
