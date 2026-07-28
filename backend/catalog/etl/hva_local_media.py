"""Attach HVA product photos + dimension drawings from the local HV photo pack.

Sources (Yandex Disk archive, resolved via common roots)::

    …/HV seria/hva-5/hva-5.webp
    …/HV seria/hva-5/hva-5 razmer.webp
    …/HV seria/hva-5/hva-cxema.webp
    …/HV seria/hva-10/hva-10.webp + razmer
    …/HV seria/hva-5q/hva-5q.webp

Falls back to the std Nm photo for Q families when a dedicated Q folder
has no product shot (10Q/20Q/40Q share the same body photo as 10/20/40).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Final

from django.core.files.base import ContentFile
from django.db import transaction

from catalog.etl.manual_diagrams import SORT_WIRING, parse_hva_series
from catalog.etl.webp import convert_bytes_to_webp
from catalog.models import SKU, ProductImage

logger = logging.getLogger(__name__)

_SOURCE_URL = "https://hoocon.ru/.local-assets/hva-catalog/hva{nm}{fast}-{kind}.webp"
SORT_PRODUCT: Final[int] = 0
# Keep below wiring(5) / AI-catalog dims(8) so gallery order is photo → schema → razmer → AI.
SORT_LOCAL_DIMENSIONS: Final[int] = 6

_CANDIDATE_ROOTS: Final[tuple[Path, ...]] = (
    Path.home() / "Yandex.Disk.localized/фото для сайта/архив/foto/HV seria",
    Path.home() / "Yandex.Disk.localized/фото для сайта/архив/продукция фото/HV seria",
)


def default_hva_photo_root() -> Path | None:
    """First existing HV seria photo directory, if any."""
    for root in _CANDIDATE_ROOTS:
        if root.is_dir():
            return root
    return None


def _family_dir_name(nm: int, *, fast: bool) -> str:
    if fast and nm == 5:
        return "hva-5q"
    return f"hva-{nm}"


def _photo_paths(
    root: Path,
    *,
    nm: int,
    fast: bool,
) -> dict[str, Path | None]:
    """Resolve product / dimensions / wiring files for one family."""
    family_dir = root / _family_dir_name(nm, fast=fast)
    std_dir = root / f"hva-{nm}"
    product: Path | None = None
    dimensions: Path | None = None
    wiring: Path | None = None

    if family_dir.is_dir():
        for name in (f"hva-{nm}q.webp", f"hva-{nm}.webp", "hva-5q.webp"):
            candidate = family_dir / name
            if candidate.is_file():
                product = candidate
                break
        for name in (f"hva-{nm} razmer.webp", f"hva-{nm}q razmer.webp"):
            candidate = family_dir / name
            if candidate.is_file():
                dimensions = candidate
                break

    if product is None and std_dir.is_dir():
        candidate = std_dir / f"hva-{nm}.webp"
        if candidate.is_file():
            product = candidate
    if dimensions is None and std_dir.is_dir():
        candidate = std_dir / f"hva-{nm} razmer.webp"
        if candidate.is_file():
            dimensions = candidate

    # Shared modulating wiring schema from HVA-5 pack (same Y/U pinout family).
    for base in (root / "hva-5", family_dir, std_dir):
        for name in ("hva-cxema.webp", "hva cxema.jpeg", "hva-5q-cxema 1.png"):
            candidate = base / name
            if candidate.is_file():
                wiring = candidate
                break
        if wiring is not None:
            break

    return {"product": product, "dimensions": dimensions, "wiring": wiring}


def _source_url(nm: int, *, fast: bool, kind: str) -> str:
    return _SOURCE_URL.format(nm=nm, fast="q" if fast else "", kind=kind)


def _upsert_bytes(
    sku: SKU,
    *,
    kind: str,
    raw: bytes,
    alt: str,
    sort_order: int,
    source_url: str,
    dry_run: bool,
) -> str:
    webp = convert_bytes_to_webp(raw, quality=90, max_edge=1600)
    existing = ProductImage.objects.filter(sku=sku, source_url=source_url).first()
    if dry_run:
        return "update" if existing else "create"
    filename = f"{sku.sku_code.lower()}-{kind}.webp"
    with transaction.atomic():
        if existing is None:
            image = ProductImage(
                sku=sku,
                alt=alt[:300],
                source_url=source_url,
                sort_order=sort_order,
                is_published=True,
            )
            image.image.save(filename, ContentFile(webp), save=False)
            image.full_clean()
            image.save()
            return "create"
        existing.alt = alt[:300]
        existing.sort_order = sort_order
        existing.is_published = True
        existing.image.save(filename, ContentFile(webp), save=False)
        existing.full_clean()
        existing.save()
        return "update"


def apply_hva_local_media(
    *,
    dry_run: bool = False,
    photo_root: Path | None = None,
) -> dict[str, Any]:
    """Attach product / dimensions / wiring images to all HVA std/Q SKUs."""
    root = photo_root or default_hva_photo_root()
    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "dry_run": dry_run,
        "photo_root": str(root) if root else "",
        "warnings": [],
    }
    if root is None:
        summary["warnings"].append("HVA photo root not found")
        return summary

    path_cache: dict[tuple[int, bool], dict[str, Path | None]] = {}
    bytes_cache: dict[Path, bytes] = {}
    skus = list(SKU.objects.filter(sku_code__istartswith="HVA").order_by("sku_code"))
    for sku in skus:
        parsed = parse_hva_series(sku.sku_code)
        if parsed is None:
            summary["skipped"] += 1
            continue
        nm, fast = parsed
        if (nm, fast) not in path_cache:
            path_cache[(nm, fast)] = _photo_paths(root, nm=nm, fast=fast)
        paths = path_cache[(nm, fast)]
        label = f"HVA-{nm}{'Q' if fast else ''}"
        jobs: list[tuple[str, str, int, Path | None]] = [
            ("product", f"{label} | фото привода", SORT_PRODUCT, paths["product"]),
            (
                "dimensions",
                f"{label} | Габаритные размеры привода (мм)",
                SORT_LOCAL_DIMENSIONS,
                paths["dimensions"],
            ),
            (
                "wiring",
                f"{label} | Схема подключения",
                SORT_WIRING,
                paths["wiring"],
            ),
        ]
        attached_any = False
        for kind, alt, sort_order, path in jobs:
            if path is None or not path.is_file():
                continue
            if path not in bytes_cache:
                bytes_cache[path] = path.read_bytes()
            action = _upsert_bytes(
                sku,
                kind=kind,
                raw=bytes_cache[path],
                alt=alt,
                sort_order=sort_order,
                source_url=_source_url(nm, fast=fast, kind=kind),
                dry_run=dry_run,
            )
            attached_any = True
            if action == "create":
                summary["created"] += 1
            elif action == "update":
                summary["updated"] += 1
        if not attached_any:
            summary["skipped"] += 1
            summary["warnings"].append(f"no local media for {sku.sku_code}")
    return summary
