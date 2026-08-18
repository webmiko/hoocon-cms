"""Tests for 1C Excel stock import (Артикул + Остатки)."""

from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import Workbook

from catalog.etl.stock_import import (
    StockImportError,
    apply_stock_rows,
    build_stock_template_xlsx,
    import_stock_xlsx,
    normalize_stock_article_key,
    parse_stock_qty,
    parse_stock_rows,
    stock_article_is_ma_option,
)


def _xlsx_bytes(rows: list[list[object]]) -> BytesIO:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    buf = BytesIO()
    book.save(buf)
    buf.seek(0)
    return buf


def test_parse_stock_qty_floors_fraction() -> None:
    assert parse_stock_qty(3.9) == 3
    assert parse_stock_qty("1,5") == 1
    assert parse_stock_qty(0) == 0
    assert parse_stock_qty(-2) == -2
    assert parse_stock_qty("нет") is None
    assert parse_stock_qty(None) is None


def test_normalize_stock_article_key_bv_aliases() -> None:
    """1C BV bodies alias to CMS 8100-bv* keys; H81 kits stay distinct."""
    assert normalize_stock_article_key("BV232-A") == "BV232A"
    assert normalize_stock_article_key("BV232A") == "BV232A"
    assert normalize_stock_article_key("8100-bv232a") == "BV232A"
    assert normalize_stock_article_key("8100-BV232A") == "BV232A"
    assert normalize_stock_article_key("BV265 DN65") == "BV265"
    assert normalize_stock_article_key("BV2100") == "BV2100"
    assert normalize_stock_article_key("H8121-BV265") == "H8121-BV265"
    assert normalize_stock_article_key("H8103-BV265-24A") == "H8103-BV265-24A"
    assert normalize_stock_article_key("H8101-BV215A-24A") == "H8101-BV215A-24A"
    assert normalize_stock_article_key("DA5FU24-DS") == "DA5FU24-DS"
    assert normalize_stock_article_key("DA10FU24-AS 4-20 mA") == "DA10FU24-AS"
    assert normalize_stock_article_key("DA15FU24-AS 4-20mA") == "DA15FU24-AS"


def test_stock_article_is_ma_option() -> None:
    """4–20 mA warehouse note is an option on the same SKU, not HVA24-20."""
    assert stock_article_is_ma_option("DA10FU24-AS 4-20 mA") is True
    assert stock_article_is_ma_option("DA15FU24-AS 4-20mA") is True
    assert stock_article_is_ma_option("DA10FU24-AS 4–20 мА") is True
    assert stock_article_is_ma_option("DA10FU24-AS") is False
    assert stock_article_is_ma_option("HVA24-20") is False
    assert stock_article_is_ma_option("BV265 DN65") is False


def test_parse_stock_rows_requires_headers() -> None:
    buf = _xlsx_bytes([["Код", "Кол-во"], ["A", 1]])
    with pytest.raises(StockImportError, match="Артикул"):
        parse_stock_rows(buf)


def test_parse_stock_rows_accepts_ostatok_alias() -> None:
    buf = _xlsx_bytes([["Артикул", "Остаток"], ["DA1", 5], ["DA2", ""], ["", 9]])
    rows = parse_stock_rows(buf)
    assert rows == [("DA1", 5), ("DA2", None)]


def test_parse_stock_rows_accepts_svobodno_header() -> None:
    """1C export uses «Свободно» for free stock qty."""
    buf = _xlsx_bytes(
        [
            ["Наименование", "Свободно", "Артикул"],
            ["BR-H Кронштейн", 2, "BR-H"],
            ["Ghost", 9, "NOPE-X"],
        ],
    )
    rows = parse_stock_rows(buf)
    assert rows == [("BR-H", 2), ("NOPE-X", 9)]


