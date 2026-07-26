"""Attach HVA-5 product photo as cover for launch-hva-5nm news."""

from __future__ import annotations

from pathlib import Path

from django.core.files.base import ContentFile
from django.db import migrations

_NEWS_SLUG = "launch-hva-5nm"
_SKU_CODE = "HVA230-5"


def _attach_cover(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Copy primary HVA230-5 ProductImage onto news cover if empty."""
    News = apps.get_model("content", "News")
    SKU = apps.get_model("catalog", "SKU")
    ProductImage = apps.get_model("catalog", "ProductImage")

    news = News.objects.filter(slug=_NEWS_SLUG).first()
    if news is None or news.cover:
        return

    sku = SKU.objects.filter(sku_code=_SKU_CODE, is_published=True).first()
    if sku is None:
        return

    product_image = (
        ProductImage.objects.filter(sku_id=sku.pk, is_published=True)
        .order_by("sort_order", "id")
        .first()
    )
    if product_image is None or not product_image.image:
        return

    basename = Path(product_image.image.name).name or "hva230-5-0.webp"
    with product_image.image.open("rb") as handle:
        payload = handle.read()
    if not payload:
        return

    news.cover.save(basename, ContentFile(payload), save=True)


def _noop_reverse(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Keep cover on reverse — removing media mid-rollback is unsafe."""
    return


class Migration(migrations.Migration):
    """Data: news launch-hva-5nm cover from HVA230-5 product card photo."""

    dependencies = [
        ("content", "0008_admin_ru_help_text"),
        ("catalog", "0013_sku_stock_qty"),
    ]

    operations = [
        migrations.RunPython(_attach_cover, _noop_reverse),
    ]
