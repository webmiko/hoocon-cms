"""Tests for public content API: Page / Article / News (TDD).

Spec: ПЛАН §6 Iter 3–4 — content API (GET only, published only);
docs/readiness-backend-ux.md §2.3.
"""

from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_page_list_returns_published_only(client) -> None:
    """GET /api/content/pages/ returns published pages only."""
    from content.models import Page

    Page.objects.create(title="Pub", slug="pub-page", body="x", is_published=True)
    Page.objects.create(title="Draft", slug="draft-page", body="", is_published=False)
    response = client.get("/api/content/pages/")
    assert response.status_code == 200
    body = response.json()
    slugs = [p["slug"] for p in body["results"]]
    assert "pub-page" in slugs
    assert "draft-page" not in slugs


@pytest.mark.django_db
def test_page_detail_by_slug(client) -> None:
    """GET /api/content/pages/{slug}/ returns page detail."""
    from content.models import Page

    Page.objects.create(
        title="О компании",
        slug="o-kompanii",
        body="<p>Hoocon — приводы ОВК.</p>",
        is_published=True,
    )
    response = client.get("/api/content/pages/o-kompanii/")
    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == "o-kompanii"
    assert data["title"] == "О компании"
    assert "Hoocon" in data["body"]


@pytest.mark.django_db
def test_page_detail_unpublished_returns_404(client) -> None:
    """Unpublished page returns 404."""
    from content.models import Page

    Page.objects.create(title="Draft", slug="draft", body="", is_published=False)
    response = client.get("/api/content/pages/draft/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_article_list_returns_published_only(client) -> None:
    """GET /api/content/articles/ returns published articles only."""
    from content.models import Article

    Article.objects.create(title="A1", slug="a1", body="x", is_published=True)
    Article.objects.create(title="A2", slug="a2", body="", is_published=False)
    response = client.get("/api/content/articles/")
    slugs = [a["slug"] for a in response.json()["results"]]
    assert "a1" in slugs
    assert "a2" not in slugs


@pytest.mark.django_db
def test_article_detail_by_slug(client) -> None:
    """GET /api/content/articles/{slug}/ returns article detail."""
    from content.models import Article

    Article.objects.create(
        title="Гайд",
        slug="gayd",
        body="<p>Текст гайда.</p>",
        excerpt="Краткий анонс",
        is_published=True,
    )
    response = client.get("/api/content/articles/gayd/")
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Гайд"
    assert data["excerpt"] == "Краткий анонс"
    assert "cover" in data
    assert "related_skus" in data
    assert data["related_skus"] == []


@pytest.mark.django_db
def test_news_list_returns_published_only(client) -> None:
    """GET /api/content/news/ returns published news only."""
    from content.models import News

    News.objects.create(title="N1", slug="n1", body="x", is_published=True)
    News.objects.create(title="N2", slug="n2", body="", is_published=False)
    response = client.get("/api/content/news/")
    slugs = [n["slug"] for n in response.json()["results"]]
    assert "n1" in slugs
    assert "n2" not in slugs


@pytest.mark.django_db
def test_news_detail_by_slug(client) -> None:
    """GET /api/content/news/{slug}/ returns news detail."""
    from content.models import News

    News.objects.create(
        title="Анонс",
        slug="anons",
        body="<p>Текст анонса.</p>",
        is_published=True,
    )
    response = client.get("/api/content/news/anons/")
    assert response.status_code == 200
    assert response.json()["title"] == "Анонс"


@pytest.mark.django_db
def test_content_api_post_not_allowed(client) -> None:
    """POST to content API is not allowed (read-only)."""
    response = client.post("/api/content/pages/", data={"title": "X"}, content_type="application/json")
    assert response.status_code == 405
