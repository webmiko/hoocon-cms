"""Attach optimized HV product heroes from the flat ``media-webp`` pack.

Source (Yandex Disk)::

    ~/Yandex.Disk.localized/фото для сайта/media-webp/
        hva24s-5q.webp, hva-10q.webp, hva-10qx.webp, …
        hvd-10q.webp, hvd-10qx.webp, hvd-5qx.webp, …

Files are already WebP cutouts; we re-encode with catalog WebP settings
(quality 90, max edge 1600) and upsert as the primary product shot
(``sort_order=0``), unpublishing other hero competitors on the same SKU.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Final

from django.core.files.base import ContentFile
from django.db import transaction

from catalog.etl.product_image_audit import _is_hero_candidate
from catalog.etl.webp import DEFAULT_WEBP_QUALITY, MAX_EDGE_PX, convert_bytes_to_webp
from catalog.models import SKU, ProductImage

logger = logging.getLogger(__name__)

SORT_PRODUCT: Final[int] = 0
_SOURCE_URL = "https://hoocon.ru/.local-assets/media-webp/{stem}-product.webp"

_DEFAULT_ROOTS: Final[tuple[Path, ...]] = (Path.home() / "Yandex.Disk.localized/фото для сайта/media-webp",)

# Pack stem → SKU code regex (case-insensitive). ``*qa`` variants skipped (no SKUs).
_STEM_SKU_RE: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("hva24s-5q", re.compile(r"(?i)^hva(?:24|230)s?-5q$")),
    ("hva-5qx", re.compile(r"(?i)^hva(?:24|230)s?-5qx$")),
    ("hva-10q", re.compile(r"(?i)^hva(?:24|230)s?-10q$")),
    ("hva-10qx", re.compile(r"(?i)^hva(?:24|230)s?-10qx$")),
    ("hva-20q", re.compile(r"(?i)^hva(?:24|230)s?-20q$")),
    ("hva-20qx", re.compile(r"(?i)^hva(?:24|230)s?-20qx$")),
    ("hva-40q", re.compile(r"(?i)^hva(?:24|230)s?-40q$")),
    ("hva-40qx", re.compile(r"(?i)^hva(?:24|230)s?-40qx$")),
    ("hvd-5qx", re.compile(r"(?i)^hvd(?:24|230)s?-5qx$")),
    ("hvd-10q", re.compile(r"(?i)^hvd(?:24|230)s?-10q$")),
    ("hvd-10qx", re.compile(r"(?i)^hvd(?:24|230)s?-10qx$")),
    ("hvd-20q", re.compile(r"(?i)^hvd(?:24|230)s?-20q$")),
    ("hvd-20qx", re.compile(r"(?i)^hvd(?:24|230)s?-20qx$")),
    ("hvd-40q", re.compile(r"(?i)^hvd(?:24|230)s?-40q$")),
    ("hvd-40qx", re.compile(r"(?i)^hvd(?:24|230)s?-40qx$")),
)


def default_media_webp_root() -> Path | None:
    """First existing media-webp directory, if any."""
    for root in _DEFAULT_ROOTS:
        if root.is_dir():
            return root
    return None


def _label_from_stem(stem: str) -> str:
    """Human label for alt text, e.g. ``hva-10q`` → ``HVA-10Q``."""
    return stem.upper()


def _upsert_product(
    sku: SKU,
    *,
    stem: str,
    webp: bytes,
    dry_run: bool,
) -> str:
    """Create or update the media-webp product hero; demote other heroes."""
    source_url = _SOURCE_URL.format(stem=stem)
    existing = ProductImage.objects.filter(sku=sku, source_url=source_url).first()
    if dry_run:
        return "update" if existing else "create"

    label = _label_from_stem(stem)
    alt = f"{label} | фото привода"
    filename = f"{sku.sku_code.lower()}-product.webp"
    with transaction.atomic():
        if existing is None:
            image = ProductImage(
                sku=sku,
                alt=alt[:300],
                source_url=source_url,
                sort_order=SORT_PRODUCT,
                is_published=True,
            )
            image.image.save(filename, ContentFile(webp), save=False)
            image.full_clean()
            image.save()
            action = "create"
            keep_pk = image.pk
        else:
            existing.alt = alt[:300]
            existing.sort_order = SORT_PRODUCT
            existing.is_published = True
            existing.image.save(filename, ContentFile(webp), save=False)
            existing.full_clean()
            existing.save()
            action = "update"
            keep_pk = existing.pk

        # Demote other hero slots so list/category tiles pick the new cutout.
        for other in ProductImage.objects.filter(sku=sku).exclude(pk=keep_pk):
            if not _is_hero_candidate(other):
                continue
            if other.is_published or other.sort_order == SORT_PRODUCT:
                other.is_published = False
                if other.sort_order == SORT_PRODUCT:
                    other.sort_order = 10
                other.save(update_fields=["is_published", "sort_order", "updated_at"])
    return action


def apply_hv_media_webp(
    *,
    dry_run: bool = False,
    photo_root: Path | None = None,
) -> dict[str, Any]:
    """Attach media-webp product heroes to matching HVA/HVD SKUs.

    Args:
        dry_run: Count only.
        photo_root: Override pack directory.

    Returns:
        Counters: created, updated, skipped, missing_files, dry_run, photo_root.
    """
    root = photo_root or default_media_webp_root()
    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "missing_files": [],
        "dry_run": dry_run,
        "photo_root": str(root) if root else "",
        "by_stem": {},
    }
    if root is None:
        summary["missing_files"].append("(root not found)")
        return summary

    bytes_cache: dict[Path, bytes] = {}
    webp_cache: dict[Path, bytes] = {}
    skus = list(
        SKU.objects.filter(sku_code__iregex=r"(?i)^hv[ad]", is_published=True).order_by(
            "sku_code",
        ),
    )

    for stem, pattern in _STEM_SKU_RE:
        path = root / f"{stem}.webp"
        if not path.is_file():
            summary["missing_files"].append(stem)
            continue
        if path not in webp_cache:
            raw = path.read_bytes()
            bytes_cache[path] = raw
            webp_cache[path] = convert_bytes_to_webp(
                raw,
                quality=DEFAULT_WEBP_QUALITY,
                max_edge=MAX_EDGE_PX,
            )
        matched = [sku for sku in skus if pattern.match(sku.sku_code or "")]
        stem_stats = {"skus": 0, "created": 0, "updated": 0}
        for sku in matched:
            action = _upsert_product(
                sku,
                stem=stem,
                webp=webp_cache[path],
                dry_run=dry_run,
            )
            stem_stats["skus"] += 1
            if action == "create":
                summary["created"] += 1
                stem_stats["created"] += 1
            else:
                summary["updated"] += 1
                stem_stats["updated"] += 1
            logger.info("hv_media_webp %s %s ← %s", action, sku.sku_code, stem)
        if stem_stats["skus"] == 0:
            summary["skipped"] += 1
        summary["by_stem"][stem] = stem_stats

    return summary
