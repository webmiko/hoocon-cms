"""Public read-only content API: Page / Article / News (list + detail).

Spec: ПЛАН §6 Iter 3–4; docs/readiness-backend-ux.md §2.3.
GET only (AllowAny); published items only (respects future published_at).
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q, QuerySet
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny

from content.models import Article, News, NewsCategory, Page
from content.serializers import (
    ArticleListSerializer,
    ArticleSerializer,
    NewsCategorySerializer,
    NewsSerializer,
    PageSerializer,
)


def publicly_visible(model: type[models.Model]) -> QuerySet:
    """``is_published``; hide future ``published_at`` unless preview flag.

    Local QA: set ``CONTENT_SHOW_SCHEDULED=True`` (see ``.env.example``) to
    preview staggered articles/news before go-live. Prod keeps the flag off.
    """
    from django.conf import settings

    qs = model._default_manager.filter(is_published=True)
    if getattr(settings, "CONTENT_SHOW_SCHEDULED", False):
        return qs
    now = timezone.now()
    return qs.filter(Q(published_at__isnull=True) | Q(published_at__lte=now))


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
        qs = self.queryset
        assert qs is not None
        model = qs.model
        return publicly_visible(model).order_by(
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
    """GET /api/content/news/ and /api/content/news/{slug}/.

    Query params (list):
      category — NewsCategory.slug
      ordering — ``newest`` (default) | ``oldest``
    """

    serializer_class = NewsSerializer
    queryset = News.objects.none()

    def get_queryset(self) -> QuerySet:
        """Published news with optional category filter and date ordering."""
        qs = publicly_visible(News).select_related("category")
        category = (self.request.query_params.get("category") or "").strip()
        if category:
            qs = qs.filter(
                category__slug=category,
                category__is_published=True,
            )
        ordering = (self.request.query_params.get("ordering") or "newest").strip()
        if ordering == "oldest":
            return qs.order_by("published_at", "created_at")
        return qs.order_by("-published_at", "-created_at")


class NewsCategoryViewSet(
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """GET /api/content/news-categories/ — published rubrics for chips."""

    permission_classes = (AllowAny,)
    http_method_names = ["get", "head", "options"]
    serializer_class = NewsCategorySerializer
    pagination_class = None
    queryset = NewsCategory.objects.none()

    def get_queryset(self) -> QuerySet:
        """Published categories ordered for the filter bar."""
        return NewsCategory.objects.filter(is_published=True).order_by(
            "sort_order",
            "name",
        )
