"""Unified search views: GET /api/search/ and /api/search/suggest/.

Spec: ПЛАН §6 — глобальный поиск по сайту (Postgres FTS);
docs/readiness-backend-ux.md §2.3 (`GET /api/search/?q=`).

Smart layer (2026-11): every query is expanded into variants — the raw
text plus the keyboard-layout flip («вф-100» → «da-100», «ghbdjl» →
«привод», see ``catalog.search_intent.expand_search_variants``). Each
variant is scored on two signals:

- FTS rank on ``search_vector`` (russian config, stems Cyrillic);
- trigram ``word_similarity`` on name/title/sku_code — tolerates typos
  («превод» → «привод») that FTS stemming rejects.

Hybrid score keeps semantics simple: any FTS hit scores above 1.0;
trigram-only rows cap at ``_TRGM_ONLY_CAP``; a ``sku_code`` substring
match (partial article) sits at ``_CODE_SUBSTRING_SCORE``.

Контракт /api/search/:
- Публичный (AllowAny); read-only (GET only).
- Параметр `q` — текст запроса; пустой/короткий → пустой список (не 400).
- Результаты объединяются, ранжируются по релевантности (score).
- Каждый результат: type, slug, title, url, snippet (канонический path).
- Для SKU title = ``format_sku_heading_name`` (полный ``sku_code``, не
  только семейное имя) — издания в поиске различимы.
- Для SKU snippet = ``extract_sku_lead`` (тот же lead, что под H1 на PDP).
- ``corrected_query`` — перевернутая раскладка, когда она нашла заметно
  лучше исходного запроса (did-you-mean для фронта).
- PII: Lead НЕ участвует в поиске; никаких email/phone в выдаче.
- Пагинация стандартная (``config.pagination.DefaultPagination``).

/api/search/suggest/ — компактная выдача для дропдауна в шапке:
``{results: [{type, title, url}]}``, без пагинации, лимит
``_SUGGEST_LIMIT``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from django.contrib.postgres.search import (
    SearchQuery,
    SearchRank,
    TrigramSimilarity,
    TrigramWordSimilarity,
)
from django.db.models import BooleanField, Case, F, Q, Value, When
from django.db.models.functions import Greatest
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from catalog.facets.copy import extract_sku_lead, format_sku_heading_name
from catalog.models import SKU
from catalog.search_intent import (
    SEARCH_Q_MAX_LEN,
    TRGM_WORD_THRESHOLD,
    expand_search_variants,
)
from catalog.urls_paths import catalog_path_for_sku
from config.pagination import DefaultPagination
from content.etl.tilda_articles import strip_html_to_text
from content.models import Article, News, Page
from content.views import publicly_visible
from search.serializers import (
    SearchResponseSerializer,
    SearchSuggestResponseSerializer,
)

_SNIPPET_MAX_LEN = 220
# Cap each FTS source before Python merge/sort (audit: RAM/CPU on broad queries).
_SEARCH_PER_SOURCE_LIMIT = 50

# FTS hit base — always above trigram-only scores (< 1.0).
_FTS_HIT_BASE = 1.0
# Trigram-only score ceiling (below any real FTS hit).
_TRGM_ONLY_CAP = 0.45
# Small extra weight when a row has both FTS and trigram signal.
_TRGM_FTS_BONUS = 0.25
# sku_code substring match («lav210» in «H8205-LAV2100-230A») — strong
# intent, outranks plain FTS hits.
_CODE_SUBSTRING_SCORE = 1.5
# When the layout-flipped variant wins while the original produced at most
# this many hits, report it as ``corrected_query`` (did-you-mean).
_CORRECTED_MAX_ORIG_HITS = 2

# Suggest dropdown: short prefixes only, compact payload.
_SUGGEST_MIN_LEN = 2
_SUGGEST_SKU_LIMIT = 6
_SUGGEST_CONTENT_LIMIT = 4
_SUGGEST_LIMIT = 10


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


def _variant_score(*, rank: float, sim: float, substring_hit: bool) -> float:
    """Score one row for one query variant.

    FTS hits start at ``_FTS_HIT_BASE`` (+rank +small trgm bonus);
    trigram-only rows cap at ``_TRGM_ONLY_CAP``; a substring match on
    ``sku_code``/title is treated as strong intent.

    Args:
        rank: ``ts_rank`` for this variant (0 when no FTS match).
        sim: trigram ``word_similarity`` for this variant (0–1).
        substring_hit: raw variant is a substring of sku_code/title.

    Returns:
        Comparable score; higher wins.
    """
    score = sim * _TRGM_ONLY_CAP
    if rank > 0:
        score = _FTS_HIT_BASE + rank + sim * _TRGM_FTS_BONUS
    if substring_hit:
        score = max(score, _CODE_SUBSTRING_SCORE)
    return score


class SearchView(APIView):
    """GET /api/search/?q=<text> — unified FTS across the whole site.

    Searches published SKUs, Articles, News, and Pages using pre-computed
    `search_vector` fields (Postgres FTS, russian config) with trigram
    typo tolerance and keyboard-layout correction. PII (Lead) is never
    included.
    """

    permission_classes = (AllowAny,)
    http_method_names = ["get", "head", "options"]
    pagination_class = DefaultPagination
    serializer_class = SearchResponseSerializer

    def get(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Handle GET: parse `q`, run hybrid search on all models, paginate.

        Args:
            request: DRF request with optional `q` query parameter.

        Returns:
            200 with paginated results: {count, next, previous, results,
            corrected_query}. Each result: {type, slug, title, url, snippet}.
        """
        q = (request.query_params.get("q") or "").strip()[:SEARCH_Q_MAX_LEN]
        if not q:
            return self._paginated_response(request, [], corrected=None)

        items, corrected = self._collect_results(q)
        return self._paginated_response(request, items, corrected=corrected)

    def _collect_results(
        self,
        raw_q: str,
    ) -> tuple[list[dict[str, str]], str | None]:
        """Run hybrid search on SKU, Article, News, Page; merge + rank.

        Args:
            raw_q: user search text (may trigger kit intent for SKUs).

        Returns:
            (items, corrected_query): items sorted by score desc;
            corrected_query is the layout-flipped variant when it clearly
            outperformed the original text (else None).
        """
        variants = expand_search_variants(raw_q)
        if not variants:
            return [], None

        rows: list[dict[str, Any]] = []
        rows += self._sku_rows(variants)
        rows += self._content_rows(
            Article,
            variants,
            kind="article",
            url_for=lambda obj: f"/statyi/{obj.slug}",
        )
        rows += self._content_rows(
            News,
            variants,
            kind="news",
            url_for=lambda obj: f"/novosti/{obj.slug}",
        )
        rows += self._content_rows(
            Page,
            variants,
            kind="page",
            url_for=lambda obj: f"/{obj.slug}",
        )

        orig_hits = sum(1 for row in rows if row["orig_hit"])
        flip_won = any(row["flip_hit"] for row in rows)
        corrected = variants[1] if len(variants) > 1 and flip_won and orig_hits <= _CORRECTED_MAX_ORIG_HITS else None

        rows.sort(key=lambda row: float(row["score"]), reverse=True)
        items = [
            {
                "type": str(row["type"]),
                "slug": str(row["slug"]),
                "title": str(row["title"]),
                "url": str(row["url"]),
                "snippet": str(row["snippet"]),
            }
            for row in rows
        ]
        return items, corrected

    # ── Row builders ────────────────────────────────────────────────

    @staticmethod
    def _sku_row(
        sku: SKU,
        *,
        score: float,
        orig_hit: bool,
        flip_hit: bool,
    ) -> dict[str, Any]:
        """Result dict for one SKU with scoring internals attached."""
        return {
            "type": "sku",
            "slug": sku.slug,
            "title": search_title_for_sku(sku),
            "url": catalog_path_for_sku(sku),
            "snippet": search_snippet_for_sku(sku),
            "score": score,
            "orig_hit": orig_hit,
            "flip_hit": flip_hit,
        }

    @staticmethod
    def _content_row(
        obj: Article | News | Page,
        *,
        kind: str,
        url: str,
        score: float,
        orig_hit: bool,
        flip_hit: bool,
    ) -> dict[str, Any]:
        """Result dict for one CMS object with scoring internals attached."""
        return {
            "type": kind,
            "slug": obj.slug,
            "title": obj.title,
            "url": url,
            "snippet": _content_snippet(obj.body or ""),
            "score": score,
            "orig_hit": orig_hit,
            "flip_hit": flip_hit,
        }

    @staticmethod
    def _best_variant_scores(
        obj: object,
        variants: tuple[str, ...],
        *,
        substring_field: str,
    ) -> tuple[float, bool, bool]:
        """Per-variant scores for an annotated row + correction flags.

        Args:
            obj: row annotated with ``rank_{i}`` / ``sim_{i}`` per variant.
            variants: query variants in order (index 0 = original).
            substring_field: field checked for a raw substring match
                (``sku_code`` for SKU, ``title`` for CMS objects).

        Returns:
            (best_score, orig_hit, flip_hit): best variant score; whether
            the original variant scored at all; whether the flipped
            variant produced the winning score.
        """
        haystack = (getattr(obj, substring_field, "") or "").casefold()
        scores = []
        orig_hit = False
        for idx, variant in enumerate(variants):
            rank = float(getattr(obj, f"rank_{idx}", 0.0) or 0.0)
            sim = float(getattr(obj, f"sim_{idx}", 0.0) or 0.0)
            substring_hit = bool(haystack) and variant.casefold() in haystack
            scores.append(
                _variant_score(
                    rank=rank,
                    sim=sim,
                    substring_hit=substring_hit,
                )
            )
            if idx == 0:
                # Only a real match counts (FTS ``@@`` or substring). Trigram
                # similarity is excluded: a wrong-layout string («рмф») shares
                # stray trigrams with unrelated titles, and counting those
                # kept ``corrected_query`` from ever firing on short queries.
                orig_hit = bool(getattr(obj, "ftshit_0", False)) or substring_hit
        best = max(scores)
        flip_hit = len(variants) > 1 and scores.index(best) == 1
        return best, orig_hit, flip_hit

    @staticmethod
    def _variant_annotations(
        variants: tuple[str, ...],
        *,
        sim_fields: tuple[str, ...],
    ) -> tuple[dict[str, Any], Q]:
        """Per-variant ``rank_{i}``/``sim_{i}`` annotations + match Q.

        Args:
            variants: query variants.
            sim_fields: fields fed to ``TrigramWordSimilarity``.

        Returns:
            (annotations, matched_q): dict for ``.annotate()`` and the OR
            of FTS/substring/trigram-operator conditions.
        """
        annotations: dict[str, Any] = {}
        matched = Q()
        for idx, variant in enumerate(variants):
            query = SearchQuery(variant, config="russian")
            matched |= Q(search_vector=query)
            # Boolean @@ match flag per variant — ts_rank alone is unreliable
            # (returns ~1e-20 even on non-matching rows) so rank>0 cannot
            # serve as the hit signal for corrected_query gating.
            annotations[f"ftshit_{idx}"] = Case(
                When(search_vector=query, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
            annotations[f"rank_{idx}"] = SearchRank("search_vector", query)
            sim_exprs = [TrigramWordSimilarity(variant, field) for field in sim_fields]
            annotations[f"sim_{idx}"] = Greatest(*sim_exprs) if len(sim_exprs) > 1 else sim_exprs[0]
        return annotations, matched

    @staticmethod
    def _trigram_hit_q(variants_count: int) -> Q:
        """OR condition on ``sim_{i}`` annotations above threshold."""
        trigram_hit = Q()
        for idx in range(variants_count):
            trigram_hit |= Q(**{f"sim_{idx}__gt": TRGM_WORD_THRESHOLD})
        return trigram_hit

    @staticmethod
    def _best_signal_order(variants_count: int) -> Any:
        """SQL-side pre-sort so the per-source cap keeps top candidates."""
        signals = [F(f"rank_{idx}") for idx in range(variants_count)]
        signals += [F(f"sim_{idx}") for idx in range(variants_count)]
        return Greatest(*signals).desc()

    # ── Per-source queries ──────────────────────────────────────────

    def _sku_rows(self, variants: tuple[str, ...]) -> list[dict[str, Any]]:
        """Scored SKU rows: kit intent, FTS, code substring, trigrams."""
        from catalog.search_intent import resolve_catalog_search_intent

        intent = resolve_catalog_search_intent(variants[0])
        qs = SKU.objects.filter(is_published=True).select_related("product__category")
        if intent.category_slug:
            qs = qs.filter(product__category__slug=intent.category_slug)
            if not intent.residual:
                # Pure kit phrase — keep kits above generic FTS hits
                # (score > _FTS_HIT_BASE + typical rank).
                return [
                    self._sku_row(sku, score=_FTS_HIT_BASE + 1.0, orig_hit=True, flip_hit=False)
                    for sku in qs.order_by("sku_code")[:_SEARCH_PER_SOURCE_LIMIT]
                ]
            variants = expand_search_variants(intent.residual) or (intent.residual,)

        # Kit-residual (DN, code) narrows strictly — «dn65» must not blur
        # into «dn15»; trigram fuzz stays off on the intent path.
        strict_residual = bool(intent.category_slug)

        annotations, matched = self._variant_annotations(
            variants,
            sim_fields=("name", "sku_code"),
        )
        for variant in variants:
            matched |= Q(sku_code__icontains=variant)
            if not strict_residual:
                matched |= Q(sku_code__trigram_similar=variant)
            matched |= Q(analog_belimo_code__icontains=variant)
        trigram_hit = Q()
        if not strict_residual:
            trigram_hit = self._trigram_hit_q(len(variants))
        qs = (
            qs.annotate(**annotations)
            .filter(matched | trigram_hit)
            .order_by(self._best_signal_order(len(variants)), "sku_code")
        )
        rows = []
        for sku in qs[:_SEARCH_PER_SOURCE_LIMIT]:
            score, orig_hit, flip_hit = self._best_variant_scores(
                sku,
                variants,
                substring_field="sku_code",
            )
            rows.append(
                self._sku_row(sku, score=score, orig_hit=orig_hit, flip_hit=flip_hit),
            )
        return rows

    def _content_rows(
        self,
        model: type[Article] | type[News] | type[Page],
        variants: tuple[str, ...],
        *,
        kind: str,
        url_for: Any,
    ) -> list[dict[str, Any]]:
        """Scored rows for one CMS model (title trgm + FTS + substring)."""
        qs = publicly_visible(model)
        annotations, matched = self._variant_annotations(
            variants,
            sim_fields=("title",),
        )
        for variant in variants:
            matched |= Q(title__icontains=variant)
        qs = (
            qs.annotate(**annotations)
            .filter(matched | self._trigram_hit_q(len(variants)))
            .order_by(self._best_signal_order(len(variants)), "slug")
        )
        rows = []
        for obj in qs[:_SEARCH_PER_SOURCE_LIMIT]:
            score, orig_hit, flip_hit = self._best_variant_scores(
                obj,
                variants,
                substring_field="title",
            )
            rows.append(
                self._content_row(
                    obj,
                    kind=kind,
                    url=url_for(obj),
                    score=score,
                    orig_hit=orig_hit,
                    flip_hit=flip_hit,
                )
            )
        return rows

    # ── Response ────────────────────────────────────────────────────

    def _paginated_response(
        self,
        request: Request,
        items: Sequence[dict[str, str]],
        *,
        corrected: str | None,
    ) -> Response:
        """Apply DRF pagination to the merged list and return a Response.

        Args:
            request: DRF request (for pagination context).
            items: merged, ranked list of result dicts.
            corrected: layout-flipped did-you-mean query (or None).

        Returns:
            DRF Response with paginated structure {count, next, previous,
            results, corrected_query}.
        """
        paginator = self.pagination_class()
        page: list[dict[str, str]] | None = paginator.paginate_queryset(  # type: ignore[assignment]
            list(items),  # type: ignore[arg-type]
            request,
            view=self,
        )
        if page is not None:
            response = paginator.get_paginated_response(page)
            response.data["corrected_query"] = corrected
            return response
        return Response({"results": list(items), "corrected_query": corrected})


class SearchSuggestView(APIView):
    """GET /api/search/suggest/?q=<text> — dropdown suggestions.

    Compact payload ({type, title, url}) for the header search box: SKU
    codes first (prefix > substring > trigram), then CMS titles. Same
    layout-flip expansion as the main search. No pagination; capped at
    ``_SUGGEST_LIMIT``.
    """

    permission_classes = (AllowAny,)
    http_method_names = ["get", "head", "options"]
    serializer_class = SearchSuggestResponseSerializer
    # Per-keystroke calls: own bucket so shared-office IPs don't burn
    # the anon budget used by catalog/forms (review M6). Explicit class list:
    # the global defaults also include Anon/UserRateThrottle, which would
    # keep counting every keystroke against the shared 120/min bucket.
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "search_suggest"

    def get(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Handle GET: return up to ``_SUGGEST_LIMIT`` compact items.

        Args:
            request: DRF request with optional `q` query parameter.

        Returns:
            200 with {"results": [{type, title, url}]} — empty list for
            queries shorter than ``_SUGGEST_MIN_LEN``.
        """
        q = (request.query_params.get("q") or "").strip()[:SEARCH_Q_MAX_LEN]
        if len(q) < _SUGGEST_MIN_LEN:
            return Response({"results": [], "corrected_query": None})

        variants = expand_search_variants(q)
        items = self._suggest_skus(variants)[:_SUGGEST_SKU_LIMIT]
        items += self._suggest_content(variants)[:_SUGGEST_CONTENT_LIMIT]
        items.sort(key=lambda item: float(item["score"]), reverse=True)
        # Did-you-mean: the layout-flipped text matched real titles/codes
        # while the raw text matched none (substring, not trigram noise).
        corrected = None
        if len(variants) > 1 and any(i["flip_hit"] for i in items) and not any(i["orig_hit"] for i in items):
            corrected = variants[1]
        return Response(
            {
                "results": [{"type": i["type"], "title": i["title"], "url": i["url"]} for i in items[:_SUGGEST_LIMIT]],
                "corrected_query": corrected,
            },
        )

    def _suggest_skus(self, variants: tuple[str, ...]) -> list[dict[str, Any]]:
        """Top SKU suggestions: code prefix/substring beats similarity."""
        matched = Q()
        for variant in variants:
            matched |= Q(sku_code__icontains=variant) | Q(name__icontains=variant)
        # Greatest() needs ≥2 args; a digits-only query yields one variant.
        sim_exprs = [
            Greatest(
                TrigramWordSimilarity(variant, "name"),
                TrigramSimilarity("sku_code", variant),
            )
            for variant in variants
        ]
        qs = (
            SKU.objects.filter(is_published=True)
            .select_related("product__category")
            .annotate(sim=Greatest(*sim_exprs) if len(sim_exprs) > 1 else sim_exprs[0])
            .filter(matched | Q(sim__gt=TRGM_WORD_THRESHOLD))
            .order_by("-sim", "sku_code")
        )
        items: list[dict[str, Any]] = []
        for sku in qs[: _SUGGEST_SKU_LIMIT * 2]:
            score = float(getattr(sku, "sim", 0.0) or 0.0)
            code = (sku.sku_code or "").casefold()
            name = (sku.name or "").casefold()
            hits = [False] * len(variants)
            for idx, variant in enumerate(variants):
                needle = variant.casefold()
                if code.startswith(needle):
                    score = max(score, 3.0)
                    hits[idx] = True
                elif needle in code:
                    score = max(score, 2.0)
                    hits[idx] = True
                elif needle in name:
                    score = max(score, 1.2)
                    hits[idx] = True
            items.append(
                {
                    "type": "sku",
                    "title": search_title_for_sku(sku),
                    "url": catalog_path_for_sku(sku),
                    "score": score,
                    "orig_hit": hits[0],
                    "flip_hit": len(hits) > 1 and hits[1],
                },
            )
        items.sort(key=lambda item: float(item["score"]), reverse=True)
        return items[:_SUGGEST_SKU_LIMIT]

    def _suggest_content(self, variants: tuple[str, ...]) -> list[dict[str, Any]]:
        """Top CMS suggestions by title substring / word similarity."""
        items: list[dict[str, Any]] = []
        for model, kind, url_for in (
            (Article, "article", lambda obj: f"/statyi/{obj.slug}"),
            (News, "news", lambda obj: f"/novosti/{obj.slug}"),
            (Page, "page", lambda obj: f"/{obj.slug}"),
        ):
            matched = Q()
            for variant in variants:
                matched |= Q(title__icontains=variant)
            sim_exprs = [TrigramWordSimilarity(variant, "title") for variant in variants]
            qs = (
                publicly_visible(model)
                .annotate(sim=Greatest(*sim_exprs) if len(sim_exprs) > 1 else sim_exprs[0])
                .filter(matched | Q(sim__gt=TRGM_WORD_THRESHOLD))
                .order_by("-sim", "slug")
            )
            for obj in qs[:_SUGGEST_CONTENT_LIMIT]:
                score = float(getattr(obj, "sim", 0.0) or 0.0)
                title = (obj.title or "").casefold()
                hits = [variant.casefold() in title for variant in variants]
                if any(hits):
                    score = max(score, 1.2)
                items.append(
                    {
                        "type": kind,
                        "title": obj.title,
                        "url": url_for(obj),
                        "score": score,
                        "orig_hit": hits[0],
                        "flip_hit": len(hits) > 1 and hits[1],
                    },
                )
        items.sort(key=lambda item: float(item["score"]), reverse=True)
        return items[:_SUGGEST_CONTENT_LIMIT]
