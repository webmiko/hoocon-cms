"""Tests for catalog «Новинки» (first_published_at / is_new / ?new=1)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import SKU, Category, Product
from catalog.newness import (
    NEW_WINDOW_DAYS,
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
