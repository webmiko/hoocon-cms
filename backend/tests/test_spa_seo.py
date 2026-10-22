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
    assert "no-cache" in response["Cache-Control"]


@pytest.mark.django_db
def test_spa_home_preloads_lcp_hero(client) -> None:
    """GET / preloads the hero and puts picker text plus catalog links in the first HTML."""
    from config.seo.spa_index import HOME_LCP_IMAGE

    response = client.get("/")
    assert response.status_code == 200
    body = response.content.decode()
    assert f'rel="preload" as="image" href="{HOME_LCP_IMAGE}"' in body
    assert 'id="seo-crawl"' in body
    assert "hidden" not in body.split('id="seo-crawl"', 1)[1].split("</article>", 1)[0]
    assert "Подбор модели за минуту" in body
    assert 'href="/catalog"' in body
    assert "SearchAction" not in body
    assert "+78003505898" in body
    assert "/og-image.png" in body
    assert "hoocon-ssr-hero" not in body
    assert "hoocon-lcp-boot" not in body
    assert 'type="module" src="/assets/index.js"' in body
    assert 'getElementById("hoocon-lcp-boot")' not in body


@pytest.mark.django_db
def test_spa_catalog_skips_home_lcp_boot(client) -> None:
    """Non-home routes must not inject the home LCP preload."""
    from config.seo.spa_index import HOME_LCP_IMAGE

    response = client.get("/catalog")
    assert response.status_code == 200
    body = response.content.decode()
    assert "hoocon-ssr-hero" not in body
    assert "hoocon-lcp-boot" not in body
    assert f'rel="preload" as="image" href="{HOME_LCP_IMAGE}"' not in body


@pytest.mark.django_db
def test_spa_unknown_address_is_gone(client) -> None:
    """A path with no page and no redirect is 410, not a 200 page hidden by noindex."""
    response = client.get("/etot-adres-uzhe-ne-sushchestvuet")
    assert response.status_code == 410
    body = response.content.decode()
    assert 'name="robots" content="noindex, nofollow"' in body
    assert "Страница не найдена" in body


