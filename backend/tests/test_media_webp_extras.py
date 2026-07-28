"""Tests for media-webp montage / emergency / SAF72 extras."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.etl.media_webp_extras import apply_media_webp_extras, sku_code_is_hv_qa
from catalog.models import SKU, Category, Product, ProductImage


def _png(color: tuple[int, int, int] = (30, 30, 30)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (800, 600), color=color).save(buf, format="PNG")
    return buf.getvalue()


def test_sku_code_is_hv_qa() -> None:
    """Only HVA/HVD *QA editions match emergency-feedback wiring."""
    assert sku_code_is_hv_qa("HVD24S-20QA")
    assert sku_code_is_hv_qa("hvd230-10qa")
    assert not sku_code_is_hv_qa("HVD24S-20")
    assert not sku_code_is_hv_qa("HVD24S-20Q")
    assert not sku_code_is_hv_qa("sa5fu24-ds")


@pytest.mark.django_db
def test_media_webp_extras_montage_saf72_no_emergency_on_aux(tmp_path: Path) -> None:
    """DST gets SAF72; plain DS gets montage only — not аварийная связь."""
    pack = tmp_path / "media-webp"
    pack.mkdir()
    (pack / "montazhnaya_sxema_sa5fu.webp").write_bytes(_png((10, 10, 10)))
    (pack / "podkluchenie_avariynaya_obratnaya_sviaz.webp").write_bytes(_png((20, 20, 20)))
    (pack / "podkluchenie_avariynaya_obratnaya_sviaz_3-spdt.webp").write_bytes(_png((25, 25, 25)))
    (pack / "termodatchik_saf72.webp").write_bytes(_png((30, 30, 30)))
    (pack / "sxema_termodatchik_saf72.webp").write_bytes(_png((35, 35, 35)))

    cat = Category.objects.create(name="Fire", slug="fire-extras-webp")
    product = Product.objects.create(name="SA5FU", slug="sa5fu-extras", category=cat)
    ds = SKU.objects.create(
        product=product,
        sku_code="sa5fu24-ds",
        name="sa5fu24-ds",
        slug="sa5fu24-ds-extras",
        is_published=True,
    )
    dst = SKU.objects.create(
        product=product,
        sku_code="sa5fu24-dst",
        name="sa5fu24-dst",
        slug="sa5fu24-dst-extras",
        is_published=True,
    )
    ProductImage.objects.create(
        sku=ds,
        image=SimpleUploadedFile("tilda.png", _png((200, 100, 50)), content_type="image/png"),
        alt="sa5fu | Монтажная схема воздушного привода",
        source_url="https://static.tildacdn.com/montage.jpg",
        sort_order=4,
        is_published=True,
    )

    summary = apply_media_webp_extras(dry_run=False, photo_root=pack)
    assert summary["montage"] >= 2
    assert summary["emergency"] == 0
    assert summary["saf72_photo"] == 1
    assert summary["saf72_schema"] == 1
    assert summary["demoted_tilda_montage"] >= 1

    assert ProductImage.objects.filter(
        sku=ds,
        source_url__contains="montazhnaya_sxema_sa5fu",
        is_published=True,
    ).exists()
    assert (
        ProductImage.objects.filter(
            sku=ds,
            source_url__contains="tildacdn",
            is_published=True,
        ).count()
        == 0
    )
    assert not ProductImage.objects.filter(
        sku=ds,
        source_url__icontains="avariynaya",
        is_published=True,
    ).exists()
    assert ProductImage.objects.filter(
        sku=dst,
        source_url__contains="termodatchik_saf72",
        is_published=True,
    ).exists()
    assert ProductImage.objects.filter(
        sku=dst,
        source_url__contains="sxema_termodatchik_saf72",
        is_published=True,
    ).exists()


@pytest.mark.django_db
def test_media_webp_extras_emergency_only_on_qa(tmp_path: Path) -> None:
    """Аварийная обратная связь attaches to *QA and is demoted from plain -S."""
    pack = tmp_path / "media-webp"
    pack.mkdir()
    (pack / "montazhnaya_sxema_hv.webp").write_bytes(_png((10, 10, 10)))
    (pack / "podkluchenie_avariynaya_obratnaya_sviaz_3-spdt.webp").write_bytes(_png((25, 25, 25)))

    cat = Category.objects.create(name="Air", slug="air-qa-extras")
    product = Product.objects.create(name="HVD-20QA", slug="hvd-20qa-extras", category=cat)
    plain_s = SKU.objects.create(
        product=product,
        sku_code="HVD24S-20",
        name="HVD24S-20",
        slug="hvd24s-20-extras",
        is_published=True,
    )
    qa = SKU.objects.create(
        product=product,
        sku_code="HVD24S-20QA",
        name="HVD24S-20QA",
        slug="hvd24s-20qa-extras",
        is_published=True,
    )
    ProductImage.objects.create(
        sku=plain_s,
        image=SimpleUploadedFile("wrong.png", _png((1, 1, 1)), content_type="image/png"),
        alt="HVD24S-20 | Схема подключения с аварийной обратной связью",
        source_url=("https://hoocon.ru/.local-assets/media-webp/podkluchenie_avariynaya_obratnaya_sviaz_3-spdt.webp"),
        sort_order=7,
        is_published=True,
    )

    summary = apply_media_webp_extras(dry_run=False, photo_root=pack)
    assert summary["emergency"] == 1
    assert summary["demoted_emergency_non_qa"] >= 1

    assert ProductImage.objects.filter(
        sku=qa,
        source_url__icontains="avariynaya",
        is_published=True,
    ).exists()
    assert not ProductImage.objects.filter(
        sku=plain_s,
        source_url__icontains="avariynaya",
        is_published=True,
    ).exists()


@pytest.mark.django_db
def test_media_webp_extras_trims_and_flattens_montage(tmp_path: Path) -> None:
    """Oversized transparent montage canvas is cropped onto white."""
    from io import BytesIO

    from PIL import Image

    from catalog.etl.webp import convert_bytes_to_webp

    canvas = Image.new("RGBA", (2000, 3000), (0, 0, 0, 0))
    for x in range(1500, 1800):
        for y in range(2200, 2500):
            canvas.putpixel((x, y), (20, 20, 20, 255))
    buf = BytesIO()
    canvas.save(buf, format="WEBP")
    webp = convert_bytes_to_webp(
        buf.getvalue(),
        trim_alpha=True,
        flatten_white=True,
        max_edge=1600,
    )
    out = Image.open(BytesIO(webp))
    out.load()
    assert out.mode == "RGB"
    assert max(out.size) <= 1600
    assert out.size[0] * out.size[1] < 2000 * 3000 * 0.1

    pack = tmp_path / "media-webp"
    pack.mkdir()
    (pack / "montazhnaya_sxema_hv.webp").write_bytes(buf.getvalue())
    cat = Category.objects.create(name="Air", slug="air-montage-trim")
    product = Product.objects.create(name="HVD", slug="hvd-trim", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="HVD24-20",
        name="HVD24-20",
        slug="hvd24-20-trim",
        is_published=True,
    )
    apply_media_webp_extras(dry_run=False, photo_root=pack)
    img = ProductImage.objects.filter(
        sku=sku,
        source_url__contains="montazhnaya_sxema_hv",
    ).first()
    assert img is not None
    stored = Image.open(img.image)
    stored.load()
    assert stored.mode in {"RGB", "RGBA"}
    assert max(stored.size) <= 1600
    assert stored.size[0] * stored.size[1] < 400_000
