"""Attach optimized HV product heroes from the flat ``media-webp`` pack.

Source (Yandex Disk)::

    ~/Yandex.Disk.localized/фото для сайта/media-webp/
        hva-5.webp, hva-5q.webp, hva-10.webp, hva-10qx.webp, …
        hvd-5.webp, hvd-5q.webp, hvd-10q.webp, hvd-10qx.webp, …

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

from catalog.etl.product_image_audit import _DIMS_OR_DIAGRAM, _is_hero_candidate
from catalog.etl.webp import DEFAULT_WEBP_QUALITY, MAX_EDGE_PX, convert_bytes_to_webp
from catalog.models import SKU, ProductImage

logger = logging.getLogger(__name__)

SORT_PRODUCT: Final[int] = 0
_SOURCE_URL = "https://hoocon.ru/.local-assets/media-webp/{stem}-product.webp"

_DEFAULT_ROOTS: Final[tuple[Path, ...]] = (Path.home() / "Yandex.Disk.localized/фото для сайта/media-webp",)

# Pack stem → SKU code regex (case-insensitive). ``*qa`` / ``*P`` skipped (no RF pack).
# More specific Q/QX before bare Nm so ``hva-5`` does not steal ``HVA24-5Q``.
_STEM_SKU_RE: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("hva-5qx", re.compile(r"(?i)^hva(?:24|230)s?-5qx$")),
    ("hva-5q", re.compile(r"(?i)^hva(?:24|230)s?-5q$")),
    ("hva-5", re.compile(r"(?i)^hva(?:24|230)s?-5$")),
    ("hva-10qx", re.compile(r"(?i)^hva(?:24|230)s?-10qx$")),
    ("hva-10q", re.compile(r"(?i)^hva(?:24|230)s?-10q$")),
    ("hva-10", re.compile(r"(?i)^hva(?:24|230)s?-10$")),
    ("hva-20qx", re.compile(r"(?i)^hva(?:24|230)s?-20qx$")),
    ("hva-20q", re.compile(r"(?i)^hva(?:24|230)s?-20q$")),
    ("hva-20", re.compile(r"(?i)^hva(?:24|230)s?-20$")),
    ("hva-40qx", re.compile(r"(?i)^hva(?:24|230)s?-40qx$")),
    ("hva-40q", re.compile(r"(?i)^hva(?:24|230)s?-40q$")),
    ("hva-40", re.compile(r"(?i)^hva(?:24|230)s?-40$")),
    ("hvd-5", re.compile(r"(?i)^hvd(?:24|230)s?-5$")),
    ("hvd-5q", re.compile(r"(?i)^hvd(?:24|230)s?-5q$")),
    ("hvd-5qx", re.compile(r"(?i)^hvd(?:24|230)s?-5qx$")),
    ("hvd-10qx", re.compile(r"(?i)^hvd(?:24|230)s?-10qx$")),
    ("hvd-10q", re.compile(r"(?i)^hvd(?:24|230)s?-10q$")),
    ("hvd-10", re.compile(r"(?i)^hvd(?:24|230)s?-10$")),
    ("hvd-20q", re.compile(r"(?i)^hvd(?:24|230)s?-20q$")),
    ("hvd-20qx", re.compile(r"(?i)^hvd(?:24|230)s?-20qx$")),
    ("hvd-20", re.compile(r"(?i)^hvd(?:24|230)s?-20$")),
    ("hvd-40", re.compile(r"(?i)^hvd(?:24|230)s?-40$")),
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
    """Human label for alt text, e.g. ``hva24s-5q`` → ``HVA-5Q``."""
    match = re.match(r"(?i)^(hv[ad])(?:24s-|-)?(\d+)(qx|q)?$", (stem or "").strip())
    if match is None:
        return stem.upper()
    series, nm, suffix = match.group(1), match.group(2), match.group(3) or ""
    return f"{series.upper()}-{nm}{suffix.upper()}"


def _label_from_sku(sku_code: str, *, stem: str) -> str:
    """Prefer edition label (``HVA-5P``) over pack stem when attaching shared bodies."""
    match = re.match(r"(?i)^(hv[ad])(?:24|230)s?-(.+)$", (sku_code or "").strip())
    if match is not None:
        return f"{match.group(1).upper()}-{match.group(2).upper()}"
    return _label_from_stem(stem)


def _demote_other_product_shots(sku: SKU, *, keep_pk: int) -> int:
    """Unpublish leftover product/promo photos; keep wiring/dimensions tiles."""
    demoted = 0
    for other in ProductImage.objects.filter(sku=sku).exclude(pk=keep_pk):
        alt = other.alt or ""
        url = other.source_url or ""
        if _DIMS_OR_DIAGRAM.search(alt) or _DIMS_OR_DIAGRAM.search(url):
            continue
        url_l = url.casefold()
        if "-wiring" in url_l or "-dimensions" in url_l:
            continue
        # Demote competing heroes, Tilda angles, and other product shots.
        is_tilda = "tildacdn" in url_l
        if not (_is_hero_candidate(other) or is_tilda or other.sort_order in {0, 1}):
            continue
        if not other.is_published and other.sort_order != SORT_PRODUCT:
            continue
        other.is_published = False
        if other.sort_order == SORT_PRODUCT:
            other.sort_order = 10
        other.save(update_fields=["is_published", "sort_order", "updated_at"])
        demoted += 1
    return demoted


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

    label = _label_from_sku(sku.sku_code or "", stem=stem)
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

        _demote_other_product_shots(sku, keep_pk=keep_pk)
    return action


def promote_local_hv_product_over_tilda(*, dry_run: bool = False) -> dict[str, Any]:
    """Prefer ``.local-assets/*-product.webp`` over Tilda heroes on HVA/HVD.

    Used for std families without a media-webp cutout (e.g. HVA-5).
    """
    summary: dict[str, Any] = {"promoted": 0, "demoted_tilda": 0, "dry_run": dry_run}
    locals_ = ProductImage.objects.filter(
        sku__sku_code__iregex=r"(?i)^hv[ad]",
        source_url__icontains="hoocon.ru/.local-assets/",
        source_url__endswith="-product.webp",
    ).exclude(source_url__icontains="media-webp/")
    for img in locals_.select_related("sku").iterator():
        sku = img.sku
        # media-webp hero already wins when present.
        if ProductImage.objects.filter(
            sku_id=img.sku_id,
            is_published=True,
            source_url__icontains="media-webp/",
            source_url__endswith="-product.webp",
        ).exists():
            if img.is_published:
                if not dry_run:
                    img.is_published = False
                    img.sort_order = 10
                    img.save(update_fields=["is_published", "sort_order", "updated_at"])
                summary["demoted_tilda"] += 1
            continue
        if not img.is_published or img.sort_order != SORT_PRODUCT:
            summary["promoted"] += 1
            if not dry_run:
                img.is_published = True
                img.sort_order = SORT_PRODUCT
                img.save(update_fields=["is_published", "sort_order", "updated_at"])
        if dry_run:
            continue
        summary["demoted_tilda"] += _demote_other_product_shots(sku, keep_pk=int(img.pk))
    return summary


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

    promote = promote_local_hv_product_over_tilda(dry_run=dry_run)
    summary["promoted_local"] = promote["promoted"]
    summary["demoted_tilda"] = promote["demoted_tilda"]
    return summary
