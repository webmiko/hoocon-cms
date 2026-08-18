"""Tests for sitemap.xml + robots.txt (TDD: red → green → refactor).

Spec: ПЛАН §6 Iter 2 — sitemap.xml generator (only canonical paths, no
/tproduct/, no query filters); robots.txt (Disallow /tilda/, /admin/).
docs/seo-url-migration.md (canonical URLs only).
"""

from __future__ import annotations

import pytest


def _seed_for_sitemap():
    """Seed categories + products + SKUs for sitemap tests."""
    from catalog.models import SKU, Category, Product

    cat1 = Category.objects.create(name="Воздушные", slug="vozdushnie-sm")
    cat2 = Category.objects.create(name="Противопожарные", slug="protivopozharnie-sm")
    p1 = Product.objects.create(name="HVA", slug="hva-sm", category=cat1)
    p2 = Product.objects.create(name="SA", slug="sa-sm", category=cat2)
    SKU.objects.create(
        product=p1,
        name="HVA 5NM",
        slug="privod-hva-5nm-sm",
        sku_code="HVA-5NM-SM",
        is_published=True,
    )
    SKU.objects.create(
        product=p1,
        name="HVA 10NM",
        slug="privod-hva-10nm-sm",
        sku_code="HVA-10NM-SM",
        is_published=True,
    )
    # Unpublished SKU must NOT appear in sitemap.
    SKU.objects.create(
        product=p2,
        name="Draft",
        slug="draft-sm",
        sku_code="DRAFT-SM",
        is_published=False,
    )
    return {"cat1": cat1, "cat2": cat2, "p1": p1, "p2": p2}


# ── robots.txt ──────────────────────────────────────────────────────


def test_robots_txt_returns_200(client) -> None:
    """GET /robots.txt returns 200."""
    response = client.get("/robots.txt")
    assert response.status_code == 200


def test_robots_txt_content_type(client) -> None:
    """robots.txt is served as text/plain."""
    response = client.get("/robots.txt")
    assert "text/plain" in response["Content-Type"]


def test_robots_txt_disallows_admin(client) -> None:
    """robots.txt disallows /admin/ (no indexing of admin)."""
    response = client.get("/robots.txt")
    body = response.content.decode()
    assert "Disallow: /admin/" in body or "Disallow: /admin" in body


def test_robots_txt_disallows_tilda(client) -> None:
    """robots.txt disallows /tilda/ (legacy Tilda paths)."""
    response = client.get("/robots.txt")
    body = response.content.decode()
    assert "Disallow: /tilda/" in body or "Disallow: /tilda" in body


def test_robots_txt_allows_catalog(client) -> None:
    """robots.txt allows / (catalog, articles) — no blanket Disallow: /."""
    response = client.get("/robots.txt")
    body = response.content.decode()
    # Must NOT have a blanket "Disallow: /" (only specific paths like /admin/).
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("Disallow:"):
            path = line[len("Disallow:") :].strip()
            # Each Disallow must target a specific sub-path, not "/" alone.
            assert path != "/", "Blanket Disallow: / found in robots.txt"


def test_robots_txt_disallows_lead_and_utility_paths(client) -> None:
    """Utility SPA routes stay out of the crawl (Helmet already noindex)."""
    response = client.get("/robots.txt")
    body = response.content.decode()
    for path in ("/search", "/consultation", "/rfq", "/replacement", "/compare"):
        assert f"Disallow: {path}" in body


# ── sitemap.xml ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_sitemap_xml_returns_200(client) -> None:
    """GET /sitemap.xml returns 200."""
    _seed_for_sitemap()
    response = client.get("/sitemap.xml")
    assert response.status_code == 200


@pytest.mark.django_db
def test_sitemap_xml_content_type(client) -> None:
    """sitemap.xml is served as application/xml."""
    _seed_for_sitemap()
    response = client.get("/sitemap.xml")
    assert "xml" in response["Content-Type"]


@pytest.mark.django_db
def test_sitemap_includes_published_sku_slugs(client) -> None:
    """sitemap.xml includes canonical URLs for published SKUs."""
    _seed_for_sitemap()
    response = client.get("/sitemap.xml")
    body = response.content.decode()
    assert "/catalog/vozdushnie-sm/privod-hva-5nm-sm" in body
    assert "/catalog/vozdushnie-sm/privod-hva-10nm-sm" in body
    assert "/catalog/vozdushnie-sm" in body
    assert "/catalog/protivopozharnie-sm" in body


