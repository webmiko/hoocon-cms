"""Backfill family dimensions/weight for HVD air dampers (no spring) with gaps.

Source: English datasheets ``HVD 10`` / ``HVD 40Q`` (on/off, 2-/3-point).
Within one Nm family all SKUs share the same envelope; mass is per family row.
"""

from __future__ import annotations

import re
from typing import Any

from catalog.etl.attr_write import set_sku_attribute
from catalog.models import SKU

# HVD24-10 / HVD24S-10 / HVD230-40Q — voltage, optional S, torque, optional Q.
_HVD_AIR_CODE = re.compile(
    r"(?i)^hvd(?:24|230)s?-(?P<nm>\d+)(?P<fast>q)?$",
)

# Per-Nm family from datasheet drawings + Weight row (shared by all SKUs of that family).
_HVD_AIR_SIZE: dict[tuple[int, bool], dict[str, str]] = {
    (10, False): {
        "dimensions": "167,8 × 86,2 × 68 мм",
        "weight": "< 1,1 кг",
    },
    (40, True): {
        "dimensions": "198,6 × 110,2 × 68 мм",
        "weight": "< 1,5 кг",
    },
}


def parse_hvd_air_series(sku_code: str) -> tuple[int, bool] | None:
    """Return ``(nm, is_fast_q)`` from ``HVD24S-40Q`` → ``(40, True)``."""
    match = _HVD_AIR_CODE.match((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    return int(match.group("nm")), bool(match.group("fast"))


def apply_hvd_air_size_backfill(*, dry_run: bool = False) -> dict[str, Any]:
    """Set family dimensions/weight on HVD air SKUs that have a known datasheet row."""
    summary: dict[str, Any] = {"skus": 0, "updated": 0, "skipped": 0, "dry_run": dry_run}
    skus = list(SKU.objects.filter(sku_code__istartswith="HVD").order_by("sku_code"))
    for sku in skus:
        parsed = parse_hvd_air_series(sku.sku_code)
        if parsed is None:
            summary["skipped"] += 1
            continue
        row = _HVD_AIR_SIZE.get(parsed)
        if row is None:
            summary["skipped"] += 1
            continue
        summary["skus"] += 1
        if dry_run:
            continue
        set_sku_attribute(
            sku,
            slug="dimensions",
            value=row["dimensions"],
            name="Габаритные размеры",
            unit="мм",
        )
        set_sku_attribute(
            sku,
            slug="weight",
            value=row["weight"],
            name="Масса",
            unit="кг",
        )
        summary["updated"] += 1
    return summary
