"""Catalog services: public analog matching (ЛК-10)."""

from __future__ import annotations

from django.db.models import QuerySet

from catalog.models import SKU, AnalogMap, normalize_analog_code


def analogs_find(brand: str, code: str) -> QuerySet[AnalogMap]:
    """Find active AnalogMap rows for a foreign brand + article.

    ``foreign_code`` матчится по нормализованному ключу (upper, только
    буквы/цифры) — написания «NM24A-SR» и «nm 24a sr» равнозначны. Пустой
    бренд допустим: тогда матч только по коду (бренд подсказывает в выдаче).
    Код без букв/цифр («---») ничего не находит, а не отдаёт всю карту;
    неопубликованные SKU в публичный подбор не попадают.
    """
    key = normalize_analog_code(code)
    if not key:
        return AnalogMap.objects.none()
    qs = AnalogMap.objects.filter(
        is_active=True,
        foreign_code_key=key,
        sku__is_published=True,
    ).select_related("sku")
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
