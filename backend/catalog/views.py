"""Public read-only catalog API views.

Spec: docs/readiness-backend-ux.md §2.3; security — AllowAny GET only,
prices gated in serializers via SiteSettings.
"""

from __future__ import annotations

from django.db.models import Prefetch, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny

from catalog.filters import AttributeQueryFilterBackend, SKUFilterSet
from catalog.models import SKU, AttributeValue, Category, ProductFile
from catalog.serializers import (
    CategorySerializer,
    SKUDetailSerializer,
    SKUListSerializer,
)


class CategoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """GET /api/catalog/categories/ — public category list."""

    permission_classes = (AllowAny,)
    serializer_class = CategorySerializer
    queryset = Category.objects.all().order_by("name")
    http_method_names = ["get", "head", "options"]


class SKUViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """GET /api/catalog/skus/ and /api/catalog/skus/{slug}/."""

    permission_classes = (AllowAny,)
    lookup_field = "slug"
    filter_backends = (DjangoFilterBackend, AttributeQueryFilterBackend)
    filterset_class = SKUFilterSet
    http_method_names = ["get", "head", "options"]

    def get_queryset(self) -> QuerySet[SKU]:
        """Published SKUs only; prefetch ТТХ/files for detail."""
        qs = SKU.objects.filter(is_published=True).select_related("product", "product__category").order_by("sku_code")
        if self.action == "retrieve":
            qs = qs.prefetch_related(
                Prefetch(
                    "attribute_values",
                    queryset=AttributeValue.objects.select_related("attribute"),
                ),
                Prefetch(
                    "files",
                    queryset=ProductFile.objects.filter(is_published=True),
                ),
            )
        return qs

    def get_serializer_class(self) -> type[SKUListSerializer]:
        """List vs detail serializer."""
        if self.action == "retrieve":
            return SKUDetailSerializer
        return SKUListSerializer