@pytest.mark.django_db
def test_apply_stock_maps_bv232_hyphen_to_8100_sku() -> None:
    """Stock «BV232-A» updates CMS «8100-bv232a»; unknown H81 bare stays ignored."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C", slug="stock-bv-c")
    product = Product.objects.create(name="P", slug="stock-bv-p", category=cat)
    body = SKU.objects.create(
        product=product,
        name="BV232",
        slug="stock-bv232a",
        sku_code="8100-bv232a",
        stock_qty=0,
    )
    other = SKU.objects.create(
        product=product,
        name="BV265",
        slug="stock-bv265",
        sku_code="8100-bv265",
        stock_qty=0,
    )

    report = apply_stock_rows(
        [
            ("BV232-A", 12),
            ("H8121-BV265", 99),
            ("BV265 DN65", 3),
        ],
    )
    body.refresh_from_db()
    other.refresh_from_db()
    assert body.stock_qty == 12
    assert other.stock_qty == 3
    assert report.updated == 2
    assert report.ignored_unknown == 1
    assert "H8121-BV265" in report.unknown_codes


@pytest.mark.django_db
def test_apply_stock_bare_h81_kit_fans_out_to_all_editions() -> None:
    """1C ``H8121-BV265`` sets qty on every electrical edition of that body."""
    from catalog.etl.h81_kits import KIT_CONTROL_SUFFIXES, KIT_VOLTAGES
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C", slug="stock-h81-c")
    product = Product.objects.create(name="P", slug="stock-h81-p", category=cat)
    for voltage in KIT_VOLTAGES:
        for suffix in KIT_CONTROL_SUFFIXES:
            code = f"H8121-BV265-{voltage}{suffix}"
            SKU.objects.create(
                product=product,
                name=code,
                slug=f"stock-{code.lower()}",
                sku_code=code,
                stock_qty=0,
            )
    other = SKU.objects.create(
        product=product,
        name="other",
        slug="stock-h8121-bv280-24a",
        sku_code="H8121-BV280-24A",
        stock_qty=0,
    )

    report = apply_stock_rows([("H8121-BV265", 1)])
    other.refresh_from_db()

    assert report.updated == 8
    assert report.ignored_unknown == 0
    assert other.stock_qty == 0
    for sku in SKU.objects.filter(sku_code__istartswith="H8121-BV265-"):
        assert sku.stock_qty == 1
        assert sku.in_stock is True


@pytest.mark.django_db
def test_apply_stock_exact_h81_edition_does_not_fan_out() -> None:
    """Full ``H8121-BV265-24A`` updates only that edition."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C", slug="stock-h81-e")
    product = Product.objects.create(name="P", slug="stock-h81-ep", category=cat)
    a = SKU.objects.create(
        product=product,
        name="A",
        slug="stock-h8121-24a",
        sku_code="H8121-BV265-24A",
        stock_qty=0,
    )
    sibling = SKU.objects.create(
        product=product,
        name="AS",
        slug="stock-h8121-24as",
        sku_code="H8121-BV265-24AS",
        stock_qty=0,
    )
    report = apply_stock_rows([("H8121-BV265-24A", 3)])
    a.refresh_from_db()
    sibling.refresh_from_db()
    assert report.updated == 1
    assert a.stock_qty == 3
    assert sibling.stock_qty == 0


def test_h81_kit_bare_stock_key() -> None:
    from catalog.etl.stock_import import h81_kit_bare_stock_key

    assert h81_kit_bare_stock_key("H8121-BV265") == "H8121-BV265"
    assert h81_kit_bare_stock_key("H8121-BV265-24AS") == "H8121-BV265"
    assert h81_kit_bare_stock_key("H8101-BV215A-230D") == "H8101-BV215A"
    assert h81_kit_bare_stock_key("BV265") is None
    assert h81_kit_bare_stock_key("DA5FU24-D") is None


