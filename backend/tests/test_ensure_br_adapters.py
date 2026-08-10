"""Tests for BR-M / BR-ML adapter ensure ETL (local enhanced photos)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PIL import Image

from catalog.etl.ensure_br_adapters import (
    adapters_data_dir,
    ensure_br_adapters,
    resolve_adapter_photo_bytes,
)
from catalog.etl.webp import enhance_transparent_catalog_photo_bytes
from catalog.models import SKU, AttributeValue, Category, ProductImage


def _png_bytes(size: tuple[int, int] = (120, 80)) -> bytes:
    from io import BytesIO

    buf = BytesIO()
    Image.new("RGB", size, color=(200, 40, 40)).save(buf, format="PNG")
    return buf.getvalue()


def test_resolve_adapter_photo_uses_committed_nobg_pack() -> None:
    """Committed ``*-nobg-source.png`` enhance to ~1600 transparent WebP."""
    from io import BytesIO

    from catalog.etl.webp import enhance_transparent_catalog_photo_bytes

    data = adapters_data_dir()
    assert (data / "br-m-nobg-source.png").is_file()
    assert (data / "br-ml-nobg-source.png").is_file()
    webp = resolve_adapter_photo_bytes("br-m")
    with Image.open(BytesIO(webp)) as img:
        assert max(img.size) >= 1500
        assert img.mode in {"RGBA", "RGB"}
        assert img.format == "WEBP"

    tiny = enhance_transparent_catalog_photo_bytes(_png_bytes((100, 90)))
    with Image.open(BytesIO(tiny)) as img:
        assert max(img.size) >= 1500


def test_enhance_catalog_photo_upscales_small_thumbs() -> None:
    """Opaque dealer thumbs grow toward the enhance target edge."""
    from io import BytesIO

    from catalog.etl.webp import enhance_catalog_photo_bytes

    webp = enhance_catalog_photo_bytes(_png_bytes((200, 180)))
    with Image.open(BytesIO(webp)) as img:
        assert max(img.size) >= 1000
        assert img.format == "WEBP"


@pytest.mark.django_db
def test_ensure_br_adapters_creates_cards_and_images() -> None:
    """BR-M / BR-ML land in adaptery with local heroes (no partner URL)."""
    summary = ensure_br_adapters(dry_run=False)

    assert summary["products_created"] == 2
    assert summary["skus_created"] == 2
    assert summary["images"] == {"BR-M": "written", "BR-ML": "written"}

    cat = Category.objects.get(slug="adaptery")
    assert cat.name == "Адаптеры"

    br_m = SKU.objects.get(sku_code="BR-M")
    br_ml = SKU.objects.get(sku_code="BR-ML")
    assert br_m.product.category_id == cat.id
    assert br_ml.product.category_id == cat.id
    assert br_m.is_published and br_ml.is_published

    hero = ProductImage.objects.get(sku=br_m, is_published=True)
    assert hero.source_url.startswith("https://hoocon.ru/.local-assets/adapters-br/")
    assert "hoocon.spb.ru" not in (hero.source_url or "")
    assert hero.image.name.endswith(".webp")
    assert hero.image_card  # auto on save

    by_slug = {
        av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=br_m).select_related("attribute")
    }
    assert by_slug["drive-kind"] == "без возвратной пружины (MU / MQU)"
    assert by_slug["compatible-actuators"] == "DA4MU…DA16MU, DA8MQU…DA16MQU (24/230 В)"
    assert "не DA" not in by_slug["compatible-actuators"]
    br_ml_attrs = {
        av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=br_ml).select_related("attribute")
    }
    assert br_ml_attrs["compatible-actuators"] == "DA5FU (24/230 В)"
    assert "не DA" not in br_ml_attrs["compatible-actuators"]
    assert "DA4MU" in br_m.description
    assert "DA3FU" not in br_ml.description
    assert "DA5FU24" in br_ml.description
    for omitted in (
        "manufacturer",
        "trademark",
        "warranty",
        "country-of-origin",
        "brand-origin",
    ):
        assert omitted not in by_slug

    again = ensure_br_adapters(dry_run=False)
    assert again["products_created"] == 0
    assert again["skus_created"] == 0
    assert again["images"] == {"BR-M": "exists", "BR-ML": "exists"}


@pytest.mark.django_db
def test_ensure_br_adapters_force_images_rewrites_local_hero() -> None:
    """``--force-images`` re-enhances from the local pack."""
    ensure_br_adapters(dry_run=False)
    br_m = SKU.objects.get(sku_code="BR-M")
    first = ProductImage.objects.get(sku=br_m, is_published=True)
    size_before = first.image.size

    with patch(
        "catalog.etl.ensure_br_adapters.resolve_adapter_photo_bytes",
        return_value=enhance_transparent_catalog_photo_bytes(_png_bytes((160, 100))),
    ):
        summary = ensure_br_adapters(dry_run=False, force_images=True)

    assert summary["images"]["BR-M"] == "written"
    first.refresh_from_db()
    assert first.is_published is True
    assert first.image.size != size_before
    assert "hoocon.spb.ru" not in (first.source_url or "")
