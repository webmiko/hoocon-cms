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
def test_article_related_sku_serializer_image() -> None:
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
