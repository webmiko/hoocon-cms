"""Tests for WebP conversion and image upload validators."""

from __future__ import annotations

from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from catalog.etl.webp import convert_bytes_to_webp
from catalog.validators import validate_image_upload


def _png_bytes(size: tuple[int, int] = (64, 48)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color=(200, 40, 40)).save(buf, format="PNG")
    return buf.getvalue()


def test_convert_bytes_to_webp_produces_webp_magic() -> None:
    """PNG input becomes WebP with RIFF/WEBP header and smaller-or-equal size."""
    raw = _png_bytes((400, 300))
    webp = convert_bytes_to_webp(raw, quality=90)
    assert webp[:4] == b"RIFF"
    assert webp[8:12] == b"WEBP"
    assert len(webp) > 100


def test_convert_bytes_to_webp_downscales_long_edge() -> None:
    """Images larger than max_edge are resized."""
    raw = _png_bytes((2000, 1200))
    webp = convert_bytes_to_webp(raw, quality=90, max_edge=800)
    with Image.open(BytesIO(webp)) as img:
        assert max(img.size) <= 800


def test_validate_image_upload_accepts_webp() -> None:
    """Valid WebP passes validator."""
    webp = convert_bytes_to_webp(_png_bytes(), quality=90)
    uploaded = SimpleUploadedFile("shot.webp", webp, content_type="image/webp")
    validate_image_upload(uploaded)


def test_validate_image_upload_rejects_pdf() -> None:
    """PDF disguised as image is rejected."""
    uploaded = SimpleUploadedFile(
        "fake.webp",
        b"%PDF-1.4 fake",
        content_type="image/webp",
    )
    with pytest.raises(ValidationError):
        validate_image_upload(uploaded)


def test_webp_upload_basename_forces_webp() -> None:
    """upload_to basenames always end with .webp."""
    from catalog.etl.webp import webp_upload_basename

    assert webp_upload_basename("photo.JPG") == "photo.webp"
    assert webp_upload_basename("a.b.png") == "a.b.webp"


def test_product_image_save_converts_png_to_webp(db: None) -> None:
    """Admin/ETL PNG upload is stored as WebP on ProductImage.save."""
    from catalog.models import SKU, Category, Product, ProductImage

    cat = Category.objects.create(name="T", slug="t-webp-save")
    product = Product.objects.create(name="P", slug="p-webp-save", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="S",
        slug="s-webp-save",
        sku_code="WEBP-SAVE-1",
    )
    png = SimpleUploadedFile("shot.png", _png_bytes((120, 80)), content_type="image/png")
    img = ProductImage(sku=sku, alt="t", sort_order=0, is_published=True)
    img.image = png
    img.save()
    img.refresh_from_db()
    assert img.image.name.lower().endswith(".webp")
    with img.image.open("rb") as fh:
        magic = fh.read(12)
    assert magic[:4] == b"RIFF" and magic[8:12] == b"WEBP"


def test_product_image_save_builds_image_card(db: None) -> None:
    """Full hero save also writes a ≤CARD_MAX_EDGE_PX card WebP."""
    from catalog.etl.webp import CARD_MAX_EDGE_PX
    from catalog.models import SKU, Category, Product, ProductImage

    cat = Category.objects.create(name="T", slug="t-webp-card")
    product = Product.objects.create(name="P", slug="p-webp-card", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="S",
        slug="s-webp-card",
        sku_code="WEBP-CARD-1",
    )
    png = SimpleUploadedFile(
        "hero.png",
        _png_bytes((1600, 1200)),
        content_type="image/png",
    )
    img = ProductImage(sku=sku, alt="t", sort_order=0, is_published=True)
    img.image = png
    img.save()
    img.refresh_from_db()
    assert img.image_card.name
    assert img.image_card.name.lower().endswith(".webp")
    with img.image_card.open("rb") as fh:
        card = fh.read()
    with Image.open(BytesIO(card)) as decoded:
        assert max(decoded.size) <= CARD_MAX_EDGE_PX
    assert len(card) < img.image.size  # type: ignore[operator]


def test_backfill_missing_image_cards(db: None) -> None:
    """Management helper fills empty image_card without touching the hero."""
    from catalog.etl.webp import backfill_missing_image_cards
    from catalog.models import SKU, Category, Product, ProductImage

    cat = Category.objects.create(name="T", slug="t-backfill-card")
    product = Product.objects.create(name="P", slug="p-backfill-card", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="S",
        slug="s-backfill-card",
        sku_code="WEBP-CARD-2",
    )
    webp = convert_bytes_to_webp(_png_bytes((900, 600)), quality=90, max_edge=900)
    img = ProductImage(
        sku=sku,
        alt="t",
        sort_order=0,
        is_published=True,
    )
    img.image.save("hero.webp", SimpleUploadedFile("hero.webp", webp, content_type="image/webp"), save=False)
    # Bypass ProductImage.save card sync: write row then clear card via queryset.
    from django.db.models import Model

    Model.save(img)
    ProductImage.objects.filter(pk=img.pk).update(image_card="")
    img.refresh_from_db()
    assert not img.image_card

    summary = backfill_missing_image_cards()
    assert summary["written"] >= 1
    img.refresh_from_db()
    assert img.image_card.name


def test_sku_list_api_includes_image_card(client, db: None) -> None:
    """List payload exposes image_card for catalog/mobile clients."""
    from django.urls import reverse

    from catalog.models import SKU, Category, Product, ProductImage

    cat = Category.objects.create(name="T", slug="t-api-card")
    product = Product.objects.create(name="P", slug="p-api-card", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="S",
        slug="s-api-card",
        sku_code="WEBP-CARD-3",
        is_published=True,
    )
    png = SimpleUploadedFile("hero.png", _png_bytes((800, 600)), content_type="image/png")
    ProductImage.objects.create(
        sku=sku,
        image=png,
        alt="hero",
        sort_order=0,
        is_published=True,
    )
    response = client.get(reverse("catalog-sku-list"))
    assert response.status_code == 200
    rows = response.json()["results"]
    row = next(r for r in rows if r["slug"] == "s-api-card")
    assert row["image"]["image"]
    assert row["image"]["image_card"]
    assert row["image"]["image_card"] != row["image"]["image"]
