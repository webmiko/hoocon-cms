"""Per-SKU GOST passports from ``_инструкции-pdf/паспорт изделия/``."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.base import ContentFile

from catalog.etl.manual_pdfs import (
    PASSPORT_SUBDIR,
    attach_product_passports,
    discover_product_passports,
    parse_passport_sku_code,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("DA2MU24-D — паспорт (RU).pdf", "DA2MU24-D"),
        ("DA2MU230-AS — паспорт (RU).pdf", "DA2MU230-AS"),
        ("SA5FU24-DST — паспорт (RU).pdf", "SA5FU24-DST"),
        ("DA2MU24-D.pdf", "DA2MU24-D"),
        ("da5fu-d:ds.pdf", None),
        ("readme.pdf", None),
        ("Инструкция DA2MU.pdf", None),
    ],
)
def test_parse_passport_sku_code(raw: str, expected: str | None) -> None:
    assert parse_passport_sku_code(raw) == expected


def test_discover_product_passports_ignores_ru_manuals(tmp_path: Path) -> None:
    (tmp_path / "RU").mkdir()
    (tmp_path / "RU" / "DA2MU-D_DS.pdf").write_bytes(b"%PDF-manual")
    folder = tmp_path / PASSPORT_SUBDIR
    folder.mkdir()
    (folder / "DA2MU24-D — паспорт (RU).pdf").write_bytes(b"%PDF-pass")
    (folder / "notes.pdf").write_bytes(b"%PDF-notes")

    matches, warnings = discover_product_passports(tmp_path)
    assert [m.sku_code for m in matches] == ["DA2MU24-D"]
    assert matches[0].path.parent.name == PASSPORT_SUBDIR
    assert any("notes.pdf" in w for w in warnings)


@pytest.mark.django_db
def test_attach_product_passports_keeps_instruction(tmp_path: Path) -> None:
    from catalog.models import SKU, Category, Product, ProductFile

    cat = Category.objects.create(name="DAMU", slug="damu-passports")
    product = Product.objects.create(
        name="DA2MU",
        slug="privod-vozdushniy-bez-pruzhini-damu-2nm-pass",
        category=cat,
    )
    sku = SKU.objects.create(
        product=product,
        sku_code="DA2MU24-D",
        name="DA2MU24-D",
        slug="da2mu24-d-pass",
        is_published=True,
    )
    instruction = ProductFile(
        sku=sku,
        title="Инструкция DA2MU (D/DS)",
        file_type=ProductFile.FileType.DATASHEET,
        is_published=True,
        sort_order=0,
    )
    instruction.file.save("da2mu-d-ds.pdf", ContentFile(b"%PDF-instruction"), save=True)

    folder = tmp_path / PASSPORT_SUBDIR
    folder.mkdir()
    (folder / "DA2MU24-D — паспорт (RU).pdf").write_bytes(b"%PDF-passport-v1")

    summary = attach_product_passports(tmp_path, dry_run=False)
    assert summary["created"] == 1
    assert summary["warnings"] == []

    instruction.refresh_from_db()
    assert instruction.title == "Инструкция DA2MU (D/DS)"
    instruction.file.open("rb")
    try:
        assert instruction.file.read() == b"%PDF-instruction"
    finally:
        instruction.file.close()

    passport = ProductFile.objects.get(sku=sku, title="Паспорт DA2MU24-D")
    assert passport.sort_order == 1
    assert passport.file_type == ProductFile.FileType.DATASHEET
    passport.file.open("rb")
    try:
        assert passport.file.read() == b"%PDF-passport-v1"
    finally:
        passport.file.close()

    again = attach_product_passports(tmp_path, dry_run=False)
    assert again["created"] == 0
    assert again["skipped"] == 1
    assert ProductFile.objects.filter(sku=sku).count() == 2

    (folder / "DA2MU24-D — паспорт (RU).pdf").write_bytes(b"%PDF-passport-v1-longer")
    updated = attach_product_passports(tmp_path, dry_run=False)
    assert updated["updated"] == 1
    assert ProductFile.objects.filter(sku=sku, title="Инструкция DA2MU (D/DS)").count() == 1


@pytest.mark.django_db
def test_attach_product_passports_warns_when_sku_missing(tmp_path: Path) -> None:
    folder = tmp_path / PASSPORT_SUBDIR
    folder.mkdir()
    (folder / "DA2MU24-D — паспорт (RU).pdf").write_bytes(b"%PDF-x")
    summary = attach_product_passports(tmp_path, dry_run=False)
    assert summary["created"] == 0
    assert any("DA2MU24-D" in w for w in summary["warnings"])
