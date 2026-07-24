"""Collapse multi-edition Product cards to one SKU row in catalog lists.

H81 kits (``h8101``…``h8122``), brass ``8100-bv*``, H8205 LAV, DAMU,
SAMU, SAFU (``privod-protivopozharniy-*nm``), HVA, HVD (air + smoke
``…-hvd-*f``) keep many published SKUs under one Product. Paginated list APIs
must return a single representative per family Product (within the current
filter), otherwise the first page is filled by one series and siblings never
appear.
"""

from __future__ import annotations

import re

from django.db.models import Q, QuerySet

from catalog.models import SKU

H81_FAMILY_PRODUCT_SLUGS: frozenset[str] = frozenset(
    {
        "h8101",
        "h8102",
        "h8103",
        "h8104",
        "h8105",
        "h8106",
        "h8107",
        "h8108",
        "h8121",
        "h8122",
    },
)

# SAMU Nm only (``…-10nm``); HVD-F uses ``…-hvd-3f`` and must not share this.
_SAMU_NM_SLUG = r"privod-dimoudaleniya-\d+nm"
_SAFU_NM_SLUG = r"privod-protivopozharniy-\d+nm"
_HVA_SLUG = (
    r"privod-vozdushniy-hva-\d+nm"
    r"|privod-vozdushniy-bez-pruzhini-uskorenniy-hva-q-\d+nm"
)
_HVD_AIR_SLUG = r"privod-vozdushniy-hvd-(?:\d+nm|\d+q)"
_HVD_SMOKE_SLUG = r"privod-dimoudaleniya-hvd-\d+f"

_FAMILY_PRODUCT_SLUG_RE = re.compile(
    r"(?i)^("
    r"h81(?:01|02|03|04|05|06|07|08|21|22)"
    r"|8100-bv\d+"
    r"|h8205-lav\d+[st]*"
    r"|privod-vozdushniy-bez-pruzhini-damu-\d+nm"
    rf"|{_SAMU_NM_SLUG}"
    rf"|{_SAFU_NM_SLUG}"
    rf"|{_HVA_SLUG}"
    rf"|{_HVD_AIR_SLUG}"
    rf"|{_HVD_SMOKE_SLUG}"
    r")$",
)


def is_collapsible_family_product_slug(slug: str | None) -> bool:
    """True when catalog UI shows one card per Product (many SKU editions)."""
    return bool(_FAMILY_PRODUCT_SLUG_RE.fullmatch((slug or "").strip()))


def family_product_q() -> Q:
    """ORM filter for SKUs belonging to collapsible family Products."""
    return (
        Q(product__slug__in=H81_FAMILY_PRODUCT_SLUGS)
        | Q(product__slug__istartswith="8100-bv")
        | Q(product__slug__istartswith="h8205-lav")
        | Q(product__slug__iregex=r"(?i)^privod-vozdushniy-bez-pruzhini-damu-\d+nm$")
        | Q(product__slug__iregex=rf"(?i)^{_SAMU_NM_SLUG}$")
        | Q(product__slug__iregex=rf"(?i)^{_SAFU_NM_SLUG}$")
        | Q(product__slug__iregex=rf"(?i)^(?:{_HVA_SLUG})$")
        | Q(product__slug__iregex=rf"(?i)^{_HVD_AIR_SLUG}$")
        | Q(product__slug__iregex=rf"(?i)^{_HVD_SMOKE_SLUG}$")
    )


def collapse_family_skus_for_list(queryset: QuerySet[SKU]) -> QuerySet[SKU]:
    """Keep one SKU per family Product; leave other series unchanged.

    Representative among rows still in ``queryset`` (facets apply first):

    1. If any edition is in stock (``stock_qty > 0``) — lowest ``sku_code``
       (then ``id``) among in-stock editions so the catalog card shows
       «В наличии» whenever the family has stock.
    2. Otherwise (all out / empty) — lowest ``sku_code`` among all editions
       (stable first-of-series).

    Uses a lean unannotated SKU scan (2–3 queries). Never loop ``.first()`` on
    the caller's annotated/ordered queryset — that caused ~N queries equal to
    the number of SKUs when ``DISTINCT product_id`` was defeated by annotations.

    Args:
        queryset: Already filtered published catalog SKUs.

    Returns:
        Queryset with at most one row per family Product (H81 / brass / LAV /
        DAMU / SAMU / SAFU / HVA / HVD).
    """
    # Drop ORDER BY / annotations: only PKs in scope matter for representatives.
    scoped = queryset.order_by().values("pk")
    lean_family = SKU.objects.filter(pk__in=scoped).filter(family_product_q())
    rows = list(
        lean_family.values_list("product_id", "id", "sku_code", "stock_qty"),
    )
    if not rows:
        return queryset

    by_product: dict[int, list[tuple[int, str, int]]] = {}
    for product_id, sku_id, sku_code, stock_qty in rows:
        by_product.setdefault(product_id, []).append(
            (sku_id, sku_code or "", int(stock_qty or 0)),
        )

    rep_ids: list[int] = []
    for _product_id, editions in by_product.items():
        in_stock = [row for row in editions if row[2] > 0]
        pool = in_stock if in_stock else editions
        pool.sort(key=lambda row: (row[1], row[0]))
        rep_ids.append(pool[0][0])

    if not rep_ids:
        return queryset

    return queryset.filter(~family_product_q() | Q(pk__in=rep_ids))
