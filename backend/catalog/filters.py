"""Query filters for public SKU list.

Spec: docs/readiness-backend-ux.md §2.3 —
``?category=&q=&moment=&voltage=&control=`` (canonical facets + EAV slug).
"""

from __future__ import annotations

from typing import Any

import django_filters
from django.db.models import F, Q, QuerySet
from rest_framework.filters import BaseFilterBackend
from rest_framework.request import Request
from rest_framework.views import APIView

from catalog.compatible_positions import exact_adapter_sku_code
from catalog.facets import FACET_BY_KEY, FACET_KEYS, filter_skus_by_facet
from catalog.models import SKU, Attribute
from catalog.newness import new_since

# Reserved query keys — not treated as Attribute.slug / facet filters.
_RESERVED_QUERY_KEYS: frozenset[str] = frozenset(
    {
        "page",
        "page_size",
        "q",
        "category",
        "ordering",
        "format",
        "search",
        "in_stock",
        "new",
    },
)

_IN_STOCK_TRUE: frozenset[str] = frozenset({"1", "true", "yes", "on"})


class SKUFilterSet(django_filters.FilterSet):
    """Base filters: category slug + free-text q + in-stock."""

    category = django_filters.CharFilter(method="filter_category")
    q = django_filters.CharFilter(method="filter_q")
    in_stock = django_filters.CharFilter(method="filter_in_stock")
    new = django_filters.CharFilter(method="filter_new")

    class Meta:
        model = SKU
        fields = ("category",)

    def filter_category(
        self,
        queryset: QuerySet[SKU],
        _name: str,
        value: str,
    ) -> QuerySet[SKU]:
        """Filter by category slug; accept legacy Tilda aliases."""
        if not value:
            return queryset
        from catalog.series_categories import resolve_alias

        slug = resolve_alias(value.strip()) or value.strip()
        return queryset.filter(product__category__slug=slug)

    def filter_in_stock(
        self,
        queryset: QuerySet[SKU],
        _name: str,
        value: str,
    ) -> QuerySet[SKU]:
        """When truthy (``1`` / ``true`` / ``yes``), keep only ``stock_qty > 0``."""
        if not value or value.strip().casefold() not in _IN_STOCK_TRUE:
            return queryset
        return queryset.filter(stock_qty__gt=0)

    def filter_new(
        self,
        queryset: QuerySet[SKU],
        _name: str,
        value: str,
    ) -> QuerySet[SKU]:
        """When truthy, keep SKUs with ``first_published_at`` in the Новинки window."""
        if not value or value.strip().casefold() not in _IN_STOCK_TRUE:
            return queryset
        return queryset.filter(first_published_at__gte=new_since())

    def filter_q(self, queryset: QuerySet[SKU], _name: str, value: str) -> QuerySet[SKU]:
        """Hybrid search: FTS for name/slug (stemming) + icontains for sku_code.

        FTS (SearchVector with russian config) handles Cyrillic stemming for
        product names. sku_code is matched with icontains because articles
        (e.g. 'HVA-5NM') don't benefit from stemming — exact substring is
        what the engineer types. Results ranked by SearchRank (FTS matches
        rank higher than sku_code-only matches).

        Spec: ПЛАН §6 Iter 2 — FTS по SKU + артикул.
        """
        if not value:
            return queryset
        adapter_code = exact_adapter_sku_code(value)
        if adapter_code is not None:
            return queryset.filter(sku_code__iexact=adapter_code).order_by(
                F("moment_nm").asc(nulls_last=True),
                F("sku_code_nm").asc(nulls_last=True),
                "sku_code",
            )
        from django.contrib.postgres.search import SearchQuery, SearchRank

        query = SearchQuery(value, config="russian")
        return (
            queryset.filter(
                Q(search_vector=query) | Q(sku_code__icontains=value) | Q(analog_belimo_code__icontains=value),
            )
            .annotate(rank=SearchRank("search_vector", query))
            .order_by(
                "-rank",
                F("moment_nm").asc(nulls_last=True),
                F("sku_code_nm").asc(nulls_last=True),
                "sku_code",
            )
        )


class AttributeQueryFilterBackend(BaseFilterBackend):
    """Apply facet aliases and ``?<attribute_slug>=<value>`` EAV filters."""

    def get_schema_operation_parameters(self, view: APIView) -> list[dict[str, object]]:
        """Document stable facet keys; dynamic attr slugs stay out of schema."""
        return [
            {
                "name": key,
                "required": False,
                "in": "query",
                "description": f"ТТХ facet: {FACET_BY_KEY[key].label}",
                "schema": {"type": "string"},
            }
            for key in sorted(FACET_KEYS)
        ] + [
            {
                "name": "in_stock",
                "required": False,
                "in": "query",
                "description": "Только товары в наличии (stock_qty > 0). Значения: 1 / true / yes.",
                "schema": {"type": "string", "enum": ["1", "true", "yes"]},
            },
            {
                "name": "new",
                "required": False,
                "in": "query",
                "description": (
                    "Только новинки (first_published_at за последние 30 суток). "
                    "Порядок: в наличии, затем newer first. Значения: 1 / true / yes."
                ),
                "schema": {"type": "string", "enum": ["1", "true", "yes"]},
            },
        ]

    def filter_queryset(
        self,
        request: Request,
        queryset: QuerySet[Any],
        _view: APIView,
    ) -> QuerySet[Any]:
        """Filter by canonical facets first, then raw Attribute.slug params."""
        params = request.query_params
        candidate_keys = [key for key in params if key not in _RESERVED_QUERY_KEYS]
        if not candidate_keys:
            return queryset

        for key in candidate_keys:
            value = params.get(key)
            if value is None or value == "":
                continue
            if key in FACET_BY_KEY:
                queryset = filter_skus_by_facet(queryset, FACET_BY_KEY[key], value)
                continue

        # Remaining keys that are real Attribute.slug values (legacy / exact).
        leftover = [key for key in candidate_keys if key not in FACET_KEYS and params.get(key) not in (None, "")]
        if not leftover:
            return queryset.distinct()

        attr_slugs = set(
            Attribute.objects.filter(slug__in=leftover).values_list("slug", flat=True),
        )
        for slug in attr_slugs:
            value = params.get(slug)
            if value is None or value == "":
                continue
            queryset = queryset.filter(
                attribute_values__attribute__slug=slug,
                attribute_values__value=value,
            )
        return queryset.distinct()


class FamilyCardCollapseFilterBackend(BaseFilterBackend):
    """Collapse H81 / brass / LAV multi-SKU Products to one list row.

    Must run after facet filters so the representative is chosen among
    matching editions (e.g. voltage=230 → a 230 SKU of that series).
    """

    def filter_queryset(
        self,
        request: Request,
        queryset: QuerySet[Any],
        view: APIView,
    ) -> QuerySet[Any]:
        """Apply family collapse on list actions only."""
        _ = request
        if getattr(view, "action", None) != "list":
            return queryset
        from catalog.family_cards import collapse_family_skus_for_list

        return collapse_family_skus_for_list(queryset)
