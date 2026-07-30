"""Tests for DAFU manual diagram crops and source URL helpers."""

from __future__ import annotations

import pytest
from PIL import Image

from catalog.etl.manual_diagrams import (
    DiagramCrop,
    crop_modulating_diagrams,
    crop_on_off_diagrams,
    crop_safu_diagrams,
    edition_for_sku,
    parse_dafu_series_nm,
    parse_hva_series,
    parse_safu_series_nm,
    parse_samu_series_nm,
    pdf_source_series_nm,
    relabel_diagram_crops,
    relabel_samu_diagram_crops,
    safu_pdf_source_series_nm,
    samu_pdf_source_series_nm,
    source_url_for,
    source_url_for_hva,
    source_url_for_safu,
    source_url_for_samu,
)


def test_parse_series_and_edition() -> None:
    assert parse_dafu_series_nm("da10fu24-ds") == 10
    assert edition_for_sku("da10fu24-ds") == "on_off"
    assert edition_for_sku("da5fu24-as") == "modulating_24"
    assert edition_for_sku("da5fu24") is None


def test_da3_reuses_da5_pdf() -> None:
    assert pdf_source_series_nm(3) == 5
    assert pdf_source_series_nm(5) == 5
    assert pdf_source_series_nm(10) == 10


def test_relabel_diagram_crops_for_da3() -> None:
    raw = [
        DiagramCrop(
            kind="wiring",
            png_bytes=b"png",
            alt="DA5FU | Схема подключения из инструкции",
            sort_order=5,
            source_url=source_url_for(5, "on_off", "wiring"),
        ),
        DiagramCrop(
            kind="dimensions",
            png_bytes=b"png",
            alt="DA5FU | Габаритные размеры",
            sort_order=6,
            source_url=source_url_for(5, "on_off", "dimensions"),
        ),
    ]
    labeled = relabel_diagram_crops(raw, series_nm=3, edition="on_off")
    assert labeled[0].source_url == source_url_for(3, "on_off", "wiring")
    assert "DA3FU" in labeled[0].alt
    assert labeled[1].source_url == source_url_for(3, "on_off", "dimensions")
    assert labeled[0].png_bytes == b"png"


def test_source_url_stable() -> None:
    url = source_url_for(5, "on_off", "wiring")
    assert "da5fu-dds-wiring" in url
    assert source_url_for(10, "modulating_24", "dimensions").endswith(
        "da10fu-aas-dimensions.webp",
    )


def test_crop_on_off_returns_two_bands() -> None:
    page = Image.new("RGB", (900, 1200), color=(255, 255, 255))
    wiring, dims = crop_on_off_diagrams(page)
    assert wiring.size[0] == dims.size[0]
    assert wiring.size[1] > 0 and dims.size[1] > 0
    assert wiring.size[1] + dims.size[1] < page.size[1]


def test_crop_modulating_uses_right_column() -> None:
    page = Image.new("RGB", (1600, 1200), color=(240, 240, 240))
    wiring, dims = crop_modulating_diagrams(page)
    assert wiring.size[0] < page.size[0] * 0.6
    assert dims.size[0] == wiring.size[0]
    assert wiring.size[1] > 0


def test_parse_safu_series_and_fallback() -> None:
    assert parse_safu_series_nm("sa10fu24-dst") == 10
    assert safu_pdf_source_series_nm(20) == 15
    assert safu_pdf_source_series_nm(15) == 15
    assert "sa5fu-ds-wiring" in source_url_for_safu(5, "wiring")


def test_parse_samu_series_and_source_url() -> None:
    assert parse_samu_series_nm("SA10MU24-DS") == 10
    assert parse_samu_series_nm("sa15mu230-dst") == 15
    assert samu_pdf_source_series_nm(15) == 15
    assert "sa15mu-ds-wiring" in source_url_for_samu(15, "wiring")


def test_relabel_samu_diagram_crops_for_borrowed_pdf() -> None:
    """Fallback PDF crops must retarget source_url/alt to the SKU series."""
    raw = [
        DiagramCrop(
            kind="wiring",
            png_bytes=b"png",
            alt="SA15MU | Схема подключения из инструкции",
            sort_order=5,
            source_url=source_url_for_samu(15, "wiring"),
        ),
        DiagramCrop(
            kind="dimensions",
            png_bytes=b"png",
            alt="SA15MU | Габаритные размеры привода (мм), чертёж из инструкции",
            sort_order=6,
            source_url=source_url_for_samu(15, "dimensions"),
        ),
    ]
    labeled = relabel_samu_diagram_crops(raw, series_nm=20)
    assert labeled[0].source_url == source_url_for_samu(20, "wiring")
    assert "SA20MU" in labeled[0].alt
    assert "sa15mu" not in labeled[0].source_url
    assert labeled[1].source_url == source_url_for_samu(20, "dimensions")
    assert labeled[0].png_bytes == b"png"