@pytest.mark.django_db
def test_sitemap_excludes_unpublished_skus(client) -> None:
    """sitemap.xml does NOT include unpublished SKUs."""
    _seed_for_sitemap()
    response = client.get("/sitemap.xml")
    body = response.content.decode()
    assert "/draft-sm" not in body
    assert "/catalog/protivopozharnie-sm/draft-sm" not in body


@pytest.mark.django_db
def test_sitemap_excludes_tproduct_urls(client) -> None:
    """sitemap.xml has no /tproduct/ URLs (legacy Tilda paths)."""
    _seed_for_sitemap()
    response = client.get("/sitemap.xml")
    body = response.content.decode()
    assert "/tproduct/" not in body


@pytest.mark.django_db
def test_sitemap_excludes_query_filters(client) -> None:
    """sitemap.xml <loc> URLs have no query strings (no ?moment=5 etc.)."""
    import xml.etree.ElementTree as ET

    _seed_for_sitemap()
    response = client.get("/sitemap.xml")
    root = ET.fromstring(response.content)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    for url in root.findall("sm:url", ns):
        loc = url.find("sm:loc", ns)
        assert loc is not None and loc.text is not None
        assert "?" not in loc.text, f"query string in sitemap URL: {loc.text}"


@pytest.mark.django_db
def test_sitemap_has_valid_xml_structure(client) -> None:
    """sitemap.xml is valid XML with <urlset> and <url> elements."""
    import xml.etree.ElementTree as ET

    _seed_for_sitemap()
    response = client.get("/sitemap.xml")
    root = ET.fromstring(response.content)
    # Namespace for sitemap 0.9.
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = root.findall("sm:url", ns)
    assert len(urls) >= 2  # at least the 2 published SKUs
    for url in urls:
        loc = url.find("sm:loc", ns)
        assert loc is not None
        assert loc.text and loc.text.startswith("http")


@pytest.mark.django_db
def test_sitemap_includes_home_and_static_pages(client) -> None:
    """sitemap.xml includes home and CMS static paths (no trailing slash)."""
    response = client.get("/sitemap.xml")
    body = response.content.decode()
    assert "<loc>http://testserver/</loc>" in body or "https://hoocon.ru/" in body
    assert "/catalog</loc>" in body or "/catalog<" in body
    assert "/company" in body
    assert "/zavod" in body
    assert "/faq" in body
    assert "/novosti</loc>" in body or 'novosti"' in body or "/novosti\n" in body


# ── sitemap.xml: Article / News (Iter 3) ──────────────────────────────


@pytest.mark.django_db
def test_sitemap_includes_published_articles(client) -> None:
    """sitemap.xml includes /statyi/<slug> for published articles."""
    from content.models import Article

    Article.objects.create(title="A1", slug="article-pub", body="", is_published=True)
    Article.objects.create(title="A2", slug="article-draft", body="", is_published=False)
    response = client.get("/sitemap.xml")
    body = response.content.decode()
    assert "/statyi/article-pub" in body
    assert "/statyi/article-draft" not in body


@pytest.mark.django_db
def test_sitemap_excludes_future_published_at_articles(client) -> None:
    """sitemap.xml omits articles with published_at in the future."""
    from datetime import timedelta

    from django.utils import timezone

    from content.models import Article

    Article.objects.create(
        title="Soon",
        slug="article-soon",
        body="",
        is_published=True,
        published_at=timezone.now() + timedelta(days=3),
    )
    response = client.get("/sitemap.xml")
    assert "/statyi/article-soon" not in response.content.decode()


@pytest.mark.django_db
def test_sitemap_includes_published_news(client) -> None:
    """sitemap.xml includes /novosti/<slug> for published news."""
    from content.models import News

    News.objects.create(title="N1", slug="news-pub", body="", is_published=True)
    News.objects.create(title="N2", slug="news-draft", body="", is_published=False)
    response = client.get("/sitemap.xml")
    body = response.content.decode()
    assert "/novosti/news-pub" in body
    assert "/novosti/news-draft" not in body
