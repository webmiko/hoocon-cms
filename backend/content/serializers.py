"""DRF serializers for public content API (Page / Article / News).

Spec: ПЛАН §6 Iter 3–4; docs/readiness-backend-ux.md §2.3.
Public read-only; body is HTML from CMS (frontend escapes — no
dangerouslySetInnerHTML on user HTML; see security-baseline §3.6).
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from content.models import Article, News, Page
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


class ArticleListSerializer(_ContentSerializer):
    """Article card for /statyi list (no related SKUs)."""

    cover = serializers.ImageField(read_only=True, allow_null=True)

    class Meta(_ContentSerializer.Meta):
        model = Article
        fields = (
            "id",
            "title",
            "slug",
            "excerpt",
            "cover",
            "body",
            "is_published",
            "published_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ArticleRelatedSkuSerializer(serializers.Serializer):
    """Compact SKU card embedded in an article detail response."""

    name = serializers.CharField()
    slug = serializers.CharField()
    sku_code = serializers.CharField()
    image = serializers.SerializerMethodField()

    def get_image(self, obj: Any) -> str | None:
        """Primary published image URL, if any."""
        images = getattr(obj, "_prefetched_images", None)
        if images is None:
            images = list(
                obj.images.filter(is_published=True).order_by("sort_order", "id")[:1],
            )
        if not images:
            return None
        request = self.context.get("request")
        url = images[0].image.url
        if request is not None:
            return request.build_absolute_uri(url)
        return url


class ArticleSerializer(ArticleListSerializer):
    """Article detail: list fields + SKUs mentioned in the text."""

    related_skus = serializers.SerializerMethodField()

    class Meta(ArticleListSerializer.Meta):
        fields = (*ArticleListSerializer.Meta.fields, "related_skus")
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


class NewsSerializer(_ContentSerializer):
    """Company news item (/novosti/<slug>)."""

    cover = serializers.ImageField(read_only=True, allow_null=True)

    class Meta(_ContentSerializer.Meta):
        model = News
        fields = (
            "id",
            "title",
            "slug",
            "body",
            "cover",
            "is_published",
            "published_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
