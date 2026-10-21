"""Stock exports: a later file shows how many free pieces disappeared."""

from __future__ import annotations

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from catalog.etl.stock_snapshots import (
    build_snapshot_drop_report,
    record_stock_snapshot,
    stock_date_from_filename,
)
from catalog.models import SKU, Category, Product, StockSnapshot

User = get_user_model()


def _sku(code: str) -> SKU:
    cat, _ = Category.objects.get_or_create(name="Снимки", slug="stock-snap-cat")
    product, _ = Product.objects.get_or_create(name="Линейка", slug="stock-snap-p", category=cat)
    return SKU.objects.create(product=product, name=code, slug=code.lower(), sku_code=code, stock_qty=0)


def test_stock_date_from_russian_filename() -> None:
    """Export titles carry the warehouse date, including the «на» form."""
    assert stock_date_from_filename("Остатки товаров 10 августа 2026.xlsx") == date(2026, 8, 10)
    assert stock_date_from_filename("Остатки товаров на 19 октября 2026.xlsx") == date(2026, 10, 19)
    assert stock_date_from_filename("ostatki.xlsx") is None


@pytest.mark.django_db
def test_snapshot_drop_counts_only_decreases_and_ma_bucket() -> None:
    """10→4 and a 4–20 mA 5→1 are decreases; a receipt and a flat line are not."""
    fell = _sku("SNAP-FELL")
    rose = _sku("SNAP-ROSE")
    flat = _sku("SNAP-FLAT")
    record_stock_snapshot(
        [
            ("SNAP-FELL", 10),
            ("SNAP-ROSE", 1),
            ("SNAP-FLAT", 4),
            ("SNAP-FELL 4-20 mA", 5),
            ("NO-CARD", 8),
        ],
        taken_on=date(2026, 8, 10),
        source_name="Остатки товаров 10 августа 2026.xlsx",
    )
    record_stock_snapshot(
        [
            ("SNAP-FELL", 4),
            ("SNAP-ROSE", 6),
            ("SNAP-FLAT", 4),
            ("SNAP-FELL 4-20 mA", 1),
            ("NO-CARD", 8),
        ],
        taken_on=date(2026, 10, 19),
        source_name="Остатки товаров на 19 октября 2026.xlsx",
    )
    # Same day replaces the file instead of adding a second snapshot.
    record_stock_snapshot(
        [("SNAP-FELL", 4), ("SNAP-ROSE", 6), ("SNAP-FLAT", 4), ("SNAP-FELL 4-20 mA", 1), ("NO-CARD", 8)],
        taken_on=date(2026, 10, 19),
        source_name="повтор.xlsx",
    )
    assert StockSnapshot.objects.count() == 2

    report = build_snapshot_drop_report()
    # 70 days between the files: 7 and 30 day cards reach 10 Aug; longer ones are partial.
    week = report.window("7")
    year = report.window("365")
    assert week is not None and year is not None
    assert week.partial is False
    assert week.baseline_on == date(2026, 8, 10)
    assert week.latest_on == date(2026, 10, 19)
    # 6 base + 4 mA on SNAP-FELL. NO-CARD did not change.
    assert week.dropped_qty == 10
    assert week.dropped_positions == 1
    assert week.unmatched == 0
    assert fell.pk in week.sku_ids
    assert rose.pk not in week.sku_ids
    assert flat.pk not in week.sku_ids
    assert year.partial is True
    assert year.dropped_qty == week.dropped_qty


@pytest.mark.django_db
def test_sku_changelist_filters_articles_that_fell() -> None:
    """The export card opens the SKU list for articles whose free stock fell."""
    fell = _sku("UI-FELL")
    _sku("UI-ROSE")
    record_stock_snapshot([("UI-FELL", 9), ("UI-ROSE", 1)], taken_on=date(2026, 9, 1))
    record_stock_snapshot([("UI-FELL", 2), ("UI-ROSE", 3)], taken_on=date(2026, 10, 1))
    admin = User.objects.create_superuser(username="snap-admin", email="snap@example.com", password="password12")
    client = pytest.importorskip("django.test").Client()
    client.force_login(admin)
    url = reverse("admin:catalog_sku_changelist")
    html = client.get(url).content.decode()
    assert "По выгрузкам" in html or "стало меньше" in html
    assert "7 дн." in html
    filtered = client.get(url, {"stock_drop": "30"}).content.decode()
    assert "UI-FELL" in filtered
    assert "UI-ROSE" not in filtered
    assert fell.sku_code == "UI-FELL"
