"""Public read-only content API: Page / Article / News (list + detail).

Spec: ПЛАН §6 Iter 3–4; docs/readiness-backend-ux.md §2.3.
GET only (AllowAny); published items only.
"""

from __future__ import annotations

from django.db.models import QuerySet
from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny

from content.models import Article, News, Page
from content.serializers import (
    ArticleListSerializer,
    ArticleSerializer,
    NewsSerializer,
    PageSerializer,
)


class _ContentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Shared config for Page / Article / News viewsets (DRY)."""

    permission_classes = (AllowAny,)
    lookup_field = "slug"
    http_method_names = ["get", "head", "options"]

    def get_queryset(self) -> QuerySet:
        """Published items only, ordered by published_at desc."""
        model = self.queryset.model
        return model.objects.filter(is_published=True).order_by(
            "-published_at",
            "-created_at",
        )


class PageViewSet(_ContentViewSet):
    """GET /api/content/pages/ and /api/content/pages/{slug}/."""

    serializer_class = PageSerializer
    queryset = Page.objects.none()


class ArticleViewSet(_ContentViewSet):
    """GET /api/content/articles/ and /api/content/articles/{slug}/."""

    queryset = Article.objects.none()

    def get_serializer_class(self) -> type:
        """List stays light; detail includes related_skus."""
        if self.action == "retrieve":
            return ArticleSerializer
        return ArticleListSerializer


class NewsViewSet(_ContentViewSet):
    """GET /api/content/news/ and /api/content/news/{slug}/."""

    serializer_class = NewsSerializer
    queryset = News.objects.none()
