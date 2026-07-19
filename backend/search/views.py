"""Unified search view: GET /api/search/?q= (SKU + Article + News).

Spec: ПЛАН §6 — глобальный поиск по каталогу и статьям (Postgres FTS);
docs/readiness-backend-ux.md §2.3 (`GET /api/search/?q=`).

Контракт:
- Публичный (AllowAny); read-only (GET only).
- Параметр `q` — текст запроса; пустой/короткий → пустой список (не 400).
- Ищет по search_vector (FTS) на SKU (published), Article (published), News (published).
- Результаты объединяются, ранжируются по релевантности (SearchRank).
- Каждый результат: type, slug, title, url (канонический path).
- PII: Lead НЕ участвует в поиске; никаких email/phone в выдаче.
- Пагинация стандартная (DRF PageNumberPagination).
"""

from __future__ import annotations

from collections.abc import Sequence

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import QuerySet
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import SKU
from content.models import Article, News


class SearchView(APIView):
    """GET /api/search/?q=<text> — unified FTS search across catalog + content.

    Searches published SKUs, Articles, and News using their pre-computed
    `search_vector` fields (Postgres FTS with russian config). Returns a
    combined, ranked list. PII (Lead) is never included.
    """

    permission_classes = (AllowAny,)
    http_method_names = ["get", "head", "options"]
    pagination_class = PageNumberPagination

    def get(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Handle GET: parse `q`, run FTS on all three models, return paginated.

        Args:
            request: DRF request with optional `q` query parameter.

        Returns:
            200 with paginated results: {count, next, previous, results}.
            Each result: {type, slug, title, url}.
        """
        q = (request.query_params.get("q") or "").strip()
        if not q:
            return self._paginated_response(request, [])

        query = SearchQuery(q, config="russian")
        items = self._collect_results(query)
        return self._paginated_response(request, items)

    def _collect_results(self, query: SearchQuery) -> list[dict[str, str]]:
        """Run FTS on SKU, Article, News and merge into a ranked list.

        Args:
            query: pre-built SearchQuery (russian config).

        Returns:
            List of dicts: {type, slug, title, url, rank}, sorted by rank desc.
        """
        results: list[dict[str, str | float]] = []

        # SKU: published only; canonical URL = /<slug>.
        for sku in self._search_skus(query):
            results.append(
                {
                    "type": "sku",
                    "slug": sku.slug,
                    "title": sku.name,
                    "url": f"/{sku.slug}/",
                    "rank": float(sku.rank),  # type: ignore[attr-defined]
                },
            )

        # Article: published only; canonical URL = /statyi/<slug>.
        for art in self._search_articles(query):
            results.append(
                {
                    "type": "article",
                    "slug": art.slug,
                    "title": art.title,
                    "url": f"/statyi/{art.slug}/",
                    "rank": float(art.rank),  # type: ignore[attr-defined]
                },
            )

        # News: published only; canonical URL = /novosti/<slug>.
        for news in self._search_news(query):
            results.append(
                {
                    "type": "news",
                    "slug": news.slug,
                    "title": news.title,
                    "url": f"/novosti/{news.slug}/",
                    "rank": float(news.rank),  # type: ignore[attr-defined]
                },
            )

        # Sort by rank descending (most relevant first).
        results.sort(key=lambda r: r["rank"], reverse=True)  # type: ignore[arg-type]
        # Drop rank from the output (internal only).
        return [
            {"type": str(r["type"]), "slug": str(r["slug"]), "title": str(r["title"]), "url": str(r["url"])}
            for r in results
        ]

    @staticmethod
    def _search_skus(query: SearchQuery) -> QuerySet[SKU]:
        """FTS on published SKUs, ranked by SearchRank."""
        return (
            SKU.objects.filter(is_published=True, search_vector=query)
            .annotate(rank=SearchRank("search_vector", query))
            .order_by("-rank", "sku_code")
        )

    @staticmethod
    def _search_articles(query: SearchQuery) -> QuerySet[Article]:
        """FTS on published Articles, ranked by SearchRank."""
        return (
            Article.objects.filter(is_published=True, search_vector=query)
            .annotate(rank=SearchRank("search_vector", query))
            .order_by("-rank", "slug")
        )

    @staticmethod
    def _search_news(query: SearchQuery) -> QuerySet[News]:
        """FTS on published News, ranked by SearchRank."""
        return (
            News.objects.filter(is_published=True, search_vector=query)
            .annotate(rank=SearchRank("search_vector", query))
            .order_by("-rank", "slug")
        )

    def _paginated_response(self, request: Request, items: Sequence[dict[str, str]]) -> Response:
        """Apply DRF pagination to the merged list and return a Response.

        Args:
            request: DRF request (for pagination context).
            items: merged, ranked list of result dicts.

        Returns:
            DRF Response with paginated structure {count, next, previous, results}.
        """
        paginator = self.pagination_class()
        # DRF paginate_queryset accepts a sequence; stubs type it as QuerySet,
        # but it works with plain lists (our merged cross-model results).
        page: list[dict[str, str]] | None = paginator.paginate_queryset(  # type: ignore[assignment]
            list(items),  # type: ignore[arg-type]
            request,
            view=self,
        )
        if page is not None:
            return paginator.get_paginated_response(page)
        return Response({"results": list(items)})
