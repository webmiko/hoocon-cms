"""Tests for DAFU manual PDF discovery and SKU mapping."""

from __future__ import annotations

from pathlib import Path

import pytest

from catalog.etl.manual_pdfs import (
    normalize_manual_stem,
    parse_manual_stem,
    sku_codes_for_manual,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("da5fu-d:ds.pdf", "da5fu-d:ds"),
        ("da5fu-d:ds\xa0.pdf", "da5fu-d:ds"),
        ("da10fu24-a:as.PDF", "da10fu24-a:as"),
    ],
)
def test_normalize_manual_stem(raw: str, expected: str) -> None:
    assert normalize_manual_stem(raw) == expected


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("da5fu-d:ds", (5, "on_off")),
        ("da5fu-d:ds\xa0", (5, "on_off")),
        ("da20fu-d:ds", (20, "on_off")),
        ("da5fu24-a:as", (5, "modulating_24")),
        ("da15fu24-a:as", (15, "modulating_24")),
        ("da5mu-d:ds", None),
        ("readme", None),
    ],
)
def test_parse_manual_stem(stem: str, expected: tuple[int, str] | None) -> None:
    assert parse_manual_stem(stem) == expected


def test_sku_codes_for_manual_on_off() -> None:
    codes = [
        "DA5FU24-D",
        "DA5FU24-DS",
        "DA5FU230-D",
        "DA5FU230-DS",
        "DA5FU24-A",
        "DA5FU24-AS",
        "DA10FU24-D",
        "DA3FU24-D",
    ]
    got = sku_codes_for_manual("on_off", 5, codes)
    assert got == [
        "DA5FU24-D",
        "DA5FU24-DS",
        "DA5FU230-D",
        "DA5FU230-DS",
    ]


def test_sku_codes_for_manual_modulating_24() -> None:
    codes = [
        "DA5FU24-A",
        "DA5FU24-AS",
        "DA5FU230-A",
        "DA5FU24-D",
        "DA10FU24-AS",
    ]
    got = sku_codes_for_manual("modulating_24", 5, codes)
    assert got == ["DA5FU24-A", "DA5FU24-AS"]


def test_discover_ignores_damu(tmp_path: Path) -> None:
    from catalog.etl.manual_pdfs import discover_dafu_manuals

    (tmp_path / "da5fu-d:ds.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "da5mu-d:ds.pdf").write_bytes(b"%PDF-1.4")
    matches, warnings = discover_dafu_manuals(
        tmp_path,
        sku_codes=["DA5FU24-D", "DA5FU24-DS", "DA5MU24-D"],
    )
    assert len(matches) == 1
    assert matches[0].sku_codes == ("DA5FU24-D", "DA5FU24-DS")
    assert warnings == []