@pytest.mark.django_db
def test_spa_missing_catalog_sku_is_gone(client) -> None:
    """An unpublished catalog address is 410. A published card stays 200."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="Воздушные", slug="vozdushnie-gone")
    prod = Product.objects.create(name="HVA", slug="hva-gone", category=cat)
    SKU.objects.create(
        product=prod,
        name="Черновик",
        slug="chernovik-gone",
        sku_code="GONE-1",
        price="1.00",
        is_published=False,
    )
    missing = client.get("/catalog/vozdushnie-gone/chernovik-gone")
    assert missing.status_code == 410
    assert 'name="robots" content="noindex, nofollow"' in missing.content.decode()

    SKU.objects.filter(slug="chernovik-gone").update(is_published=True)
    live = client.get("/catalog/vozdushnie-gone/chernovik-gone")
    assert live.status_code == 200
    assert 'name="robots" content="index, follow"' in live.content.decode()


@pytest.mark.django_db
def test_spa_account_stays_open_and_noindex(client) -> None:
    """Cabinet screens are real pages. A missing address must not close them."""
    response = client.get("/account/orders")
    assert response.status_code == 200
    body = response.content.decode()
    assert 'name="robots" content="noindex, nofollow"' in body
    assert "Страница не найдена" not in body


@pytest.mark.django_db
def test_spa_search_is_noindex(client) -> None:
    """GET /search has robots noindex."""
    response = client.get("/search")
    assert response.status_code == 200
    body = response.content.decode()
    assert 'name="robots" content="noindex, nofollow"' in body


@pytest.mark.django_db
def test_spa_rfq_is_noindex_not_404_title(client) -> None:
    """GET /rfq is a real SPA page (noindex), not a server 404 title."""
    response = client.get("/rfq")
    assert response.status_code == 200
    body = response.content.decode()
    assert 'name="robots" content="noindex, nofollow"' in body
    assert "Страница не найдена" not in body
    assert "коммерческого предложения" in body


@pytest.mark.django_db
def test_spa_compare_is_noindex_not_404_title(client) -> None:
    """GET /compare is a real SPA page (noindex), not a server 404 title."""
    response = client.get("/compare")
    assert response.status_code == 200
    body = response.content.decode()
    assert 'name="robots" content="noindex, nofollow"' in body
    assert "Страница не найдена" not in body
    assert "Сравнение моделей" in body


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


@pytest.mark.django_db
def test_llms_txt(client) -> None:
    """GET /llms.txt returns llmstxt.org-shaped plain text summary."""
    response = client.get("/llms.txt")
    assert response.status_code == 200
    body = response.content.decode()
    assert "Hoocon" in body
    assert "/catalog" in body
    assert "/dokumentaciya" in body
    assert "/llms-full.txt" in body


@pytest.mark.django_db
def test_llm_txt_alias(client) -> None:
    """GET /llm.txt mirrors /llms.txt."""
    response = client.get("/llm.txt")
    assert response.status_code == 200
    assert "Hoocon" in response.content.decode()


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_spa_article_json_ld_cannot_close_script(client) -> None:
    """M30: «</script>» в заголовке статьи не выходит из JSON-LD (XSS в SSR head)."""
    import json
    import re

    from django.utils import timezone

    from content.models import Article

    Article.objects.create(
        title='Привод </script><script>alert(1)</script> & "кавычки"',
        slug="xss-seo",
        body="<p>Текст.</p>",
        excerpt="</script><img src=x onerror=alert(2)>",
        is_published=True,
        published_at=timezone.now(),
    )
    response = client.get("/statyi/xss-seo")
    assert response.status_code == 200
    body = response.content.decode()
    assert "<script>alert(1)" not in body
    assert "<img src=x" not in body
    blocks = re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', body, flags=re.DOTALL)
    parsed = [json.loads(block) for block in blocks]
    assert any(item.get("@type") == "Article" for item in parsed)


def test_inject_json_ld_escapes_script_breakout() -> None:
    """M30: любое поле JSON-LD с «</script>» экранируется как \\u003c — блок не закрывается."""
    import json

    from config.seo.head import inject_json_ld

    html = "<html><head></head><body></body></html>"
    block = {"@type": "Product", "name": "DA5 </script><script>alert(1)</script> & co"}
    out = inject_json_ld(html, [block], nonce="n1")

    assert "<script>alert(1)" not in out
    assert out.count("</script>") == 1
    payload = out.split('nonce="n1">', 1)[1].split("</script>", 1)[0]
    assert "\\u003c/script\\u003e" in payload
    assert json.loads(payload) == block


@pytest.mark.django_db
def test_spa_title_with_group_reference_does_not_500(client) -> None:
    """M30: «\\1» / «\\g<0>» в заголовке из CMS не ломает re.subn (500)."""
    from django.utils import timezone

    from content.models import Article

    Article.objects.create(
        title=r"Схема \1 и \g<0> подключения",
        slug="backref-seo",
        body="<p>Текст.</p>",
        is_published=True,
        published_at=timezone.now(),
    )
    response = client.get("/statyi/backref-seo")
    assert response.status_code == 200
    assert r"Схема \1 и \g&lt;0&gt; подключения" in response.content.decode()


@pytest.mark.django_db
def test_home_title_is_a_full_phrase(client) -> None:
    """The home title stays a whole phrase under 60 characters."""
    response = client.get("/")
    assert response.status_code == 200
    body = response.content.decode()
    title = body.split("<title>", 1)[1].split("</title>", 1)[0]
    assert "…" not in title
    assert len(title) <= 60
    assert title == "Электроприводы для вентиляции и подбор — Hoocon"


@pytest.mark.django_db
def test_spa_sku_html_contains_heading_and_article(client) -> None:
    """The first HTML of a product page has the heading and article code."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="Воздушные факты", slug="vozdushnie-facts")
    prod = Product.objects.create(name="HVA факты", slug="hva-facts", category=cat)
    SKU.objects.create(
        product=prod,
        name="Привод HVA факты",
        slug="privod-hva-facts",
        sku_code="HVA-FACTS-1",
        is_published=True,
    )
    response = client.get("/catalog/vozdushnie-facts/privod-hva-facts")
    assert response.status_code == 200
    body = response.content.decode()
    assert '<article id="seo-crawl">' in body
    assert 'id="sku-crawl" hidden' not in body
    assert "<h1>" in body
    assert "HVA-FACTS-1" in body
    assert 'href="/catalog/vozdushnie-facts"' in body
    assert "priceSpecification" not in body
    assert '"Brand"' in body or '"@type": "Brand"' in body


