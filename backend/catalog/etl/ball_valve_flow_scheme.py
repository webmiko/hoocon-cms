"""Attach 3-way flow-direction schematic to brass 8100 BV3xx SKUs.

Pack: ``catalog/etl/data/ball-valve-flow-scheme/flow-3way.webp``
built by ``python -m catalog.etl.generate_ball_valve_flow_scheme``.

Only published ``8100-bv3*`` edition SKUs (3-ходовые). Does not replace hero
or Kvs-disc tiles.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Final

from catalog.etl.image_upsert import upsert_sku_image
from catalog.models import SKU

logger = logging.getLogger(__name__)

_PACK_DIR: Final[Path] = Path(__file__).resolve().parent / "data" / "ball-valve-flow-scheme"
_PACK_FILE: Final[str] = "flow-3way.webp"
_SOURCE_URL: Final[str] = "https://hoocon.ru/.local-assets/flow-scheme/flow-3way.webp"
_SORT_FLOW: Final[int] = 25
# 3-way brass editions only: body starts with 3 (BV315a…BV350b).
_SKU_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)^8100-bv3\d{2,3}[a-e]$",
)


def flow_scheme_pack_path() -> Path:
    """Committed ``flow-3way.webp`` path."""
    return _PACK_DIR / _PACK_FILE


def is_8100_three_way_edition(sku_code: str) -> bool:
    """True for published-style ``8100-bv3…`` edition codes."""
    return _SKU_RE.fullmatch((sku_code or "").strip()) is not None


def _upsert_flow(sku: SKU, *, webp: bytes, dry_run: bool) -> str:
    action, _image = upsert_sku_image(
        sku,
        source_url=_SOURCE_URL,
        filename=f"{sku.sku_code.lower()}-flow-3way.webp",
        webp=webp,
        alt=f"{sku.sku_code} | схема направления потока (3-ходовой)",
        sort_order=_SORT_FLOW,
        dry_run=dry_run,
    )
    return action


def apply_ball_valve_flow_scheme(*, dry_run: bool = False) -> dict[str, Any]:
    """Attach flow schematic to matching published 3-way 8100 edition SKUs."""
    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "pack": str(flow_scheme_pack_path()),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "missing_pack": 0,
    }
    path = flow_scheme_pack_path()
    if not path.is_file():
        summary["error"] = f"missing pack {path}"
        summary["missing_pack"] = 1
        return summary

    webp = path.read_bytes()
    skus = list(
        SKU.objects.filter(
            is_published=True,
            sku_code__istartswith="8100-bv3",
        ).select_related("product"),
    )
    for sku in skus:
        if not is_8100_three_way_edition(sku.sku_code):
            summary["skipped"] += 1
            continue
        action = _upsert_flow(sku, webp=webp, dry_run=dry_run)
        if action == "create":
            summary["created"] += 1
        elif action == "update":
            summary["updated"] += 1
        else:
            summary["skipped"] += 1
        logger.info("flow_scheme_%s sku=%s", action, sku.sku_code)
    return summary
