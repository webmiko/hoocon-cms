"""Tests for media-webp montage / emergency / SAF72 extras."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.etl.media_webp_extras import _MontageShot, _pick_montage, apply_media_webp_extras, sku_code_is_hv_qa
from catalog.models import SKU, Category, Product, ProductImage


def _png(color: tuple[int, int, int] = (30, 30, 30)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (800, 600), color=color).save(buf, format="PNG")
    return buf.getvalue()


def test_sa15_montage_is_not_the_sa10_sheet() -> None:
    """SA7 shares the SA10 body; SA15 is 156×98×59 and must not take that sheet."""
    shot = _MontageShot(
        stem="montazhnaya_sxema_sa10mu",
        path=Path("montazhnaya_sxema_sa10mu.webp"),
        kind="da_sa",
        family="sa",
        nms=frozenset({10}),
        series="mu",
    )
    assert _pick_montage("SA7MU24-DS", [shot]) is shot
    assert _pick_montage("SA15MU24-DS", [shot]) is None


@pytest.mark.django_db
def test_sa15_borrowed_sa10_montage_is_unpublished() -> None:
    """A published SA10 mounting row on SA15 is hidden."""
    from catalog.etl.media_webp_extras import unpublish_sa15_borrowed_sa10_montage

    cat = Category.objects.create(name="SA", slug="sa-montage")
    product = Product.objects.create(name="SA15", slug="sa15", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="SA15MU230-DS",
        name="SA15MU230-DS",
        slug="sa15mu230-ds",
        is_published=True,
    )
    image = ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile("m.webp", _png(), content_type="image/webp"),
        alt="SA15MU230-DS | Монтажная схема",
        source_url="https://hoocon.ru/.local-assets/media-webp/montazhnaya_sxema_sa10mu.webp",
        sort_order=4,
        is_published=True,
    )
    assert unpublish_sa15_borrowed_sa10_montage() == 1
    image.refresh_from_db()
    assert image.is_published is False


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
def test_hvdf_cards_drop_the_hva_montage(tmp_path: Path) -> None:
    """HVD-F не показывает монтажную схему HVA; воздушный HVD её сохраняет."""
    pack = tmp_path / "media-webp"
    pack.mkdir()
    (pack / "montazhnaya_sxema_hv.webp").write_bytes(_png((10, 10, 10)))

    cat = Category.objects.create(name="Smoke", slug="hvdf-no-montage")
    product = Product.objects.create(name="HVD-F", slug="hvdf-no-montage-p", category=cat)
    hvdf = SKU.objects.create(
        product=product,
        sku_code="HVD24S-5F",
        name="HVD24S-5F",
        slug="hvd24s-5f-no-montage",
        is_published=True,
    )
    air = SKU.objects.create(
        product=product,
        sku_code="HVD24-5",
        name="HVD24-5",
        slug="hvd24-5-keeps-montage",
        is_published=True,
    )
    ProductImage.objects.create(
        sku=hvdf,
        image=SimpleUploadedFile("old.png", _png((2, 2, 2)), content_type="image/png"),
        alt="HVD24S-5F | Монтажная схема",
        source_url="https://hoocon.ru/.local-assets/media-webp/montazhnaya_sxema_hv.webp",
        sort_order=4,
        is_published=True,
    )

    hv_shot = _MontageShot(
        stem="montazhnaya_sxema_hv",
        path=pack / "montazhnaya_sxema_hv.webp",
        kind="hv",
        family=None,
        nms=frozenset(),
        series=None,
    )
    assert _pick_montage("HVD24S-5F", [hv_shot]) is None
    assert _pick_montage("HVD230ST-3F", [hv_shot]) is None
    assert _pick_montage("HVD24-5", [hv_shot]) is hv_shot
    assert _pick_montage("HVA24S-5", [hv_shot]) is hv_shot

    summary = apply_media_webp_extras(dry_run=False, photo_root=pack)
    assert summary["unpublished_hvdf_montage"] == 1
    hidden = ProductImage.objects.get(sku=hvdf)
    assert hidden.is_published is False
    assert hidden.hidden_by_editor is True
    assert ProductImage.objects.filter(
        sku=air,
        source_url__contains="montazhnaya_sxema_hv",
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


@pytest.mark.django_db
def test_demote_tilda_montage_reversed_alt_word_order() -> None:
    """Tilda alts like «схема монтажная …» are demoted when local montage exists."""
    from catalog.etl.media_webp_extras import demote_tilda_montages_where_local_exists

    cat = Category.objects.create(name="MQU demote", slug="mqu-demote-montage")
    product = Product.objects.create(name="DA8MQU", slug="da8mqu-demote", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="DA8MQU24-A",
        name="DA8MQU24-A",
        slug="da8mqu24-a-demote",
        is_published=True,
    )
    local = ProductImage(
        sku=sku,
        alt="DA8MQU24-A | Монтажная схема",
        source_url="https://hoocon.ru/.local-assets/media-webp/montazhnaya_sxema_da8:16:24mu.webp",
        sort_order=4,
        is_published=True,
    )
    local.image.save(
        "local.webp",
        SimpleUploadedFile("local.webp", _png((10, 10, 10)), content_type="image/webp"),
        save=False,
    )
    local.full_clean()
    local.save()
    tilda = ProductImage(
        sku=sku,
        alt="схема монтажная для привода вентиляции Hoocon da8mqu",
        source_url="https://static.tildacdn.com/stor3864/76088397.jpg",
        sort_order=3,
        is_published=True,
    )
    tilda.image.save(
        "tilda.webp",
        SimpleUploadedFile("tilda.webp", _png((200, 100, 50)), content_type="image/webp"),
        save=False,
    )
    tilda.full_clean()
    tilda.save()

    assert demote_tilda_montages_where_local_exists() == 1
    tilda.refresh_from_db()
    local.refresh_from_db()
    assert tilda.is_published is False
    assert local.is_published is True
