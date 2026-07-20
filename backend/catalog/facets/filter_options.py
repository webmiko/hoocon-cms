"""Filter SKU querysets and collect facet chip options.

Part of ``catalog.facets`` package (audit P3-3).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from django.db.models import QuerySet

from catalog.facets.aux import AUX_SWITCH_NONE
from catalog.facets.defs import (
    FACET_BY_KEY,
    FACET_DEFS,
    FacetDef,
    attribute_ids_for_facet,
)
from catalog.facets.normalize import normalize_facet_value, values_match
from catalog.models import SKU, AttributeValue


def filter_skus_by_facet(
    queryset: QuerySet[SKU],
    facet: FacetDef,
    value: str,
    *,
    attr_ids: Iterable[int] | None = None,
) -> QuerySet[SKU]:
    """Filter SKUs whose EAV value matches the facet (loose)."""
    if facet.key == "analog":
        return _filter_skus_by_belimo_analog(queryset, value)

    ids = list(attr_ids) if attr_ids is not None else attribute_ids_for_facet(facet)
    if not ids:
        return queryset.none()

    # Prefer exact DB filter when possible; fall back to Python match for loose.
    # Area / voltage / control / aux need canon match (legacy spellings in DB).
    if facet.key not in {"aux_switch", "voltage", "control", "area"}:
        exact = queryset.filter(
            attribute_values__attribute_id__in=ids,
            attribute_values__value=value,
        )
        if exact.exists():
            return exact.distinct()

    matching_sku_ids: set[int] = set()
    if facet.key in {"aux_switch", "voltage", "control", "area"}:
        detailed_rows = AttributeValue.objects.filter(
            attribute_id__in=ids,
        ).values_list(
            "sku_id",
            "value",
            "sku__sku_code",
            "sku__description",
            "sku__product__category__slug",
        )
        for sku_id, stored, sku_code, description, category_slug in detailed_rows:
            normalized = normalize_facet_value(
                facet.key,
                str(stored),
                sku_code=str(sku_code or "") or None,
                description=str(description or ""),
                category_slug=str(category_slug or "") or None,
            )
            if normalized == normalize_facet_value(facet.key, value):
                matching_sku_ids.add(sku_id)
            elif values_match(str(stored), value):
                matching_sku_ids.add(sku_id)
    else:
        simple_rows = AttributeValue.objects.filter(
            attribute_id__in=ids,
        ).values_list(
            "sku_id",
            "value",
        )
        for sku_id, stored in simple_rows:
            if values_match(str(stored), value):
                matching_sku_ids.add(sku_id)
    if not matching_sku_ids:
        return queryset.none()
    return queryset.filter(pk__in=matching_sku_ids)


def collect_facet_options(
    *,
    base_queryset: QuerySet[SKU] | None = None,
) -> list[dict[str, object]]:
    """Build facet payload for the public facets endpoint.

    Args:
        base_queryset: Optional SKU scope (e.g. current category). Defaults to
            all published SKUs.

    Returns:
        List of ``{key, label, values: [{value, count}]}``.
    """
    if base_queryset is None:
        base_queryset = SKU.objects.filter(is_published=True)
    sku_ids = list(base_queryset.values_list("id", flat=True))
    result: list[dict[str, object]] = []

    for facet in FACET_DEFS:
        if facet.key == "analog":
            analog_facet = _collect_analog_facet_options(sku_ids)
            if analog_facet is not None:
                result.append(analog_facet)
            continue
        attr_ids = attribute_ids_for_facet(facet)
        if not attr_ids:
            continue
        counts: dict[str, set[int]] = {}
        rows = AttributeValue.objects.filter(
            attribute_id__in=attr_ids,
            sku_id__in=sku_ids,
        ).values_list(
            "sku_id",
            "value",
            "sku__sku_code",
            "sku__description",
            "sku__product__category__slug",
        )
        for sku_id, raw, sku_code, description, category_slug in rows:
            val = normalize_facet_value(
                facet.key,
                str(raw),
                sku_code=str(sku_code or "") or None,
                description=str(description or ""),
                category_slug=str(category_slug or "") or None,
            )
            if not val:
                continue
            # Aux absent («Нет») is not a filter chip — only SPDT-1 / SPDT-2.
            if facet.key == "aux_switch" and val == AUX_SWITCH_NONE:
                continue
            counts.setdefault(val, set()).add(sku_id)
        if not counts:
            continue
        values = [
            {"value": value, "count": len(sku_set)}
            for value, sku_set in sorted(
                counts.items(),
                key=lambda item: _facet_sort_key(facet.key, item[0]),
            )
        ]
        result.append({"key": facet.key, "label": facet.label, "values": values})
    return result


def _filter_skus_by_belimo_analog(
    queryset: QuerySet[SKU],
    value: str,
) -> QuerySet[SKU]:
    """Match SKUs that list the Belimo article (card text, field, or inference)."""
    from catalog.etl.belimo_analogs import belimo_codes_for_sku, normalize_belimo_code

    needle = normalize_belimo_code(value)
    if not needle:
        return queryset.none()
    # Fast path: persisted primary code.
    direct_ids = set(
        queryset.filter(analog_belimo_code__iexact=needle).values_list("id", flat=True),
    )
    skus = queryset.select_related("product", "product__category").prefetch_related(
        "attribute_values__attribute",
    )
    matching: set[int] = set(direct_ids)
    for sku in skus:
        if sku.id in matching:
            continue
        codes = {normalize_belimo_code(c) for c in belimo_codes_for_sku(sku)}
        if needle in codes:
            matching.add(sku.id)
    if not matching:
        return queryset.none()
    return queryset.filter(id__in=matching)


def _collect_analog_facet_options(
    sku_ids: list[int],
) -> dict[str, object] | None:
    """Build «Аналоги» facet from card Belimo lines, field, or ТТХ inference."""
    from catalog.etl.belimo_analogs import belimo_codes_for_sku

    if not sku_ids:
        return None
    counts: dict[str, set[int]] = {}
    skus = (
        SKU.objects.filter(id__in=sku_ids)
        .select_related("product", "product__category")
        .prefetch_related("attribute_values__attribute")
    )
    for sku in skus:
        for code in belimo_codes_for_sku(sku):
            counts.setdefault(code, set()).add(sku.id)
    if not counts:
        return None
    values = [
        {"value": value, "count": len(sku_set)}
        for value, sku_set in sorted(
            counts.items(),
            key=lambda item: _facet_sort_key("analog", item[0]),
        )
    ]
    return {
        "key": "analog",
        "label": FACET_BY_KEY["analog"].label,
        "values": values,
    }


def _facet_sort_key(facet_key: str, value: str) -> tuple:
    """Sort numeric-ish facets by number, else alphabetically."""
    if facet_key == "aux_switch":
        order = {"нет": 0, "spdt-1": 1, "spdt-2": 2}
        return (order.get(value.casefold(), 9), value.casefold())
    if facet_key == "control":
        order = {
            "открыто/закрыто": 0,
            "2-/3-позиционное": 1,
            "пропорциональное": 2,
        }
        return (order.get(value.casefold(), 9), value.casefold())
    if facet_key == "area":
        match = re.search(r"(\d+[.,]?\d*)", value)
        number = float(match.group(1).replace(",", ".")) if match else 0.0
        return (number,)
    if facet_key in {"moment", "voltage", "dn", "kvs"}:
        token = value.split()[0].replace(",", ".").replace("до", "").strip()
        try:
            return (0, float(token))
        except ValueError:
            return (1, value.casefold())
    return (0, value.casefold())
