"""Catalog «Новинки» window: first_published_at within N days.

Do not use ``created_at`` / ``updated_at`` (ETL noise). Stamp
``SKU.first_published_at`` on first public publish or via ``stamp_hv_newness``.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from django.db.models import QuerySet
from django.utils import timezone

from catalog.models import SKU

NEW_WINDOW_DAYS: int = 30

# HV wave (2025 catalog fill): all HVA; HVD fast-Q; spring P; capacitor QX.
_HV_NEWNESS_CODE = re.compile(
    r"(?i)^(?:"
    r"hva(?:24|230)s?-\d+(?:q|p|qx)?"
    r"|hvd(?:24|230)s?-\d+(?:q|qx)"
    r")$",
)


def new_since(*, now: datetime | None = None) -> datetime:
    """Lower bound for ``is_new`` / ``?new=1`` (aware datetime)."""
    current = now if now is not None else timezone.now()
    return current - timedelta(days=NEW_WINDOW_DAYS)


def sku_is_new(sku: SKU, *, now: datetime | None = None) -> bool:
    """True when ``first_published_at`` falls inside the newness window."""
    stamped = getattr(sku, "first_published_at", None)
    if stamped is None:
        return False
    return stamped >= new_since(now=now)


def ensure_first_published_at(sku: SKU, *, now: datetime | None = None) -> bool:
    """Set ``first_published_at`` once when the SKU is (or becomes) published.

    Returns:
        True if the field was set on this call.
    """
    if not sku.is_published:
        return False
    if sku.first_published_at is not None:
        return False
    sku.first_published_at = now if now is not None else timezone.now()
    return True


def hv_newness_queryset(queryset: QuerySet[SKU] | None = None) -> QuerySet[SKU]:
    """Published SKUs in the HV backfill wave (HVA / HVD-Q / P / QX)."""
    qs = queryset if queryset is not None else SKU.objects.all()
    return qs.filter(is_published=True, sku_code__iregex=_HV_NEWNESS_CODE.pattern)


def stamp_hv_newness(
    *,
    dry_run: bool = False,
    only_empty: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Backfill ``first_published_at`` for the HV catalog wave.

    Args:
        dry_run: Count only.
        only_empty: Skip rows that already have a stamp.
        now: Override stamp time (default ``timezone.now()``).

    Returns:
        Counters: matched, updated, dry_run.
    """
    stamped_at = now if now is not None else timezone.now()
    qs = hv_newness_queryset()
    if only_empty:
        qs = qs.filter(first_published_at__isnull=True)
    matched = qs.count()
    if dry_run or matched == 0:
        return {"matched": matched, "updated": 0 if dry_run else matched, "dry_run": dry_run}
    updated = qs.update(first_published_at=stamped_at)
    return {"matched": matched, "updated": updated, "dry_run": dry_run}
