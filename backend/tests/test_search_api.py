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
def test_search_hides_future_published_at_articles(client) -> None:
    """Search must not return articles with published_at in the future."""
    from datetime import timedelta

    from django.contrib.postgres.search import SearchVector
    from django.utils import timezone

    from content.models import Article

    future = timezone.now() + timedelta(days=5)
    art = Article.objects.create(
        title="Будущий гайд по заслонкам XYZUNIQ",
        slug="future-guide",
        body="<p>Будущий гайд по заслонкам XYZUNIQ</p>",
        is_published=True,
        published_at=future,
    )
    Article.objects.filter(pk=art.pk).update(
        search_vector=SearchVector("title", "body", config="russian"),
    )
    response = client.get("/api/search/", {"q": "XYZUNIQ"})
    slugs = [r["slug"] for r in response.json()["results"] if r.get("type") == "article"]
    assert "future-guide" not in slugs


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
    assert "/o-kompanii" in page_urls
    assert "/o-kompanii/" not in page_urls


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
    """Each result item has type, slug, title, url, and snippet."""
    _seed_search_data()
    response = client.get("/api/search/", {"q": "привод"})
    body = response.json()
    assert len(body["results"]) > 0
    for item in body["results"]:
        assert "type" in item
        assert "slug" in item
        assert "title" in item
        assert "url" in item
        assert "snippet" in item
        assert isinstance(item["snippet"], str)


@pytest.mark.django_db
def test_search_result_url_is_canonical_path(client) -> None:
    """Result URL is nested catalog path for SKU; articles/news keep prefixes."""
    _seed_search_data()
    response = client.get("/api/search/", {"q": "привод"})
    body = response.json()
    for item in body["results"]:
        assert not item["url"].endswith("/") or item["url"] == "/"
        if item["type"] == "sku":
            assert item["url"].startswith("/catalog/")
            assert item["url"].count("/") >= 3
            assert "/catalog/catalog/" not in item["url"]
        elif item["type"] == "article":
            assert item["url"].startswith("/statyi/")
            assert item["url"] == f"/statyi/{item['slug']}"
        elif item["type"] == "news":
            assert item["url"].startswith("/novosti/")
            assert item["url"] == f"/novosti/{item['slug']}"


def test_search_title_for_sku_uses_full_article_code() -> None:
    """Family-shared name must still show full sku_code in search title."""
    from catalog.models import SKU
    from search.views import search_title_for_sku

    sku = SKU(
        name="H8205-LAV2100 | Электрический регулирующий клапан 2-ходовый DN 100",
        sku_code="H8205-LAV2100-230A",
        slug="h8205-lav2100-230a",
    )
    title = search_title_for_sku(sku)
    assert title.startswith("H8205-LAV2100-230A")
    assert "H8205-LAV2100 |" not in title.split("|")[0]
    assert "клапан" in title.casefold()


def test_search_snippet_for_sku_uses_pdp_lead() -> None:
    """Search snippet matches the short lead shown under the PDP H1."""
    from catalog.models import SKU
    from search.views import search_snippet_for_sku

    sku = SKU(
        name="H8205-LAV2100-230A | Клапан",
        sku_code="H8205-LAV2100-230A",
        slug="h8205-lav2100-230a-snip",
        description=(
            "H8205-LAV2100 | Электрический регулирующий клапан.\n"
            "Используется для регулирования потока тепло-/хладоносителя "
            "в системах отопления и вентиляции зданий."
        ),
    )
    snippet = search_snippet_for_sku(sku)
    assert "используется" in snippet.casefold()
    assert len(snippet) >= 40


def test_content_snippet_strips_html_markup() -> None:
    """CMS bodies are HTML; search snippets must be plain text only."""
    from search.views import _content_snippet

    raw = '<h2>Как работает вентиляция</h2> <p class="dash-note">Цифры по метро — <strong>ориентиры</strong>.</p>'
    snippet = _content_snippet(raw)
    assert "<" not in snippet
    assert ">" not in snippet
    assert "Как работает вентиляция" in snippet
    assert "ориентиры" in snippet
    assert "dash-note" not in snippet


@pytest.mark.django_db
def test_search_sku_title_includes_edition_code(client) -> None:
    """Search lists each SKU with edition code, not only shared family name."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="Комплекты", slug="komplekty-search-ed")
    prod = Product.objects.create(
        name="H8205-LAV2100",
        slug="h8205-lav2100-search-ed",
        category=cat,
    )
    shared = "H8205-LAV2100 | Электрический регулирующий клапан 2-ходовый DN 100"
    SKU.objects.create(
        product=prod,
        name=shared,
        slug="h8205-lav2100-230a-search-ed",
        sku_code="H8205-LAV2100-230A",
        is_published=True,
    )
    SKU.objects.create(
        product=prod,
        name=shared,
        slug="h8205-lav2100-24a-search-ed",
        sku_code="H8205-LAV2100-24A",
        is_published=True,
    )

    response = client.get("/api/search/", {"q": "H8205-LAV2100"})
    body = response.json()
    sku_titles = [r["title"] for r in body["results"] if r.get("type") == "sku"]
    assert any(t.startswith("H8205-LAV2100-230A") for t in sku_titles)
    assert any(t.startswith("H8205-LAV2100-24A") for t in sku_titles)
    # Shared body-only prefix without edition must not be the sole left side.
    left_sides = [t.split("|", 1)[0].strip() for t in sku_titles]
    assert "H8205-LAV2100" not in left_sides


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
