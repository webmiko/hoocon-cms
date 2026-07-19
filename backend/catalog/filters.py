"""Query filters for public SKU list.

Spec: docs/readiness-backend-ux.md §2.3 —
`?category=&q=&moment=&voltage=&spring=` (EAV exact match by Attribute.slug).
"""

from __future__ import annotations

import django_filters
from django.db.models import Q, QuerySet
from rest_framework.request import Request
from rest_framework.views import APIView

from catalog.models import SKU, Attribute

# Reserved query keys — not treated as Attribute.slug filters.
_RESERVED_QUERY_KEYS: frozenset[str] = frozenset(
    {
        "page",
        "page_size",
        "q",
        "category",
        "ordering",
        "format",
        "search",
    },
)


class SKUFilterSet(django_filters.FilterSet):
    """Base filters: category slug + free-text q."""

    category = django_filters.CharFilter(
        field_name="product__category__slug",
        lookup_expr="exact",
    )
    q = django_filters.CharFilter(method="filter_q")

    class Meta:
        model = SKU
        fields = ("category",)

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
        from django.contrib.postgres.search import SearchQuery, SearchRank

        query = SearchQuery(value, config="russian")
        return (
            queryset.filter(Q(search_vector=query) | Q(sku_code__icontains=value))
            .annotate(rank=SearchRank("search_vector", query))
            .order_by("-rank", "sku_code")
        )


class AttributeQueryFilterBackend:
    """Apply `?<attribute_slug>=<value>` as EAV exact filters.

    DRF filter backend (duck-typed): filter_queryset(request, queryset, view).
    """

    def filter_queryset(
        self,
        request: Request,
        queryset: QuerySet[SKU],
        _view: APIView,
    ) -> QuerySet[SKU]:
        """Filter by Attribute.slug query params (exact value match)."""
        candidate_keys = [key for key in request.query_params if key not in _RESERVED_QUERY_KEYS]
        if not candidate_keys:
            return queryset

        attr_slugs = set(
            Attribute.objects.filter(slug__in=candidate_keys).values_list(
                "slug",
                flat=True,
            ),
        )
        for slug in attr_slugs:
            value = request.query_params.get(slug)
            if value is None or value == "":
                continue
            queryset = queryset.filter(
                attribute_values__attribute__slug=slug,
                attribute_values__value=value,
            )
        return queryset.distinct()
