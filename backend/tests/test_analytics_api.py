"""Tests for first-party analytics hit API and aggregation."""

from __future__ import annotations

import pytest
from django.urls import reverse
from django.utils import timezone

from analytics.models import ObjectType, PageDailyStat, SiteDailyStat
from analytics.services import classify_path, normalize_path, record_page_hit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/catalog/foo/bar/", "/catalog/foo/bar"),
        ("catalog/x", "/catalog/x"),
        ("https://hoocon.ru/company?x=1", "/company"),
        ("/admin/login", ""),
        ("/api/catalog/skus/", ""),
    ],
)
def test_normalize_path(raw: str, expected: str) -> None:
    assert normalize_path(raw) == expected


@pytest.mark.parametrize(
    ("path", "otype", "okey"),
    [
        ("/", ObjectType.HOME, ""),
        ("/catalog/privody/sku-1", ObjectType.SKU, "sku-1"),
        ("/catalog/privody", ObjectType.CATALOG, "privody"),
        ("/statyi/hello", ObjectType.ARTICLE, "hello"),
        ("/novosti/news-1", ObjectType.NEWS, "news-1"),
        ("/company", ObjectType.PAGE, "company"),
        ("/search", ObjectType.SEARCH, ""),
        ("/rfq", ObjectType.LEAD, "rfq"),
    ],
)
def test_classify_path(path: str, otype: str, okey: str) -> None:
    assert classify_path(path) == (otype, okey)


@pytest.mark.django_db
def test_record_page_hit_increments_views_and_uniques() -> None:
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    factory = RequestFactory()
    request = factory.post("/api/analytics/hit/")

    def _get_response(_req):  # pragma: no cover
        return None

    SessionMiddleware(_get_response).process_request(request)
    request.session.save()

    assert record_page_hit(request=request, path="/catalog/a/sku-x", title="SKU X")
    assert record_page_hit(request=request, path="/catalog/a/sku-x", title="SKU X")

    page = PageDailyStat.objects.get(path="/catalog/a/sku-x")
    assert page.views == 2
    assert page.unique_visitors == 1
    assert page.object_type == ObjectType.SKU
    assert page.object_key == "sku-x"

    site = SiteDailyStat.objects.get(day=timezone.localdate())
    assert site.views == 2
    assert site.unique_visitors == 1


@pytest.mark.django_db
def test_hit_api_accepts_post_and_sets_session(client) -> None:
    url = reverse("analytics-hit")
    response = client.post(
        url,
        data={"path": "/company", "title": "О компании"},
        content_type="application/json",
    )
    assert response.status_code == 202
    assert response.json() == {"ok": True}
    assert PageDailyStat.objects.filter(path="/company", views=1).exists()
    assert client.session.session_key


@pytest.mark.django_db
def test_hit_api_rejects_admin_path(client) -> None:
    url = reverse("analytics-hit")
    response = client.post(
        url,
        data={"path": "/admin/"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert PageDailyStat.objects.count() == 0