@pytest.mark.django_db
def test_apply_stock_updates_known_ignores_unknown_keeps_missing() -> None:
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C", slug="stock-c")
    product = Product.objects.create(name="P", slug="stock-p", category=cat)
    a = SKU.objects.create(
        product=product,
        name="A",
        slug="stock-a",
        sku_code="DA-A",
        stock_qty=1,
    )
    b = SKU.objects.create(
        product=product,
        name="B",
        slug="stock-b",
        sku_code="DA-B",
        stock_qty=7,
    )
    c = SKU.objects.create(
        product=product,
        name="C",
        slug="stock-c-sku",
        sku_code="DA-C",
        stock_qty=3,
    )

    report = apply_stock_rows(
        [
            ("DA-A", 10),
            ("UNKNOWN-X", 99),
            ("DA-B", 0),
            ("DA-B", None),  # last wins → bad
        ],
    )
    a.refresh_from_db()
    b.refresh_from_db()
    c.refresh_from_db()

    assert a.stock_qty == 10
    assert a.in_stock is True
    assert a.stock_updated_at is not None
    # last wins is None → bad_rows, DA-B not updated
    assert b.stock_qty == 7
    assert c.stock_qty == 3  # not in file
    assert report.updated == 1
    assert report.ignored_unknown == 1
    assert report.bad_rows == 1
    assert "UNKNOWN-X" in report.unknown_codes


@pytest.mark.django_db
def test_apply_stock_splits_ma_option_from_base_qty() -> None:
    """``DA10FU24-AS 4-20 mA`` updates stock_qty_ma; base row keeps stock_qty."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C", slug="stock-ma-c")
    product = Product.objects.create(name="P", slug="stock-ma-p", category=cat)
    both = SKU.objects.create(
        product=product,
        name="AS",
        slug="stock-da10-as",
        sku_code="DA10FU24-AS",
        stock_qty=0,
        stock_qty_ma=0,
    )
    only_ma = SKU.objects.create(
        product=product,
        name="AS15",
        slug="stock-da15-as",
        sku_code="DA15FU24-AS",
        stock_qty=9,
        stock_qty_ma=0,
    )
    only_base = SKU.objects.create(
        product=product,
        name="D",
        slug="stock-da5-d",
        sku_code="DA5FU24-D",
        stock_qty=4,
        stock_qty_ma=11,
    )
    missing = SKU.objects.create(
        product=product,
        name="Keep",
        slug="stock-keep",
        sku_code="DA08MU24-AS",
        stock_qty=2,
        stock_qty_ma=3,
    )

    report = apply_stock_rows(
        [
            ("DA10FU24-AS 4-20 mA", 58),
            ("DA10FU24-AS", 251),
            ("DA15FU24-AS 4-20mA", 60),
            ("DA5FU24-D", 4),
        ],
    )
    both.refresh_from_db()
    only_ma.refresh_from_db()
    only_base.refresh_from_db()
    missing.refresh_from_db()

    assert both.stock_qty == 251
    assert both.stock_qty_ma == 58
    assert both.in_stock is True
    assert both.in_stock_ma is True
    assert only_ma.stock_qty == 9
    assert only_ma.stock_qty_ma == 60
    assert only_base.stock_qty == 4
    assert only_base.stock_qty_ma == 0
    assert missing.stock_qty == 2
    assert missing.stock_qty_ma == 3
    assert report.updated == 3
    assert report.ignored_unknown == 0


@pytest.mark.django_db
def test_import_stock_xlsx_end_to_end() -> None:
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C2", slug="stock-c2")
    product = Product.objects.create(name="P2", slug="stock-p2", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="S",
        slug="stock-s",
        sku_code="HVD-1",
        stock_qty=0,
    )
    buf = _xlsx_bytes([["Артикул", "Остатки"], ["hvd-1", 4.8], ["NOPE", 1]])
    report = import_stock_xlsx(buf)
    sku.refresh_from_db()
    assert sku.stock_qty == 4
    assert sku.in_stock is True
    assert report.updated == 1
    assert report.ignored_unknown == 1


def test_build_stock_template_xlsx_has_headers() -> None:
    rows = parse_stock_rows(BytesIO(build_stock_template_xlsx()))
    assert rows[0][0] == "DA5FU24-D"
    assert rows[0][1] == 10
