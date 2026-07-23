"""Tests for spa_index_view + SEO head (БЗ SEO-индексация-SPA.md)."""

from __future__ import annotations

import pytest
from django.test import override_settings


@pytest.fixture(autouse=True)
def _spa_index_settings() -> None:
    """Clear SPA index cache around spa SEO tests (path set in conftest)."""
    from config.seo.spa_index import clear_index_html_cache

    clear_index_html_cache()
    yield
    clear_index_html_cache()


@pytest.mark.django_db
def test_spa_home_has_unique_title_and_canonical(client) -> None:
    """GET / returns HTML with title + canonical for home."""
    response = client.get("/")
    assert response.status_code == 200
    body = response.content.decode()
    assert "<title>" in body
    assert 'rel="canonical" href="https://hoocon.ru/"' in body
    assert "application/ld+json" in body
    assert "Organization" in body


@pytest.mark.django_db
def test_spa_search_is_noindex(client) -> None:
    """GET /search has robots noindex."""
    response = client.get("/search")
    assert response.status_code == 200
    body = response.content.decode()
    assert 'name="robots" content="noindex, nofollow"' in body


@pytest.mark.django_db
def test_spa_sku_injects_product_json_ld(client) -> None:
    """Published SKU URL gets Product JSON-LD without leaking price."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="Воздушные", slug="vozdushnie-seo")
    prod = Product.objects.create(name="HVA", slug="hva-seo", category=cat)
    SKU.objects.create(
        product=prod,
        name="HVA 5NM",
        slug="privod-hva-5nm-seo",
        sku_code="HVA-5NM-SEO",
        price="1234.00",
        is_published=True,
    )
    response = client.get("/catalog/vozdushnie-seo/privod-hva-5nm-seo")
    assert response.status_code == 200
    body = response.content.decode()
    assert "Product" in body
    assert "HVA-5NM-SEO" in body
    assert "1234" not in body  # prices gated
    assert 'rel="canonical" href="https://hoocon.ru/catalog/vozdushnie-seo/privod-hva-5nm-seo"' in body


@pytest.mark.django_db
def test_spa_article_json_ld(client) -> None:
    """Published article gets Article JSON-LD."""
    from django.utils import timezone

    from content.models import Article

    Article.objects.create(
        title="Подбор момента",
        slug="podbor-momenta-seo",
        body="<p>Текст статьи о моменте.</p>",
        excerpt="Краткий анонс.",
        is_published=True,
        published_at=timezone.now(),
    )
    response = client.get("/statyi/podbor-momenta-seo")
    assert response.status_code == 200
    body = response.content.decode()
    assert "Article" in body
    assert "Подбор момента" in body


def test_llms_txt(client) -> None:
    """GET /llms.txt returns llmstxt.org-shaped plain text summary."""
    response = client.get("/llms.txt")
    assert response.status_code == 200
    body = response.content.decode()
    assert "Hoocon" in body
    assert "/catalog" in body
    assert "/llms-full.txt" in body


def test_llm_txt_alias(client) -> None:
    """GET /llm.txt mirrors /llms.txt."""
    response = client.get("/llm.txt")
    assert response.status_code == 200
    assert "Hoocon" in response.content.decode()


def test_llms_full_txt(client) -> None:
    """GET /llms-full.txt returns expanded LLM context."""
    response = client.get("/llms-full.txt")
    assert response.status_code == 200
    body = response.content.decode()
    assert "полный контекст" in body
    assert "protivopozharniy" in body


@override_settings(SITE_URL="https://hoocon.ru")
def test_normalize_strips_trailing_slash() -> None:
    """Canonical paths never keep a trailing slash."""
    from config.seo.sanitize import normalize_spa_path

    assert normalize_spa_path("/catalog/") == "/catalog"
    assert normalize_spa_path("/") == "/"
