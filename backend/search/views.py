"""Unified search view: GET /api/search/?q= (SKU + Article + News + Page).

Spec: ПЛАН §6 — глобальный поиск по сайту (Postgres FTS);
docs/readiness-backend-ux.md §2.3 (`GET /api/search/?q=`).

Контракт:
- Публичный (AllowAny); read-only (GET only).
- Параметр `q` — текст запроса; пустой/короткий → пустой список (не 400).
- Ищет по search_vector (FTS) на SKU, Article, News, Page (published).
- Результаты объединяются, ранжируются по релевантности (SearchRank).
- Каждый результат: type, slug, title, url, snippet (канонический path).
- Для SKU title = ``format_sku_heading_name`` (полный ``sku_code``, не
  только семейное имя) — издания в поиске различимы.
- Для SKU snippet = ``extract_sku_lead`` (тот же lead, что под H1 на PDP).
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

from catalog.facets.copy import extract_sku_lead, format_sku_heading_name
from catalog.models import SKU
from catalog.urls_paths import catalog_path_for_sku
from content.etl.tilda_articles import strip_html_to_text
from content.models import Article, News, Page
from search.serializers import SearchResponseSerializer

_SNIPPET_MAX_LEN = 220


def search_title_for_sku(sku: SKU) -> str:
    """Build search result title with unique article (family editions differ).

    Catalog cards collapse by family; search lists each published SKU. Shared
    ``SKU.name`` often starts with the body code only (e.g. ``H8205-LAV2100``),
    so we prefix with ``sku_code`` via the same helper as PDP/list headings.

    Args:
        sku: published SKU row (needs ``name`` and ``sku_code``).

    Returns:
        Display title, e.g. ``H8205-LAV2100-230A | Электрический…``.
    """
    return format_sku_heading_name(
        sku.name or "",
        sku_code=sku.sku_code or "",
    )


def search_snippet_for_sku(sku: SKU) -> str:
    """Short prose under the search title — same lead as on the SKU PDP hero.

    Args:
        sku: published SKU (uses ``description``).

    Returns:
        Application blurb from ``extract_sku_lead``, or empty string.
    """
    return extract_sku_lead(sku.description or "", max_len=_SNIPPET_MAX_LEN)


def _content_snippet(body: str, *, max_len: int = _SNIPPET_MAX_LEN) -> str:
    """First plain sentence(s) from CMS HTML body for the search list.

    Args:
        body: Raw CMS HTML (article / news / page).
        max_len: Soft max length; truncate on a word boundary.

    Returns:
        Plain text without tags, or empty string.
    """
    text = strip_html_to_text(body or "")
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    cut = text[: max_len - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return f"{cut}…"


class SearchView(APIView):
    """GET /api/search/?q=<text> — unified FTS across the whole site.

    Searches published SKUs, Articles, News, and Pages using pre-computed
    `search_vector` fields (Postgres FTS, russian config). PII (Lead) is
    never included.
    """

    permission_classes = (AllowAny,)
    http_method_names = ["get", "head", "options"]
    pagination_class = PageNumberPagination
    serializer_class = SearchResponseSerializer

    def get(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Handle GET: parse `q`, run FTS on all content models, paginate.

        Args:
            request: DRF request with optional `q` query parameter.

        Returns:
            200 with paginated results: {count, next, previous, results}.
            Each result: {type, slug, title, url, snippet}.
        """
        q = (request.query_params.get("q") or "").strip()
        if not q:
            return self._paginated_response(request, [])

        query = SearchQuery(q, config="russian")
        items = self._collect_results(query)
        return self._paginated_response(request, items)

    def _collect_results(self, query: SearchQuery) -> list[dict[str, str]]:
        """Run FTS on SKU, Article, News, Page and merge into a ranked list.

        Args:
            query: pre-built SearchQuery (russian config).

        Returns:
            List of dicts: {type, slug, title, url, snippet}, sorted by rank.
        """
        results: list[dict[str, str | float]] = []

        for sku in self._search_skus(query):
            results.append(
                {
                    "type": "sku",
                    "slug": sku.slug,
                    "title": search_title_for_sku(sku),
                    "url": catalog_path_for_sku(sku),
                    "snippet": search_snippet_for_sku(sku),
                    "rank": float(sku.rank),  # type: ignore[attr-defined]
                },
            )

        for art in self._search_articles(query):
            results.append(
                {
                    "type": "article",
                    "slug": art.slug,
                    "title": art.title,
                    "url": f"/statyi/{art.slug}/",
                    "snippet": _content_snippet(art.body or ""),
                    "rank": float(art.rank),  # type: ignore[attr-defined]
                },
            )

        for news in self._search_news(query):
            results.append(
                {
                    "type": "news",
                    "slug": news.slug,
                    "title": news.title,
                    "url": f"/novosti/{news.slug}/",
                    "snippet": _content_snippet(news.body or ""),
                    "rank": float(news.rank),  # type: ignore[attr-defined]
                },
            )

        for page in self._search_pages(query):
            results.append(
                {
                    "type": "page",
                    "slug": page.slug,
                    "title": page.title,
                    "url": f"/{page.slug}/",
                    "snippet": _content_snippet(page.body or ""),
                    "rank": float(page.rank),  # type: ignore[attr-defined]
                },
            )

        results.sort(key=lambda r: r["rank"], reverse=True)  # type: ignore[arg-type]
        return [
            {
                "type": str(r["type"]),
                "slug": str(r["slug"]),
                "title": str(r["title"]),
                "url": str(r["url"]),
                "snippet": str(r.get("snippet") or ""),
            }
            for r in results
        ]

    @staticmethod
    def _search_skus(query: SearchQuery) -> QuerySet[SKU]:
        """FTS on published SKUs, ranked by SearchRank."""
        return (
            SKU.objects.filter(is_published=True, search_vector=query)
            .select_related("product__category")
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

    @staticmethod
    def _search_pages(query: SearchQuery) -> QuerySet[Page]:
        """FTS on published CMS pages, ranked by SearchRank."""
        return (
            Page.objects.filter(is_published=True, search_vector=query)
            .annotate(rank=SearchRank("search_vector", query))
            .order_by("-rank", "slug")
        )

    def _paginated_response(
        self,
        request: Request,
        items: Sequence[dict[str, str]],
    ) -> Response:
        """Apply DRF pagination to the merged list and return a Response.

        Args:
            request: DRF request (for pagination context).
            items: merged, ranked list of result dicts.

        Returns:
            DRF Response with paginated structure {count, next, previous, results}.
        """
        paginator = self.pagination_class()
        page: list[dict[str, str]] | None = paginator.paginate_queryset(  # type: ignore[assignment]
            list(items),  # type: ignore[arg-type]
            request,
            view=self,
        )
        if page is not None:
            return paginator.get_paginated_response(page)
        return Response({"results": list(items)})
