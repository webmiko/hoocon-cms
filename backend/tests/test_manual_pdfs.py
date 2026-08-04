"""Tests for DAFU manual PDF discovery and SKU mapping."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.base import ContentFile

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
    assert parse_hvd_f_manual_stem("HVD-5F-S_ST.pdf") == 5
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


def test_discover_hvd_prefers_ru_uppercase(tmp_path: Path) -> None:
    """RU ``HVD-*.pdf`` must win over EN ``hvd-*.pdf`` (case-sensitive FS)."""
    from catalog.etl.manual_pdfs import discover_hvd_manuals

    (tmp_path / "RU").mkdir()
    (tmp_path / "EN").mkdir()
    (tmp_path / "RU" / "HVD-5F-S_ST.pdf").write_bytes(b"%PDF-ru-hvd")
    (tmp_path / "EN" / "hvd-5f-s_st.pdf").write_bytes(b"%PDF-en-hvd-bigger!!!!!")
    matches, warnings = discover_hvd_manuals(
        tmp_path,
        sku_codes=["HVD24S-5F", "HVD24ST-5F"],
    )
    assert len(matches) == 1
    assert matches[0].path.parent.name == "RU"
    assert matches[0].path.read_bytes() == b"%PDF-ru-hvd"
    assert any("duplicate HVD" in w for w in warnings)


def test_discover_hva_prefers_ru_over_en(tmp_path: Path) -> None:
    """When both RU/HVA-5.pdf and EN/hva-5.pdf exist, attach RU bytes."""
    from catalog.etl.manual_pdfs import discover_hva_manuals

    (tmp_path / "RU").mkdir()
    (tmp_path / "EN").mkdir()
    (tmp_path / "RU" / "HVA-5.pdf").write_bytes(b"%PDF-ru-hva5")
    (tmp_path / "EN" / "hva-5.pdf").write_bytes(b"%PDF-en-hva5-xxxxxxxx")
    (tmp_path / "EN" / "hva-10.pdf").write_bytes(b"%PDF-en-only")
    matches, _warnings = discover_hva_manuals(
        tmp_path,
        sku_codes=["HVA24-5", "HVA24-10"],
    )
    by_token = {m.kind: m for m in matches}
    assert by_token["5"].path.parent.name == "RU"
    assert by_token["5"].path.read_bytes() == b"%PDF-ru-hva5"
    assert by_token["10"].path.parent.name == "EN"


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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("sa10mu-ds_dst.pdf", (10, True)),
        ("SA10MU-DS — руководство (RU).pdf", (10, False)),
        ("SA3FU-DS_DST — руководство (RU).pdf", (3, True)),
        ("sa5fu-ds_dst", (5, True)),
        ("sa7mu-ds", (7, False)),
        ("da5fu-d:ds", None),
    ],
)
def test_parse_sa_manual_stems_ru_and_en(
    raw: str,
    expected: tuple[int, bool] | None,
) -> None:
    from catalog.etl.manual_pdfs import parse_safu_manual_stem, parse_samu_manual_stem

    if "fu" in raw.casefold():
        assert parse_safu_manual_stem(raw) == expected
        assert parse_samu_manual_stem(raw) is None
    elif "mu" in raw.casefold():
        assert parse_samu_manual_stem(raw) == expected
        assert parse_safu_manual_stem(raw) is None
    else:
        assert parse_safu_manual_stem(raw) is None
        assert parse_samu_manual_stem(raw) is None


def test_discover_samu_prefers_ru_ds_only_over_en(tmp_path: Path) -> None:
    from catalog.etl.manual_pdfs import discover_samu_manuals

    (tmp_path / "RU").mkdir()
    (tmp_path / "EN").mkdir()
    (tmp_path / "RU" / "SA10MU-DS — руководство (RU).pdf").write_bytes(b"%PDF-ru")
    (tmp_path / "EN" / "sa10mu-ds_dst.pdf").write_bytes(b"%PDF-en")
    codes = [
        "SA10MU24-DS",
        "SA10MU24-DST",
        "SA10MU230-DS",
        "SA10MU230-DST",
    ]
    matches, warnings = discover_samu_manuals(tmp_path, sku_codes=codes)
    assert warnings == []
    assert len(matches) == 1
    assert matches[0].path.parent.name == "RU"
    assert matches[0].kind == "samu_ds"
    assert set(matches[0].sku_codes) == {"SA10MU24-DS", "SA10MU230-DS"}


@pytest.mark.django_db
def test_attach_samu_renames_legacy_ds_dst_title(tmp_path: Path) -> None:
    """Legacy ``(DS/DST)`` titles become ``(DS)`` on re-attach."""
    from catalog.etl.manual_pdfs import _samu_manual_title, attach_samu_manuals
    from catalog.models import SKU, Category, Product, ProductFile

    cat = Category.objects.create(name="Дым", slug="dym-samu-title")
    product = Product.objects.create(name="SA10MU", slug="samu-title-prod", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="SA10MU24-DS",
        name="SA10MU24-DS",
        slug="sa10mu24-ds-title",
        is_published=True,
    )
    legacy = ProductFile.objects.create(
        sku=sku,
        title="Инструкция SA10MU (DS/DST)",
        file_type=ProductFile.FileType.DATASHEET,
        is_published=True,
        sort_order=0,
    )
    legacy.file.save("sa10mu-ds_dst.pdf", ContentFile(b"%PDF-old"), save=True)

    (tmp_path / "RU").mkdir()
    (tmp_path / "RU" / "SA10MU-DS — руководство (RU).pdf").write_bytes(b"%PDF-ru-new")
    summary = attach_samu_manuals(tmp_path, dry_run=False)
    assert summary["updated"] >= 1
    legacy.refresh_from_db()
    assert legacy.title == _samu_manual_title(10)
    assert ProductFile.objects.filter(sku=sku, title__contains="DST").count() == 0


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


@pytest.mark.django_db
def test_clone_damqu_manuals_from_da8_to_16_24() -> None:
    """DA16/DA24 get the same datasheet titles/bytes as DA8 editions."""
    from catalog.etl.manual_pdfs import clone_damqu_manuals_from_donor
    from catalog.models import SKU, Category, Product, ProductFile

    cat = Category.objects.create(name="MQU manuals", slug="mqu-manuals-clone")
    skus: dict[str, SKU] = {}
    for nm in (8, 16, 24):
        product = Product.objects.create(
            name=f"DA{nm}MQU",
            slug=f"privod-vozdushniy-da{nm}mqu-{nm}nm",
            category=cat,
        )
        for ed in ("24-A", "24-D"):
            code = f"DA{nm}MQU{ed}"
            skus[code] = SKU.objects.create(
                product=product,
                sku_code=code,
                name=code,
                slug=f"{code.lower()}-man",
                is_published=True,
            )
    title_a = "Инструкция DA8/16/24MQU24 (A/AS)"
    title_d = "Инструкция DA8/16/24MQU (D/DS)"
    for code, title, body in (
        ("DA8MQU24-A", title_a, b"%PDF-a"),
        ("DA8MQU24-D", title_d, b"%PDF-d"),
    ):
        pf = ProductFile(
            sku=skus[code],
            title=title,
            file_type=ProductFile.FileType.DATASHEET,
            is_published=True,
            sort_order=0,
        )
        pf.file.save(f"{code.lower()}.pdf", ContentFile(body), save=True)

    stats = clone_damqu_manuals_from_donor()
    assert stats["targets"] == 4
    assert stats["created"] == 4
    for nm in (16, 24):
        assert ProductFile.objects.filter(sku=skus[f"DA{nm}MQU24-A"], title=title_a).exists()
        assert ProductFile.objects.filter(sku=skus[f"DA{nm}MQU24-D"], title=title_d).exists()
