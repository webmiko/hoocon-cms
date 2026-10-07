"""Catalog services: public analog matching (ЛК-10)."""

from __future__ import annotations

from django.db.models import QuerySet

from catalog.models import SKU, AnalogMap, normalize_analog_code


def analogs_find(brand: str, code: str) -> QuerySet[AnalogMap]:
    """Find active AnalogMap rows for a foreign brand + article.

    ``foreign_code`` матчится по нормализованному ключу (upper, только
    буквы/цифры) — написания «NM24A-SR» и «nm 24a sr» равнозначны. Пустой
    бренд допустим: тогда матч только по коду (бренд подсказывает в выдаче).
    """
    qs = AnalogMap.objects.filter(is_active=True).select_related("sku")
    key = normalize_analog_code(code)
    if key:
        qs = qs.filter(foreign_code_key=key)
    brand_norm = (brand or "").strip().casefold()
    if brand_norm:
        qs = qs.filter(brand__iexact=brand_norm)
    return qs.order_by("brand", "foreign_code")


def resolve_position_code(code: str) -> tuple[SKU | None, AnalogMap | None]:
    """Resolve one spec line: own SKU first, then the analog map.

    Returns ``(sku, analog_map_row)`` — ``analog_map_row`` non-null marks
    that the SKU came from a foreign-article match (для подсказки
    менеджеру/инженеру).
    """
    key = (code or "").strip()
    if not key:
        return None, None
    sku = SKU.objects.filter(sku_code__iexact=key).first()
    if sku is not None:
        return sku, None
    norm_key = normalize_analog_code(key)
    row = AnalogMap.objects.filter(is_active=True, foreign_code_key=norm_key).select_related("sku").first()
    if row is not None:
        return row.sku, row
    return None, None
