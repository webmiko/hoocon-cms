"""Attach optimized brass 8100 body heroes from the flat ``media-webp`` pack.

Source (Yandex Disk)::

    ~/Yandex.Disk.localized/фото для сайта/media-webp/
        2-WAY BRASS DN15.webp, 2-WAY BRASS DN20.webp, …
        3-WAY BRASS DN15.webp, …
        2-WAY BRASS DN50.heic, 3-WAY BRASS DN50.heic

Maps ``{ways}-WAY BRASS DN{dn}`` → Product ``8100-bv{ways}{dn}``
(e.g. 2-way DN15 → ``8100-bv215``) and upserts the hero on every published
SKU of that DN card. Re-encodes with catalog WebP settings (q90, max edge
1600). HEIC is converted via macOS ``sips`` when Pillow cannot decode it.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Final

from django.core.files.base import ContentFile
from django.db import transaction

from catalog.etl.hv_media_webp import (
    SORT_PRODUCT,
    _demote_other_product_shots,
    default_media_webp_root,
)
from catalog.etl.webp import DEFAULT_WEBP_QUALITY, MAX_EDGE_PX, convert_bytes_to_webp
from catalog.models import SKU, Product, ProductImage

logger = logging.getLogger(__name__)

_SOURCE_URL = "https://hoocon.ru/.local-assets/media-webp/{stem}-product.webp"

# ``2-WAY BRASS DN15`` / ``2-WAY  BRASS DN20`` / ``3-WAY BRASS DN50``.
_PACK_STEM_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)^\s*(?P<ways>[23])[\s\-]*way[\s\-]+brass[\s\-]+dn[\s\-]*(?P<dn>\d+)\s*$",
)
_IMAGE_SUFFIXES: Final[frozenset[str]] = frozenset({".webp", ".png", ".jpg", ".jpeg", ".heic", ".heif"})


def _canonical_stem(*, ways: int, dn: int) -> str:
    """Stable pack id for source_url / logs, e.g. ``2way-brass-dn15``."""
    return f"{ways}way-brass-dn{dn}"


def _product_slug(*, ways: int, dn: int) -> str:
    """8100 DN card slug, e.g. ``8100-bv215``."""
    return f"8100-bv{ways}{dn}"


def _parse_pack_stem(stem: str) -> tuple[int, int] | None:
    """Parse pack filename stem → (ways, dn)."""
    match = _PACK_STEM_RE.fullmatch((stem or "").strip())
    if match is None:
        return None
    return int(match.group("ways")), int(match.group("dn"))


def _discover_pack_shots(root: Path) -> list[tuple[str, int, int, Path]]:
    """List brass pack files as (canonical_stem, ways, dn, path).

    Prefer ``.webp`` over ``.heic`` when both exist for the same ways/DN.
    """
    by_key: dict[tuple[int, int], Path] = {}
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        parsed = _parse_pack_stem(path.stem)
        if parsed is None:
            continue
        ways, dn = parsed
        key = (ways, dn)
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = path
            continue
        # Prefer WebP over HEIC/JPEG sources.
        rank = {".webp": 0, ".png": 1, ".jpg": 2, ".jpeg": 2, ".heic": 3, ".heif": 3}
        if rank.get(path.suffix.lower(), 9) < rank.get(prev.suffix.lower(), 9):
            by_key[key] = path

    found: list[tuple[str, int, int, Path]] = []
    for (ways, dn), path in sorted(by_key.items()):
        found.append((_canonical_stem(ways=ways, dn=dn), ways, dn, path))
    return found


def _heic_to_png_bytes(path: Path) -> bytes:
    """Decode HEIC via macOS ``sips`` (Pillow has no HEIC by default)."""
    sips = shutil.which("sips")
    if sips is None:
        raise OSError(
            f"Cannot decode HEIC {path.name}: install macOS sips or convert to WebP first",
        )
    with tempfile.TemporaryDirectory(prefix="bv-heic-") as tmp:
        out = Path(tmp) / "out.png"
        subprocess.run(
            [sips, "-s", "format", "png", str(path), "--out", str(out)],
            check=True,
            capture_output=True,
        )
        return out.read_bytes()


def _raw_image_bytes(path: Path) -> bytes:
    """Read pack file bytes; HEIC → PNG via sips."""
    if path.suffix.lower() in {".heic", ".heif"}:
        return _heic_to_png_bytes(path)
    return path.read_bytes()


def _upsert_product(
    sku: SKU,
    *,
    stem: str,
    label: str,
    webp: bytes,
    dry_run: bool,
) -> str:
    """Create or update the media-webp product hero; demote other heroes."""
    source_url = _SOURCE_URL.format(stem=stem)
    existing = ProductImage.objects.filter(sku=sku, source_url=source_url).first()
    if dry_run:
        return "update" if existing else "create"

    alt = f"{label} | фото шарового крана"
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


def apply_ball_valve_media_webp(
    *,
    dry_run: bool = False,
    photo_root: Path | None = None,
) -> dict[str, Any]:
    """Attach media-webp brass heroes to published 8100-bv* SKUs.

    Args:
        dry_run: Count only.
        photo_root: Override pack directory.

    Returns:
        Counters: created, updated, skipped, missing_products, dry_run, …
    """
    root = photo_root or default_media_webp_root()
    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "missing_products": [],
        "dry_run": dry_run,
        "photo_root": str(root) if root else "",
        "by_stem": {},
    }
    if root is None:
        summary["missing_products"].append("(root not found)")
        return summary

    shots = _discover_pack_shots(root)
    if not shots:
        summary["missing_products"].append("(no *WAY BRASS DN* files)")
        return summary

    webp_cache: dict[Path, bytes] = {}

    for stem, ways, dn, path in shots:
        product_slug = _product_slug(ways=ways, dn=dn)
        product = Product.objects.filter(slug=product_slug).prefetch_related("skus").first()
        if product is None:
            summary["missing_products"].append(product_slug)
            summary["skipped"] += 1
            continue

        if path not in webp_cache:
            webp_cache[path] = convert_bytes_to_webp(
                _raw_image_bytes(path),
                quality=DEFAULT_WEBP_QUALITY,
                max_edge=MAX_EDGE_PX,
            )

        skus = [sku for sku in product.skus.all() if sku.is_published]
        if not skus:
            summary["missing_products"].append(f"{product_slug} (no published SKUs)")
            summary["skipped"] += 1
            continue

        label = product.name.split("|", 1)[0].strip() or f"BV{ways}{dn}"
        created_n = 0
        updated_n = 0
        for sku in skus:
            action = _upsert_product(
                sku,
                stem=stem,
                label=label,
                webp=webp_cache[path],
                dry_run=dry_run,
            )
            if action == "create":
                summary["created"] += 1
                created_n += 1
            else:
                summary["updated"] += 1
                updated_n += 1
            logger.info(
                "ball_valve_media_webp %s %s ← %s (%s)",
                action,
                sku.sku_code,
                stem,
                path.name,
            )
        summary["by_stem"][stem] = {
            "skus": len(skus),
            "created": created_n,
            "updated": updated_n,
            "product": product_slug,
        }

    return summary
