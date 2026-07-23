"""Crop wiring + overall-dimensions diagrams from DAFU / SAFU instruction PDFs.

D/DS manuals (4 pages): diagrams on page 3 (stacked).
A/AS manuals (2 pages, landscape): diagrams in the right column of page 2.
SA..FU manuals (2 pages, landscape): wiring + dimensions in the right column of page 2.

Source PDFs: attached ``ProductFile`` rows, with fallback to ``_инструкции-pdf``.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

import pypdfium2 as pdfium
from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image

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

DiagramKind = Literal["wiring", "dimensions"]
Edition = Literal["on_off", "modulating_24"]

_DAFU_CODE = re.compile(r"(?i)^da(?P<nm>\d+)fu")
_SAFU_CODE = re.compile(r"(?i)^sa(?P<nm>\d+)fu")
_RENDER_SCALE = 3.0

# Idempotent CDN-style keys (URLField-valid); files are local media, not fetched.
_SOURCE_URL = "https://hoocon.ru/.local-assets/manual-diagrams/{series}-{edition}-{kind}.webp"
_SAFU_SOURCE_URL = "https://hoocon.ru/.local-assets/manual-diagrams/sa{nm}fu-ds-{kind}.webp"

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


def _upsert_diagram(sku: SKU, crop: DiagramCrop, *, dry_run: bool) -> str:
    """Create or refresh one diagram image. Returns ``create`` / ``update`` / ``skip``."""
    webp = convert_bytes_to_webp(crop.png_bytes, quality=92, max_edge=1600)
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
                except Exception:
                    logger.exception(
                        "manual_diagram_crop_failed pdf=%s series=%s edition=%s",
                        pdf_path,
                        series_nm,
                        edition,
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
                except Exception:
                    logger.exception(
                        "safu_manual_diagram_crop_failed pdf=%s series=%s",
                        pdf_path,
                        series_nm,
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
