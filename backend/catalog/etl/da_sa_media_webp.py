"""Attach optimized DA/SA product heroes from the flat ``media-webp`` pack.

Source (Yandex Disk)::

    ~/Yandex.Disk.localized/фото для сайта/media-webp/
        da3fu-d:ds.webp, da5fu24-a:as.webp, da10:15:20fu-a:as.webp,
        da10:15:20fu-d:ds.webp, …
        sa3fu-ds.webp, sa3fu-dst.webp, sa10:15mu-ds.webp, …

Edition rules
-------------
- Pack stem ``…-d:ds`` / ``…-a:as`` covers both suffixes.
- SA ``…-ds`` is the **body** hero for both DS and DST cards.
- Dedicated ``…-dst`` body shots are **not** preferred: DST cards use the
  ``-ds`` photo plus SAF72 tiles from ``media_webp_extras`` (full DST set).
- If only a ``-dst`` pack exists (no ``-ds``), it is still used as fallback.
- DA10/15/20 FU ``-A`` / ``-AS`` use the shared ``…-d:ds`` body photo (same
  chassis as on/off); ``da10:15:20fu-a:as.webp`` is not attached as hero.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.core.files.base import ContentFile
from django.db import transaction

from catalog.etl.hv_media_webp import (
    SORT_PRODUCT,
    _demote_other_product_shots,
    default_media_webp_root,
)
from catalog.etl.webp import DEFAULT_WEBP_QUALITY, MAX_EDGE_PX, convert_bytes_to_webp
from catalog.models import SKU, ProductImage

logger = logging.getLogger(__name__)

_SOURCE_URL = "https://hoocon.ru/.local-assets/media-webp/{stem}-product.webp"

_STEM_RE = re.compile(
    r"(?i)^"
    r"(?P<fam>da|sa)"
    r"(?P<nms>\d+(?::\d+)*)"
    r"(?P<series>fu|mu|mqu|eu)"
    r"(?P<volt>24|230)?"
    r"-(?P<eds>.+)$",
)
_SKU_RE = re.compile(
    r"(?i)^"
    r"(?P<fam>da|sa)"
    r"(?P<nm>\d+)"
    r"(?P<series>fu|mu|mqu|eu)"
    r"(?P<volt>24|230)?"
    r"-(?P<ed>as|dst|ds|a|d)$",
)

# Pack masks without this Nm → reuse neighbour (DA32 ≈ DA24; DA8MQU ≈ DA10MQU).
_PHOTO_NM_FALLBACK: dict[tuple[str, str], dict[int, int]] = {
    ("da", "mu"): {32: 24},
    ("da", "mqu"): {8: 10},
}

# DA10/15/20 FU modulating editions share the on/off body photo.
_DAFU_MOD_USES_ON_OFF_BODY_NM: frozenset[int] = frozenset({10, 15, 20})


@dataclass(frozen=True, slots=True)
class _PackShot:
    """One media-webp cutout for DA/SA editions."""

    stem: str
    path: Path
    family: str
    nms: frozenset[int]
    series: str
    voltage: str | None
    editions: frozenset[str]


@dataclass(frozen=True, slots=True)
class _SkuParts:
    """Parsed DA/SA edition code."""

    family: str
    nm: int
    series: str
    voltage: str | None
    edition: str
    code: str


def _parse_stem(stem: str, path: Path) -> _PackShot | None:
    """Parse ``da10:15:20fu-d:ds`` / ``sa3fu-dst`` pack stem."""
    match = _STEM_RE.fullmatch((stem or "").strip())
    if match is None:
        return None
    nms = frozenset(int(part) for part in match.group("nms").split(":"))
    eds = frozenset(part.strip().casefold() for part in match.group("eds").split(":") if part.strip())
    if not eds:
        return None
    volt = match.group("volt")
    return _PackShot(
        stem=stem,
        path=path,
        family=match.group("fam").casefold(),
        nms=nms,
        series=match.group("series").casefold(),
        voltage=volt.casefold() if volt else None,
        editions=eds,
    )


def _parse_sku(sku_code: str) -> _SkuParts | None:
    """Parse ``da5fu24-ds`` / ``SA10MU230-DST``."""
    match = _SKU_RE.fullmatch((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    volt = match.group("volt")
    return _SkuParts(
        family=match.group("fam").casefold(),
        nm=int(match.group("nm")),
        series=match.group("series").casefold(),
        voltage=volt.casefold() if volt else None,
        edition=match.group("ed").casefold(),
        code=(sku_code or "").strip(),
    )


def _edition_score(shot: _PackShot, edition: str) -> int:
    """Higher is better. DST prefers pure ``-ds`` body over ``-dst`` composite."""
    eds = shot.editions
    if edition == "dst":
        # Prefer DS-only pack (SAF72 attached separately on DST cards).
        if "ds" in eds and "dst" not in eds:
            return 3
        if "dst" in eds and "ds" not in eds:
            return 1
        if "ds" in eds:
            return 2
        return 0
    if edition in eds:
        return 2
    return 0


def _photo_edition_for_sku(parts: _SkuParts) -> str:
    """Pack edition key to match for this SKU's body hero.

    DA10/15/20 FU ``-A``/``-AS`` reuse the on/off ``-D``/``-DS`` chassis photo.
    """
    if (
        parts.family == "da"
        and parts.series == "fu"
        and parts.nm in _DAFU_MOD_USES_ON_OFF_BODY_NM
        and parts.edition in {"a", "as"}
    ):
        return "ds"
    return parts.edition


def _pick_shot(parts: _SkuParts, shots: list[_PackShot]) -> _PackShot | None:
    """Best pack file for this SKU (voltage + edition, DST prefers DS body)."""
    fallback = _PHOTO_NM_FALLBACK.get((parts.family, parts.series), {})
    nm = fallback.get(parts.nm, parts.nm)
    photo_edition = _photo_edition_for_sku(parts)
    best: _PackShot | None = None
    best_key: tuple[int, int] = (0, 0)
    for shot in shots:
        if shot.family != parts.family:
            continue
        if nm not in shot.nms:
            continue
        if shot.series != parts.series:
            continue
        if shot.voltage is not None and parts.voltage is not None and shot.voltage != parts.voltage:
            continue
        if shot.voltage is not None and parts.voltage is None:
            continue
        ed_score = _edition_score(shot, photo_edition)
        if ed_score == 0:
            continue
        # Prefer exact edition, then voltage-specific pack over generic.
        volt_score = 1 if shot.voltage is not None else 0
        key = (ed_score, volt_score)
        if key > best_key:
            best_key = key
            best = shot
    return best


def _scan_pack(root: Path) -> list[_PackShot]:
    """Index DA/SA ``*.webp`` stems in the pack directory."""
    shots: list[_PackShot] = []
    for path in sorted(root.glob("*.webp")):
        parsed = _parse_stem(path.stem, path)
        if parsed is not None:
            shots.append(parsed)
    return shots


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

    alt = f"{sku.sku_code} | фото привода"
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


def apply_da_sa_media_webp(
    *,
    dry_run: bool = False,
    photo_root: Path | None = None,
) -> dict[str, Any]:
    """Attach media-webp product heroes to matching DA/SA SKUs.

    Args:
        dry_run: Count only.
        photo_root: Override pack directory.

    Returns:
        Counters: created, updated, skipped, unmatched, missing_root, by_stem.
    """
    root = photo_root or default_media_webp_root()
    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "unmatched": [],
        "dry_run": dry_run,
        "photo_root": str(root) if root else "",
        "by_stem": {},
    }
    if root is None or not root.is_dir():
        summary["missing_root"] = True
        return summary

    shots = _scan_pack(root)
    if not shots:
        summary["skipped"] = 1
        return summary

    webp_cache: dict[Path, bytes] = {}
    skus = list(
        SKU.objects.filter(sku_code__iregex=r"(?i)^(?:da|sa)\d", is_published=True).order_by(
            "sku_code",
        ),
    )

    for sku in skus:
        parts = _parse_sku(sku.sku_code or "")
        if parts is None:
            summary["skipped"] += 1
            continue
        shot = _pick_shot(parts, shots)
        if shot is None:
            summary["unmatched"].append(sku.sku_code)
            continue
        if shot.path not in webp_cache:
            if dry_run:
                webp_cache[shot.path] = b""
            else:
                webp_cache[shot.path] = convert_bytes_to_webp(
                    shot.path.read_bytes(),
                    quality=DEFAULT_WEBP_QUALITY,
                    max_edge=MAX_EDGE_PX,
                )
        action = _upsert_product(
            sku,
            stem=shot.stem,
            webp=webp_cache[shot.path],
            dry_run=dry_run,
        )
        stem_stats = summary["by_stem"].setdefault(
            shot.stem,
            {"skus": 0, "created": 0, "updated": 0},
        )
        stem_stats["skus"] += 1
        if action == "create":
            summary["created"] += 1
            stem_stats["created"] += 1
        else:
            summary["updated"] += 1
            stem_stats["updated"] += 1
        logger.info("da_sa_media_webp %s %s ← %s", action, sku.sku_code, shot.stem)

    return summary
