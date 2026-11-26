"""Approved ProductImage rows stay frozen until an explicit Admin edit."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from catalog.etl.file_refresh import stored_sha256
from catalog.etl.manual_diagrams import unpublish_legacy_combined_photos
from catalog.etl.product_image_audit import (
    optimize_non_webp_images,
    prune_inferior_hero_duplicates,
    restore_secondary_gallery_angles,
)
from catalog.etl.series_copy_ball_valves import _refresh_gallery_row
from catalog.etl.webp import backfill_missing_image_cards
from catalog.models import ADMIN_EDIT_FLAG, SKU, Category, Product, ProductImage

pytestmark = pytest.mark.django_db


def _webp(color: str = "red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, format="WEBP")
    return buf.getvalue()


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "green").save(buf, format="PNG")
    return buf.getvalue()


def _make_sku(code: str) -> SKU:
    category = Category.objects.create(name="Приводы", slug=f"lock-cat-{code.casefold()}")
    product = Product.objects.create(category=category, name=code, slug=f"lock-product-{code.casefold()}")
    return SKU.objects.create(
        product=product,
        sku_code=code,
        name=code,
        slug=f"lock-sku-{code.casefold()}",
        is_published=True,
    )


@pytest.fixture
def sku(settings, tmp_path) -> SKU:
    settings.MEDIA_ROOT = str(tmp_path / "media")
    return _make_sku("DA5FU24-D")


def _create_image(
    sku: SKU,
    *,
    filename: str = "hero.webp",
    alt: str = "hero",
    sort_order: int = 0,
    is_published: bool = True,
    source_url: str = "",
) -> ProductImage:
    row = ProductImage(
        sku=sku,
        alt=alt,
        source_url=source_url,
        sort_order=sort_order,
        is_published=is_published,
    )
    row.image.save(
        filename,
        SimpleUploadedFile(filename, _webp(), content_type="image/webp"),
        save=False,
    )
    row.save()
    row.refresh_from_db()
    return row


def _media_files(media_root: str) -> set[str]:
    root = Path(media_root)
    return {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()}


def _lock(row: ProductImage) -> None:
    ProductImage.objects.filter(pk=row.pk).update(image_locked=True)


def test_locked_image_survives_non_admin_save_without_orphan(settings, sku: SKU) -> None:
    row = _create_image(sku, alt="approved", sort_order=3)
    _lock(row)
    row.refresh_from_db()
    original = {
        "image": row.image.name,
        "image_card": row.image_card.name,
        "sha256": stored_sha256(row.image),
        "alt": row.alt,
        "sort_order": row.sort_order,
        "is_published": row.is_published,
    }
    files_before = _media_files(settings.MEDIA_ROOT)

    row.image = SimpleUploadedFile("replacement.webp", _webp("blue"), content_type="image/webp")
    row.alt = "ETL rewrite"
    row.sort_order = 99
    row.is_published = False
    row.save()

    row.refresh_from_db()
    assert row.image.name == original["image"]
    assert row.image_card.name == original["image_card"]
    assert stored_sha256(row.image) == original["sha256"]
    assert row.alt == original["alt"]
    assert row.sort_order == original["sort_order"]
    assert row.is_published is original["is_published"]
    assert _media_files(settings.MEDIA_ROOT) == files_before


def test_unlocked_image_non_admin_save_behaves_as_before(sku: SKU) -> None:
    row = _create_image(sku, alt="before", sort_order=3)
    original_hash = stored_sha256(row.image)

    row.image = SimpleUploadedFile("replacement.webp", _webp("blue"), content_type="image/webp")
    row.alt = "ETL rewrite"
    row.sort_order = 99
    row.is_published = False
    row.save()

    row.refresh_from_db()
    assert row.alt == "ETL rewrite"
    assert row.sort_order == 99
    assert row.is_published is False
    assert stored_sha256(row.image) != original_hash


def test_admin_flag_save_can_replace_locked_image(sku: SKU) -> None:
    row = _create_image(sku, alt="approved")
    _lock(row)
    row.refresh_from_db()
    replacement = _webp("blue")

    row.image = SimpleUploadedFile("replacement.webp", replacement, content_type="image/webp")
    row.alt = "admin replacement"
    row.__dict__[ADMIN_EDIT_FLAG] = True
    row.save()

    row.refresh_from_db()
    assert row.alt == "admin replacement"
    assert stored_sha256(row.image) == hashlib.sha256(replacement).hexdigest()


def test_locked_row_is_not_backfilled_with_a_new_card(settings, sku: SKU) -> None:
    row = _create_image(sku)
    ProductImage.objects.filter(pk=row.pk).update(image_card="", image_locked=True)
    files_before = _media_files(settings.MEDIA_ROOT)

    summary = backfill_missing_image_cards()

    row.refresh_from_db()
    assert summary["written"] == 0
    assert not row.image_card
    assert _media_files(settings.MEDIA_ROOT) == files_before


def test_non_webp_optimize_does_not_rewrite_locked_file(settings, sku: SKU) -> None:
    row = _create_image(sku)
    payload = _png()
    rel_name = str(Path(row.image.name).with_name("legacy.png")).replace("\\", "/")
    legacy_path = Path(settings.MEDIA_ROOT) / rel_name
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_bytes(payload)
    ProductImage.objects.filter(pk=row.pk).update(image=rel_name, image_locked=True)

    summary = optimize_non_webp_images(dry_run=False)

    row.refresh_from_db()
    assert summary["converted"] == 0
    assert row.image.name == rel_name
    assert legacy_path.read_bytes() == payload


def test_bulk_unpublish_helpers_skip_locked_rows(sku: SKU) -> None:
    locked = _create_image(sku, filename="combined-locked.webp", alt="размеры и способ подключения")
    unlocked = _create_image(sku, filename="combined-free.webp", alt="размеры и способ подключения")
    _lock(locked)

    changed = unpublish_legacy_combined_photos(dry_run=False)

    locked.refresh_from_db()
    unlocked.refresh_from_db()
    assert changed == 1
    assert locked.is_published is True
    assert unlocked.is_published is False


def test_restore_secondary_angles_skips_locked_rows(sku: SKU) -> None:
    locked = _create_image(sku, filename="locked-angle.webp", alt="DA5FU | фото 2", is_published=False)
    unlocked = _create_image(sku, filename="free-angle.webp", alt="DA5FU | фото 3", is_published=False)
    _lock(locked)

    summary = restore_secondary_gallery_angles(dry_run=False)

    locked.refresh_from_db()
    unlocked.refresh_from_db()
    assert summary["restored"] == 1
    assert locked.is_published is False
    assert unlocked.is_published is True


def test_locked_best_hero_still_wins_and_unlocked_duplicate_is_pruned(sku: SKU) -> None:
    locked = _create_image(
        sku,
        filename="locked-hero.webp",
        source_url="https://hoocon.ru/.local-assets/da5fu24d-product.webp",
    )
    unlocked = _create_image(
        sku,
        filename="free-hero.webp",
        source_url="https://static.tildacdn.com/da5fu24d-product.webp",
    )
    _lock(locked)

    summary = prune_inferior_hero_duplicates(dry_run=False)

    locked.refresh_from_db()
    unlocked.refresh_from_db()
    assert summary["unpublished"] == 1
    assert locked.is_published is True
    assert unlocked.is_published is False


def test_refresh_gallery_row_does_not_rewrite_or_duplicate_locked_row(sku: SKU) -> None:
    source_url = "https://hoocon.ru/gallery/locked.webp"
    locked = _create_image(
        sku,
        filename="gallery-locked.webp",
        source_url=source_url,
        sort_order=7,
        is_published=False,
    )
    _lock(locked)

    assert _refresh_gallery_row(sku, source_url, sort_order=2, dry_run=False) is True

    locked.refresh_from_db()
    assert locked.sort_order == 7
    assert locked.is_published is False
    assert ProductImage.objects.filter(sku=sku, source_url=source_url).count() == 1

    free_url = "https://hoocon.ru/gallery/free.webp"
    free = _create_image(
        sku,
        filename="gallery-free.webp",
        source_url=free_url,
        sort_order=7,
        is_published=False,
    )
    assert _refresh_gallery_row(sku, free_url, sort_order=2, dry_run=False) is True
    free.refresh_from_db()
    assert free.sort_order == 2
    assert free.is_published is True


def test_admin_lock_and_unlock_actions(client, django_user_model, sku: SKU) -> None:  # type: ignore[no-untyped-def]
    row = _create_image(sku)
    user = django_user_model.objects.create_user(
        username="image-editor",
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )
    client.force_login(user)
    url = reverse("admin:catalog_productimage_changelist")

    response = client.post(url, {"action": "lock_product_images", "_selected_action": [str(row.pk)]})
    assert response.status_code == 302
    row.refresh_from_db()
    assert row.image_locked is True
    assert row.locked_at is not None
    assert "image-editor" in row.locked_by

    response = client.post(url, {"action": "unlock_product_images", "_selected_action": [str(row.pk)]})
    assert response.status_code == 302
    row.refresh_from_db()
    assert row.image_locked is False
    assert row.locked_at is None
    assert row.locked_by == ""
