"""Serializers for the search API (drf-spectacular schema + response shape).

Spec: ПЛАН §6 — GET /api/search/?q=; docs/readiness-backend-ux.md §2.3.
"""

from __future__ import annotations

from rest_framework import serializers


class SearchResultItemSerializer(serializers.Serializer):
    """One item in the unified search results list."""

    type = serializers.CharField(help_text="Тип результата: sku | article | news.")
    slug = serializers.CharField(help_text="Slug (path-сегмент) найденной записи.")
    title = serializers.CharField(help_text="Заголовок (H1) найденной записи.")
    url = serializers.CharField(help_text="Канонический path (напр. /<slug>/, /statyi/<slug>/).")


class SearchResponseSerializer(serializers.Serializer):
    """Paginated search response (DRF PageNumberPagination shape)."""

    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = SearchResultItemSerializer(many=True)
