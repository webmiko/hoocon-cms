"""Unit tests for catalog.docs_hub family/kind helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from catalog.docs_hub import (
    OTHER_FAMILY,
    SERIES_BR,
    SERIES_DA,
    SERIES_H81,
    SERIES_HV,
    SERIES_SA,
    DocsFileRow,
    build_family_metas,
    dedupe_files_by_family_title,
    doc_family_key,
    doc_family_sort_key,
    doc_kind,
    doc_series,
    natural_doc_sort_parts,
    normalize_doc_title,
)


@pytest.mark.parametrize(
    ("sku_code", "expected"),
    [
        ("DA2MU24-D", "DA2MU"),
        ("DA2MU230-AS", "DA2MU"),
        ("DA5MQU24-A", "DA5MQU"),
        ("DA10FU230-DS", "DA10FU"),
        ("SA5FU24-DST", "SA5FU"),
        ("SA3MU24-DS", "SA3MU"),
        ("HVD24S-5F", "HVD-5F"),
        ("HVD230ST-3F", "HVD-3F"),
        ("HVD24-5", "HVD-5"),
        ("HVD24S-40", "HVD-40"),
        ("HVD230-40QX", "HVD-40QX"),
        ("HVA24-5", "HVA-5"),
        ("HVA230S-5Q", "HVA-5Q"),
        ("HVA24-5UQ", "HVA-5UQ"),
        ("H8101-BV215A-24A", "H8101"),
        ("8100-bv215a", "8100-BV215"),
        ("H8205-LAV280ST-230A", "H8205-LAV280"),
        ("BR-M", "BR-M"),
        ("BR-ML", "BR-ML"),
        ("", OTHER_FAMILY),
        ("mystery-sku", OTHER_FAMILY),
    ],
)
def test_doc_family_key(sku_code: str, expected: str) -> None:
    assert doc_family_key(sku_code) == expected


@pytest.mark.parametrize(
    ("family", "series"),
    [
        ("DA2MU", SERIES_DA),
        ("SA5FU", SERIES_SA),
        ("HVA-5", SERIES_HV),
        ("HVD-5F", SERIES_HV),
        ("H8101", SERIES_H81),
        ("8100-BV215", SERIES_H81),
        ("BR-M", SERIES_BR),
        (OTHER_FAMILY, "OTHER"),
    ],
)
def test_doc_series(family: str, series: str) -> None:
    assert doc_series(family) == series


def test_doc_family_sort_key_orders_model_then_nm() -> None:
    """DA10… must not precede DA2…; MU / MQU / FU stay contiguous."""
    keys = [
        "DA10FU",
        "DA2MU",
        "DA5MQU",
        "DA5FU",
        "DA16MU",
        "SA10FU",
        "SA3FU",
        "SA7MU",
        "HVA-5",
        "HVD-5F",
        "OTHER",
    ]
    assert sorted(keys, key=doc_family_sort_key) == [
        "DA2MU",
        "DA16MU",
        "DA5MQU",
        "HVA-5",
        "HVD-5F",
        "DA5FU",
        "DA10FU",
        "SA3FU",
        "SA10FU",
        "SA7MU",
        "OTHER",
    ]


def test_natural_doc_sort_parts_digits() -> None:
    assert natural_doc_sort_parts("DA2MU") < natural_doc_sort_parts("DA10MU")
    assert natural_doc_sort_parts("Паспорт DA2MU24-D") < natural_doc_sort_parts(
        "Паспорт DA2MU230-D",
    )


def test_build_family_metas_uses_model_sort() -> None:
    now = datetime(2026, 8, 21, tzinfo=UTC)

    def row(family: str) -> DocsFileRow:
        return DocsFileRow(
            id=1,
            title=f"Паспорт {family}",
            file_url="/x.pdf",
            kind="passport",
            family=family,
            series=doc_series(family),
            sku_code=family,
            sku_slug=family.lower(),
            product_slug="p",
            category_slug="c",
            size_bytes=1,
            updated_at=now,
        )

    metas = build_family_metas([row("DA10FU"), row("DA2MU"), row("DA5FU")])
    assert [m.key for m in metas] == ["DA2MU", "DA5FU", "DA10FU"]


@pytest.mark.parametrize(
    ("title", "file_type", "expected"),
    [
        ("Паспорт DA2MU24-D", "datasheet", "passport"),
        ("Паспорт серии 8100 (шаровые краны)", "datasheet", "manual"),
        ("Инструкция DA2MU (D/DS)", "datasheet", "manual"),
        ("Инструкция серии 8100 (шаровые краны)", "datasheet", "manual"),
        ("Техничка на кронштейн", "datasheet", "manual"),
        ("CE certificate", "certificate", "certificate"),
        ("Каталог 2026", "catalog", "catalog"),
        ("Misc PDF", "datasheet", "datasheet"),
        ("Misc PDF", "other", "other"),
    ],
)
def test_doc_kind(title: str, file_type: str, expected: str) -> None:
    assert doc_kind(title, file_type) == expected


def test_normalize_doc_title() -> None:
    assert normalize_doc_title("  Инструкция  DA2MU  ") == "инструкция da2mu"


@pytest.mark.django_db
def test_dedupe_files_by_family_title_keeps_min_id() -> None:
    from django.core.files.base import ContentFile

    from catalog.models import SKU, Category, Product, ProductFile

    cat = Category.objects.create(name="DAMU", slug="damu-docs-hub")
    product = Product.objects.create(
        name="DA2MU",
        slug="privod-vozdushniy-bez-pruzhini-damu-2nm-docs",
        category=cat,
    )
    sku_a = SKU.objects.create(
        product=product,
        sku_code="DA2MU24-D",
        name="DA2MU24-D",
        slug="da2mu24-d-docs",
        is_published=True,
    )
    sku_b = SKU.objects.create(
        product=product,
        sku_code="DA2MU24-DS",
        name="DA2MU24-DS",
        slug="da2mu24-ds-docs",
        is_published=True,
    )
    title = "Инструкция DA2MU (D/DS)"
    first = ProductFile(
        sku=sku_a,
        title=title,
        file_type=ProductFile.FileType.DATASHEET,
        is_published=True,
        sort_order=0,
    )
    first.file.save("a.pdf", ContentFile(b"%PDF-a"), save=True)
    second = ProductFile(
        sku=sku_b,
        title=title,
        file_type=ProductFile.FileType.DATASHEET,
        is_published=True,
        sort_order=0,
    )
    second.file.save("b.pdf", ContentFile(b"%PDF-b"), save=True)
    passport = ProductFile(
        sku=sku_a,
        title="Паспорт DA2MU24-D",
        file_type=ProductFile.FileType.DATASHEET,
        is_published=True,
        sort_order=1,
    )
    passport.file.save("p.pdf", ContentFile(b"%PDF-p"), save=True)

    unique = dedupe_files_by_family_title(
        ProductFile.objects.filter(sku__in=[sku_a, sku_b]).order_by("id"),
    )
    titles = sorted(pf.title for pf in unique)
    assert titles == [title, "Паспорт DA2MU24-D"]
    assert unique[0].id == first.id or unique[1].id == first.id
    kept_manual = next(pf for pf in unique if pf.title == title)
    assert kept_manual.id == first.id
