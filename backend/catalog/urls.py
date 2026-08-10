"""URL routes for public catalog API + ProductFile upload."""

from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from catalog.views import (
    CategoryViewSet,
    CompareViewSet,
    FacetViewSet,
    ProductFileViewSet,
    SKUViewSet,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="catalog-category")
router.register("facets", FacetViewSet, basename="catalog-facet")
router.register("compare", CompareViewSet, basename="catalog-compare")
router.register("skus", SKUViewSet, basename="catalog-sku")

# Nested route for ProductFile upload under a SKU.
sku_files = ProductFileViewSet.as_view({"get": "list", "post": "create"})

urlpatterns = [
    path(
        "skus/<str:sku_slug>/files/",
        sku_files,
        name="catalog-sku-file-list",
    ),
    path("", include(router.urls)),
]
