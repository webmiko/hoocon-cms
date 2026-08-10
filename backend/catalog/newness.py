"""Catalog «Новинки» window: first_published_at within N days.

Do not use ``created_at`` / ``updated_at`` (ETL noise). Stamp
``SKU.first_published_at`` on first public publish or via ``stamp_hv_newness``.

Home carousel / ``?new=1`` list order: in-stock first, then newest
``first_published_at`` (left / first page = newer).

- Home carousel: FE ``page_size`` = :data:`NOVINKI_CAROUSEL_LIMIT` (20).
- Catalog ``/catalog?new=1`` (and with ``?category=``): same order and 30-day
  window, **no** total cap — only DRF page size for pagination.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from django.db.models import Case, F, IntegerField, QuerySet, Value, When
from django.utils import timezone

from catalog.models import SKU

NEW_WINDOW_DAYS: int = 30
# Home «Новинки» carousel hard cap (FE ``page_size`` only; catalog is uncapped).
NOVINKI_CAROUSEL_LIMIT: int = 20

# HV wave (2025 catalog fill): all HVA; HVD fast-Q; spring P; capacitor QX.
_HV_NEWNESS_CODE = re.compile(
    r"(?i)^(?:"
    r"hva(?:24|230)s?-\d+(?:uq|q|p|qx)?"
    r"|hvd(?:24|230)s?-\d+(?:q|qx)"
    r")$",
)

_NEW_QUERY_TRUE: frozenset[str] = frozenset({"1", "true", "yes", "on"})


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


def is_new_query_param(value: str | None) -> bool:
    """True when ``?new=`` is a truthy flag (same tokens as FilterSet)."""
    if not value:
        return False
    return value.strip().casefold() in _NEW_QUERY_TRUE


def novinki_list_order_by() -> tuple[Any, ...]:
    """Carousel / ``?new=1`` order: in stock → newer ``first_published_at`` → code.

    Newest land on the left; adding a card shifts older ones right and off the
    FE page (home keeps at most :data:`NOVINKI_CAROUSEL_LIMIT`).
    """
    return (
        Case(
            When(stock_qty__gt=0, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        ),
        F("first_published_at").desc(nulls_last=True),
        "sku_code",
    )


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
