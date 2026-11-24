"""Tests for suggest endpoint: GET /api/search/suggest/?q= (TDD).

Контракт:
- Публичный (AllowAny), read-only (GET).
- `q` короче 2 символов → пустой список.
- Ответ: {results: [{type, title, url}]} без пагинации, лимит 10.
- SKU с кодом-префиксом идут первыми; опечатки и раскладка работают.
- Неопубликованное не попадает в выдачу.
"""

from __future__ import annotations

import pytest


def _seed_suggest_data() -> None:
    """Seed SKUs + content for suggest tests."""
    from catalog.models import SKU, Category, Product
    from content.models import Article

    cat = Category.objects.create(name="Воздушные", slug="vozdushnie-sug")
    prod = Product.objects.create(name="HVA серия", slug="hva-sug", category=cat)
    SKU.objects.create(
        product=prod,
        name="Привод воздушный HVA-5NM",
        slug="privod-hva5-sug",
        sku_code="HVA-5NM-SUG",
        is_published=True,
    )
    SKU.objects.create(
        product=prod,
        name="Привод воздушный HVA-10NM",
        slug="privod-hva10-sug",
        sku_code="HVA-10NM-SUG",
        is_published=True,
    )
    SKU.objects.create(
        product=prod,
        name="Draft привод",
        slug="draft-sug",
        sku_code="DRAFT-SUG",
        is_published=False,
    )
    Article.objects.create(
        title="Как подобрать привод для вентиляции",
        slug="podbor-privoda-sug",
        body="Текст статьи.",
        is_published=True,
    )


@pytest.mark.django_db
def test_suggest_returns_200_and_shape(client) -> None:
    """GET /api/search/suggest/?q= returns 200 with compact item shape."""
    _seed_suggest_data()
    response = client.get("/api/search/suggest/", {"q": "hva"})
    assert response.status_code == 200
    body = response.json()
    assert "results" in body
    assert len(body["results"]) > 0
    for item in body["results"]:
        assert set(item) == {"type", "title", "url"}


@pytest.mark.django_db
def test_suggest_short_query_returns_empty(client) -> None:
    """Queries under 2 chars return an empty list (no DB hits needed)."""
    _seed_suggest_data()
    response = client.get("/api/search/suggest/", {"q": "п"})
    assert response.status_code == 200
    assert response.json()["results"] == []


@pytest.mark.django_db
def test_suggest_code_prefix_ranks_first(client) -> None:
    """sku_code prefix match beats fuzzy hits and lands first."""
    _seed_suggest_data()
    response = client.get("/api/search/suggest/", {"q": "hva-5"})
    body = response.json()
    assert body["results"][0]["type"] == "sku"
    assert "HVA-5NM" in body["results"][0]["title"]


@pytest.mark.django_db
def test_suggest_layout_flip_finds_cyrillic(client) -> None:
    """«ghbdjl» (привод в латинской раскладке) suggests «Привод» SKU."""
    _seed_suggest_data()
    response = client.get("/api/search/suggest/", {"q": "ghbdjl"})
    assert response.status_code == 200
    titles = [item["title"] for item in response.json()["results"]]
    assert any("HVA" in title for title in titles)


@pytest.mark.django_db
def test_suggest_typo_finds_sku(client) -> None:
    """«превод» (typo) still suggests «Привод» SKUs."""
    _seed_suggest_data()
    response = client.get("/api/search/suggest/", {"q": "превод"})
    assert response.status_code == 200
    titles = [item["title"] for item in response.json()["results"]]
    assert any("привод" in title.casefold() for title in titles)


@pytest.mark.django_db
def test_suggest_includes_article_by_title(client) -> None:
    """CMS titles appear in suggestions alongside SKUs."""
    _seed_suggest_data()
    response = client.get("/api/search/suggest/", {"q": "подобрать"})
    assert response.status_code == 200
    types = {item["type"] for item in response.json()["results"]}
    assert "article" in types
    urls = [item["url"] for item in response.json()["results"] if item["type"] == "article"]
    assert "/statyi/podbor-privoda-sug" in urls


@pytest.mark.django_db
def test_suggest_excludes_unpublished(client) -> None:
    """Unpublished SKU never reaches the dropdown."""
    _seed_suggest_data()
    response = client.get("/api/search/suggest/", {"q": "draft"})
    titles = [item["title"] for item in response.json()["results"]]
    assert not any("Draft" in title for title in titles)


@pytest.mark.django_db
def test_suggest_caps_total_results(client) -> None:
    """Total suggestions stay within the compact dropdown cap."""
    from catalog.models import SKU, Category, Product

    _seed_suggest_data()
    cat = Category.objects.create(name="Лимит", slug="limit-sug")
    prod = Product.objects.create(name="Серия", slug="limit-prod-sug", category=cat)
    for idx in range(12):
        SKU.objects.create(
            product=prod,
            name=f"Привод лимитный HVL-{idx}",
            slug=f"privod-limit-sug-{idx}",
            sku_code=f"HVL-{idx:02d}-SUG",
            is_published=True,
        )
    response = client.get("/api/search/suggest/", {"q": "привод"})
    assert response.status_code == 200
    assert len(response.json()["results"]) <= 10


@pytest.mark.django_db
def test_suggest_single_variant_queries_no_500(client) -> None:
    """Queries without a layout counterpart (digits, dashes) must not 500.

    expand_search_variants('100') yields one variant; Greatest() with a
    single expression raised ValueError before the guard was added.
    """
    _seed_suggest_data()
    for q in ("100", "230", "24", "--"):
        response = client.get("/api/search/suggest/", {"q": q})
        assert response.status_code == 200, f"q={q!r} -> {response.status_code}"
        assert "results" in response.json()


@pytest.mark.django_db
def test_suggest_long_query_truncated(client) -> None:
    """Very long q is truncated to the cap, not run raw (linear FTS cost)."""
    _seed_suggest_data()
    response = client.get("/api/search/suggest/", {"q": "hva" + "x" * 6000})
    assert response.status_code == 200
    assert "results" in response.json()


@pytest.mark.django_db
def test_suggest_post_not_allowed(client) -> None:
    """POST /api/search/suggest/ is not allowed (read-only)."""
    response = client.post("/api/search/suggest/", {"q": "test"})
    assert response.status_code == 405


def test_suggest_view_has_own_throttle_scope() -> None:
    """Suggest uses its own bucket, not the shared anon 120/min (review M6)."""
    from search.views import SearchSuggestView

    assert SearchSuggestView.throttle_scope == "search_suggest"
    from django.conf import settings

    assert "search_suggest" in settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]


def test_suggest_throttle_is_scoped_only() -> None:
    """Only the scoped bucket applies: anon/user defaults must not double-count."""
    from rest_framework.throttling import ScopedRateThrottle

    from search.views import SearchSuggestView

    assert SearchSuggestView.throttle_classes == (ScopedRateThrottle,)


@pytest.mark.django_db
def test_suggest_throttle_returns_429_over_scope_limit(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """Scope limit trips on its own rate, independent of the anon rate."""
    from django.core.cache import cache
    from rest_framework.throttling import ScopedRateThrottle

    cache.clear()
    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {"search_suggest": "3/min"},
    )
    statuses = [client.get("/api/search/suggest/", {"q": "hva"}).status_code for _ in range(4)]
    cache.clear()
    assert statuses == [200, 200, 200, 429]
