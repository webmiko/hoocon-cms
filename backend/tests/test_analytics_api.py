"""Tests for first-party analytics hit API and aggregation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import time_machine
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


# Секунда до полуночи по МСК: без заморозки хит и проверка попадали в разные дни.
_JUST_BEFORE_MIDNIGHT_MSK = datetime(2026, 10, 9, 20, 59, 59, 900000, tzinfo=UTC)


@pytest.mark.django_db
@time_machine.travel(_JUST_BEFORE_MIDNIGHT_MSK, tick=False)
def test_record_page_hit_increments_views_and_uniques() -> None:
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    factory = RequestFactory()
    request = factory.post("/api/analytics/hit/")

    def _get_response(_req):  # pragma: no cover
        return None

    SessionMiddleware(_get_response).process_request(request)
    request.session.save()
    _published_sku("sku-x", "SKU X")

    assert record_page_hit(request=request, path="/catalog/a/sku-x")
    assert record_page_hit(request=request, path="/catalog/a/sku-x")

    page = PageDailyStat.objects.get(path="/catalog/a/sku-x")
    assert page.views == 2
    assert page.unique_visitors == 1
    assert page.object_type == ObjectType.SKU
    assert page.object_key == "sku-x"
    assert page.title == "SKU X"

    site = SiteDailyStat.objects.get(day=timezone.localdate())
    assert site.views == 2
    assert site.unique_visitors == 1


def _published_sku(slug: str, name: str):
    from catalog.models import SKU, Category, Product

    category, _ = Category.objects.get_or_create(slug="a", defaults={"name": "A"})
    product, _ = Product.objects.get_or_create(slug=f"p-{slug}", defaults={"name": name, "category": category})
    return SKU.objects.create(product=product, name=name, slug=slug, sku_code=slug.upper(), is_published=True)


@pytest.mark.django_db
def test_hit_api_accepts_post_without_creating_session(client) -> None:
    """M28: хит анонима не создаёт строку сессии; уникальность — по дневному хэшу."""
    from django.contrib.sessions.models import Session

    url = reverse("analytics-hit")
    response = client.post(
        url,
        data={"path": "/company", "title": "О компании"},
        content_type="application/json",
    )
    assert response.status_code == 202
    assert response.json() == {"ok": True}
    assert PageDailyStat.objects.filter(path="/company", views=1, unique_visitors=1).exists()
    assert Session.objects.count() == 0
    client.post(url, data={"path": "/company"}, content_type="application/json")
    assert PageDailyStat.objects.get(path="/company").unique_visitors == 1


@pytest.mark.django_db
def test_hit_api_ignores_unknown_and_unpublished_paths(client) -> None:
    """M28: любой path от анонима не плодит строки PageDailyStat."""
    url = reverse("analytics-hit")
    hidden = _published_sku("hidden-sku", "Hidden")
    hidden.is_published = False
    hidden.save(update_fields=["is_published"])

    for path in ("/random-junk-123", "/catalog/a/no-such-sku", "/catalog/a/hidden-sku", "/statyi/nope"):
        response = client.post(url, data={"path": path}, content_type="application/json")
        assert response.status_code == 202

    assert PageDailyStat.objects.count() == 0
    assert SiteDailyStat.objects.count() == 0


@pytest.mark.django_db
def test_hit_api_title_and_type_come_from_server(client) -> None:
    """M28: title / object_type от клиента не переписывают топы в Admin."""
    url = reverse("analytics-hit")
    _published_sku("real-sku", "Привод DA5FU")

    for title in ("Казино 777", "ещё спам"):
        client.post(
            url,
            data={"path": "/catalog/a/real-sku", "title": title, "object_type": "article", "object_key": "x"},
            content_type="application/json",
        )

    page = PageDailyStat.objects.get(path="/catalog/a/real-sku")
    assert page.title == "Привод DA5FU"
    assert page.object_type == ObjectType.SKU
    assert page.object_key == "real-sku"
    assert page.views == 2


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
