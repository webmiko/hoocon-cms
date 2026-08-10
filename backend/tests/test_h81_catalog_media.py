"""Tests for H81 catalog photo + dimensions + wiring media helpers."""

from __future__ import annotations

from PIL import Image

from catalog.etl.h81_catalog_media import (
    _FAMILY_MEDIA,
    crop_h81_dimensions,
    extract_catalog_page_range_pdf,
    find_h81_catalog_pdf,
    instruction_title_for_h81,
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
    assert source_url_for_h81("H8101", "wiring").endswith("h8101-wiring.webp")
    assert source_url_for_h81("H8101", "aux_switch").endswith("h8101-aux_switch.webp")
    assert source_url_for_h81("H8101", "settings").endswith("h8101-settings.webp")
    assert source_url_for_h81("H8101", "photo").startswith(
        "https://hoocon.ru/.local-assets/h81-catalog/",
    )


def test_crop_h81_dimensions_band() -> None:
    page = Image.new("RGB", (1000, 1400), color=(255, 255, 255))
    dims = crop_h81_dimensions(page, top=0.70, bottom=0.95, left=0.03, right=0.90)
    assert dims.size[0] == int(0.90 * 1000) - int(0.03 * 1000)
    assert dims.size[1] == int(0.95 * 1400) - int(0.70 * 1400)
    assert dims.size[1] < page.size[1]


def test_instruction_title_and_page_ranges() -> None:
    """H8101/02 use catalog pages 6–9; every family has a wiring page."""
    assert instruction_title_for_h81("H8101/H8102", 6, 9) == ("Инструкция H8101/H8102 (каталог 2026, стр. 6–9)")
    h8101 = _FAMILY_MEDIA["H8101"]
    assert (h8101.instr_first_page, h8101.instr_last_page) == (6, 9)
    assert h8101.wiring_page_index == 8
    for _prefix, media in _FAMILY_MEDIA.items():
        assert media.instr_first_page >= 1
        assert media.instr_last_page >= media.instr_first_page
        assert media.wiring_page_index == media.instr_last_page - 1
        assert media.pair_label


def test_extract_catalog_page_range_pdf_bytes() -> None:
    """Sliced PDF for pages 6–9 is non-empty and smaller than the full catalog."""
    pdf = find_h81_catalog_pdf()
    if pdf is None:
        return
    payload = extract_catalog_page_range_pdf(pdf, first_page=6, last_page=9)
    assert payload[:4] == b"%PDF"
    assert len(payload) < pdf.stat().st_size
    assert len(payload) > 1000
