"""Tests for unified search endpoint: GET /api/search/?q= (TDD).

Spec: ПЛАН §6 — глобальный поиск по каталогу и статьям (Postgres FTS);
docs/readiness-backend-ux.md §2.3 (`GET /api/search/?q=`).

Контракт:
- GET /api/search/?q=<текст> — публичный (AllowAny).
- Возвращает результаты по трём типам: sku, article, news.
- Использует search_vector (FTS) на каждой модели; ранжирование по релевантности.
- Пагинация стандартная (PageNumberPagination, PAGE_SIZE=20).
- Пустой или короткий запрос → пустой список (не 400).
- Нет результатов → 200 с пустым списком (не 404).
- PII не утекает (в поиске нет заявок/Lead).
"""

from __future__ import annotations

import pytest

# ── Helpers ──────────────────────────────────────────────────────────


def _seed_search_data():
    """Seed SKU + Article + News + Page for search tests."""
    from catalog.models import SKU, Category, Product
    from content.models import Article, News, Page

    cat = Category.objects.create(name="Воздушные", slug="vozdushnie-s")
    prod = Product.objects.create(name="HVA серия", slug="hva-s", category=cat)

    SKU.objects.create(
        product=prod,
        name="Привод воздушный HVA-5NM",
        slug="privod-vozdushniy-hva-5nm-s",
        sku_code="HVA-5NM-S",
        is_published=True,
    )
    SKU.objects.create(
        product=prod,
        name="Привод воздушный HVA-10NM",
        slug="privod-vozdushniy-hva-10nm-s",
        sku_code="HVA-10NM-S",
        is_published=True,
    )
    # Unpublished SKU must NOT appear in search.
    SKU.objects.create(
        product=prod,
        name="Draft привод",
        slug="draft-privod-s",
        sku_code="DRAFT-S",
        is_published=False,
    )

    Article.objects.create(
        title="Как подобрать электропривод для вентиляции",
        slug="kak-podobrat-elektroprivod-s",
        body="Гайд по подбору привода по моменту и напряжению.",
        is_published=True,
    )
    # Unpublished article must NOT appear.
    Article.objects.create(
        title="Черновик статьи про привод",
        slug="draft-statya-s",
        body="",
        is_published=False,
    )

    News.objects.create(
        title="Анонс нового привода HVA",
        slug="anons-novogo-privoda-s",
        body="Компания Hoocon расширяет линейку приводов.",
        is_published=True,
    )

    Page.objects.create(
        title="О компании Hoocon",
        slug="o-kompanii",
        body="Производство электроприводов ОВК, склад в Москве.",
        is_published=True,
    )
    Page.objects.create(
        title="Скрытая страница",
        slug="hidden-page",
        body="Не должна попасть в поиск.",
        is_published=False,
    )


# ── Endpoint basic ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_search_returns_200(client) -> None:
    """GET /api/search/?q= returns 200."""
    _seed_search_data()
    response = client.get("/api/search/", {"q": "привод"})
    assert response.status_code == 200


@pytest.mark.django_db
def test_search_response_has_results_structure(client) -> None:
    """Response has a `results` list (DRF pagination convention)."""
    _seed_search_data()
    response = client.get("/api/search/", {"q": "привод"})
    body = response.json()
    # DRF PageNumberPagination returns {count, next, previous, results}.
    assert "results" in body
    assert isinstance(body["results"], list)


# ── Search across types ──────────────────────────────────────────────


@pytest.mark.django_db
def test_search_finds_skus(client) -> None:
    """Search finds published SKUs by name."""
    _seed_search_data()
    response = client.get("/api/search/", {"q": "привод"})
    body = response.json()
    types = {r.get("type") for r in body["results"]}
    assert "sku" in types
    sku_results = [r for r in body["results"] if r.get("type") == "sku"]
    assert len(sku_results) >= 2  # HVA-5NM and HVA-10NM


@pytest.mark.django_db
def test_search_finds_articles(client) -> None:
    """Search finds published Articles by title/body."""
    _seed_search_data()
    response = client.get("/api/search/", {"q": "электропривод"})
    body = response.json()
    types = {r.get("type") for r in body["results"]}
    assert "article" in types


@pytest.mark.django_db
def test_search_finds_news(client) -> None:
    """Search finds published News by title/body."""
    _seed_search_data()
    response = client.get("/api/search/", {"q": "анонс"})
    body = response.json()
    types = {r.get("type") for r in body["results"]}
    assert "news" in types


@pytest.mark.django_db
def test_search_finds_pages(client) -> None:
    """Search finds published CMS pages by title/body."""
    _seed_search_data()
    response = client.get("/api/search/", {"q": "компании"})
    body = response.json()
    types = {r.get("type") for r in body["results"]}
    assert "page" in types
    page_urls = [r["url"] for r in body["results"] if r.get("type") == "page"]
    assert "/o-kompanii/" in page_urls


