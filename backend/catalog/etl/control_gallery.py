"""Unpublish A/AS ↔ D/DS sibling photos that do not belong on this SKU card.

Tilda product pages attach both the modulating (0…10 V) and on/off (2-/3-point)
marketing shots to every edition. Each SKU should only keep the photo whose
control type matches the article suffix (-A/-AS vs -D/-DS).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from django.db.models import Prefetch

from catalog.etl.sku_variant import parse_sku_variant
from catalog.models import SKU, Product, ProductImage

logger = logging.getLogger(__name__)

# Series that ship dual control marketing photos on one Tilda product page.
_DUAL_CONTROL_CODE = re.compile(r"(?i)^(?:da\d+(?:fu|mu|mqu)|hva)")


def _primary_source_url(sku: SKU) -> str | None:
    """First published gallery ``source_url`` for ``sku`` (sort_order, id)."""
    images = getattr(sku, "_prefetched_images", None)
    if images is None:
        images = list(
            sku.images.filter(is_published=True).order_by("sort_order", "id")[:1],
        )
    else:
        images = [img for img in images if img.is_published][:1]
    if not images:
        return None
    return (images[0].source_url or "").strip() or None


def prune_cross_control_images(*, dry_run: bool = False) -> dict[str, Any]:
    """Hide opposite-control photos (A card keeps modulating URL, D keeps on/off).

    Classification uses each edition's primary (sort_order 0) Tilda photo URL.
    Shared heroes (same URL as primary on both roles) are left alone.

    Args:
        dry_run: When True, count only.

    Returns:
        Counters: products, unpublished, dry_run.
    """
    published = Prefetch(
        "images",
        queryset=ProductImage.objects.filter(is_published=True).order_by(
            "sort_order",
            "id",
        ),
        to_attr="_prefetched_images",
    )
    products = (
        Product.objects.filter(
            skus__sku_code__iregex=r"(?i)^(?:da\d+(?:fu|mu|mqu)|hva)",
        )
        .distinct()
        .prefetch_related(
            Prefetch(
                "skus",
                queryset=SKU.objects.prefetch_related(published),
            ),
        )
    )

    unpublished = 0
    touched_products = 0
    for product in products:
        skus = [s for s in product.skus.all() if _DUAL_CONTROL_CODE.match((s.sku_code or "").replace(" ", ""))]
        if len(skus) < 2:
            continue

        modulating_urls: set[str] = set()
        on_off_urls: set[str] = set()
        for sku in skus:
            variant = parse_sku_variant(sku.sku_code)
            if variant.control not in {"modulating", "on_off"}:
                continue
            url = _primary_source_url(sku)
            if not url:
                continue
            if variant.control == "modulating":
                modulating_urls.add(url)
            else:
                on_off_urls.add(url)

        if not modulating_urls or not on_off_urls:
            continue
        only_mod = modulating_urls - on_off_urls
        only_on_off = on_off_urls - modulating_urls
        if not only_mod and not only_on_off:
            continue

        touched_products += 1
        for sku in skus:
            variant = parse_sku_variant(sku.sku_code)
            if variant.control == "modulating":
                drop = only_on_off
            elif variant.control == "on_off":
                drop = only_mod
            else:
                continue
            if not drop:
                continue
            qs = ProductImage.objects.filter(
                sku=sku,
                is_published=True,
                source_url__in=drop,
            )
            count = qs.count()
            if count == 0:
                continue
            unpublished += count
            logger.info(
                "control_gallery_prune sku=%s drop=%s count=%s dry_run=%s",
                sku.sku_code,
                sorted(drop)[:2],
                count,
                dry_run,
            )
            if not dry_run:
                qs.update(is_published=False)

    return {
        "products": touched_products,
        "unpublished": unpublished,
        "dry_run": dry_run,
    }
