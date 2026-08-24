"""Filter SKU querysets and collect facet chip options.

Part of ``catalog.facets`` package (audit P3-3).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from django.db.models import QuerySet

from catalog.facets.aux import AUX_SWITCH_NONE
from catalog.facets.defs import (
    CATEGORY_FACET_KEYS,
    FACET_BY_KEY,
    FACET_DEFS,
    FacetDef,
    attribute_ids_for_facet,
)
from catalog.facets.normalize import normalize_facet_value, values_match
from catalog.models import SKU, Attribute, AttributeValue


def filter_skus_by_facet(
    queryset: QuerySet[SKU],
    facet: FacetDef,
    value: str,
    *,
    attr_ids: Iterable[int] | None = None,
) -> QuerySet[SKU]:
    """Filter SKUs whose EAV value matches the facet (loose).

    Comma-separated ``value`` means OR (any part matches) — used by the
    product picker when discrete on/off spans several canon labels
    (``Открыто/закрыто`` and ``2-/3-позиционное``).
    """
    if facet.key == "analog":
        return _filter_skus_by_belimo_analog(queryset, value)

    parts = [part.strip() for part in str(value).split(",") if part.strip()]
    if len(parts) > 1:
        matching: set[int] = set()
        for part in parts:
            matching.update(
                filter_skus_by_facet(
                    queryset,
                    facet,
                    part,
                    attr_ids=attr_ids,
                ).values_list("pk", flat=True),
            )
        if not matching:
            return queryset.none()
        return queryset.filter(pk__in=matching)

    ids = list(attr_ids) if attr_ids is not None else attribute_ids_for_facet(facet)
    if not ids:
        return queryset.none()

    # Prefer exact DB filter when possible; fall back to Python match for loose.
    # Area / voltage / control / aux / temp_sensor need canon match (legacy spellings).
    if facet.key not in {"aux_switch", "voltage", "control", "area", "temp_sensor"}:
        exact = queryset.filter(
            attribute_values__attribute_id__in=ids,
            attribute_values__value=value,
        )
        if exact.exists():
            return exact.distinct()

    matching_sku_ids: set[int] = set()
    if facet.key in {"aux_switch", "voltage", "control", "area", "temp_sensor"}:
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


def facet_defs_for_category(category_slug: str | None) -> tuple[FacetDef, ...]:
    """Return ordered facet defs for a category (or the full catalog set).

    Args:
        category_slug: Category slug from ``?category=``; None/empty → all facets.

    Returns:
        Ordered ``FacetDef`` tuple used by :func:`collect_facet_options`.
    """
    slug = (category_slug or "").strip()
    keys = CATEGORY_FACET_KEYS.get(slug)
    if not keys:
        return FACET_DEFS
    return tuple(FACET_BY_KEY[key] for key in keys if key in FACET_BY_KEY)


# Facets that need sku_code / description / category for normalize_facet_value.
_FACETS_NEEDING_SKU_CONTEXT: frozenset[str] = frozenset(
    {"aux_switch", "voltage", "control", "area", "temp_sensor"},
)
# Above this size, skip Belimo inference and use only persisted analog codes.
_ANALOG_INFERENCE_SKU_CAP = 150


def collect_facet_options(
    *,
    base_queryset: QuerySet[SKU] | None = None,
    category_slug: str | None = None,
) -> list[dict[str, object]]:
    """Build facet payload for the public facets endpoint.

    Args:
        base_queryset: Optional SKU scope (e.g. current category). Defaults to
            all published SKUs.
        category_slug: Optional category for a fixed facet set/order
            (e.g. ``sharovye-krany`` → DN, тип крана, Kvs, материал).

    Returns:
        List of ``{key, label, values: [{value, count}]}``.
    """
    if base_queryset is None:
        base_queryset = SKU.objects.filter(is_published=True)
    sku_ids = list(base_queryset.values_list("id", flat=True))
    result: list[dict[str, object]] = []
    # Read Attribute once for the whole payload: one scan per facet meant ~11
    # identical queries on this endpoint.
    attributes = list(Attribute.objects.all().only("id", "name", "slug"))

    for facet in facet_defs_for_category(category_slug):
        if facet.key == "analog":
            analog_facet = _collect_analog_facet_options(sku_ids)
            if analog_facet is not None:
                result.append(analog_facet)
            continue
        attr_ids = attribute_ids_for_facet(facet, attributes=attributes)
        if not attr_ids:
            continue
        counts: dict[str, set[int]] = {}
        need_context = facet.key in _FACETS_NEEDING_SKU_CONTEXT
        if need_context:
            context_rows = AttributeValue.objects.filter(
                attribute_id__in=attr_ids,
                sku_id__in=sku_ids,
            ).values_list(
                "sku_id",
                "value",
                "sku__sku_code",
                "sku__description",
                "sku__product__category__slug",
            )
            for sku_id, raw, sku_code, description, row_category in context_rows:
                val = normalize_facet_value(
                    facet.key,
                    str(raw),
                    sku_code=str(sku_code or "") or None,
                    description=str(description or ""),
                    category_slug=str(row_category or "") or None,
                )
                if not val:
                    continue
                if facet.key == "aux_switch" and val == AUX_SWITCH_NONE:
                    continue
                counts.setdefault(val, set()).add(sku_id)
        else:
            simple_rows = AttributeValue.objects.filter(
                attribute_id__in=attr_ids,
                sku_id__in=sku_ids,
            ).values_list("sku_id", "value")
            for sku_id, raw in simple_rows:
                val = normalize_facet_value(facet.key, str(raw))
                if not val:
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
    """Build «Аналоги» facet from card Belimo lines, field, or ТТХ inference.

    Large scopes (kits / valves with hundreds of SKUs) only use the persisted
    ``analog_belimo_code`` field — full Belimo inference over every row is too
    expensive and usually empty for those categories.
    """
    from catalog.etl.belimo_analogs import belimo_codes_for_sku, normalize_belimo_code

    if not sku_ids:
        return None
    counts: dict[str, set[int]] = {}

    if len(sku_ids) > _ANALOG_INFERENCE_SKU_CAP:
        for sku_id, code in (
            SKU.objects.filter(id__in=sku_ids)
            .exclude(analog_belimo_code__isnull=True)
            .exclude(analog_belimo_code="")
            .values_list("id", "analog_belimo_code")
        ):
            normalized = normalize_belimo_code(str(code))
            if normalized:
                counts.setdefault(normalized, set()).add(sku_id)
    else:
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
    if facet_key == "temp_sensor":
        order = {"нет": 0, "saf72": 1}
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
