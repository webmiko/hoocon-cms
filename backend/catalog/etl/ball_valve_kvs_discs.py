"""Attach Kvs characterizing-disc photo tiles to brass 8100 edition SKUs.

Pack: ``catalog/etl/data/ball-valve-kvs-discs/dn{DN}-{letter}.webp``
from circular port photos in ``…/src/`` (white bg + labels). Built by
``python -m catalog.etl.generate_kvs_disc_schematics``.

Each published ``8100-bv*`` SKU with matching DN + edition letter gets one
extra gallery tile (does not replace the hero).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Final

from django.core.files.base import ContentFile
from django.db import transaction

from catalog.models import SKU, ProductImage
from catalog.sku_access import sku_attribute_values

logger = logging.getLogger(__name__)

_PACK_DIR: Final[Path] = Path(__file__).resolve().parent / "data" / "ball-valve-kvs-discs"
_SOURCE_URL: Final[str] = "https://hoocon.ru/.local-assets/kvs-disc/dn{dn}-{letter}.webp"
_SORT_DISC: Final[int] = 30
_SKU_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)^8100-bv(?P<body>\d{3,4})(?P<letter>[a-e])$",
)


def kvs_disc_pack_dir() -> Path:
    """Directory with committed ``dn{{DN}}-{{letter}}.webp`` crops."""
    return _PACK_DIR


def parse_8100_edition(sku_code: str) -> tuple[int, str] | None:
    """Return ``(dn, letter)`` for ``8100-bv215a``-style codes.

    Body encodes ways+dn (``215`` → DN15, ``315`` → DN15). DN is the last
    two digits for 3-digit bodies and last two for 4-digit (``2150`` → 50).
    """
    match = _SKU_RE.fullmatch((sku_code or "").strip())
    if match is None:
        return None
    body = match.group("body")
    letter = match.group("letter").casefold()
    if len(body) == 4:
        dn = int(body[-2:])
    else:
        dn = int(body[1:])
    return dn, letter


def _disc_path(*, dn: int, letter: str) -> Path | None:
    path = _PACK_DIR / f"dn{dn}-{letter.casefold()}.webp"
    return path if path.is_file() else None


def _kvs_label(sku: SKU) -> str:
    for av in sku_attribute_values(sku):
        if (av.attribute.slug or "").casefold() == "kvs":
            return str(av.value or "").strip()
    return ""


def _upsert_disc(
    sku: SKU,
    *,
    dn: int,
    letter: str,
    webp: bytes,
    dry_run: bool,
) -> str:
    source_url = _SOURCE_URL.format(dn=dn, letter=letter.casefold())
    existing = ProductImage.objects.filter(sku=sku, source_url=source_url).first()
    if dry_run:
        return "update" if existing else "create"

    kvs = _kvs_label(sku)
    kvs_bit = f" Kvs {kvs}" if kvs else ""
    alt = f"{sku.sku_code} | фото расходного диска{kvs_bit}"
    filename = f"{sku.sku_code.lower()}-kvs-disc.webp"
    with transaction.atomic():
        if existing is None:
            image = ProductImage(
                sku=sku,
                alt=alt[:300],
                source_url=source_url,
                sort_order=_SORT_DISC,
                is_published=True,
            )
            image.image.save(filename, ContentFile(webp), save=False)
            image.full_clean()
            image.save()
            return "create"

        existing.alt = alt[:300]
        existing.sort_order = _SORT_DISC
        existing.is_published = True
        current = existing.image.size if existing.image else 0
        if current != len(webp):
            existing.image.save(filename, ContentFile(webp), save=False)
        existing.full_clean()
        existing.save()
        return "update"


def apply_ball_valve_kvs_discs(*, dry_run: bool = False) -> dict[str, Any]:
    """Attach disc crops to matching published brass 8100 edition SKUs."""
    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "pack_dir": str(_PACK_DIR),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "missing_pack": 0,
        "by_key": {},
    }
    if not _PACK_DIR.is_dir():
        summary["error"] = f"missing pack {_PACK_DIR}"
        return summary

    skus = list(
        SKU.objects.filter(
            is_published=True,
            sku_code__istartswith="8100-bv",
        ).select_related("product"),
    )
    for sku in skus:
        parsed = parse_8100_edition(sku.sku_code)
        if parsed is None:
            summary["skipped"] += 1
            continue
        dn, letter = parsed
        path = _disc_path(dn=dn, letter=letter)
        if path is None:
            summary["missing_pack"] += 1
            summary["by_key"][f"dn{dn}-{letter}"] = "pack_missing"
            continue
        webp = path.read_bytes()
        action = _upsert_disc(sku, dn=dn, letter=letter, webp=webp, dry_run=dry_run)
        if action == "create":
            summary["created"] += 1
        elif action == "update":
            summary["updated"] += 1
        else:
            summary["skipped"] += 1
        key = f"dn{dn}-{letter}"
        prev = summary["by_key"].get(key, 0)
        summary["by_key"][key] = (prev + 1) if isinstance(prev, int) else 1
        logger.info("kvs_disc_%s sku=%s dn=%s letter=%s", action, sku.sku_code, dn, letter)
    return summary
