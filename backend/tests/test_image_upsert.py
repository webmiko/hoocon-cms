"""ETL image upsert is idempotent (M42).

Before: every media/diagram rerun re-saved the file (new storage name,
card re-render) and the promised ``skip`` was never returned.
"""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from PIL import Image

from catalog.etl.image_upsert import upsert_sku_image
from catalog.etl.manual_diagrams import DiagramCrop, _upsert_diagram
from catalog.models import SKU, Category, Product, ProductImage

pytestmark = pytest.mark.django_db


def _webp(color: str = "red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, format="WEBP")
    return buf.getvalue()


@pytest.fixture
def sku(settings, tmp_path) -> SKU:
    settings.MEDIA_ROOT = str(tmp_path)
    category = Category.objects.create(name="Приводы", slug="drives-upsert")
    product = Product.objects.create(category=category, name="DA", slug="da-upsert")
    return SKU.objects.create(product=product, sku_code="DA2-UPS", name="DA2", slug="da2-ups")


def _upsert(sku: SKU, webp: bytes, *, alt: str = "DA2 | схема", dry_run: bool = False):
    return upsert_sku_image(
        sku,
        source_url="https://hoocon.ru/etl/test/wiring",
        filename="da2-ups-wiring.webp",
        webp=webp,
        alt=alt,
        sort_order=20,
        dry_run=dry_run,
    )


def test_rerun_with_same_bytes_is_skip_without_storage_write(sku: SKU) -> None:
    webp = _webp()
    assert _upsert(sku, webp)[0] == "create"
    name_before = ProductImage.objects.get(sku=sku).image.name

    with patch("django.db.models.fields.files.FieldFile.save") as file_save:
        action, image = _upsert(sku, webp)
    assert action == "skip"
    file_save.assert_not_called()
    assert image is not None and image.image.name == name_before
    assert ProductImage.objects.filter(sku=sku).count() == 1


def test_dry_run_reports_skip_for_unchanged_image(sku: SKU) -> None:
    webp = _webp()
    _upsert(sku, webp)
    assert _upsert(sku, webp, dry_run=True)[0] == "skip"
    assert _upsert(sku, _webp("blue"), dry_run=True)[0] == "update"


def test_metadata_change_updates_row_without_rewriting_file(sku: SKU) -> None:
    webp = _webp()
    _upsert(sku, webp)
    with patch("django.db.models.fields.files.FieldFile.save") as file_save:
        action, image = _upsert(sku, webp, alt="DA2 | новая подпись")
    assert action == "update"
    file_save.assert_not_called()
    assert image is not None and image.alt == "DA2 | новая подпись"


def test_new_bytes_replace_file(sku: SKU) -> None:
    _upsert(sku, _webp("red"))
    action, image = _upsert(sku, _webp("blue"))
    assert action == "update"
    assert image is not None
    with image.image.open("rb") as handle:
        assert handle.read() == _webp("blue")


def test_missing_stored_file_is_reuploaded(sku: SKU) -> None:
    webp = _webp()
    _, image = _upsert(sku, webp)
    assert image is not None
    image.image.storage.delete(image.image.name)
    action, _ = _upsert(sku, webp)
    assert action == "update"
    refreshed = ProductImage.objects.get(pk=image.pk)
    assert refreshed.image.storage.exists(refreshed.image.name)


def test_editor_hidden_image_stays_hidden_and_counts_as_skip(sku: SKU) -> None:
    webp = _webp()
    _, image = _upsert(sku, webp)
    assert image is not None
    ProductImage.objects.filter(pk=image.pk).update(is_published=False, hidden_by_editor=True)
    action, _ = _upsert(sku, webp)
    assert action == "skip"
    assert ProductImage.objects.get(pk=image.pk).is_published is False


def test_manual_diagram_rerun_returns_skip(sku: SKU) -> None:
    """The manual-diagram ETL (one of the former copies) now reports ``skip``."""
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "green").save(buf, format="PNG")
    crop = DiagramCrop(
        kind="wiring",
        png_bytes=buf.getvalue(),
        alt="DA2 | схема подключения",
        source_url="https://hoocon.ru/manual/da2/wiring",
        sort_order=30,
    )
    assert _upsert_diagram(sku, crop, dry_run=False) == "create"
    assert _upsert_diagram(sku, crop, dry_run=False) == "skip"