def test_crop_safu_uses_right_column() -> None:
    page = Image.new("RGB", (1682, 1191), color=(255, 255, 255))
    wiring, dims = crop_safu_diagrams(page)
    assert wiring.size[0] < page.size[0] * 0.6
    assert dims.size[0] == wiring.size[0]
    assert wiring.size[1] > 0
    assert dims.size[1] > wiring.size[1]


def test_crop_damu_skips_black_section_titles() -> None:
    """Wiring/dimensions crops exclude black title bars and stay between them."""
    from catalog.etl.manual_diagrams import crop_damu_diagrams

    width, height = 2000, 1600
    page = Image.new("RGB", (width, height), color=(255, 255, 255))
    # Three black section titles in the right column.
    for y0, y1 in ((160, 200), (560, 600), (1100, 1140)):
        for y in range(y0, y1):
            for x in range(int(width * 0.48), width):
                page.putpixel((x, y), (0, 0, 0))
    # Mark content pixels just below first and second bars.
    page.putpixel((int(width * 0.7), 220), (12, 34, 56))
    page.putpixel((int(width * 0.7), 620), (78, 90, 12))

    wiring, dims = crop_damu_diagrams(page)
    assert wiring.size[0] < width * 0.6
    assert dims.size[0] == wiring.size[0]
    wire_colors = set(wiring.get_flattened_data())
    dim_colors = set(dims.get_flattened_data())
    assert (12, 34, 56) in wire_colors
    assert (78, 90, 12) in dim_colors
    assert (0, 0, 0) not in wire_colors
    assert (0, 0, 0) not in dim_colors


