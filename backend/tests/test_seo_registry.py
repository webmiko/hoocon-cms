"""SEO contract for every public page and every published product.

The loops walk the route table and the published querysets. A new static
page or a new SKU is checked without a new test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.conf import settings

from config.seo.head import news_mirrors_article
from config.seo.meta_text import DESCRIPTION_MAX_LEN, TITLE_MAX_LEN
from config.seo.routes import CANONICAL_REPLACEMENTS, NOINDEX_PREFIXES, PUBLIC_STATIC_ROUTES

# source-lint: App.tsx — загружаемая таблица маршрутов SPA. Pytest не монтирует
# React, поэтому новый path ловится разбором этого файла: иначе адрес отдаёт 410
# и не попадает в sitemap.
_SPA_APP = Path(__file__).resolve().parents[2] / "frontend" / "src" / "App.tsx"
_LAYOUT_ROUTE_INDENT = 12
_DESCRIPTION_MIN = 40


def _title(html: str) -> str:
    match = re.search(r"<title>(.*?)</title>", html, flags=re.DOTALL)
    return match.group(1).strip() if match else ""


def _meta(html: str, name: str) -> str:
    match = re.search(rf'<meta[^>]+name="{name}"[^>]+content="([^"]*)"', html)
    return match.group(1) if match else ""


def _canonical(html: str) -> str:
    match = re.search(r'<link[^>]+rel="canonical"[^>]+href="([^"]*)"', html)
    return match.group(1) if match else ""


def _crawl(html: str) -> str:
    marker = 'id="seo-crawl"'
    assert marker in html, "first HTML has no crawl block"
    return html.split(marker, 1)[1].split("</article>", 1)[0]


def _locs(sitemap: str) -> set[str]:
    return set(re.findall(r"<loc>(.*?)</loc>", sitemap))


def _layout_route_paths(source: str) -> list[str]:
    """Top-level SPA paths. Account children stay under the /account prefix."""
    paths: list[str] = []
    for line in source.splitlines():
        if "<Route" not in line:
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent != _LAYOUT_ROUTE_INDENT:
            continue
        if re.search(r"<Route\s+index\b", line):
            paths.append("/")
            continue
        match = re.search(r'path="([^"]+)"', line)
        if match:
            raw = match.group(1)
            paths.append(raw if raw.startswith("/") else f"/{raw}")
    return paths


def _server_knows_spa_path(path: str) -> bool:
    """True when the server will not answer this SPA path with a bare 410."""
    if path in PUBLIC_STATIC_ROUTES or path in CANONICAL_REPLACEMENTS:
        return True
    if any(path == prefix or path.startswith(f"{prefix}/") for prefix in NOINDEX_PREFIXES):
        return True
    if path in {"/news", "/:slug", "/*"} or path.startswith("/news/"):
        return True
    if ":" in path or path.endswith("*"):
        head = "/" + path.strip("/").split("/")[0]
        if head.startswith("/:"):
            return True
        return head in PUBLIC_STATIC_ROUTES or head == "/news"
    return False


def _seed_catalog_and_content() -> None:
    from django.utils import timezone

    from catalog.models import SKU, Category, Product
    from content.models import Article, News

    short = Category.objects.create(name="Адаптеры", slug="adaptery-registry", description="Адаптеры")
    long = Category.objects.create(
        name="Электроприводы с пружинным возвратом",
        slug="pruzhina-registry",
        description=(
            "Электроприводы Hoocon с возвратной пружиной для воздушных заслонок и огнезадерживающих клапанов."
        ),
    )
    bracket = Product.objects.create(name="BR", slug="br-registry", category=short)
    drive = Product.objects.create(name="DA", slug="da-registry", category=long)
    SKU.objects.create(
        product=bracket,
        name="Кронштейн BR-M",
        slug="kronshteyn-br-m-registry",
        sku_code="BR-M-REG",
        is_published=True,
    )
    SKU.objects.create(
        product=drive,
        name="Привод DA5",
        slug="privod-da5-registry",
        sku_code="DA5FU24-REG",
        analog_belimo_code="LF24",
        is_published=True,
    )
    SKU.objects.create(
        product=drive,
        name="Черновик",
        slug="chernovik-registry",
        sku_code="DRAFT-REG",
        is_published=False,
    )
    Article.objects.create(
        title="Подбор аналога",
        slug="podbor-analoga-registry",
        excerpt="Как сопоставить код Belimo и Hoocon.",
        body="<p>Таблица соответствий.</p>",
        is_published=True,
        published_at=timezone.now(),
    )
    News.objects.create(
        title="Поставка на склад",
        slug="postavka-registry",
        body="<p>Партия приехала на склад в Москве.</p>",
        is_published=True,
        published_at=timezone.now(),
    )
    News.objects.create(
        title="Новая статья: Подбор аналога",
        slug="article-podbor-analoga-registry",
        body="<p>Вышла статья.</p>",
        is_published=True,
        published_at=timezone.now(),
    )


@pytest.mark.django_db
def test_every_spa_route_is_known_to_the_server() -> None:
    """A new screen in App.tsx must be indexable, noindex, or an explicit redirect."""
    source = _SPA_APP.read_text(encoding="utf-8")
    paths = _layout_route_paths(source)
    assert "/" in paths
    assert "/catalog" in paths
    missing = [path for path in paths if not _server_knows_spa_path(path)]
    assert missing == []


@pytest.mark.django_db
def test_every_public_page_and_published_sku_is_indexable(client) -> None:
    """Static pages, categories, articles, news and SKUs share one SEO contract."""
    from catalog.models import SKU, Category
    from catalog.urls_paths import catalog_category_path, catalog_path_for_sku
    from content.models import Article, News
    from content.views import publicly_visible

    _seed_catalog_and_content()
    base = settings.SITE_URL.rstrip("/")
    sitemap = client.get("/sitemap.xml").content.decode()
    locs = _locs(sitemap)
    titles: list[str] = []

    for path, meta in PUBLIC_STATIC_ROUTES.items():
        description = meta.get("description") or ""
        assert meta.get("title"), path
        assert len(description) >= _DESCRIPTION_MIN, path
        assert len(description) <= DESCRIPTION_MAX_LEN, path
        response = client.get(path)
        assert response.status_code == 200, path
        html = response.content.decode()
        title = _title(html)
        assert title
        assert len(title) <= TITLE_MAX_LEN, title
        assert "…" not in title, title
        titles.append(title)
        rendered_description = _meta(html, "description")
        assert description[:_DESCRIPTION_MIN] in rendered_description, path
        assert len(rendered_description) <= DESCRIPTION_MAX_LEN
        assert _meta(html, "robots") == "index, follow", path
        expected = f"{base}/" if path == "/" else f"{base}{path}"
        assert _canonical(html) == expected, path
        assert expected in locs, path
        block = _crawl(html)
        assert "<h1>" in block, path
        assert 'href="/' in block, path
        assert "hidden" not in block, path

    assert len(titles) == len(set(titles))

    for prefix in NOINDEX_PREFIXES:
        response = client.get(prefix)
        assert response.status_code == 200, prefix
        assert _meta(response.content.decode(), "robots") == "noindex, nofollow", prefix
        assert f"{base}{prefix}" not in locs

    for category in Category.objects.all():
        path = catalog_category_path(category.slug)
        response = client.get(path)
        assert response.status_code == 200, path
        html = response.content.decode()
        description = _meta(html, "description")
        assert _DESCRIPTION_MIN <= len(description) <= DESCRIPTION_MAX_LEN, description
        assert _meta(html, "robots") == "index, follow"
        assert _canonical(html) == f"{base}{path}"
        assert f"{base}{path}" in locs
        block = _crawl(html)
        assert category.name in block
        for sku in SKU.objects.filter(is_published=True, product__category=category):
            assert f'href="{catalog_path_for_sku(sku)}"' in block

    published = list(SKU.objects.filter(is_published=True).select_related("product__category"))
    assert published, "the registry loop needs at least one published SKU"
    llms = client.get("/llms.txt").content.decode()
    for sku in published:
        path = catalog_path_for_sku(sku)
        response = client.get(path)
        assert response.status_code == 200, path
        html = response.content.decode()
        title = _title(html)
        assert sku.sku_code in title
        assert len(title) <= TITLE_MAX_LEN
        description = _meta(html, "description")
        assert sku.sku_code in description
        assert len(description) <= DESCRIPTION_MAX_LEN
        if sku.analog_belimo_code:
            assert sku.analog_belimo_code in description
            assert sku.analog_belimo_code in llms
        assert _meta(html, "robots") == "index, follow"
        assert _canonical(html) == f"{base}{path}"
        assert f"{base}{path}" in locs
        url_block = sitemap.split(f"<loc>{base}{path}</loc>", 1)[1].split("</url>", 1)[0]
        assert "<lastmod>" in url_block
        block = _crawl(html)
        assert sku.sku_code in block
        assert "<h1>" in block
        category = sku.product.category
        assert f'href="{catalog_category_path(category.slug)}"' in block
        assert "priceSpecification" not in html
        assert '"@type": "Brand"' in html
        assert "/og-image.svg" not in html

    hidden = SKU.objects.get(sku_code="DRAFT-REG")
    hidden_path = catalog_path_for_sku(hidden)
    assert client.get(hidden_path).status_code == 410
    assert f"{base}{hidden_path}" not in locs

    for article in publicly_visible(Article):
        path = f"/statyi/{article.slug}"
        html = client.get(path).content.decode()
        assert client.get(path).status_code == 200
        assert _meta(html, "robots") == "index, follow"
        assert _canonical(html) == f"{base}{path}"
        assert article.title in _crawl(html) or article.excerpt in _crawl(html)
        assert 'href="/catalog"' in _crawl(html)
        assert f"{base}{path}" in locs

    for news in publicly_visible(News):
        path = f"/novosti/{news.slug}"
        response = client.get(path)
        assert response.status_code == 200
        html = response.content.decode()
        mirror = news_mirrors_article(news.slug)
        if mirror:
            assert _canonical(html) == f"{base}{mirror}"
            assert _meta(html, "robots") == "noindex, nofollow"
            assert f"{base}{path}" not in locs
        else:
            assert _canonical(html) == f"{base}{path}"
            assert _meta(html, "robots") == "index, follow"
            assert news.title in _crawl(html)
            assert f"{base}{path}" in locs
