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
        """icontains search on name / sku_code / slug (FTS — Iter 2)."""
        if not value:
            return queryset
        return queryset.filter(
            Q(name__icontains=value) | Q(sku_code__icontains=value) | Q(slug__icontains=value),
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
