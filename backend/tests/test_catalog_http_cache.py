"""Tests for phase-0 catalog HTTP response cache (bot-load defense)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.cache import cache
from django.urls import reverse

from catalog.http_cache import (
    build_catalog_http_cache_key,
    invalidate_catalog_http_cache,
    is_catalog_http_cacheable_path,
    normalize_query_string,
)


def _seed_sku():
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="Воздушные", slug="vozdushnie-cache")
    product = Product.objects.create(name="HVA", slug="hva-cache", category=cat)
    return SKU.objects.create(
        product=product,
        name="Привод cache",
        slug="privod-cache-test",
        sku_code="CACHE-1",
        price=Decimal("10.00"),
        is_published=True,
    )


@pytest.mark.parametrize(
    ("path", "ok"),
    [
        ("/api/catalog/categories/", True),
        ("/api/catalog/facets/", True),
        ("/api/catalog/skus/", True),
        ("/api/catalog/skus/foo/", True),
        ("/api/catalog/skus/foo/files/", False),
        ("/api/catalog/compare/", False),
        ("/api/catalog/docs/", False),
        ("/api/catalog/docs/families/HVA/zip/", False),
        ("/api/leads/", False),
    ],
)
def test_catalog_http_cacheable_path_whitelist(path: str, ok: bool) -> None:
    """Only categories / facets / skus list+detail are cacheable."""
    assert is_catalog_http_cacheable_path(path) is ok


def test_normalize_query_string_sorts_pairs() -> None:
    """Query order must not split the cache."""
    assert normalize_query_string("b=1&a=2") == normalize_query_string("a=2&b=1")


@pytest.mark.django_db
def test_sku_list_second_get_is_cache_hit(client, settings) -> None:
    """Repeat GET /skus/ is served from cache (X-Catalog-Cache: HIT)."""
    settings.CATALOG_HTTP_CACHE_SECONDS = 30
    _seed_sku()
    url = reverse("catalog-sku-list")
    miss = client.get(url)
    assert miss.status_code == 200
    assert miss["X-Catalog-Cache"] == "MISS"
    assert "public, max-age=30" in miss["Cache-Control"]
    hit = client.get(url)
    assert hit.status_code == 200
    assert hit["X-Catalog-Cache"] == "HIT"
    assert hit.json() == miss.json()


@pytest.mark.django_db
def test_different_query_strings_do_not_share_cache(client, settings) -> None:
    """page_size variants must not reuse one payload."""
    settings.CATALOG_HTTP_CACHE_SECONDS = 30
    _seed_sku()
    url = reverse("catalog-sku-list")
    a = client.get(url, {"page_size": 1})
    b = client.get(url, {"page_size": 2})
    assert a["X-Catalog-Cache"] == "MISS"
    assert b["X-Catalog-Cache"] == "MISS"
    assert client.get(url, {"page_size": 1})["X-Catalog-Cache"] == "HIT"


@pytest.mark.django_db
def test_invalidate_bumps_version_and_misses(client, settings) -> None:
    """Manual invalidate forces the next GET to miss."""
    settings.CATALOG_HTTP_CACHE_SECONDS = 30
    _seed_sku()
    url = reverse("catalog-sku-list")
    assert client.get(url)["X-Catalog-Cache"] == "MISS"
    assert client.get(url)["X-Catalog-Cache"] == "HIT"
    invalidate_catalog_http_cache()
    assert client.get(url)["X-Catalog-Cache"] == "MISS"


def test_invalidate_when_version_key_missing_skips_stale_v1_bodies(settings) -> None:
    """Lost epoch key must not re-seed to 1 (would HIT leftover ``…:1:…`` bodies)."""
    from catalog.http_cache import (
        _VERSION_KEY,
        build_catalog_http_cache_key,
        catalog_http_cache_version,
    )

    settings.CATALOG_HTTP_CACHE_SECONDS = 30
    cache.clear()
    assert catalog_http_cache_version() == 1
    stale_key = build_catalog_http_cache_key("/api/catalog/skus/", "")
    cache.set(
        stale_key,
        {"body": b'{"stale":true}', "status": 200, "content_type": "application/json"},
        timeout=30,
    )
    cache.delete(_VERSION_KEY)

    new_ver = invalidate_catalog_http_cache()
    assert new_ver == 2
    fresh_key = build_catalog_http_cache_key("/api/catalog/skus/", "")
    assert fresh_key != stale_key
    assert cache.get(fresh_key) is None


@pytest.mark.django_db
def test_sitesettings_save_invalidates_catalog_cache(client, settings) -> None:
    """Price gate change must not leave stale priced/hidden JSON in cache."""
    settings.CATALOG_HTTP_CACHE_SECONDS = 30
    _seed_sku()
    url = reverse("catalog-sku-list")
    assert client.get(url)["X-Catalog-Cache"] == "MISS"
    assert client.get(url)["X-Catalog-Cache"] == "HIT"

    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    site.show_prices_on_site = not site.show_prices_on_site
    site.save()

    assert client.get(url)["X-Catalog-Cache"] == "MISS"


@pytest.mark.django_db
def test_compare_is_not_cached(client, settings) -> None:
    """Compare stays uncached (combinatorial query; doc phase 0 exclude)."""
    settings.CATALOG_HTTP_CACHE_SECONDS = 30
    resp = client.get(reverse("catalog-compare-list"), {"skus": ""})
    assert resp.status_code == 200
    assert "X-Catalog-Cache" not in resp


@pytest.mark.django_db
def test_cache_disabled_when_ttl_zero(client, settings) -> None:
    """CATALOG_HTTP_CACHE_SECONDS=0 turns the middleware into a no-op."""
    settings.CATALOG_HTTP_CACHE_SECONDS = 0
    _seed_sku()
    url = reverse("catalog-sku-list")
    a = client.get(url)
    b = client.get(url)
    assert "X-Catalog-Cache" not in a
    assert "X-Catalog-Cache" not in b


@pytest.mark.django_db
def test_cache_key_stable_across_query_order(settings) -> None:
    """Sorted query → identical keys."""
    settings.CATALOG_HTTP_CACHE_SECONDS = 30
    cache.clear()
    k1 = build_catalog_http_cache_key("/api/catalog/skus/", "b=1&a=2")
    k2 = build_catalog_http_cache_key("/api/catalog/skus/", "a=2&b=1")
    assert k1 == k2


@pytest.mark.django_db
def test_head_uses_get_cache_without_storing_empty_body(client, settings) -> None:
    """HEAD is served from the GET entry; empty HEAD bodies are not stored."""
    settings.CATALOG_HTTP_CACHE_SECONDS = 30
    _seed_sku()
    url = reverse("catalog-sku-list")
    assert client.get(url)["X-Catalog-Cache"] == "MISS"
    head = client.head(url)
    assert head.status_code == 200
    assert head["X-Catalog-Cache"] == "HIT"
    assert head.content == b""


def test_load_skips_corrupt_payload_and_store_guards(settings, rf) -> None:
    """Defensive branches: bad payload, Set-Cookie, non-JSON, oversize, POST."""
    from django.http import HttpResponse

    from catalog.http_cache import (
        build_catalog_http_cache_key,
        load_cached_catalog_response,
        store_catalog_http_response,
    )

    settings.CATALOG_HTTP_CACHE_SECONDS = 30
    settings.CATALOG_HTTP_CACHE_MAX_BYTES = 64
    cache.clear()

    get_req = rf.get("/api/catalog/skus/")
    key = build_catalog_http_cache_key("/api/catalog/skus/", "")
    cache.set(key, {"body": "not-bytes", "status": 200, "content_type": "application/json"}, 30)
    assert load_cached_catalog_response(get_req) is None

    post_req = rf.post("/api/catalog/skus/")
    assert load_cached_catalog_response(post_req) is None

    ok = HttpResponse(b'{"ok":true}', content_type="application/json", status=200)
    store_catalog_http_response(get_req, ok)
    assert cache.get(build_catalog_http_cache_key("/api/catalog/skus/", "")) is not None

    cache.clear()
    cookie = HttpResponse(b'{"ok":true}', content_type="application/json", status=200)
    cookie["Set-Cookie"] = "a=1"
    store_catalog_http_response(get_req, cookie)
    assert cache.get(build_catalog_http_cache_key("/api/catalog/skus/", "")) is None

    html = HttpResponse(b"<html/>", content_type="text/html", status=200)
    store_catalog_http_response(get_req, html)
    assert cache.get(build_catalog_http_cache_key("/api/catalog/skus/", "")) is None

    empty = HttpResponse(b"", content_type="application/json", status=200)
    store_catalog_http_response(get_req, empty)
    assert cache.get(build_catalog_http_cache_key("/api/catalog/skus/", "")) is None

    huge = HttpResponse(b"x" * 128, content_type="application/json", status=200)
    store_catalog_http_response(get_req, huge)
    assert cache.get(build_catalog_http_cache_key("/api/catalog/skus/", "")) is None

    err = HttpResponse(b'{"e":1}', content_type="application/json", status=500)
    store_catalog_http_response(get_req, err)
    assert cache.get(build_catalog_http_cache_key("/api/catalog/skus/", "")) is None

    head_req = rf.head("/api/catalog/skus/")
    store_catalog_http_response(head_req, ok)
    assert head_req.method == "HEAD"