def test_patch_damu_wiring_labels_ru_replaces_english_titles() -> None:
    """Title ink spans are wiped and redrawn as Belimo RU glossary terms."""
    from catalog.etl.manual_diagrams import (
        _WIRING_LABEL_ACTUATOR_RU,
        _WIRING_LABEL_AUX_RU,
        patch_damu_wiring_labels_ru,
    )

    width, height = 1300, 400
    image = Image.new("RGB", (width, height), color=(255, 255, 255))
    # Synthetic title bars sized like PDF "Actuator" (~98px) and
    # "Auxiliary switch" (~176px) at render scale 3.
    actuator_box = (474, 46, 572, 64)
    aux_box = (908, 39, 1084, 64)
    for box in (actuator_box, aux_box):
        for y in range(box[1], box[3]):
            for x in range(box[0], box[2]):
                image.putpixel((x, y), (20, 20, 20))

    patched = patch_damu_wiring_labels_ru(image)
    assert patched.size == image.size
    # Original solid bars must not remain as continuous black rectangles.
    for box in (actuator_box, aux_box):
        crop = patched.crop(box)
        dark = sum(1 for px in crop.get_flattened_data() if sum(px) // 3 < 40)
        assert dark < (box[2] - box[0]) * (box[3] - box[1]) * 0.5
    title_band = patched.crop((0, int(0.08 * height), width, int(0.18 * height)))
    assert sum(1 for px in title_band.get_flattened_data() if sum(px) // 3 < 80) > 40
    assert _WIRING_LABEL_ACTUATOR_RU == "Привод"
    assert _WIRING_LABEL_AUX_RU == "Вспомогательный переключатель"


def test_parse_hva_series_and_source_url() -> None:
    assert parse_hva_series("HVA24-5") == (5, False)
    assert parse_hva_series("HVA230S-5Q") == (5, True)
    assert parse_hva_series("HVA24-5QX") is None
    assert parse_hva_series("da5fu24-ds") is None
    assert "hva5-dimensions" in source_url_for_hva(5, fast=False, kind="dimensions")
    assert "hva5q-dimensions" in source_url_for_hva(5, fast=True, kind="dimensions")


@pytest.mark.django_db
def test_hva_manual_diagrams_backfills_family_weight_without_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HVA-5Q gets datasheet envelope/mass even when the .ai catalog is missing."""
    from catalog.etl import manual_diagrams as md
    from catalog.models import SKU, AttributeValue, Category, Product

    monkeypatch.setattr(md, "find_hva_catalog_ai", lambda **_kw: None)

    cat = Category.objects.create(name="Воздушные", slug="vozdushnye-hva-wt-test")
    product = Product.objects.create(name="HVA-5Q", slug="hva-5q-wt-test", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="HVA24-5Q",
        slug="hva24-5q-wt-test",
        sku_code="HVA24-5Q",
        is_published=True,
    )

    md.apply_hva_manual_diagrams(dry_run=False)
    by = {av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=sku).select_related("attribute")}
    assert by["dimensions"] == "71,1 × 141,1 × 62,1 мм"
    assert by["weight"] == "< 0,8 кг"


def test_crop_hvdf_product_photos_excludes_datasheet_chrome() -> None:
    """Product crops stay left of feature bullets and above the spec table."""
    from catalog.etl.manual_diagrams import crop_hvdf_product_photos

    width, height = 2523, 1786
    page = Image.new("RGB", (width, height), color=(255, 255, 255))
    body, thermal = crop_hvdf_product_photos(page)
    assert body.size == thermal.size
    assert thermal.size[0] < width * 0.18
    assert thermal.size[1] < height * 0.20


def test_center_cutout_on_canvas_centers_and_fills() -> None:
    """Kit heroes land centered on the shared portrait canvas."""
    from catalog.etl.manual_diagrams import CATALOG_HERO_CANVAS, center_cutout_on_canvas

    src = Image.new("RGBA", (200, 300), (0, 0, 0, 0))
    for y in range(20, 280):
        for x in range(40, 160):
            src.putpixel((x, y), (50, 50, 50, 255))
    out = center_cutout_on_canvas(src)
    assert out.size == CATALOG_HERO_CANVAS
    a = out.split()[-1]
    bbox = a.getbbox()
    assert bbox is not None
    w, _h = out.size
    left, right = bbox[0], w - bbox[2]
    assert abs(left - right) <= 2


def test_center_hvdf_photos_on_canvas_centers_asymmetric_s_pad() -> None:
    """S edition empty sensor column must not leave a right-hand catalog gap."""
    from catalog.etl.manual_diagrams import (
        _HVDF_PHOTO_CANVAS,
        center_hvdf_photos_on_canvas,
    )

    # Mimic punched S (body left) vs ST (body + sensor).
    body = Image.new("RGBA", (200, 120), (0, 0, 0, 0))
    for y in range(10, 110):
        for x in range(10, 100):
            body.putpixel((x, y), (40, 40, 40, 255))
    thermal = Image.new("RGBA", (200, 120), (0, 0, 0, 0))
    for y in range(10, 110):
        for x in range(10, 190):
            thermal.putpixel((x, y), (40, 40, 40, 255))

    out_body, out_thermal = center_hvdf_photos_on_canvas(body, thermal, series_nm=5)
    assert out_body.size == _HVDF_PHOTO_CANVAS
    assert out_thermal.size == _HVDF_PHOTO_CANVAS

    def margins(im: Image.Image) -> tuple[int, int]:
        a = im.split()[-1]
        bbox = a.getbbox()
        assert bbox is not None
        w, _h = im.size
        return bbox[0], w - bbox[2]

    left_b, right_b = margins(out_body)
    left_t, right_t = margins(out_thermal)
    assert abs(left_b - right_b) <= 2
    assert abs(left_t - right_t) <= 2


def test_punch_near_white_background_keeps_interior() -> None:
    """Edge white becomes alpha; dark product body stays opaque."""
    from catalog.etl.manual_diagrams import punch_near_white_background

    img = Image.new("RGB", (80, 60), color=(250, 250, 250))
    for y in range(15, 45):
        for x in range(20, 55):
            img.putpixel((x, y), (40, 40, 40))
    # Interior near-white “dial” not connected to edge.
    for y in range(22, 28):
        for x in range(30, 40):
            img.putpixel((x, y), (255, 255, 255))
    out = punch_near_white_background(img)
    assert out.mode == "RGBA"
    assert out.getpixel((0, 0))[3] == 0
    assert out.getpixel((40, 30))[3] == 255
    assert out.getpixel((35, 25))[3] == 255
