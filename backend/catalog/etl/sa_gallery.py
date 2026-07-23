"""Unpublish SA DS↔DST sibling photos that do not belong on this SKU card.

Tilda product pages attach both the plain and thermal body shots to every
edition. Each SKU should only keep its own edition photo(s).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from django.db.models import Prefetch

from catalog.etl.sku_variant import sku_code_is_thermal
from catalog.models import SKU, Product, ProductImage

logger = logging.getLogger(__name__)

_SA_CODE = re.compile(r"(?i)^sa\d")


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


def prune_sa_cross_edition_images(*, dry_run: bool = False) -> dict[str, Any]:
    """Hide opposite-edition SA photos (DS card keeps non-DST URL, and vice versa).

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
        Product.objects.filter(skus__sku_code__iregex=r"(?i)^sa\d")
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
        skus = [s for s in product.skus.all() if _SA_CODE.match(s.sku_code or "")]
        if len(skus) < 2:
            continue

        thermal_urls: set[str] = set()
        nont_urls: set[str] = set()
        for sku in skus:
            url = _primary_source_url(sku)
            if not url:
                continue
            if sku_code_is_thermal(sku.sku_code):
                thermal_urls.add(url)
            else:
                nont_urls.add(url)

        # Only act when both roles are known and distinct.
        if not thermal_urls or not nont_urls:
            continue
        only_thermal = thermal_urls - nont_urls
        only_nont = nont_urls - thermal_urls
        if not only_thermal and not only_nont:
            continue

        touched_products += 1
        for sku in skus:
            is_thermal = sku_code_is_thermal(sku.sku_code)
            drop = only_nont if is_thermal else only_thermal
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
                "sa_gallery_prune sku=%s drop=%s count=%s dry_run=%s",
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
