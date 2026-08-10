"""Collapse multi-edition Product cards to one SKU row in catalog lists.

H81 kits (``h8101``…``h8122``), brass ``8100-bv*``, H8205 LAV, DAMU,
DAMQU (``privod-vozdushniy-da{n}mqu-*``),
DAFU (``…-pruzhina-dafu-*nm``), SAMU, SAFU (``privod-protivopozharniy-*nm``),
HVA, HVD (air + smoke ``…-hvd-*f``) keep many published SKUs under one Product.
Paginated list APIs must return a single representative per family Product
(within the current filter), otherwise the first page is filled by one series
and siblings never appear.
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

# Shared slug bodies (no anchors) — used by both fullmatch and ORM iregex.
_H81_SLUG = "|".join(re.escape(s) for s in sorted(H81_FAMILY_PRODUCT_SLUGS))
_BRASS_DN_SLUG = r"8100-bv\d+"
_H8205_LAV_SLUG = r"h8205-lav\d+[st]*"
_DAMU_SLUG = r"privod-vozdushniy-bez-pruzhini-damu-\d+nm"
_DAMQU_SLUG = r"privod-vozdushniy-da\d+mqu-\d+nm"
_DAFU_SLUG = r"privod-vozdushniy-pruzhina-dafu-\d+nm"
# SAMU Nm only (``…-10nm``); HVD-F uses ``…-hvd-3f`` and must not share this.
_SAMU_NM_SLUG = r"privod-dimoudaleniya-\d+nm"
_SAFU_NM_SLUG = r"privod-protivopozharniy-\d+nm"
_HVA_SLUG = (
    r"privod-vozdushniy-hva-\d+nm"
    r"|privod-vozdushniy-bez-pruzhini-uskorenniy-hva-q-\d+nm"
    r"|privod-vozdushniy-bez-pruzhini-uskorenniy-hva-uq-\d+nm"
    r"|privod-vozdushniy-kondensator-hva-\d+qx"
)
_HVD_AIR_SLUG = (
    r"privod-vozdushniy-hvd-(?:\d+nm|\d+q)"
    r"|privod-vozdushniy-kondensator-hvd-\d+qx"
)
_HVD_SMOKE_SLUG = r"privod-dimoudaleniya-hvd-\d+f"

_FAMILY_PRODUCT_SLUG_RE = re.compile(
    rf"(?i)^(?:{_H81_SLUG}"
    rf"|{_BRASS_DN_SLUG}"
    rf"|{_H8205_LAV_SLUG}"
    rf"|{_DAMU_SLUG}"
    rf"|{_DAMQU_SLUG}"
    rf"|{_DAFU_SLUG}"
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
    """ORM filter for SKUs belonging to collapsible family Products.

    Anchored the same way as :func:`is_collapsible_family_product_slug` —
    never ``istartswith``, which would accept stray suffixes
    (``h8205-lav232-variant``, ``8100-bv215-extra``).
    """
    return Q(product__slug__iregex=_FAMILY_PRODUCT_SLUG_RE.pattern)


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
