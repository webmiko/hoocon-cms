"""Publish news about BR-M / BR-ML adapters + product cover."""

from __future__ import annotations

from pathlib import Path

from django.core.files.base import ContentFile
from django.db import migrations
from django.utils import timezone

_NEWS_SLUG = "launch-br-adapters"
_NEWS_TITLE = "Анонс: адаптеры BR-M и BR-ML для шаровых кранов"
_COVER_SKU = "BR-M"
_PHONE = "8 800 350-58-98"

_NEWS_BODY = f"""
<p>В каталоге опубликованы адаптеры (кронштейны)
<strong>BR-M</strong> и <strong>BR-ML</strong> — для установки электропривода
на латунные шаровые краны серии&nbsp;8100.</p>
<p><strong>BR-M</strong> — под приводы без возвратной пружины
(DA…MU / DA…MQU, 24/230&nbsp;В). <strong>BR-ML</strong> — под приводы
с пружинным возвратом: только серия <strong>DA5FU</strong>
(24/230&nbsp;В).</p>
<p>На карточках — совместимые семейства приводов, индексы партнёра и
технички PDF (кронштейн и шток). В RFQ для шаровых 8100 кронштейн
подставляется автоматически: <strong>BR-ML</strong> для DA5FU,
иначе <strong>BR-M</strong> (для фланцевых ВЧШГ — BR-H).</p>
<p>Для расчёта цены и срока отгрузки оставьте
<a href="/consultation">заявку на КП</a> или позвоните {_PHONE}.</p>
<p><a href="/catalog/adaptery">Смотреть адаптеры в каталоге</a></p>
""".strip()


def _ensure_news(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Upsert launch-br-adapters and copy cover from BR-M."""
    News = apps.get_model("content", "News")
    SKU = apps.get_model("catalog", "SKU")
    ProductImage = apps.get_model("catalog", "ProductImage")

    now = timezone.now()
    news, _created = News.objects.update_or_create(
        slug=_NEWS_SLUG,
        defaults={
            "title": _NEWS_TITLE,
            "body": _NEWS_BODY,
            "is_published": True,
        },
    )
    if news.published_at is None:
        news.published_at = now
        news.save(update_fields=["published_at", "updated_at"])

    if news.cover:
        return

    sku = SKU.objects.filter(sku_code=_COVER_SKU, is_published=True).first()
    if sku is None:
        return

    product_image = (
        ProductImage.objects.filter(sku_id=sku.pk, is_published=True)
        .order_by("sort_order", "id")
        .first()
    )
    if product_image is None or not product_image.image:
        return

    basename = Path(product_image.image.name).name or "br-m-photo.webp"
    with product_image.image.open("rb") as handle:
        payload = handle.read()
    if not payload:
        return

    news.cover.save(basename, ContentFile(payload), save=True)


def _noop_reverse(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Keep news on reverse — content rollback via Admin if needed."""
    return


class Migration(migrations.Migration):
    """Data: news launch-br-adapters with BR-M product cover."""

    dependencies = [
        ("content", "0011_company_warranty_24_months"),
        ("catalog", "0013_sku_stock_qty"),
    ]

    operations = [
        migrations.RunPython(_ensure_news, _noop_reverse),
    ]
