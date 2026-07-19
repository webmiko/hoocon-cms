"""URL routes for public catalog API."""

from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from catalog.views import CategoryViewSet, SKUViewSet

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="catalog-category")
router.register("skus", SKUViewSet, basename="catalog-sku")

urlpatterns = [
    path("", include(router.urls)),
]
