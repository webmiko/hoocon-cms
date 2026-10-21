"""Tests for media-webp DA/SA product hero attach."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.etl.da_sa_media_webp import apply_da_sa_media_webp
from catalog.models import SKU, Category, Product, ProductImage


def _png(size: tuple[int, int] = (900, 1200), color: tuple[int, int, int] = (30, 30, 30)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.django_db
def test_apply_da_sa_media_webp_ds_and_dst_fallback(tmp_path: Path) -> None:
    """DST uses -ds body photo (not -dst composite); falls back if only -ds exists."""
    pack = tmp_path / "media-webp"
    pack.mkdir()
    (pack / "sa3fu-ds.webp").write_bytes(_png(color=(40, 40, 40)))
    (pack / "sa3fu-dst.webp").write_bytes(_png(color=(80, 40, 40)))
    (pack / "sa30mu-ds.webp").write_bytes(_png(color=(40, 80, 40)))

    cat = Category.objects.create(name="Fire", slug="fire-dasa-webp")
    p_fu = Product.objects.create(name="SA3FU", slug="sa3fu-webp", category=cat)
    p_mu = Product.objects.create(name="SA30MU", slug="sa30mu-webp", category=cat)

    ds = SKU.objects.create(
        product=p_fu,
        sku_code="sa3fu24-ds",
        name="sa3fu24-ds",
        slug="sa3fu24-ds-webp",
        is_published=True,
    )
    dst = SKU.objects.create(
        product=p_fu,
        sku_code="sa3fu24-dst",
        name="sa3fu24-dst",
        slug="sa3fu24-dst-webp",
        is_published=True,
    )
    mu_dst = SKU.objects.create(
        product=p_mu,
        sku_code="SA30MU24-DST",
        name="SA30MU24-DST",
        slug="sa30mu24-dst-webp",
        is_published=True,
    )
    ProductImage.objects.create(
        sku=ds,
        image=SimpleUploadedFile("old.png", _png(color=(220, 80, 80)), content_type="image/png"),
        alt="old",
        source_url="https://static.tildacdn.com/old.jpg",
        sort_order=0,
        is_published=True,
    )

    summary = apply_da_sa_media_webp(dry_run=False, photo_root=pack)
    assert summary["created"] + summary["updated"] >= 3

    ds_img = ProductImage.objects.filter(
        sku=ds,
        source_url__contains="media-webp/sa3fu-ds-product",
        is_published=True,
    ).first()
    dst_img = ProductImage.objects.filter(
        sku=dst,
        source_url__contains="media-webp/sa3fu-ds-product",
        is_published=True,
    ).first()
    dst_old = ProductImage.objects.filter(
        sku=dst,
        source_url__contains="media-webp/sa3fu-dst-product",
        is_published=True,
    ).first()
    mu_img = ProductImage.objects.filter(
        sku=mu_dst,
        source_url__contains="media-webp/sa30mu-ds-product",
        is_published=True,
    ).first()
    assert ds_img is not None and ds_img.sort_order == 0
    assert dst_img is not None and dst_img.sort_order == 0
    assert dst_old is None
    assert mu_img is not None and mu_img.sort_order == 0
    assert ProductImage.objects.filter(sku=ds, source_url__contains="tildacdn", is_published=True).count() == 0


@pytest.mark.django_db
def test_apply_da_sa_media_webp_colon_editions(tmp_path: Path) -> None:
    """``d:ds`` / ``a:as`` packs map to both edition suffixes; voltage mask respected."""
    pack = tmp_path / "media-webp"
    pack.mkdir()
    (pack / "da5fu-d:ds.webp").write_bytes(_png(color=(50, 50, 50)))
    (pack / "da5fu24-a:as.webp").write_bytes(_png(color=(60, 60, 60)))
    (pack / "da10:15:20fu-a:as.webp").write_bytes(_png(color=(65, 65, 65)))
    (pack / "da10:15:20fu-d:ds.webp").write_bytes(_png(color=(55, 55, 120)))
    (pack / "da8:16:24mu24-d:ds.webp").write_bytes(_png(color=(70, 70, 70)))
    (pack / "da10:20mqu-d:ds.webp").write_bytes(_png(color=(80, 80, 80)))
    (pack / "da10:20mqu-a:as.webp").write_bytes(_png(color=(85, 85, 85)))

    cat = Category.objects.create(name="Air DA", slug="air-dasa-webp")
    product = Product.objects.create(name="DA5FU", slug="da5fu-webp", category=cat)
    codes = ("da5fu24-d", "da5fu24-ds", "da5fu24-a", "da5fu24-as", "da5fu230-d")
    skus = [
        SKU.objects.create(
            product=product,
            sku_code=code,
            name=code,
            slug=f"{code}-webp",
            is_published=True,
        )
        for code in codes
    ]
    p10 = Product.objects.create(name="DA10FU", slug="da10fu-webp", category=cat)
    da10_a = SKU.objects.create(
        product=p10,
        sku_code="da10fu24-a",
        name="da10fu24-a",
        slug="da10fu24-a-webp",
        is_published=True,
    )
    da15_as = SKU.objects.create(
        product=p10,
        sku_code="da15fu24-as",
        name="da15fu24-as",
        slug="da15fu24-as-webp",
        is_published=True,
    )
    p32 = Product.objects.create(name="DA32MU", slug="da32mu-webp", category=cat)
    da32 = SKU.objects.create(
        product=p32,
        sku_code="DA32MU24-DS",
        name="DA32MU24-DS",
        slug="da32mu24-ds-webp",
        is_published=True,
    )
    p8 = Product.objects.create(name="DA8MQU", slug="da8mqu-webp", category=cat)
    da8 = SKU.objects.create(
        product=p8,
        sku_code="DA8MQU24-DS",
        name="DA8MQU24-DS",
        slug="da8mqu24-ds-webp",
        is_published=True,
    )

    summary = apply_da_sa_media_webp(dry_run=False, photo_root=pack)
    # DA8/16/24 MQU no longer takes the labeled da10:20mqu pack shot.
    assert summary["created"] == 8

    for sku in skus[:2] + skus[4:]:
        assert ProductImage.objects.filter(
            sku=sku,
            source_url__contains="media-webp/da5fu-d:ds-product",
            is_published=True,
        ).exists()
    for sku in skus[2:4]:
        assert ProductImage.objects.filter(
            sku=sku,
            source_url__contains="media-webp/da5fu24-a:as-product",
            is_published=True,
        ).exists()
    for sku in (da10_a, da15_as):
        assert ProductImage.objects.filter(
            sku=sku,
            source_url__contains="media-webp/da10:15:20fu-d:ds-product",
            is_published=True,
        ).exists()
    assert ProductImage.objects.filter(
        sku=da32,
        source_url__contains="media-webp/da8:16:24mu24-d:ds-product",
        is_published=True,
    ).exists()
    assert not ProductImage.objects.filter(
        sku=da8,
        source_url__contains="media-webp/da10:20mqu",
        is_published=True,
    ).exists()


@pytest.mark.django_db
def test_da20fu24_a_as_uses_d_ds_body_photo(tmp_path: Path) -> None:
    """DA20FU24-A/AS must attach the shared ``…-d:ds`` hero, not ``…-a:as``."""
    pack = tmp_path / "media-webp"
    pack.mkdir()
    (pack / "da10:15:20fu-a:as.webp").write_bytes(_png(color=(200, 40, 40)))
    (pack / "da10:15:20fu-d:ds.webp").write_bytes(_png(color=(40, 40, 200)))

    cat = Category.objects.create(name="Spring", slug="spring-da20-photo")
    product = Product.objects.create(name="DA20FU", slug="da20fu-photo", category=cat)
    a = SKU.objects.create(
        product=product,
        sku_code="da20fu24-a",
        name="da20fu24-a",
        slug="da20fu24-a-photo",
        is_published=True,
    )
    as_sku = SKU.objects.create(
        product=product,
        sku_code="da20fu24-as",
        name="da20fu24-as",
        slug="da20fu24-as-photo",
        is_published=True,
    )
    ds = SKU.objects.create(
        product=product,
        sku_code="da20fu24-ds",
        name="da20fu24-ds",
        slug="da20fu24-ds-photo",
        is_published=True,
    )

    summary = apply_da_sa_media_webp(dry_run=False, photo_root=pack)
    assert summary["created"] == 3
    for sku in (a, as_sku, ds):
        assert ProductImage.objects.filter(
            sku=sku,
            source_url__contains="media-webp/da10:15:20fu-d:ds-product",
            is_published=True,
        ).exists()
    assert (
        ProductImage.objects.filter(
            sku__in=[a, as_sku],
            source_url__contains="media-webp/da10:15:20fu-a:as-product",
            is_published=True,
        ).count()
        == 0
    )


@pytest.mark.django_db
def test_clone_damqu_images_from_da8_to_16_24() -> None:
    """DA16/DA24 reuse DA8 gallery rows (same edition)."""
    from catalog.etl.da_sa_media_webp import clone_damqu_images_from_donor

    cat = Category.objects.create(name="MQU clone", slug="mqu-clone")
    png = _png(color=(90, 90, 90))
    products = {}
    skus: dict[str, SKU] = {}
    for nm in (8, 16, 24):
        products[nm] = Product.objects.create(
            name=f"DA{nm}MQU",
            slug=f"privod-vozdushniy-da{nm}mqu-{nm}nm",
            category=cat,
        )
        for ed in ("24-A", "24-D"):
            code = f"DA{nm}MQU{ed}"
            skus[code] = SKU.objects.create(
                product=products[nm],
                sku_code=code,
                name=code,
                slug=f"{code.lower()}-clone",
                is_published=True,
            )
    for code in ("DA8MQU24-A", "DA8MQU24-D"):
        img = ProductImage(
            sku=skus[code],
            alt=f"{code} hero",
            source_url=(f"https://hoocon.ru/.local-assets/manuals-ru/da8-16-24mqu24-{code[-1].lower()}-product.webp"),
            sort_order=0,
            is_published=True,
        )
        img.image.save(
            f"{code.lower()}.webp",
            SimpleUploadedFile(f"{code.lower()}.webp", png, content_type="image/webp"),
            save=False,
        )
        img.full_clean()
        img.save()

    labeled = ProductImage(
        sku=skus["DA8MQU24-A"],
        alt="DA8MQU24-A | фото привода",
        source_url="https://hoocon.ru/.local-assets/media-webp/da10:20mqu-a:as-product.webp",
        sort_order=1,
        is_published=True,
    )
    labeled.image.save(
        "labeled.webp",
        SimpleUploadedFile("labeled.webp", png, content_type="image/webp"),
        save=False,
    )
    labeled.full_clean()
    labeled.save()

    stats = clone_damqu_images_from_donor()
    assert stats["targets"] == 4
    assert stats["created"] == 4
    for nm in (16, 24):
        for ed in ("24-A", "24-D"):
            target = skus[f"DA{nm}MQU{ed}"]
            cloned = ProductImage.objects.get(sku=target, sort_order=0, is_published=True)
            assert cloned.alt == f"DA{nm}MQU{ed} hero"
            assert not ProductImage.objects.filter(
                sku=target,
                source_url__contains="da10:20mqu",
            ).exists()

    files_before = {img.pk: img.image.name for img in ProductImage.objects.filter(sku__product__in=products.values())}
    again = clone_damqu_images_from_donor()
    assert (again["created"], again["updated"], again["skipped"]) == (0, 0, 6)
    files_after = {img.pk: img.image.name for img in ProductImage.objects.filter(sku__product__in=products.values())}
    assert files_after == files_before


@pytest.mark.django_db
def test_clone_damqu_skips_unpublished_donor_and_keeps_empty_source_idempotent() -> None:
    """M42: клон шёл мимо upsert_sku_image — без source_url плодил дубли, а скрытое фото донора копировал."""
    from catalog.etl.da_sa_media_webp import clone_damqu_images_from_donor

    cat = Category.objects.create(name="MQU clone", slug="mqu-clone")
    skus: dict[int, SKU] = {}
    for nm in (8, 16):
        product = Product.objects.create(name=f"DA{nm}MQU", slug=f"da{nm}mqu", category=cat)
        code = f"DA{nm}MQU24-A"
        skus[nm] = SKU.objects.create(product=product, sku_code=code, name=code, slug=code.lower(), is_published=True)
    for name, published in (("hero.webp", True), ("hidden.webp", False)):
        img = ProductImage(sku=skus[8], alt=name, source_url="", sort_order=0, is_published=published)
        img.image.save(name, SimpleUploadedFile(name, _png(color=(10, 10, 10)), content_type="image/webp"), save=False)
        img.save()

    clone_damqu_images_from_donor(target_nms=(16,))
    clone_damqu_images_from_donor(target_nms=(16,))

    cloned = ProductImage.objects.filter(sku=skus[16])
    assert cloned.count() == 1
    assert cloned.get().alt == "hero.webp"


@pytest.mark.django_db
def test_damqu_16_24_manual_hero_replaces_labeled_da10_pack(tmp_path: Path) -> None:
    """DA16/DA24 must not keep the da10:20mqu cutout that is labeled 8 Нм."""
    from catalog.etl.da_sa_media_webp import apply_damqu_manual_heroes

    pack = tmp_path / "media-webp"
    pack.mkdir()
    (pack / "da10:20mqu-a:as.webp").write_bytes(_png(color=(85, 85, 85)))
    (pack / "da10:20mqu-d:ds.webp").write_bytes(_png(color=(80, 80, 80)))
    assets = tmp_path / "assets"
    body = assets / "da8-16-24mqu24-a-as"
    body.mkdir(parents=True)
    (body / "product.png").write_bytes(_png(color=(180, 20, 20)))
    (body / "wiring.png").write_bytes(_png(color=(20, 20, 20)))
    (body / "dimensions.png").write_bytes(_png(color=(20, 20, 180)))

    cat = Category.objects.create(name="MQU pack", slug="mqu-pack")
    product = Product.objects.create(name="DA16", slug="da16mqu-pack", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="DA16MQU24-A",
        name="DA16MQU24-A",
        slug="da16mqu24-a-pack",
        is_published=True,
    )
    ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile("old.webp", _png(color=(1, 1, 1)), content_type="image/webp"),
        alt="DA8MQU24-A | фото привода",
        source_url="https://hoocon.ru/.local-assets/media-webp/da10:20mqu-a:as-product.webp",
        sort_order=0,
        is_published=True,
    )

    apply_da_sa_media_webp(dry_run=False, photo_root=pack)
    apply_damqu_manual_heroes(dry_run=False, assets_root=assets)

    hero = ProductImage.objects.get(
        sku=sku,
        source_url__contains="da8-16-24mqu24-a-as-product",
        is_published=True,
    )
    assert hero.alt == "DA16MQU24-A | фото привода"
    assert "da8-16-24mqu-da8-16-24mqu" not in hero.source_url
    assert not ProductImage.objects.filter(
        sku=sku,
        source_url__contains="da10:20mqu",
        is_published=True,
    ).exists()


@pytest.mark.django_db
def test_damqu_manual_hero_drops_studio_white(tmp_path: Path) -> None:
    """Studio white and the grey halo become transparent; diagrams stay paper.

    DA16MQU24-D reuses this same 230 В D cutout. The 230 В card is the one
    that also stores wiring from that folder.
    """
    from io import BytesIO

    from PIL import Image

    from catalog.etl.da_sa_media_webp import apply_damqu_manual_heroes

    img = Image.new("RGB", (120, 100), (255, 255, 255))
    for y in range(30, 70):
        for x in range(30, 90):
            img.putpixel((x, y), (180, 20, 20))
    for y in range(4, 10):
        for x in range(4, 10):
            img.putpixel((x, y), (160, 156, 154))
    buf = BytesIO()
    img.save(buf, format="PNG")
    product_png = buf.getvalue()

    assets = tmp_path / "assets"
    body = assets / "da8-16-24mqu230-d-ds"
    body.mkdir(parents=True)
    (body / "product.png").write_bytes(product_png)
    (body / "wiring.png").write_bytes(_png(size=(80, 60), color=(255, 255, 255)))
    (body / "dimensions.png").write_bytes(_png(size=(80, 60), color=(255, 255, 255)))

    cat = Category.objects.create(name="MQU wash", slug="mqu-wash")
    product = Product.objects.create(name="DA16 D", slug="da16mqu-wash", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="DA16MQU230-D",
        name="DA16MQU230-D",
        slug="da16mqu230-d-wash",
        is_published=True,
    )

    apply_damqu_manual_heroes(dry_run=False, assets_root=assets)

    hero = ProductImage.objects.get(sku=sku, sort_order=0, is_published=True)
    with Image.open(hero.image) as opened:
        opened.load()
        rgba = opened.convert("RGBA")
    assert rgba.getpixel((0, 0))[3] == 0
    assert rgba.getpixel((6, 6))[3] == 0
    assert rgba.getpixel((rgba.width // 2, rgba.height // 2))[3] == 255

    wiring = ProductImage.objects.get(sku=sku, sort_order=5, is_published=True)
    with Image.open(wiring.image) as opened:
        opened.load()
        paper = opened.convert("RGBA")
    assert paper.getpixel((0, 0))[3] == 255


@pytest.mark.django_db
def test_damqu_removebg_cutout_stays_transparent(tmp_path: Path) -> None:
    """A shared remove.bg PNG is the hero and is not punched again.

    The grey block sits on the clear backdrop. The studio punch would delete it;
    this file is already a cut-out, so the block and the red body stay.
    """
    from io import BytesIO

    from PIL import Image

    from catalog.etl.da_sa_media_webp import apply_damqu_manual_heroes

    cut = Image.new("RGBA", (80, 60), (0, 0, 0, 0))
    for y in range(20, 45):
        for x in range(25, 60):
            cut.putpixel((x, y), (200, 30, 30, 255))
    for y in range(4, 12):
        for x in range(4, 12):
            cut.putpixel((x, y), (160, 156, 154, 255))
    buf = BytesIO()
    cut.save(buf, format="PNG")

    assets = tmp_path / "assets"
    shared = assets / "da8-16-24mqu-cutout"
    shared.mkdir(parents=True)
    (shared / "product.png").write_bytes(buf.getvalue())
    studio = assets / "da8-16-24mqu230-d-ds"
    studio.mkdir()
    (studio / "product.png").write_bytes(_png(size=(80, 60), color=(0, 180, 0)))
    (studio / "wiring.png").write_bytes(_png(size=(40, 30), color=(255, 255, 255)))
    (studio / "dimensions.png").write_bytes(_png(size=(40, 30), color=(255, 255, 255)))

    cat = Category.objects.create(name="MQU cut", slug="mqu-cut")
    product = Product.objects.create(name="DA16 D", slug="da16mqu-cut", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="DA16MQU230-D",
        name="DA16MQU230-D",
        slug="da16mqu230-d-cut",
        is_published=True,
    )

    apply_damqu_manual_heroes(dry_run=False, assets_root=assets)

    hero = ProductImage.objects.get(sku=sku, sort_order=0, is_published=True)
    assert "da8-16-24mqu-cutout-product" in hero.source_url
    with Image.open(hero.image) as opened:
        opened.load()
        rgba = opened.convert("RGBA")
    assert rgba.getpixel((0, 0))[3] == 0
    assert rgba.getpixel((8, 8))[3] == 255
    red = rgba.getpixel((rgba.width // 2, rgba.height // 2))
    assert red[0] > 150 and red[1] < 80 and red[3] == 255


@pytest.mark.django_db
def test_damqu_manual_heroes_run_without_media_pack(tmp_path: Path) -> None:
    """RU cutout replaces the labeled da10:20mqu shot when the pack is missing or empty.

    ``apply_da_sa_media_webp`` used to return before ``apply_damqu_manual_heroes``.
    The cutout lives under ``_manuals-ru`` and does not need the pack.
    """
    assets = tmp_path / "assets"
    body = assets / "da8-16-24mqu24-a-as"
    body.mkdir(parents=True)
    (body / "product.png").write_bytes(_png(color=(180, 20, 20)))
    cat = Category.objects.create(name="MQU nopack", slug="mqu-nopack")
    product = Product.objects.create(name="DA MQU", slug="da-mqu-nopack", category=cat)

    def labeled(code: str) -> SKU:
        sku = SKU.objects.create(
            product=product,
            sku_code=code,
            name=code,
            slug=code.lower(),
            is_published=True,
        )
        ProductImage.objects.create(
            sku=sku,
            image=SimpleUploadedFile("old.webp", _png(color=(1, 1, 1)), content_type="image/webp"),
            alt="DA8MQU24-A | фото привода",
            source_url="https://hoocon.ru/.local-assets/media-webp/da10:20mqu-a:as-product.webp",
            sort_order=0,
            is_published=True,
        )
        return sku

    missing_sku = labeled("DA16MQU24-A")
    summary = apply_da_sa_media_webp(dry_run=False, photo_root=tmp_path / "absent-pack", assets_root=assets)
    assert summary["missing_root"] is True
    assert summary["manual_heroes"]["heroes"] >= 1
    assert not ProductImage.objects.filter(
        sku=missing_sku,
        source_url__contains="da10:20mqu",
        is_published=True,
    ).exists()
    assert ProductImage.objects.filter(
        sku=missing_sku,
        source_url__contains="da8-16-24mqu24-a-as-product",
        is_published=True,
    ).exists()

    empty_sku = labeled("DA24MQU24-A")
    empty = tmp_path / "empty-pack"
    empty.mkdir()
    empty_summary = apply_da_sa_media_webp(dry_run=False, photo_root=empty, assets_root=assets)
    assert "missing_root" not in empty_summary
    assert empty_summary["skipped"] == 1
    assert empty_summary["manual_heroes"]["heroes"] >= 1
    assert not ProductImage.objects.filter(
        sku=empty_sku,
        source_url__contains="da10:20mqu",
        is_published=True,
    ).exists()
