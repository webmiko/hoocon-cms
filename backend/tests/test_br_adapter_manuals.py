"""Tests for BR-M / BR-ML adapter tech PDF discovery and attach."""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

from catalog.etl.manual_pdfs import (
    _BR_BRACKET_TITLE,
    _BR_STEM_TITLE_M,
    _BR_STEM_TITLE_ML,
    attach_br_adapter_manuals,
    discover_br_adapter_manuals,
    parse_br_adapter_manual_stem,
)


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("Техничка на кронштейн", (_BR_BRACKET_TITLE, ("BR-M", "BR-ML"), 0)),
        ("техничка штока BR-M", (_BR_STEM_TITLE_M, ("BR-M",), 1)),
        ("техничка штока BR-ML", (_BR_STEM_TITLE_ML, ("BR-ML",), 1)),
        ("техничка штока BR-ML.pdf", (_BR_STEM_TITLE_ML, ("BR-ML",), 1)),
        ("da5fu-d:ds", None),
    ],
)
def test_parse_br_adapter_manual_stem(
    stem: str,
    expected: tuple[str, tuple[str, ...], int] | None,
) -> None:
    assert parse_br_adapter_manual_stem(stem) == expected


def test_parse_br_adapter_manual_stem_nfd_kronshteyn() -> None:
    """macOS Disk export may use NFD «кронштейн»."""
    nfd = unicodedata.normalize("NFD", "Техничка на кронштейн")
    assert nfd != unicodedata.normalize("NFC", "Техничка на кронштейн")
    assert parse_br_adapter_manual_stem(nfd) == (
        _BR_BRACKET_TITLE,
        ("BR-M", "BR-ML"),
        0,
    )


def test_discover_br_adapter_manuals(tmp_path: Path) -> None:
    ru = tmp_path / "RU"
    ru.mkdir()
    (ru / "Техничка на кронштейн.pdf").write_bytes(b"%PDF-bracket")
    (ru / "техничка штока BR-M.pdf").write_bytes(b"%PDF-m")
    (ru / "техничка штока BR-ML.pdf").write_bytes(b"%PDF-ml")
    (ru / "da5fu-d:ds.pdf").write_bytes(b"%PDF-other")

    matches, warnings = discover_br_adapter_manuals(tmp_path)
    assert warnings == []
    assert len(matches) == 3
    by_title = {m.title: m for m in matches}
    assert by_title[_BR_BRACKET_TITLE].sku_codes == ("BR-M", "BR-ML")
    assert by_title[_BR_BRACKET_TITLE].sort_order == 0
    assert by_title[_BR_STEM_TITLE_M].sku_codes == ("BR-M",)
    assert by_title[_BR_STEM_TITLE_ML].sku_codes == ("BR-ML",)


@pytest.mark.django_db
def test_attach_br_adapter_manuals(tmp_path: Path) -> None:
    from catalog.models import SKU, Category, Product, ProductFile

    cat = Category.objects.create(name="Адаптеры", slug="adaptery-br-man")
    skus: dict[str, SKU] = {}
    for code, slug in (("BR-M", "adapter-br-m-man"), ("BR-ML", "adapter-br-ml-man")):
        product = Product.objects.create(name=code, slug=f"{slug}-prod", category=cat)
        skus[code] = SKU.objects.create(
            product=product,
            sku_code=code,
            name=code,
            slug=slug,
            is_published=True,
        )

    ru = tmp_path / "RU"
    ru.mkdir()
    (ru / "Техничка на кронштейн.pdf").write_bytes(b"%PDF-bracket")
    (ru / "техничка штока BR-M.pdf").write_bytes(b"%PDF-m")
    (ru / "техничка штока BR-ML.pdf").write_bytes(b"%PDF-ml")

    summary = attach_br_adapter_manuals(tmp_path, dry_run=False)
    assert summary["created"] == 4
    assert summary["warnings"] == []

    br_m = list(ProductFile.objects.filter(sku=skus["BR-M"]).order_by("sort_order", "title"))
    br_ml = list(ProductFile.objects.filter(sku=skus["BR-ML"]).order_by("sort_order", "title"))
    assert [f.title for f in br_m] == [_BR_BRACKET_TITLE, _BR_STEM_TITLE_M]
    assert [f.title for f in br_ml] == [_BR_BRACKET_TITLE, _BR_STEM_TITLE_ML]
    assert br_m[0].sort_order == 0
    assert br_m[1].sort_order == 1
    assert br_m[0].file.read() == b"%PDF-bracket"
    assert br_m[1].file.read() == b"%PDF-m"
    assert br_ml[1].file.read() == b"%PDF-ml"

    again = attach_br_adapter_manuals(tmp_path, dry_run=False)
    assert again["created"] == 0
    assert again["skipped"] == 4

    (ru / "техничка штока BR-M.pdf").write_bytes(b"%PDF-m-updated")
    refreshed = attach_br_adapter_manuals(tmp_path, dry_run=False)
    assert refreshed["updated"] == 1
    stem_m = ProductFile.objects.get(sku=skus["BR-M"], title=_BR_STEM_TITLE_M)
    assert stem_m.file.read() == b"%PDF-m-updated"
