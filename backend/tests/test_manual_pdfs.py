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


def test_parse_damu_manual_stem() -> None:
    from catalog.etl.manual_pdfs import parse_damu_manual_stem

    assert parse_damu_manual_stem("da2mu-a_as") == ((2,), "a_as", None)
    assert parse_damu_manual_stem("da4_6mu-d_ds.pdf") == ((4, 6), "d_ds", None)
    assert parse_damu_manual_stem("da8_16_24_32mu24-a_as") == (
        (8, 16, 24, 32),
        "a_as",
        24,
    )
    assert parse_damu_manual_stem("da5fu-d:ds") is None


def test_sku_codes_for_damu_manual() -> None:
    from catalog.etl.manual_pdfs import sku_codes_for_damu_manual

    codes = [
        "DA2MU24-A",
        "DA2MU24-AS",
        "DA2MU230-D",
        "DA2MU24-D",
        "DA8MU24-A",
        "DA8MQU24-A",
    ]
    assert sku_codes_for_damu_manual((2,), "a_as", None, codes) == [
        "DA2MU24-A",
        "DA2MU24-AS",
    ]
    assert sku_codes_for_damu_manual((8, 16, 24, 32), "a_as", 24, codes) == [
        "DA8MU24-A",
    ]


def test_sku_codes_for_damqu_manual() -> None:
    from catalog.etl.manual_pdfs import sku_codes_for_damqu_manual

    codes = ["DA8MQU24-A", "DA8MQU230-DS", "DA8MU24-A", "DA5MQU24-A"]
    assert sku_codes_for_damqu_manual((8, 16, 24), "a_as", 24, codes) == [
        "DA8MQU24-A",
    ]
    assert sku_codes_for_damqu_manual((8, 16, 24), "d_ds", 230, codes) == [
        "DA8MQU230-DS",
    ]


def test_sku_codes_for_hvd_f_manual_only_f_editions() -> None:
    """HVD *F PDFs must not attach to air HVD-5 (no spring) SKUs."""
    from catalog.etl.manual_pdfs import (
        parse_hvd_f_manual_stem,
        sku_codes_for_hvd_f_manual,
    )

    assert parse_hvd_f_manual_stem("hvd-5f-s_st.pdf") == 5
    assert parse_hvd_f_manual_stem("hvd-3f-s_st.pdf") == 3
    codes = [
        "HVD24-5",
        "HVD24S-5",
        "HVD230S-5",
        "HVD24S-5F",
        "HVD24ST-5F",
        "HVD230S-5F",
        "HVD230ST-5F",
        "HVD24S-3F",
    ]
    assert sku_codes_for_hvd_f_manual(5, codes) == [
        "HVD24S-5F",
        "HVD24ST-5F",
        "HVD230S-5F",
        "HVD230ST-5F",
    ]
    assert sku_codes_for_hvd_f_manual(3, codes) == ["HVD24S-3F"]


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


def test_iter_manual_pdfs_prefers_ru_subdir(tmp_path: Path) -> None:
    from catalog.etl.manual_pdfs import find_manual_file, iter_manual_pdfs

    (tmp_path / "RU").mkdir()
    (tmp_path / "EN").mkdir()
    (tmp_path / "RU" / "da5fu-d:ds.pdf").write_bytes(b"%PDF-ru")
    (tmp_path / "EN" / "sa3fu-ds_dst.pdf").write_bytes(b"%PDF-en")
    (tmp_path / "EN" / "da5fu-d:ds.pdf").write_bytes(b"%PDF-en-dup")
    paths = iter_manual_pdfs(tmp_path)
    names = [p.name for p in paths]
    assert names.count("da5fu-d:ds.pdf") == 1
    assert paths[0].parent.name == "RU"
    assert "sa3fu-ds_dst.pdf" in names
    found = find_manual_file(tmp_path, "da5fu-d:ds.pdf")
    assert found is not None
    assert found.parent.name == "RU"
    assert find_manual_file(tmp_path, "sa3fu-ds_dst.pdf") is not None


def test_discover_dafu_in_ru_subdir(tmp_path: Path) -> None:
    from catalog.etl.manual_pdfs import discover_dafu_manuals

    (tmp_path / "RU").mkdir()
    (tmp_path / "RU" / "da5fu-d:ds.pdf").write_bytes(b"%PDF-1.4")
    matches, warnings = discover_dafu_manuals(
        tmp_path,
        sku_codes=["DA5FU24-D", "DA5FU24-DS"],
    )
    assert len(matches) == 1
    assert matches[0].path.parent.name == "RU"
    assert warnings == []
