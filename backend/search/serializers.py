"""Serializers for the search API (drf-spectacular schema + response shape).

Spec: ПЛАН §6 — GET /api/search/?q=; docs/readiness-backend-ux.md §2.3.
"""

from __future__ import annotations

from rest_framework import serializers


class SearchResultItemSerializer(serializers.Serializer):
    """One item in the unified search results list."""

    type = serializers.CharField(
        help_text="Тип результата: sku | article | news | page.",
    )
    slug = serializers.CharField(help_text="Slug (path-сегмент) найденной записи.")
    title = serializers.CharField(help_text="Заголовок (H1) найденной записи.")
    url = serializers.CharField(help_text="Канонический path (напр. /<slug>/, /statyi/<slug>/).")
    snippet = serializers.CharField(
        allow_blank=True,
        help_text="Краткое описание (для SKU — lead с PDP; для CMS — начало body).",
    )


class SearchResponseSerializer(serializers.Serializer):
    """Paginated search response (DRF PageNumberPagination shape)."""

    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = SearchResultItemSerializer(many=True)
    corrected_query = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="Перевернутая раскладка запроса (did-you-mean), если она нашла лучше.",
    )


class SearchSuggestItemSerializer(serializers.Serializer):
    """One compact item in the suggest dropdown payload."""

    type = serializers.CharField(
        help_text="Тип результата: sku | article | news | page.",
    )
    title = serializers.CharField(help_text="Заголовок (для SKU — с артикулом).")
    url = serializers.CharField(help_text="Канонический path результата.")


class SearchSuggestResponseSerializer(serializers.Serializer):
    """Suggest dropdown payload — no pagination, capped list."""

    results = SearchSuggestItemSerializer(many=True)
    corrected_query = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="Перевернутая раскладка запроса (did-you-mean), если нашла совпадения, а исходный текст — нет.",
    )
