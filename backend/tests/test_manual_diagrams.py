"""Tests for DAFU manual diagram crops and source URL helpers."""

from __future__ import annotations

from PIL import Image

from catalog.etl.manual_diagrams import (
    DiagramCrop,
    crop_modulating_diagrams,
    crop_on_off_diagrams,
    crop_safu_diagrams,
    edition_for_sku,
    parse_dafu_series_nm,
    parse_safu_series_nm,
    pdf_source_series_nm,
    relabel_diagram_crops,
    safu_pdf_source_series_nm,
    source_url_for,
    source_url_for_safu,
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


def test_crop_safu_uses_right_column() -> None:
    page = Image.new("RGB", (1682, 1191), color=(255, 255, 255))
    wiring, dims = crop_safu_diagrams(page)
    assert wiring.size[0] < page.size[0] * 0.6
    assert dims.size[0] == wiring.size[0]
    assert wiring.size[1] > 0
    assert dims.size[1] > wiring.size[1]
