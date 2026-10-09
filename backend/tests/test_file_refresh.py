"""ETL manual PDFs refresh by content hash (M45).

Before: ``existing.file.size`` raised FileNotFoundError when the stored PDF
was gone (aborting the whole batch), and a same-size edit was never picked up.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.base import ContentFile

from catalog.etl.file_refresh import refresh_product_file
from catalog.etl.manual_pdfs import attach_dafu_manuals
from catalog.models import SKU, Category, Product, ProductFile

pytestmark = pytest.mark.django_db


@pytest.fixture
def sku(settings, tmp_path) -> SKU:
    settings.MEDIA_ROOT = str(tmp_path / "media")
    category = Category.objects.create(name="Приводы", slug="drives-pdf")
    product = Product.objects.create(category=category, name="DAFU", slug="dafu-pdf")
    return SKU.objects.create(product=product, sku_code="DA5FU24-D", name="DA5FU24-D", slug="da5fu24-d")


def _row(sku: SKU, payload: bytes) -> ProductFile:
    row = ProductFile(sku=sku, title="Инструкция", file_type=ProductFile.FileType.DATASHEET)
    row.file.save("manual.pdf", ContentFile(payload), save=True)
    return row


def _read(row: ProductFile) -> bytes:
    row.refresh_from_db()
    with row.file.open("rb") as handle:
        return handle.read()


def test_same_bytes_are_not_rewritten(sku: SKU) -> None:
    row = _row(sku, b"%PDF-v1")
    name = row.file.name
    assert refresh_product_file(row, basename="manual.pdf", payload=b"%PDF-v1") is False
    row.refresh_from_db()
    assert row.file.name == name


def test_same_size_edit_is_detected(sku: SKU) -> None:
    row = _row(sku, b"%PDF-v1")
    assert refresh_product_file(row, basename="manual.pdf", payload=b"%PDF-v2") is True
    assert _read(row) == b"%PDF-v2"


def test_missing_stored_file_is_repaired(sku: SKU) -> None:
    row = _row(sku, b"%PDF-v1")
    row.file.storage.delete(row.file.name)
    assert refresh_product_file(row, basename="manual.pdf", payload=b"%PDF-v1") is True
    assert _read(row) == b"%PDF-v1"


def test_attach_batch_survives_row_with_missing_file(sku: SKU, tmp_path: Path) -> None:
    manuals = tmp_path / "manuals"
    manuals.mkdir()
    (manuals / "da5fu-d:ds.pdf").write_bytes(b"%PDF-v1")
    attach_dafu_manuals(manuals)
    row = ProductFile.objects.get(sku=sku)
    row.file.storage.delete(row.file.name)

    (manuals / "da5fu-d:ds.pdf").write_bytes(b"%PDF-v2")
    summary = attach_dafu_manuals(manuals)
    assert summary["updated"] == 1
    assert _read(row) == b"%PDF-v2"
