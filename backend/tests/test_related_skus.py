"""Tests for article → mentioned SKU resolution."""

from __future__ import annotations

import pytest

from content.related_skus import extract_model_tokens, mentioned_skus_for_article


def test_extract_model_tokens_from_copy() -> None:
    """Series and edition codes are detected in free text."""
    text = "См. DA3FU24/230-D/DS и SA10MU230-DS, также BV215."
    tokens = extract_model_tokens(text)
    assert any(t.startswith("DA3FU") for t in tokens)
    assert any(t.startswith("SA10MU") for t in tokens)
    assert "BV215" in tokens


@pytest.mark.django_db
def test_mentioned_skus_one_per_product() -> None:
    """Matching SKUs are returned, at most one edition per product line."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C", slug="c-rel")
    p1 = Product.objects.create(name="DA3FU 3", slug="dafu-3", category=cat)
    p2 = Product.objects.create(name="SA10MU", slug="sa10mu", category=cat)
    SKU.objects.create(
        product=p1,
        name="DA3FU230-D",
        slug="da3fu230-d-rel",
        sku_code="da3fu230-d",
    )
    SKU.objects.create(
        product=p1,
        name="DA3FU24-D",
        slug="da3fu24-d-rel",
        sku_code="da3fu24-d",
    )
    SKU.objects.create(
        product=p2,
        name="SA10MU24-DS",
        slug="sa10mu24-ds-rel",
        sku_code="SA10MU24-DS",
    )
    found = mentioned_skus_for_article(
        "Привод DA3FU230-D и серия SA10MU для дымоудаления",
        limit=8,
    )
    codes = {s.sku_code.lower() for s in found}
    assert "da3fu230-d" in codes or "da3fu24-d" in codes
    assert len([s for s in found if s.product_id == p1.pk]) == 1
    assert any(s.product_id == p2.pk for s in found)


@pytest.mark.django_db
def test_hva5q_does_not_match_hva5qx() -> None:
    """``HVA-5Q`` must not resolve to capacitor ``HVA-5QX`` (or UQ↔Q)."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="HV", slug="hv-rel-q")
    p_qx = Product.objects.create(
        name="HVA-5QX",
        slug="privod-vozdushniy-kondensator-hva-5qx",
        category=cat,
    )
    p_q = Product.objects.create(
        name="HVA-5Q",
        slug="privod-vozdushniy-hva-5q",
        category=cat,
    )
    p_uq = Product.objects.create(
        name="HVA-5UQ",
        slug="privod-vozdushniy-hva-5uq",
        category=cat,
    )
    SKU.objects.create(
        product=p_qx,
        name="HVA230-5QX",
        slug="hva230-5qx-rel",
        sku_code="HVA230-5QX",
        is_published=True,
    )
    SKU.objects.create(
        product=p_q,
        name="HVA230-5Q",
        slug="hva230-5q-rel",
        sku_code="HVA230-5Q",
        is_published=True,
    )
    SKU.objects.create(
        product=p_uq,
        name="HVA24-5UQ",
        slug="hva24-5uq-rel",
        sku_code="HVA24-5UQ",
        is_published=True,
    )
    found_q = mentioned_skus_for_article("Ориентир HVA-5Q — меньше 20 с", limit=8)
    codes_q = {s.sku_code.upper() for s in found_q}
    assert "HVA230-5Q" in codes_q
    assert "HVA230-5QX" not in codes_q

    found_uq = mentioned_skus_for_article("Сверхбыстрый HVA-5UQ около 2,5 с", limit=8)
    codes_uq = {s.sku_code.upper() for s in found_uq}
    assert "HVA24-5UQ" in codes_uq
    assert "HVA230-5QX" not in codes_uq


@pytest.mark.django_db
def test_da8mu_does_not_match_da8mqu() -> None:
    """``DA8MU`` must not resolve to accelerated ``DA8MQU``."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="DA", slug="da-rel-mu")
    p_mu = Product.objects.create(name="DA8MU", slug="damu-8", category=cat)
    p_mqu = Product.objects.create(name="DA8MQU", slug="damqu-8", category=cat)
    SKU.objects.create(
        product=p_mu,
        name="DA8MU230-A",
        slug="da8mu230-a-rel",
        sku_code="DA8MU230-A",
        is_published=True,
    )
    SKU.objects.create(
        product=p_mqu,
        name="DA8MQU230-A",
        slug="da8mqu230-a-rel",
        sku_code="DA8MQU230-A",
        is_published=True,
    )
    found = mentioned_skus_for_article("Пример DA8MU — меньше 55 с", limit=8)
    codes = {s.sku_code.upper() for s in found}
    assert "DA8MU230-A" in codes
    assert "DA8MQU230-A" not in codes

    """Serializer returns root-relative ``/media/...`` image path."""
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.test import RequestFactory
    from PIL import Image

    from catalog.models import SKU, Category, Product, ProductImage
    from content.serializers import ArticleRelatedSkuSerializer

    cat = Category.objects.create(name="C", slug="c-img-rel")
    product = Product.objects.create(name="P", slug="p-img-rel", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="DA1MU24-D",
        slug="da1mu24-d-img",
        sku_code="da1mu24-d",
        is_published=True,
    )
    buf = BytesIO()
    Image.new("RGB", (4, 4), color=(10, 20, 30)).save(buf, format="JPEG")
    ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile("x.jpg", buf.getvalue(), content_type="image/jpeg"),
        alt="x",
        sort_order=0,
        is_published=True,
    )
    request = RequestFactory().get("/")
    data = ArticleRelatedSkuSerializer(sku, context={"request": request}).data
    assert data["sku_code"] == "da1mu24-d"
    assert data["image"] is not None
    assert data["image"].startswith("/media/")
    assert "://" not in data["image"]

    bare = ArticleRelatedSkuSerializer(sku, context={}).data
    assert bare["image"] is not None
    assert bare["image"].startswith("/media/")