@pytest.mark.django_db
def test_search_combines_all_types(client) -> None:
    """Search for 'привод' returns sku + article + news (all match)."""
    _seed_search_data()
    response = client.get("/api/search/", {"q": "привод"})
    body = response.json()
    types = {r.get("type") for r in body["results"]}
    assert "sku" in types
    assert "article" in types
    assert "news" in types


# ── Excludes unpublished ──────────────────────────────────────────────


@pytest.mark.django_db
def test_search_excludes_unpublished_sku(client) -> None:
    """Unpublished SKU does NOT appear in search results."""
    _seed_search_data()
    response = client.get("/api/search/", {"q": "draft"})
    body = response.json()
    slugs = [r.get("slug") for r in body["results"]]
    assert "draft-privod-s" not in slugs


@pytest.mark.django_db
def test_search_excludes_unpublished_article(client) -> None:
    """Unpublished Article does NOT appear in search results."""
    _seed_search_data()
    response = client.get("/api/search/", {"q": "черновик"})
    body = response.json()
    titles = [r.get("title", "").lower() for r in body["results"]]
    assert not any("черновик" in t for t in titles)


@pytest.mark.django_db
def test_search_excludes_unpublished_page(client) -> None:
    """Unpublished Page does NOT appear in search results."""
    _seed_search_data()
    response = client.get("/api/search/", {"q": "скрытая"})
    body = response.json()
    slugs = [r.get("slug") for r in body["results"] if r.get("type") == "page"]
    assert "hidden-page" not in slugs
    body = response.json()
    slugs = [r.get("slug") for r in body["results"]]
    assert "draft-statya-s" not in slugs


# ── Edge cases ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_search_empty_q_returns_empty_results(client) -> None:
    """Empty q returns 200 with empty results (not 400)."""
    _seed_search_data()
    response = client.get("/api/search/", {"q": ""})
    assert response.status_code == 200
    body = response.json()
    assert body["results"] == []


@pytest.mark.django_db
def test_search_no_match_returns_empty_results(client) -> None:
    """Query with no matches returns 200 with empty results (not 404)."""
    _seed_search_data()
    response = client.get("/api/search/", {"q": "несуществующий-термин-xyz"})
    assert response.status_code == 200
    body = response.json()
    assert body["results"] == []


@pytest.mark.django_db
def test_search_missing_q_param_returns_empty(client) -> None:
    """Missing q param returns 200 with empty results."""
    _seed_search_data()
    response = client.get("/api/search/")
    assert response.status_code == 200
    body = response.json()
    assert body["results"] == []


# ── Result item structure ─────────────────────────────────────────────


@pytest.mark.django_db
def test_search_result_item_has_required_fields(client) -> None:
    """Each result item has type, slug, title, and url."""
    _seed_search_data()
    response = client.get("/api/search/", {"q": "привод"})
    body = response.json()
    assert len(body["results"]) > 0
    for item in body["results"]:
        assert "type" in item
        assert "slug" in item
        assert "title" in item
        assert "url" in item


@pytest.mark.django_db
def test_search_result_url_is_canonical_path(client) -> None:
    """Result URL is the canonical path (sku: /<slug>, article: /statyi/<slug>, news: /novosti/<slug>)."""
    _seed_search_data()
    response = client.get("/api/search/", {"q": "привод"})
    body = response.json()
    for item in body["results"]:
        if item["type"] == "sku":
            assert item["url"].startswith("/") and "/statyi/" not in item["url"] and "/novosti/" not in item["url"]
        elif item["type"] == "article":
            assert "/statyi/" in item["url"]
        elif item["type"] == "news":
            assert "/novosti/" in item["url"]


# ── Read-only / method ────────────────────────────────────────────────


@pytest.mark.django_db
def test_search_post_not_allowed(client) -> None:
    """POST /api/search/ is not allowed (read-only)."""
    response = client.post("/api/search/", {"q": "test"})
    assert response.status_code == 405


# ── PII: no leads in search ────────────────────────────────────────────


@pytest.mark.django_db
def test_search_does_not_leak_leads(client) -> None:
    """Search results never include Lead type (PII protection)."""
    from leads.models import Lead

    Lead.objects.create(
        name="Иван",
        email="secret@example.com",
        message="привод привод привод привод привод",
    )
    _seed_search_data()
    response = client.get("/api/search/", {"q": "привод"})
    body = response.json()
    types = {r.get("type") for r in body["results"]}
    assert "lead" not in types
    # No PII in any result.
    for item in body["results"]:
        assert "email" not in item
        assert "phone" not in item
