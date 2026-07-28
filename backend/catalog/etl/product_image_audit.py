"""Audit / optimize ProductImage rows: WebP-only, best hero, no weak duplicates.

Policy for product (hero) shots:
- Prefer cutout / low-chroma studio backdrops (catalog card wash) over
  high-chroma promo fills (e.g. red HVA pack shots).
- Prefer high-res studio / ``.local-assets`` WebP over legacy Tilda CDN crops.
- Prefer catalog embeds when no studio shot reaches ``MIN_HERO_EDGE_PX``.
- Keep at most one published hero per SKU (best rank wins).
- Storage must be ``*.webp`` (re-encode JPEG/PNG leftovers).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Final

from django.core.files.base import ContentFile
from django.db import transaction

from catalog.etl.webp import (
    DEFAULT_WEBP_QUALITY,
    MAX_EDGE_PX,
    convert_bytes_to_webp,
    webp_upload_basename,
)
from catalog.models import ProductImage

logger = logging.getLogger(__name__)

# Below this, a hero is considered weak (Tilda thumb / tiny manual crop).
MIN_HERO_EDGE_PX: Final[int] = 800

_DIMS_OR_DIAGRAM = re.compile(r"(?i)размер|схем|подключ|габарит|wiring|dimensions|settings|aux")
_LOCAL_ASSET = re.compile(r"(?i)\.local-assets/")
_TILDA_CDN = re.compile(r"(?i)tildacdn\.com|/stor\d")


def _image_size(image: ProductImage) -> tuple[int, int]:
    try:
        return int(image.image.width), int(image.image.height)
    except Exception:
        return 0, 0


def _pixel_area(image: ProductImage) -> int:
    w, h = _image_size(image)
    return max(0, w) * max(0, h)


def _backdrop_quality(image: ProductImage) -> int:
    """Score catalog-card backdrop suitability (0…100).

    Cutouts (transparent top edge) and low-chroma studio greys score high.
    High-chroma promo fills (red / maroon HVA pack shots) score low so they
    do not displace a smaller neutral gallery hero for card wash.
    """
    try:
        from PIL import Image
    except ImportError:
        return 50

    try:
        path = image.image.path
    except (ValueError, NotImplementedError, AttributeError):
        return 50
    try:
        with Image.open(path) as img:
            rgba = img.convert("RGBA")
            width, height = rgba.size
            if width < 8 or height < 8:
                return 50
            # Sparse sample of the top band (same idea as FE wash sampler).
            band_h = min(12, max(4, height // 80))
            opaque: list[tuple[int, int, int]] = []
            cells = 0
            step_x = max(1, width // 24)
            for y in range(2, 2 + band_h):
                for x in range(0, width, step_x):
                    cells += 1
                    pixel = rgba.getpixel((x, y))
                    if not isinstance(pixel, tuple) or len(pixel) < 4:
                        continue
                    if pixel[3] < 16:
                        continue
                    opaque.append((int(pixel[0]), int(pixel[1]), int(pixel[2])))
    except OSError:
        return 50

    if cells <= 0:
        return 50
    # Sparse / transparent top → cutout (white stroke peeks still count low).
    opaque_ratio = len(opaque) / cells
    if opaque_ratio < 0.28:
        return 100

    chroma_sum = 0.0
    for r, g, b in opaque:
        chroma_sum += max(r, g, b) - min(r, g, b)
    chroma = chroma_sum / len(opaque)
    if chroma < 22:
        return 90
    if chroma < 45:
        return 55
    return 15


def _is_hero_candidate(image: ProductImage) -> bool:
    """True for the primary product/hero slot (not dims, wiring, or фото 2+)."""
    alt = image.alt or ""
    url = image.source_url or ""
    if _DIMS_OR_DIAGRAM.search(alt) or _DIMS_OR_DIAGRAM.search(url):
        return False
    # Explicit product attach from local-assets / catalog pipelines.
    if "-product" in url.casefold() or url.casefold().endswith("-product.webp"):
        return True
    # Only the primary gallery slot competes as «hero» — keep secondary angles.
    if image.sort_order != 0:
        return False
    return True


def _hero_rank(image: ProductImage) -> tuple[int, int, int, int, int]:
    """Higher is better: backdrop, local-asset, not Tilda, area, id."""
    url = image.source_url or ""
    local = 1 if _LOCAL_ASSET.search(url) else 0
    not_tilda = 0 if _TILDA_CDN.search(url) else 1
    return (
        _backdrop_quality(image),
        local,
        not_tilda,
        _pixel_area(image),
        image.pk or 0,
    )


def audit_product_images() -> dict[str, Any]:
    """Count non-WebP names, weak heroes, and multi-hero SKUs."""
    published = ProductImage.objects.filter(is_published=True).select_related("sku")
    non_webp: list[dict[str, Any]] = []
    weak_heroes: list[dict[str, Any]] = []
    multi_hero_skus: set[int] = set()
    heroes_by_sku: dict[int, list[ProductImage]] = {}

    for image in published.iterator(chunk_size=500):
        name = (image.image.name or "").lower()
        if not name.endswith(".webp"):
            non_webp.append(
                {
                    "id": image.pk,
                    "sku": image.sku.sku_code if image.sku_id else "",
                    "name": name,
                },
            )
        if not _is_hero_candidate(image):
            continue
        sku_id = int(image.sku_id)
        heroes_by_sku.setdefault(sku_id, []).append(image)
        w, h = _image_size(image)
        if w > 0 and h > 0 and min(w, h) < MIN_HERO_EDGE_PX:
            weak_heroes.append(
                {
                    "id": image.pk,
                    "sku": image.sku.sku_code if image.sku_id else "",
                    "size": f"{w}x{h}",
                    "source_url": (image.source_url or "")[:120],
                },
            )

    for sku_id, heroes in heroes_by_sku.items():
        if len(heroes) > 1:
            multi_hero_skus.add(sku_id)

    return {
        "published": published.count(),
        "non_webp": len(non_webp),
        "non_webp_samples": non_webp[:20],
        "weak_heroes": len(weak_heroes),
        "weak_hero_samples": weak_heroes[:20],
        "multi_hero_skus": len(multi_hero_skus),
        "min_hero_edge_px": MIN_HERO_EDGE_PX,
    }


def optimize_non_webp_images(*, dry_run: bool = False) -> dict[str, Any]:
    """Re-encode published images whose storage basename is not ``.webp``."""
    summary: dict[str, Any] = {"converted": 0, "skipped": 0, "errors": 0, "dry_run": dry_run}
    qs = ProductImage.objects.filter(is_published=True).exclude(image="")
    for image in qs.iterator(chunk_size=200):
        name = image.image.name or ""
        if name.lower().endswith(".webp"):
            summary["skipped"] += 1
            continue
        if dry_run:
            summary["converted"] += 1
            continue
        try:
            raw = image.image.read()
            if hasattr(image.image, "seek"):
                image.image.seek(0)
            webp = convert_bytes_to_webp(raw, quality=DEFAULT_WEBP_QUALITY, max_edge=MAX_EDGE_PX)
            with transaction.atomic():
                image.image.save(
                    webp_upload_basename(Path(name).name),
                    ContentFile(webp),
                    save=False,
                )
                image.full_clean()
                image.save(update_fields=["image", "updated_at"])
            summary["converted"] += 1
        except Exception as exc:
            summary["errors"] += 1
            logger.warning("webp_convert_failed id=%s err=%s", image.pk, exc)
    return summary


def prune_inferior_hero_duplicates(*, dry_run: bool = False) -> dict[str, Any]:
    """Keep one best hero per SKU; unpublish weaker product-shot duplicates.

    Ranking prefers neutral/cutout backdrops (card wash), then ``.local-assets``
    over Tilda CDN, then higher pixel area. Unpublished former heroes are
    re-evaluated so a chroma promo does not permanently displace a studio shot.
    """
    summary: dict[str, Any] = {
        "skus": 0,
        "unpublished": 0,
        "republished": 0,
        "dry_run": dry_run,
        "samples": [],
    }
    heroes_by_sku: dict[int, list[ProductImage]] = {}
    # Include unpublished heroes so a previous prune can be corrected.
    qs = ProductImage.objects.all().select_related("sku")
    for image in qs.iterator(chunk_size=500):
        if not image.sku_id or not _is_hero_candidate(image):
            continue
        heroes_by_sku.setdefault(int(image.sku_id), []).append(image)

    for sku_id, heroes in heroes_by_sku.items():
        if len(heroes) < 2:
            continue
        summary["skus"] += 1
        ranked = sorted(heroes, key=_hero_rank, reverse=True)
        keep = ranked[0]
        if not keep.is_published:
            summary["republished"] += 1
            if not dry_run:
                keep.is_published = True
                keep.save(update_fields=["is_published", "updated_at"])
        for image in ranked[1:]:
            if not image.is_published:
                continue
            summary["unpublished"] += 1
            if len(summary["samples"]) < 25:
                summary["samples"].append(
                    {
                        "sku": keep.sku.sku_code if keep.sku_id else sku_id,
                        "keep_id": keep.pk,
                        "drop_id": image.pk,
                        "drop_url": (image.source_url or "")[:100],
                    },
                )
            if dry_run:
                continue
            image.is_published = False
            image.save(update_fields=["is_published", "updated_at"])
            logger.info(
                "hero_prune sku=%s keep=%s drop=%s",
                keep.sku.sku_code if keep.sku_id else sku_id,
                keep.pk,
                image.pk,
            )
    return summary


def restore_secondary_gallery_angles(*, dry_run: bool = False) -> dict[str, Any]:
    """Re-publish secondary gallery angles unpublished by an over-broad hero prune."""
    from django.db.models import Q

    q = Q()
    for n in range(2, 10):
        q |= Q(alt__icontains=f"фото {n}")
    qs = ProductImage.objects.filter(is_published=False).filter(q)
    count = qs.count()
    if not dry_run and count:
        qs.update(is_published=True)
    return {"restored": count, "dry_run": dry_run}


def apply_product_image_cleanup(*, dry_run: bool = False) -> dict[str, Any]:
    """Run audit → WebP optimize → prune inferior primary heroes."""
    before = audit_product_images()
    converted = optimize_non_webp_images(dry_run=dry_run)
    restored = restore_secondary_gallery_angles(dry_run=dry_run)
    pruned = prune_inferior_hero_duplicates(dry_run=dry_run)
    after = audit_product_images() if not dry_run else before
    return {
        "dry_run": dry_run,
        "before": before,
        "converted": converted,
        "restored_secondary": restored,
        "pruned": pruned,
        "after": after,
    }
