"""Tests for H81 catalog photo + dimensions media helpers."""

from __future__ import annotations

from PIL import Image

from catalog.etl.h81_catalog_media import (
    crop_h81_dimensions,
    parse_h81_kit_prefix,
    source_url_for_h81,
)


def test_parse_h81_kit_prefix() -> None:
    assert parse_h81_kit_prefix("H8101-BV215A-24AS") == "H8101"
    assert parse_h81_kit_prefix("h8122-bv2150-230d") == "H8122"
    assert parse_h81_kit_prefix("8100-bv215a") is None
    assert parse_h81_kit_prefix("H8205-LAV232-24A") is None


def test_source_url_for_h81_stable() -> None:
    assert source_url_for_h81("H8103", "photo").endswith("h8103-photo.webp")
    assert source_url_for_h81("H8121", "dimensions").endswith("h8121-dimensions.webp")
    assert source_url_for_h81("H8101", "photo").startswith(
        "https://hoocon.ru/.local-assets/h81-catalog/",
    )


def test_crop_h81_dimensions_band() -> None:
    page = Image.new("RGB", (1000, 1400), color=(255, 255, 255))
    dims = crop_h81_dimensions(page, top=0.70, bottom=0.95, left=0.03, right=0.90)
    assert dims.size[0] == int(0.90 * 1000) - int(0.03 * 1000)
    assert dims.size[1] == int(0.95 * 1400) - int(0.70 * 1400)
    assert dims.size[1] < page.size[1]
