"""Publish news about H8205-LAV order availability + product cover."""

from __future__ import annotations

from pathlib import Path

from django.core.files.base import ContentFile
from django.db import migrations
from django.utils import timezone

_NEWS_SLUG = "launch-h8205-lav"
_NEWS_TITLE = "Доступен заказ: регулирующие клапаны H8205-LAV"
_COVER_SKU = "H8205-LAV232-24A"
_PHONE = "8 800 350-58-98"

_NEWS_BODY = f"""
<p>В каталоге открыт заказ линейки <strong>H8205-LAV</strong> — электрических
регулирующих клапанов (серия&nbsp;82) для автоматического управления расходом
среды в системах ОВК и промышленных АСУ&nbsp;ТП.</p>
<p><strong>Применение.</strong> Клапан изменяет степень открытия по сигналу
управления и регулирует расход (температура, уровень, давление) в контурах
отопления, вентиляции и кондиционирования, а также в смежных отраслях:
нефтехимия, металлургия, электроэнергетика, природоохранные системы.</p>
<p><strong>Что в серии.</strong> 2- и 3-ходовые корпуса DN&nbsp;32…300,
фланец PN16/PN25, рабочая среда — вода и раствор этиленгликоля (&lt;50&nbsp;%),
температура среды –20…+150&nbsp;°C. На карточке — питания 24/230&nbsp;В,
управление открыто/закрыто, пропорциональное или Modbus, опции
вспомогательного переключателя и аварийного сигнала.</p>
<p>Паспорт, габариты и схемы подключения — в карточке комплекта. Для расчёта
цены и срока отгрузки оставьте <a href="/consultation">заявку на КП</a> или
позвоните {_PHONE}.</p>
<p><a href="/catalog/komplekty">Смотреть H8205-LAV в каталоге</a></p>
""".strip()


def _ensure_news(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Upsert launch-h8205-lav and copy cover from H8205-LAV232-24A."""
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

    basename = Path(product_image.image.name).name or "h8205-lav232-photo.webp"
    with product_image.image.open("rb") as handle:
        payload = handle.read()
    if not payload:
        return

    news.cover.save(basename, ContentFile(payload), save=True)


def _noop_reverse(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Keep news on reverse — content rollback via Admin if needed."""
    return


class Migration(migrations.Migration):
    """Data: news launch-h8205-lav with H8205 product cover."""

    dependencies = [
        ("content", "0009_news_launch_hva_cover"),
        ("catalog", "0013_sku_stock_qty"),
    ]

    operations = [
        migrations.RunPython(_ensure_news, _noop_reverse),
    ]
