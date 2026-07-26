"""Copy a catalog SKU photo onto a news cover when the cover is empty."""

from __future__ import annotations

import logging
from pathlib import Path

from django.core.files.base import ContentFile

from catalog.models import SKU, ProductImage
from content.models import News

logger = logging.getLogger(__name__)

# Primary gallery photo for the HVA-5 family (product card PDP).
_DEFAULT_SKU_CODE = "HVA230-5"
_NEWS_SLUG = "launch-hva-5nm"


def attach_sku_cover_to_news(
    *,
    news_slug: str = _NEWS_SLUG,
    sku_code: str = _DEFAULT_SKU_CODE,
    force: bool = False,
) -> bool:
    """Attach primary ProductImage of ``sku_code`` as news cover.

    Args:
        news_slug: News slug to update.
        sku_code: Catalog SKU whose primary published image is copied.
        force: Overwrite an existing cover when True.

    Returns:
        True when the cover file was saved.
    """
    news = News.objects.filter(slug=news_slug).first()
    if news is None:
        logger.info("news cover skip: news %s missing", news_slug)
        return False
    if news.cover and not force:
        return False

    sku = SKU.objects.filter(sku_code=sku_code, is_published=True).first()
    if sku is None:
        logger.info("news cover skip: SKU %s missing", sku_code)
        return False

    product_image = ProductImage.objects.filter(sku=sku, is_published=True).order_by("sort_order", "id").first()
    if product_image is None or not product_image.image:
        logger.info("news cover skip: no image for SKU %s", sku_code)
        return False

    basename = Path(product_image.image.name).name or f"{sku_code.lower()}.webp"
    with product_image.image.open("rb") as handle:
        payload = handle.read()
    if not payload:
        return False

    news.cover.save(basename, ContentFile(payload), save=True)
    return True
