"""Public read-only catalog API views + staff ProductFile upload.

Spec: docs/readiness-backend-ux.md §2.3; security — AllowAny GET only,
prices gated in serializers via SiteSettings. ProductFile upload is
staff-only (IsAdminUser).
"""

from __future__ import annotations

from django.db.models import Prefetch, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response

from catalog.filters import AttributeQueryFilterBackend, SKUFilterSet
from catalog.models import SKU, AttributeValue, Category, ProductFile
from catalog.serializers import (
    CategorySerializer,
    SKUDetailSerializer,
    SKUListSerializer,
)
from catalog.upload_serializers import ProductFileUploadSerializer


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


class ProductFileViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """GET (public) + POST (staff) /api/catalog/skus/{sku_slug}/files/."""

    serializer_class = ProductFileUploadSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self) -> list:
        """GET is public (AllowAny); POST requires staff (IsAdminUser)."""
        if self.action == "create":
            return [IsAdminUser()]
        return [AllowAny()]

    def get_queryset(self) -> QuerySet[ProductFile]:
        """Published files for the SKU identified by sku_slug."""
        sku_slug = self.kwargs.get("sku_slug")
        qs = ProductFile.objects.filter(is_published=True).select_related("sku")
        if sku_slug:
            qs = qs.filter(sku__slug=sku_slug)
        return qs.order_by("sort_order", "title")

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Upload a PDF to the SKU identified by sku_slug in the URL."""
        sku_slug = kwargs.get("sku_slug")
        try:
            sku = SKU.objects.get(slug=sku_slug)
        except SKU.DoesNotExist:
            return Response(
                {"detail": "SKU not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product_file = serializer.save(sku=sku)
        return Response(
            ProductFileUploadSerializer(
                product_file,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_201_CREATED,
        )
