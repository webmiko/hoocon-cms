"""Attach brass 8100 / 8100Q body heroes from the ``media-webp`` pack.

Source (Yandex Disk)::

    ~/Yandex.Disk.localized/фото для сайта/media-webp/
        2-WAY BRASS DN15.webp, 3-WAY BRASS DN15.webp, …
        8100Q-S.webp (DN65–80), 8100Q-L.webp (DN100–150)
        IRON DN80.jpg, …  (fallback if S/L missing)

    ~/Yandex.Disk.localized/фото для сайта/архив/foto/Valve photo/Iron/
        IRON DN80.jpg … IRON DN150.jpg

Brass ``{ways}-WAY BRASS DN{dn}`` → Product ``8100-bv{ways}{dn}``.
8100Q size heroes → ``8100q-bv2{dn}`` (2-way only): S=DN65/80, L=DN100–150.
Per-DN ``IRON DN{dn}`` is a fallback when the size-class file is absent.

Re-encodes with catalog WebP settings (q90, max edge 1600). HEIC → PNG via
macOS ``sips`` when Pillow cannot decode it.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Final, Literal

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

PackKind = Literal["brass", "iron"]

# ``2-WAY BRASS DN15`` / ``2-WAY  BRASS DN20`` / ``3-WAY BRASS DN50``.
_BRASS_STEM_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)^\s*(?P<ways>[23])[\s\-]*way[\s\-]+brass[\s\-]+dn[\s\-]*(?P<dn>\d+)\s*$",
)
# ``IRON DN80`` / ``IRON DN 100`` / ``iron-dn150``.
_IRON_STEM_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)^\s*iron[\s\-]+dn[\s\-]*(?P<dn>\d+)\s*$",
)
# ``8100Q-S`` / ``8100Q_L`` / ``8100q-s`` — size-class kit heroes.
_Q8100_SIZE_STEM_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)^\s*8100q[\s\-_]?([sl])\s*$",
)
_IMAGE_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".webp", ".png", ".jpg", ".jpeg", ".heic", ".heif"},
)
_DEFAULT_IRON_ROOTS: Final[tuple[Path, ...]] = (
    Path.home() / "Yandex.Disk.localized/фото для сайта/архив/foto/Valve photo/Iron",
)
# Published 8100Q DN set.
_Q8100_DNS: Final[tuple[int, ...]] = (65, 80, 100, 125, 150)
# Size-class cutouts: S = small DN65/80, L = large DN100–150.
_Q8100_SIZE_DNS: Final[dict[str, tuple[int, ...]]] = {
    "s": (65, 80),
    "l": (100, 125, 150),
}


def _canonical_brass_stem(*, ways: int, dn: int) -> str:
    """Stable pack id for source_url / logs, e.g. ``2way-brass-dn15``."""
    return f"{ways}way-brass-dn{dn}"


def _canonical_iron_stem(*, dn: int) -> str:
    """Stable pack id for per-DN Iron fallback, e.g. ``iron-dn80``."""
    return f"iron-dn{dn}"


def _canonical_q8100_size_stem(size: str) -> str:
    """Stable pack id for size-class heroes, e.g. ``8100q-s``."""
    return f"8100q-{size.casefold()}"


def _q8100_size_for_dn(dn: int) -> str | None:
    """Return ``s`` / ``l`` for a published 8100Q DN, or ``None``."""
    for size, dns in _Q8100_SIZE_DNS.items():
        if dn in dns:
            return size
    return None


def _product_slug(*, kind: PackKind, ways: int, dn: int) -> str:
    """CMS product slug for a pack shot."""
    if kind == "iron":
        return f"8100q-bv2{dn}"
    return f"8100-bv{ways}{dn}"


def _parse_pack_stem(stem: str) -> tuple[int, int] | None:
    """Parse brass pack filename stem → (ways, dn). Kept for tests / callers."""
    match = _BRASS_STEM_RE.fullmatch((stem or "").strip())
    if match is None:
        return None
    return int(match.group("ways")), int(match.group("dn"))


def _parse_iron_stem(stem: str) -> int | None:
    """Parse ``IRON DNxx`` stem → DN, or ``None``."""
    match = _IRON_STEM_RE.fullmatch((stem or "").strip())
    if match is None:
        return None
    return int(match.group("dn"))


def _parse_q8100_size_stem(stem: str) -> str | None:
    """Parse ``8100Q-S`` / ``8100Q-L`` stem → ``s`` / ``l``, or ``None``."""
    match = _Q8100_SIZE_STEM_RE.fullmatch((stem or "").strip())
    if match is None:
        return None
    return match.group(1).casefold()


def _image_rank(path: Path) -> int:
    """Lower = preferred source format."""
    return {".webp": 0, ".png": 1, ".jpg": 2, ".jpeg": 2, ".heic": 3, ".heif": 3}.get(
        path.suffix.lower(),
        9,
    )


def _iter_photo_roots(photo_root: Path | None) -> list[Path]:
    """media-webp first, then archive Iron/ (unless ``photo_root`` overrides)."""
    if photo_root is not None:
        return [photo_root] if photo_root.is_dir() else []
    roots: list[Path] = []
    media = default_media_webp_root()
    if media is not None:
        roots.append(media)
    for iron in _DEFAULT_IRON_ROOTS:
        if iron.is_dir() and iron not in roots:
            roots.append(iron)
    return roots


def _discover_brass_shots(roots: list[Path]) -> list[tuple[str, int, int, Path]]:
    """List brass pack files as (canonical_stem, ways, dn, path)."""
    by_key: dict[tuple[int, int], Path] = {}
    for root in roots:
        for path in sorted(root.iterdir()):
            if not path.is_file() or path.suffix.lower() not in _IMAGE_SUFFIXES:
                continue
            parsed = _parse_pack_stem(path.stem)
            if parsed is None:
                continue
            ways, dn = parsed
            key = (ways, dn)
            prev = by_key.get(key)
            if prev is None or _image_rank(path) < _image_rank(prev):
                by_key[key] = path

    found: list[tuple[str, int, int, Path]] = []
    for (ways, dn), path in sorted(by_key.items()):
        found.append((_canonical_brass_stem(ways=ways, dn=dn), ways, dn, path))
    return found


def _discover_iron_by_dn(roots: list[Path]) -> dict[int, Path]:
    """Map DN → preferred Iron pack file."""
    by_dn: dict[int, Path] = {}
    for root in roots:
        for path in sorted(root.iterdir()):
            if not path.is_file() or path.suffix.lower() not in _IMAGE_SUFFIXES:
                continue
            dn = _parse_iron_stem(path.stem)
            if dn is None:
                continue
            prev = by_dn.get(dn)
            if prev is None or _image_rank(path) < _image_rank(prev):
                by_dn[dn] = path
    return by_dn


def _discover_q8100_size_shots(roots: list[Path]) -> dict[str, Path]:
    """Map size letter ``s``/``l`` → preferred 8100Q-S / 8100Q-L pack file."""
    by_size: dict[str, Path] = {}
    for root in roots:
        for path in sorted(root.iterdir()):
            if not path.is_file() or path.suffix.lower() not in _IMAGE_SUFFIXES:
                continue
            size = _parse_q8100_size_stem(path.stem)
            if size is None:
                continue
            prev = by_size.get(size)
            if prev is None or _image_rank(path) < _image_rank(prev):
                by_size[size] = path
    return by_size


def _nearest_iron_path(by_dn: dict[int, Path], dn: int) -> tuple[int, Path] | None:
    """Exact DN file, else closest available DN (ties → lower DN)."""
    if not by_dn:
        return None
    if dn in by_dn:
        return dn, by_dn[dn]
    best = min(by_dn, key=lambda other: (abs(other - dn), other))
    return best, by_dn[best]


def _resolve_q8100_shot(
    dn: int,
    *,
    size_shots: dict[str, Path],
    iron_by_dn: dict[int, Path],
) -> tuple[str, Path] | None:
    """Prefer size-class S/L hero; fall back to nearest Iron DN file.

    Returns:
        ``(canonical_stem, path)`` or ``None`` when nothing matches.
    """
    size = _q8100_size_for_dn(dn)
    if size is not None and size in size_shots:
        return _canonical_q8100_size_stem(size), size_shots[size]
    picked = _nearest_iron_path(iron_by_dn, dn)
    if picked is None:
        return None
    file_dn, path = picked
    if file_dn != dn:
        logger.warning(
            "8100Q DN%s: no size/IRON DN%s shot — using IRON DN%s",
            dn,
            dn,
            file_dn,
        )
    return _canonical_iron_stem(dn=dn), path


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


def _attach_product_shot(
    *,
    kind: PackKind,
    ways: int,
    dn: int,
    stem: str,
    path: Path,
    webp_cache: dict[Path, bytes],
    dry_run: bool,
    summary: dict[str, Any],
) -> None:
    """Upsert hero on all published SKUs of one product card."""
    product_slug = _product_slug(kind=kind, ways=ways, dn=dn)
    product = Product.objects.filter(slug=product_slug).prefetch_related("skus").first()
    if product is None:
        summary["missing_products"].append(product_slug)
        summary["skipped"] += 1
        return

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
        return

    if kind == "iron":
        label = product.name.split("|", 1)[0].strip() or f"8100Q-BV2{dn}"
    else:
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
    summary["by_stem"][f"{stem}:{product_slug}"] = {
        "skus": len(skus),
        "created": created_n,
        "updated": updated_n,
        "product": product_slug,
        "stem": stem,
        "source": path.name,
    }


def apply_ball_valve_media_webp(
    *,
    dry_run: bool = False,
    photo_root: Path | None = None,
) -> dict[str, Any]:
    """Attach media-webp heroes to published 8100-bv* and 8100Q-bv* SKUs.

    Args:
        dry_run: Count only.
        photo_root: Override pack directory (skips archive Iron/ fallback).

    Returns:
        Counters: created, updated, skipped, missing_products, dry_run, …
    """
    roots = _iter_photo_roots(photo_root)
    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "missing_products": [],
        "dry_run": dry_run,
        "photo_root": ", ".join(str(r) for r in roots),
        "by_stem": {},
    }
    if not roots:
        summary["missing_products"].append("(root not found)")
        return summary

    webp_cache: dict[Path, bytes] = {}

    brass = _discover_brass_shots(roots)
    for stem, ways, dn, path in brass:
        _attach_product_shot(
            kind="brass",
            ways=ways,
            dn=dn,
            stem=stem,
            path=path,
            webp_cache=webp_cache,
            dry_run=dry_run,
            summary=summary,
        )

    size_shots = _discover_q8100_size_shots(roots)
    iron_by_dn = _discover_iron_by_dn(roots)
    if not brass and not size_shots and not iron_by_dn:
        summary["missing_products"].append(
            "(no *WAY BRASS DN* / 8100Q-S|L / IRON DN* files)",
        )
        return summary

    for dn in _Q8100_DNS:
        resolved = _resolve_q8100_shot(
            dn,
            size_shots=size_shots,
            iron_by_dn=iron_by_dn,
        )
        if resolved is None:
            summary["missing_products"].append(f"8100q-bv2{dn} (no 8100Q-S/L or IRON)")
            summary["skipped"] += 1
            continue
        stem, path = resolved
        _attach_product_shot(
            kind="iron",
            ways=2,
            dn=dn,
            stem=stem,
            path=path,
            webp_cache=webp_cache,
            dry_run=dry_run,
            summary=summary,
        )

    return summary
