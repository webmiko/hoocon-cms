"""URL routes for public content API.

Spec: ПЛАН §6 Iter 3–4; docs/readiness-backend-ux.md §2.3.
"""

from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from content.views import ArticleViewSet, NewsViewSet, PageViewSet

router = DefaultRouter()
router.register(r"pages", PageViewSet, basename="page")
router.register(r"articles", ArticleViewSet, basename="article")
router.register(r"news", NewsViewSet, basename="news")

urlpatterns = [
    path("", include(router.urls)),
]
