"""Public read-only catalog API views + staff ProductFile upload.

Spec: docs/readiness-backend-ux.md §2.3; security — AllowAny GET only,
prices gated in serializers via SiteSettings. ProductFile upload is
staff-only (IsAdminUser).
"""

from __future__ import annotations

from typing import cast

from django.db.models import Count, Prefetch, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response

from catalog.compare import (
    COMPARE_MAX_SKUS,
    build_compare_response,
    parse_compare_slugs,
    resolve_compare_skus,
)
from catalog.facets import collect_facet_options
from catalog.filters import AttributeQueryFilterBackend, SKUFilterSet
from catalog.models import SKU, AttributeValue, Category, Product, ProductFile, ProductImage
from catalog.ordering import annotate_moment_nm, catalog_list_order_by
from catalog.serializers import (
    CategorySerializer,
    SKUDetailSerializer,
    SKUListSerializer,
)
from catalog.series_categories import spec_order_case
from catalog.upload_serializers import ProductFileUploadSerializer

# Representative SKU photos for homepage / category tiles (slug → sku_code).
CATEGORY_PREVIEW_SKU_CODES: dict[str, str] = {
    "sharovye-krany": "8100-bv240a",  # DN 40 2-way — clearer than first DN 15
}


def preview_images_by_category(category_ids: list[int]) -> dict[int, ProductImage]:
    """Return one published ProductImage per category id.

    Prefers ``CATEGORY_PREVIEW_SKU_CODES`` when that SKU has a published photo;
    otherwise the first image by sort_order / id.

    Args:
        category_ids: Category primary keys to resolve.

    Returns:
        Mapping category_id → ProductImage (one photo each, if any).
    """
    if not category_ids:
        return {}

    result: dict[int, ProductImage] = {}
    slug_by_id = dict(
        Category.objects.filter(pk__in=category_ids).values_list("pk", "slug"),
    )
    preferred_codes = [
        CATEGORY_PREVIEW_SKU_CODES[slug] for slug in slug_by_id.values() if slug in CATEGORY_PREVIEW_SKU_CODES
    ]
    if preferred_codes:
        preferred_imgs = (
            ProductImage.objects.filter(
                is_published=True,
                sku__is_published=True,
                sku__sku_code__in=preferred_codes,
                sku__product__category_id__in=category_ids,
            )
            .select_related("sku__product__category")
            .order_by("sku__sku_code", "sort_order", "id")
        )
        by_code: dict[str, ProductImage] = {}
        for img in preferred_imgs:
            code = cast(SKU, img.sku).sku_code
            if code not in by_code:
                by_code[code] = img
        for cat_id, slug in slug_by_id.items():
            code = CATEGORY_PREVIEW_SKU_CODES.get(slug)
            if code and code in by_code:
                result[cat_id] = by_code[code]

    images = (
        ProductImage.objects.filter(
            is_published=True,
            sku__is_published=True,
            sku__product__category_id__in=category_ids,
        )
        .select_related("sku__product")
        .order_by("sku__product__category_id", "sort_order", "id")
    )
    for img in images:
        product = cast(Product, cast(SKU, img.sku).product)
        cat_id = product.category_id
        if cat_id not in result:
            result[cat_id] = img
    return result


class CategoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """GET /api/catalog/categories/ — specification categories with products."""

    permission_classes = (AllowAny,)
    serializer_class = CategorySerializer
    http_method_names = ["get", "head", "options"]

    def get_queryset(self) -> QuerySet[Category]:
        """Return non-empty categories in series-table order."""
        return (
            Category.objects.annotate(product_count=Count("products"))
            .filter(product_count__gt=0)
            .annotate(spec_order=spec_order_case())
            .order_by("spec_order", "name")
        )

    def list(self, request: Request, *args: object, **kwargs: object) -> Response:
        """List categories with a product preview image per row."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        cats = list(page) if page is not None else list(queryset)
        context = self.get_serializer_context()
        context["preview_images"] = preview_images_by_category([c.pk for c in cats])
        serializer = self.get_serializer(cats, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class FacetViewSet(viewsets.ViewSet):
    """GET /api/catalog/facets/ — ТТХ filter options with counts.

    Optional ``?category=<slug>`` scopes value counts to that category.
    """

    permission_classes = (AllowAny,)
    http_method_names = ["get", "head", "options"]

    def list(self, request: Request) -> Response:
        """Return canonical facets for the catalog filter UI."""
        qs = SKU.objects.filter(is_published=True)
        category = request.query_params.get("category", "").strip()
        if category:
            qs = qs.filter(product__category__slug=category)
        return Response({"results": collect_facet_options(base_queryset=qs)})


class CompareViewSet(viewsets.ViewSet):
    """GET /api/catalog/compare/?skus=slug-a,slug-b — side-by-side ТТХ.

    Spec: docs/plan-compare-sku.md (max 4, free mix of categories).
    """

    permission_classes = (AllowAny,)
    http_method_names = ["get", "head", "options"]

    def list(self, request: Request) -> Response:
        """Return SKU columns and highlight matrix rows."""
        raw = request.query_params.get("skus", "")
        slugs = parse_compare_slugs(raw)
        if len(slugs) > COMPARE_MAX_SKUS:
            return Response(
                {
                    "detail": (f"Не больше {COMPARE_MAX_SKUS} моделей в сравнении."),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not slugs:
            return Response({"skus": [], "rows": []})

        skus, missing = resolve_compare_skus(slugs)
        if missing:
            return Response(
                {
                    "detail": "Неизвестные или неопубликованные SKU.",
                    "missing": missing,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = build_compare_response(
            skus,
            serializer_context={"request": request},
        )
        return Response(payload)


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
        """Published SKUs only; prefetch ТТХ/files/images for cards and detail."""
        published_images = Prefetch(
            "images",
            queryset=ProductImage.objects.filter(is_published=True).order_by(
                "sort_order",
                "id",
            ),
            to_attr="_prefetched_images",
        )
        published_attrs = Prefetch(
            "attribute_values",
            queryset=AttributeValue.objects.select_related("attribute"),
            to_attr="_prefetched_attribute_values",
        )
        qs = annotate_moment_nm(
            SKU.objects.filter(is_published=True)
            .select_related("product", "product__category")
            .prefetch_related(published_images, published_attrs)
            .annotate(
                category_spec_order=spec_order_case(
                    slug_field="product__category__slug",
                ),
            ),
        ).order_by(*catalog_list_order_by())
        if self.action == "retrieve":
            qs = qs.prefetch_related(
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
