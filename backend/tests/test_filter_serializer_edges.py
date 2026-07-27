"""Edge coverage for catalog query filters and serializer helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from django.http import Http404
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from catalog.filters import AttributeQueryFilterBackend, SKUFilterSet
from catalog.models import SKU, Attribute, AttributeValue, Category, Product
from catalog.serializers import _family_list_heading, _sku_analogs_text
from config.seo.sanitize import (
    normalize_spa_path,
    plain_text_for_meta,
    validate_slug,
)


@pytest.mark.django_db
def test_sku_filterset_empty_values_are_noop() -> None:
    """Empty category / q / in_stock leave the queryset unchanged."""
    cat = Category.objects.create(name="C", slug="c-filt")
    product = Product.objects.create(name="P", slug="p-filt", category=cat)
    SKU.objects.create(product=product, name="S", slug="s-filt", sku_code="F1")
    qs = SKU.objects.all()
    fs = SKUFilterSet(data={}, queryset=qs)
    assert fs.qs.count() == qs.count()
    assert fs.filter_category(qs, "category", "") is qs
    assert fs.filter_q(qs, "q", "") is qs
    assert fs.filter_in_stock(qs, "in_stock", "") is qs
    assert fs.filter_in_stock(qs, "in_stock", "maybe") is qs


@pytest.mark.django_db
def test_attribute_backend_skips_empty_and_filters_slug() -> None:
    """Empty facet params skipped; leftover Attribute.slug filters apply."""
    cat = Category.objects.create(name="C", slug="c-attrf")
    product = Product.objects.create(name="P", slug="p-attrf", category=cat)
    sku = SKU.objects.create(product=product, name="S", slug="s-attrf", sku_code="AF1")
    attr = Attribute.objects.create(name="Цвет", slug="color-custom", unit="")
    AttributeValue.objects.create(sku=sku, attribute=attr, value="красный")
    other = SKU.objects.create(
        product=product,
        name="S2",
        slug="s-attrf-2",
        sku_code="AF2",
    )
    AttributeValue.objects.create(sku=other, attribute=attr, value="синий")

    factory = APIRequestFactory()
    backend = AttributeQueryFilterBackend()
    view = MagicMock()

    empty = Request(factory.get("/api/skus/", {"moment": ""}))
    qs = SKU.objects.filter(pk__in=[sku.pk, other.pk])
    assert backend.filter_queryset(empty, qs, view).count() == 2

    filtered = Request(factory.get("/api/skus/", {"color-custom": "красный"}))
    out = backend.filter_queryset(filtered, qs, view)
    assert list(out.values_list("sku_code", flat=True)) == ["AF1"]

    schema = backend.get_schema_operation_parameters(view)
    assert any(p["name"] == "moment" for p in schema)
    assert any(p["name"] == "in_stock" for p in schema)


@pytest.mark.django_db
def test_family_heading_and_analogs_helpers() -> None:
    """Helpers: no product → None; blank analogs_text → \"\"."""
    sku = SKU(name="x", slug="x-h", sku_code="XH1")
    sku.product_id = None  # type: ignore[assignment]
    assert _family_list_heading(sku) is None

    cat = Category.objects.create(name="C", slug="c-ser")
    product = Product.objects.create(
        name="Series",
        slug="p-ser",
        category=cat,
        analogs_text="Belimo LM24A",
    )
    row = SKU.objects.create(
        product=product,
        name="S",
        slug="s-ser",
        sku_code="SER1",
        analogs_text="   ",
    )
    assert _sku_analogs_text(row) == ""
    # Unsaved None uses product inherit path in the helper.
    unsaved = SKU(
        product=product,
        name="S2",
        slug="s-ser-2",
        sku_code="SER2",
        analogs_text=None,  # type: ignore[arg-type]
    )
    inherited = _sku_analogs_text(unsaved)
    assert inherited == "" or "Belimo" in inherited or "LM24" in inherited


def test_seo_sanitize_helpers() -> None:
    """Slug validation, path normalize, and plain-text meta trim."""
    assert validate_slug("ok-slug") == "ok-slug"
    with pytest.raises(Http404):
        validate_slug("")
    assert normalize_spa_path("/catalog/foo/") == "/catalog/foo"
    with pytest.raises(Http404):
        normalize_spa_path("/../etc")
    assert plain_text_for_meta("<b>Hi</b> there", max_len=10).startswith("Hi")
    long = "слово " * 40
    assert plain_text_for_meta(long, max_len=20).endswith("…")
