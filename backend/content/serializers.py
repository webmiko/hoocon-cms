"""DRF serializers for public content API (Page / Article / News).

Spec: ПЛАН §6 Iter 3–4; docs/readiness-backend-ux.md §2.3.
Public read-only; body is HTML from CMS (frontend escapes — no
dangerouslySetInnerHTML on user HTML; see security-baseline §3.6).
"""

from __future__ import annotations

import re
from typing import Any

from rest_framework import serializers

from catalog.media_urls import RelativeImageField, to_media_path
from content.models import Article, News, NewsCategory, Page
from content.related_skus import mentioned_skus_for_article


class _ContentSerializer(serializers.ModelSerializer):
    """Shared fields for Page / Article / News (DRY)."""

    class Meta:
        fields = (
            "id",
            "title",
            "slug",
            "body",
            "is_published",
            "published_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class PageSerializer(_ContentSerializer):
    """Public CMS page (/<slug>)."""

    class Meta(_ContentSerializer.Meta):
        model = Page


_WORDS_PER_MINUTE = 180
_TAG_RE = re.compile(r"<[^>]+>")


def article_reading_minutes(excerpt: str, body: str) -> int:
    """Same rule as the /statyi card: under 40 words → 0, else ≥1 minute."""
    words = len(_TAG_RE.sub(" ", f"{excerpt or ''} {body or ''}").split())
    if words < 40:
        return 0
    return max(1, int(words / _WORDS_PER_MINUTE + 0.5))


class ArticleListSerializer(_ContentSerializer):
    """Article card for /statyi list: no body, only the reading time."""

    cover = RelativeImageField(read_only=True, allow_null=True)
    cover_dark = RelativeImageField(read_only=True, allow_null=True)
    reading_minutes = serializers.SerializerMethodField()

    class Meta(_ContentSerializer.Meta):
        model = Article
        fields = (
            "id",
            "title",
            "slug",
            "excerpt",
            "cover",
            "cover_dark",
            "reading_minutes",
            "is_published",
            "published_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_reading_minutes(self, obj: Article) -> int:
        """Minutes to read; the list does not ship the full HTML body."""
        return article_reading_minutes(obj.excerpt, obj.body)


class ArticleRelatedSkuSerializer(serializers.Serializer):
    """Compact SKU card embedded in an article detail response."""

    name = serializers.CharField()
    slug = serializers.CharField()
    sku_code = serializers.CharField()
    category_slug = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    def get_category_slug(self, obj: Any) -> str:
        """Category path segment for nested catalog URLs."""
        product = getattr(obj, "product", None)
        category = getattr(product, "category", None) if product is not None else None
        return getattr(category, "slug", None) or ""

    def get_image(self, obj: Any) -> str | None:
        """Primary published image path (root-relative ``/media/...``)."""
        images = getattr(obj, "_prefetched_images", None)
        if images is None:
            images = list(
                obj.images.filter(is_published=True).order_by("sort_order", "id")[:1],
            )
        if not images:
            return None
        return to_media_path(images[0].image.url)


class ArticleSerializer(ArticleListSerializer):
    """Article detail: list fields + SKUs mentioned in the text."""

    related_skus = serializers.SerializerMethodField()

    class Meta(ArticleListSerializer.Meta):
        fields = (*ArticleListSerializer.Meta.fields, "body", "related_skus")
        read_only_fields = fields

    def get_related_skus(self, obj: Article) -> list[dict[str, Any]]:
        """Return catalog cards for models referenced in the article."""
        blob = f"{obj.title}\n{obj.excerpt}\n{obj.body}"
        skus = mentioned_skus_for_article(blob, limit=8)
        return ArticleRelatedSkuSerializer(
            skus,
            many=True,
            context=self.context,
        ).data


class NewsCategoryBriefSerializer(serializers.Serializer):
    """Nested category payload on a news card ({slug, name})."""

    slug = serializers.CharField()
    name = serializers.CharField()


class NewsCategorySerializer(serializers.ModelSerializer):
    """Published news rubric for /novosti filter chips."""

    class Meta:
        model = NewsCategory
        fields = ("id", "name", "slug", "sort_order")
        read_only_fields = fields


class NewsSerializer(_ContentSerializer):
    """Company news item (/novosti/<slug>)."""

    cover = RelativeImageField(read_only=True, allow_null=True)
    category = NewsCategoryBriefSerializer(read_only=True, allow_null=True)

    class Meta(_ContentSerializer.Meta):
        model = News
        fields = (
            "id",
            "title",
            "slug",
            "body",
            "cover",
            "category",
            "is_published",
            "published_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
