"""Tests for catalog «Новинки» (first_published_at / is_new / ?new=1)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import SKU, Category, Product
from catalog.newness import (
    NEW_WINDOW_DAYS,
    NOVINKI_CAROUSEL_LIMIT,
    novinki_list_order_by,
    sku_is_new,
    stamp_hv_newness,
)


@pytest.mark.django_db
def test_sku_is_new_window_boundary() -> None:
    cat = Category.objects.create(name="Air", slug="air-newness")
    product = Product.objects.create(name="HVA-5", slug="hva-5-newness", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="HVA24-5",
        name="HVA24-5",
        slug="hva24-5-newness",
        is_published=True,
        first_published_at=timezone.now() - timedelta(days=NEW_WINDOW_DAYS - 1),
    )
    assert sku_is_new(sku) is True
    sku.first_published_at = timezone.now() - timedelta(days=NEW_WINDOW_DAYS + 1)
    assert sku_is_new(sku) is False
    sku.first_published_at = None
    assert sku_is_new(sku) is False


@pytest.mark.django_db
def test_save_stamps_first_published_at() -> None:
    cat = Category.objects.create(name="Air", slug="air-newness-save")
    product = Product.objects.create(name="HVA-10", slug="hva-10-newness", category=cat)
    sku = SKU(
        product=product,
        sku_code="HVA24-10",
        name="HVA24-10",
        slug="hva24-10-newness",
        is_published=True,
    )
    sku.save()
    assert sku.first_published_at is not None
    stamped = sku.first_published_at
    sku.name = "HVA24-10 updated"
    sku.save()
    sku.refresh_from_db()
    assert sku.first_published_at == stamped


@pytest.mark.django_db
def test_stamp_hv_newness_only_hv_wave() -> None:
    cat = Category.objects.create(name="Air", slug="air-stamp-hv")
    hva = Product.objects.create(name="HVA", slug="hva-stamp", category=cat)
    da = Product.objects.create(name="DA", slug="da-stamp", category=cat)
    hva_sku = SKU.objects.create(
        product=hva,
        sku_code="HVA24-5Q",
        name="HVA24-5Q",
        slug="hva24-5q-stamp",
        is_published=True,
        first_published_at=None,
    )
    # Bypass save stamp: update null after create
    SKU.objects.filter(pk=hva_sku.pk).update(first_published_at=None)
    da_sku = SKU.objects.create(
        product=da,
        sku_code="DA5MU24-A",
        name="DA5",
        slug="da5-stamp",
        is_published=True,
    )
    SKU.objects.filter(pk=da_sku.pk).update(first_published_at=None)
    qx = SKU.objects.create(
        product=hva,
        sku_code="HVD24-10QX",
        name="HVD24-10QX",
        slug="hvd24-10qx-stamp",
        is_published=True,
    )
    SKU.objects.filter(pk=qx.pk).update(first_published_at=None)

    summary = stamp_hv_newness(dry_run=False)
    assert summary["updated"] >= 2
    hva_sku.refresh_from_db()
    da_sku.refresh_from_db()
    qx.refresh_from_db()
    assert hva_sku.first_published_at is not None
    assert qx.first_published_at is not None
    assert da_sku.first_published_at is None


@pytest.mark.django_db
def test_api_new_filter_and_is_new_flag() -> None:
    cat = Category.objects.create(name="Air", slug="air-new-api")
    product = Product.objects.create(
        name="HVD-5Q",
        slug="privod-vozdushniy-hvd-5q-api-new",
        category=cat,
    )
    fresh = SKU.objects.create(
        product=product,
        sku_code="HVD24-5Q",
        name="HVD24-5Q",
        slug="hvd24-5q-api-new",
        is_published=True,
        first_published_at=timezone.now(),
    )
    old = SKU.objects.create(
        product=product,
        sku_code="HVD230-5Q",
        name="HVD230-5Q",
        slug="hvd230-5q-api-old",
        is_published=True,
        first_published_at=timezone.now() - timedelta(days=60),
    )
    client = APIClient()
    response = client.get("/api/catalog/skus/", {"new": "1"})
    assert response.status_code == 200
    codes = {row["sku_code"] for row in response.json().get("results") or []}
    assert fresh.sku_code in codes
    assert old.sku_code not in codes

    detail = client.get(f"/api/catalog/skus/{fresh.slug}/")
    assert detail.status_code == 200
    body = detail.json()
    assert body["is_new"] is True
    assert body.get("first_published_at")


@pytest.mark.django_db
def test_api_new_orders_stock_then_newest_first() -> None:
    """``?new=1``: in stock before OOS; within group newer ``first_published_at`` left."""
    cat = Category.objects.create(name="Air", slug="air-novinki-order")
    now = timezone.now()

    def _sku(
        *,
        code: str,
        slug: str,
        stock: int,
        published_at,
    ) -> SKU:
        product = Product.objects.create(
            name=code,
            slug=f"prod-{slug}",
            category=cat,
        )
        return SKU.objects.create(
            product=product,
            sku_code=code,
            name=code,
            slug=slug,
            is_published=True,
            stock_qty=stock,
            first_published_at=published_at,
        )

    older_stock = _sku(
        code="NEW-OLD-STOCK",
        slug="new-old-stock",
        stock=3,
        published_at=now - timedelta(days=5),
    )
    newer_oos = _sku(
        code="NEW-FRESH-OOS",
        slug="new-fresh-oos",
        stock=0,
        published_at=now - timedelta(hours=1),
    )
    newest_stock = _sku(
        code="NEW-FRESH-STOCK",
        slug="new-fresh-stock",
        stock=2,
        published_at=now,
    )
    _sku(
        code="NEW-ANCIENT",
        slug="new-ancient",
        stock=5,
        published_at=now - timedelta(days=60),
    )

    client = APIClient()
    response = client.get(
        "/api/catalog/skus/",
        {"new": "1", "page_size": str(NOVINKI_CAROUSEL_LIMIT)},
    )
    assert response.status_code == 200
    codes = [row["sku_code"] for row in response.json().get("results") or []]
    assert "NEW-ANCIENT" not in codes
    assert codes.index(newest_stock.sku_code) < codes.index(older_stock.sku_code)
    assert codes.index(older_stock.sku_code) < codes.index(newer_oos.sku_code)


@pytest.mark.django_db
def test_api_new_catalog_has_no_hard_cap_beyond_page() -> None:
    """Catalog ``?new=1`` returns full 30-day count; page_size only paginates."""
    cat = Category.objects.create(name="Air", slug="air-novinki-uncapped")
    now = timezone.now()
    for i in range(NOVINKI_CAROUSEL_LIMIT + 5):
        product = Product.objects.create(
            name=f"N{i}",
            slug=f"novinki-uncapped-{i}",
            category=cat,
        )
        SKU.objects.create(
            product=product,
            sku_code=f"UNCAPPED-{i:02d}",
            name=f"UNCAPPED-{i:02d}",
            slug=f"uncapped-{i:02d}",
            is_published=True,
            stock_qty=1 if i % 2 == 0 else 0,
            first_published_at=now - timedelta(hours=i),
        )

    client = APIClient()
    page1 = client.get(
        "/api/catalog/skus/",
        {"new": "1", "page_size": str(NOVINKI_CAROUSEL_LIMIT)},
    )
    assert page1.status_code == 200
    body = page1.json()
    assert body["count"] >= NOVINKI_CAROUSEL_LIMIT + 5
    assert len(body["results"]) == NOVINKI_CAROUSEL_LIMIT
    assert body.get("next")

    page2 = client.get(
        "/api/catalog/skus/",
        {"new": "1", "page": "2", "page_size": str(NOVINKI_CAROUSEL_LIMIT)},
    )
    assert page2.status_code == 200
    assert len(page2.json()["results"]) >= 5


@pytest.mark.django_db
def test_novinki_list_order_by_matches_expected_keys() -> None:
    keys = novinki_list_order_by()
    assert len(keys) == 3
