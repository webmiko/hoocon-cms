"""freeze_product_images / verify_product_images management commands."""

from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from PIL import Image

from catalog.models import SKU, Category, Product, ProductImage

pytestmark = pytest.mark.django_db


def _webp(color: str = "red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, format="WEBP")
    return buf.getvalue()


def _make_sku(code: str) -> SKU:
    category = Category.objects.create(name="Приводы", slug=f"freeze-cat-{code.casefold()}")
    product = Product.objects.create(category=category, name=code, slug=f"freeze-product-{code.casefold()}")
    return SKU.objects.create(
        product=product,
        sku_code=code,
        name=code,
        slug=f"freeze-sku-{code.casefold()}",
        is_published=True,
    )


def _create_image(sku: SKU, *, filename: str) -> ProductImage:
    return ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile(filename, _webp(), content_type="image/webp"),
        alt=filename,
        sort_order=0,
        is_published=True,
    )


@pytest.fixture
def media_env(settings, tmp_path) -> Path:
    settings.MEDIA_ROOT = str(tmp_path / "media")
    return tmp_path


def test_freeze_dry_run_lists_rows_without_locking_or_manifest(media_env: Path) -> None:
    sku = _make_sku("DA5FU24-D")
    row = _create_image(sku, filename="da5fu-wiring.webp")
    reports_dir = media_env / "reports"
    out = io.StringIO()

    call_command(
        "freeze_product_images",
        "--scope",
        "all",
        "--sku",
        sku.sku_code,
        "--reports-dir",
        str(reports_dir),
        stdout=out,
    )

    row.refresh_from_db()
    assert row.image_locked is False
    assert sku.sku_code in out.getvalue()
    assert row.image.name in out.getvalue()
    assert not list(reports_dir.glob("product-images-manifest-*.csv"))


def test_freeze_schemes_locks_only_scheme_names_and_writes_manifest(media_env: Path) -> None:
    sku = _make_sku("DA5FU24-D")
    scheme = _create_image(sku, filename="da5fu-wiring.webp")
    hero = _create_image(sku, filename="da5fu-hero.webp")
    reports_dir = media_env / "reports"
    out = io.StringIO()

    call_command(
        "freeze_product_images",
        "--scope",
        "schemes",
        "--yes",
        "--reports-dir",
        str(reports_dir),
        stdout=out,
    )

    scheme.refresh_from_db()
    hero.refresh_from_db()
    assert scheme.image_locked is True
    assert scheme.locked_at is not None
    assert scheme.locked_by == "freeze_product_images"
    assert hero.image_locked is False

    manifests = list(reports_dir.glob("product-images-manifest-*.csv"))
    assert len(manifests) == 1
    with manifests[0].open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    payload = Path(scheme.image.path).read_bytes()
    assert rows[0]["sku"] == sku.sku_code
    assert rows[0]["image"] == scheme.image.name
    assert rows[0]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert int(rows[0]["size_bytes"]) == len(payload)
    assert rows[0]["locked_at"]


def test_freeze_scope_all_honors_series_and_excluded_skus(media_env: Path) -> None:
    keep = _make_sku("DA5FU24-D")
    excluded = _make_sku("DA10FU24-D")
    other = _make_sku("SA5FU24-D")
    keep_image = _create_image(keep, filename="da5fu-photo.webp")
    excluded_image = _create_image(excluded, filename="da10fu-photo.webp")
    other_image = _create_image(other, filename="sa5fu-photo.webp")
    reports_dir = media_env / "reports"
    exclude_file = media_env / "freeze-exclude.txt"
    exclude_file.write_text(f"# артикулы владельца\n{excluded.sku_code}\n", encoding="utf-8")

    call_command(
        "freeze_product_images",
        "--scope",
        "all",
        "--series",
        "da",
        "--exclude-file",
        str(exclude_file),
        "--yes",
        "--reports-dir",
        str(reports_dir),
        stdout=io.StringIO(),
    )

    keep_image.refresh_from_db()
    excluded_image.refresh_from_db()
    other_image.refresh_from_db()
    assert keep_image.image_locked is True
    assert excluded_image.image_locked is False
    assert other_image.image_locked is False


def test_verify_product_images_accepts_frozen_manifest_and_detects_drift(media_env: Path) -> None:
    sku = _make_sku("DA5FU24-D")
    row = _create_image(sku, filename="da5fu-wiring.webp")
    reports_dir = media_env / "reports"
    call_command(
        "freeze_product_images",
        "--scope",
        "schemes",
        "--yes",
        "--reports-dir",
        str(reports_dir),
        stdout=io.StringIO(),
    )
    manifest = next(reports_dir.glob("product-images-manifest-*.csv"))
    out = io.StringIO()

    call_command("verify_product_images", "--manifest", str(manifest), stdout=out)
    assert "mismatches=0" in out.getvalue()

    Path(row.image.path).write_bytes(_webp("blue"))
    with pytest.raises(CommandError):
        call_command("verify_product_images", "--manifest", str(manifest), stdout=io.StringIO())
