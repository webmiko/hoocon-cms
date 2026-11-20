"""Catalog services: public analog matching (ЛК-10)."""

from __future__ import annotations

from django.db.models import QuerySet

from catalog.etl.belimo_analogs import sku_takes_no_analogs
from catalog.models import SKU, normalize_analog_code


def analogs_find(brand: str, code: str) -> QuerySet[SKU]:
    """Find published Hoocon SKUs by manually stored Belimo article.

    ``analog_belimo_code`` on the card is the public source. ``AnalogMap`` in
    admin is only a worksheet while creating the card. Matching uses the same
    normalized key as legacy ``foreign_code_key`` (upper, alnum only).
    """
    key = normalize_analog_code(code)
    if not key:
        return SKU.objects.none()
    brand_norm = (brand or "").strip().casefold()
    if brand_norm and brand_norm not in ("belimo", "белимо"):
        return SKU.objects.none()
    matching: list[int] = []
    qs = (
        SKU.objects.filter(is_published=True)
        .select_related("product", "product__category")
        .exclude(analog_belimo_code__isnull=True)
        .exclude(analog_belimo_code="")
    )
    for sku in qs:
        if sku_takes_no_analogs(sku):
            continue
        if normalize_analog_code(sku.analog_belimo_code or "") != key:
            continue
        matching.append(sku.pk)
    if not matching:
        return SKU.objects.none()
    return SKU.objects.filter(pk__in=matching).select_related("product", "product__category")


def resolve_position_code(code: str) -> tuple[SKU | None, bool]:
    """Resolve one spec line: own SKU first, else Belimo code on a card.

    Returns ``(sku, via_analog)``. ``via_analog`` is True when the line matched
    ``analog_belimo_code``, not ``sku_code``. Unpublished SKUs are skipped.
    Two published SKUs sharing the same Belimo code are not a match.
    """
    key = (code or "").strip()
    if not key:
        return None, False
    sku = SKU.objects.filter(sku_code__iexact=key, is_published=True).order_by("pk").first()
    if sku is not None:
        return sku, False
    norm_key = normalize_analog_code(key)
    if not norm_key:
        return None, False
    matches: list[SKU] = []
    qs = (
        SKU.objects.filter(is_published=True)
        .select_related("product", "product__category")
        .exclude(analog_belimo_code__isnull=True)
        .exclude(analog_belimo_code="")
    )
    for row in qs:
        if sku_takes_no_analogs(row):
            continue
        if normalize_analog_code(row.analog_belimo_code or "") != norm_key:
            continue
        matches.append(row)
    if len(matches) != 1:
        return None, False
    return matches[0], True