@pytest.mark.django_db
def test_catalog_filter_query_is_noindex_and_sku_query_stays_open(client) -> None:
    """A catalog filter is noindex. A product link with a tag stays indexable."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="Фильтр SEO", slug="filtr-seo")
    prod = Product.objects.create(name="Фильтр", slug="filtr-prod", category=cat)
    SKU.objects.create(
        product=prod,
        name="Фильтр SKU",
        slug="filtr-sku",
        sku_code="FILTR-1",
        is_published=True,
    )
    listing = client.get("/catalog?moment=5")
    assert listing.status_code == 200
    listing_body = listing.content.decode()
    assert 'name="robots" content="noindex, nofollow"' in listing_body
    assert 'rel="canonical" href="https://hoocon.ru/catalog"' in listing_body

    product = client.get("/catalog/filtr-seo/filtr-sku?utm_source=newsletter")
    assert product.status_code == 200
    product_body = product.content.decode()
    assert 'name="robots" content="index, follow"' in product_body


@pytest.mark.django_db
def test_old_company_and_privacy_addresses_redirect(client) -> None:
    """Old company and privacy addresses go to the live pages."""
    company = client.get("/o-kompanii")
    assert company.status_code == 301
    assert company["Location"].endswith("/company")
    privacy = client.get("/privacy")
    assert privacy.status_code == 301
    assert privacy["Location"].endswith("/privacy-policy")


@pytest.mark.django_db
def test_sitemap_skips_replaced_pages(client) -> None:
    """A page that already has a live address is not a second sitemap URL."""
    from content.models import Page

    Page.objects.update_or_create(
        slug="o-kompanii",
        defaults={"title": "О компании", "body": "<p>Старый текст</p>", "is_published": True},
    )
    Page.objects.update_or_create(
        slug="privacy",
        defaults={"title": "Privacy", "body": "<p>Старый текст</p>", "is_published": True},
    )
    body = client.get("/sitemap.xml").content.decode()
    assert "<loc>https://hoocon.ru/o-kompanii</loc>" not in body
    assert "<loc>https://hoocon.ru/privacy</loc>" not in body
    assert "<loc>https://hoocon.ru/company</loc>" in body
    assert "<loc>https://hoocon.ru/privacy-policy</loc>" in body


@pytest.mark.django_db
def test_wrong_category_sku_redirects_to_canonical(client) -> None:
    """A live SKU under the wrong section is 301, not a second indexable page."""
    from catalog.models import SKU, Category, Product

    air = Category.objects.create(name="Воздушные", slug="vozdushnie-redir")
    other = Category.objects.create(name="Адаптеры", slug="adaptery-redir")
    prod = Product.objects.create(name="DA", slug="da-redir", category=air)
    SKU.objects.create(
        product=prod,
        name="DA3",
        slug="privod-da3-redir",
        sku_code="DA3-REDIR",
        is_published=True,
    )
    response = client.get(f"/catalog/{other.slug}/privod-da3-redir")
    assert response.status_code == 301
    assert response["Location"].endswith("/catalog/vozdushnie-redir/privod-da3-redir")


@pytest.mark.django_db
def test_catalog_and_article_first_html_have_text_and_links(client) -> None:
    """Catalog and an article name themselves and link onward before the script runs."""
    from django.utils import timezone

    from catalog.models import SKU, Category, Product
    from content.models import Article

    cat = Category.objects.create(name="Адаптеры", slug="adaptery-crawl", description="Адаптеры")
    prod = Product.objects.create(name="BR", slug="br-crawl", category=cat)
    SKU.objects.create(
        product=prod,
        name="BR-M",
        slug="adapter-br-m",
        sku_code="BR-M-1",
        is_published=True,
    )
    Article.objects.create(
        title="Замена Belimo",
        slug="zamena-belimo-crawl",
        body="<p>Таблица соответствий серий.</p>",
        excerpt="Как подбирать аналог Belimo.",
        is_published=True,
        published_at=timezone.now(),
    )
    catalog = client.get("/catalog").content.decode()
    assert 'id="seo-crawl"' in catalog
    assert 'href="/catalog/adaptery-crawl"' in catalog
    category = client.get("/catalog/adaptery-crawl").content.decode()
    assert 'href="/catalog/adaptery-crawl/adapter-br-m"' in category
    assert "паспорта PDF" in category
    article = client.get("/statyi/zamena-belimo-crawl").content.decode()
    assert "Как подбирать аналог Belimo." in article
    assert 'href="/catalog"' in article


@pytest.mark.django_db
def test_news_that_repeats_an_article_is_not_a_second_index_url(client) -> None:
    """A news item slug article-{slug} points canonical at the article and stays noindex."""
    from django.utils import timezone

    from content.models import Article, News

    Article.objects.create(
        title="Суффиксы",
        slug="suffiksy-crawl",
        body="<p>Текст статьи.</p>",
        is_published=True,
        published_at=timezone.now(),
    )
    News.objects.create(
        title="Новая статья: Суффиксы",
        slug="article-suffiksy-crawl",
        body="<p>Анонс.</p>",
        is_published=True,
        published_at=timezone.now(),
    )
    page = client.get("/novosti/article-suffiksy-crawl")
    assert page.status_code == 200
    body = page.content.decode()
    assert 'rel="canonical" href="https://hoocon.ru/statyi/suffiksy-crawl"' in body
    assert 'name="robots" content="noindex, nofollow"' in body
    sitemap = client.get("/sitemap.xml").content.decode()
    assert "/novosti/article-suffiksy-crawl" not in sitemap
    assert "/statyi/suffiksy-crawl" in sitemap


@pytest.mark.django_db
def test_llms_txt_lists_a_belimo_analog(client) -> None:
    """llms.txt names a Belimo code and the Hoocon card, not only the section list."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="Воздушные", slug="vozdushnie-llms")
    prod = Product.objects.create(name="HVD", slug="hvd-llms", category=cat)
    SKU.objects.create(
        product=prod,
        name="HVD",
        slug="privod-hvd-llms",
        sku_code="HVD230S-5",
        analog_belimo_code="LM230A-S",
        is_published=True,
    )
    body = client.get("/llms.txt").content.decode()
    assert "LM230A-S" in body
    assert "HVD230S-5" in body
    assert "/catalog/vozdushnie-llms" in body
