"""SKU changelist cards: order movement over 1/3/6/12 months, cancelled excluded."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from cabinet.models import Order, OrderItem, OrderStatus
from catalog.stock_movement import build_stock_movement_report
from crm.models import Client

User = get_user_model()


def _sku(*, code: str, stock: int) -> object:
    from catalog.models import SKU, Category, Product

    cat, _ = Category.objects.get_or_create(name="Склад", slug="stock-move-cat")
    product, _ = Product.objects.get_or_create(name="Линейка", slug="stock-move-p", category=cat)
    return SKU.objects.create(
        product=product,
        name=code,
        slug=code.lower(),
        sku_code=code,
        stock_qty=stock,
        is_published=True,
    )


def _order(*, client: Client, number: str, sku, qty: int, days_ago: int, status: str, now) -> None:
    order = Order.objects.create(client=client, number=number, status=status)
    Order.objects.filter(pk=order.pk).update(created_at=now - timedelta(days=days_ago))
    OrderItem.objects.create(order=order, sku=sku, sku_code=sku.sku_code, quantity=qty)


@pytest.mark.django_db
def test_stock_movement_counts_orders_inside_each_window() -> None:
    """10-day order is in every window; 40-day order starts at 3 months; cancelled and 400-day stay out."""
    now = timezone.now()
    client = Client.objects.create(name="Склад", email="stock-move@example.com")
    recent = _sku(code="MOVE-NEW", stock=1)
    older = _sku(code="MOVE-OLD", stock=0)
    idle = _sku(code="MOVE-IDLE", stock=5)
    by_code = _sku(code="MOVE-CODE", stock=0)
    _order(client=client, number="З-1", sku=recent, qty=4, days_ago=10, status=OrderStatus.SHIPPED, now=now)
    _order(client=client, number="З-2", sku=older, qty=2, days_ago=40, status=OrderStatus.ACCEPTED, now=now)
    _order(client=client, number="З-3", sku=recent, qty=100, days_ago=5, status=OrderStatus.CANCELLED, now=now)
    _order(client=client, number="З-4", sku=recent, qty=50, days_ago=400, status=OrderStatus.DONE, now=now)
    orphan = Order.objects.create(client=client, number="З-5", status=OrderStatus.READY)
    Order.objects.filter(pk=orphan.pk).update(created_at=now - timedelta(days=3))
    OrderItem.objects.create(order=orphan, sku=None, sku_code="move-code", quantity=8)

    report = build_stock_movement_report(now=now)
    month = report.period(1)
    quarter = report.period(3)
    year = report.period(12)
    assert month is not None and quarter is not None and year is not None
    assert month.ordered_qty == 12
    assert quarter.ordered_qty == 14
    assert year.ordered_qty == 14
    assert recent.pk in month.moved_ids
    assert by_code.pk in month.moved_ids
    assert older.pk not in month.moved_ids
    assert older.pk in quarter.moved_ids
    assert idle.pk in month.idle_ids
    assert recent.pk not in month.idle_ids
    assert month.idle_in_stock == 1
    assert report.on_hand == 6


@pytest.mark.django_db
def test_sku_changelist_cards_filter_movers_and_hide_orders_without_perm(client) -> None:
    """Superuser sees the 1-month card and can open movers; a catalog-only user cannot."""
    now = timezone.now()
    buyer = Client.objects.create(name="Покупатель", email="stock-ui@example.com")
    moved = _sku(code="UI-MOVED", stock=2)
    _sku(code="UI-IDLE", stock=9)
    _order(client=buyer, number="З-UI", sku=moved, qty=11, days_ago=2, status=OrderStatus.SHIPPED, now=now)

    admin = User.objects.create_superuser(username="stock-cards", email="cards@example.com", password="x")
    client.force_login(admin)
    url = reverse("admin:catalog_sku_changelist")
    page = client.get(url)
    assert page.status_code == 200
    html = page.content.decode()
    assert "1 мес." in html
    assert "12 мес." in html
    assert "в заказах" in html
    assert ">11<" in html

    movers = client.get(url, {"stock_flow": "move-1"})
    body = movers.content.decode()
    assert movers.status_code == 200
    assert "UI-MOVED" in body
    assert "UI-IDLE" not in body

    idle_page = client.get(url, {"stock_flow": "idle-1"})
    idle_body = idle_page.content.decode()
    assert "UI-IDLE" in idle_body
    assert "UI-MOVED" not in idle_body

    client.logout()
    catalog_only = User.objects.create_user(
        username="catalog-only",
        email="catalog-only@example.com",
        password="x",
        is_staff=True,
    )
    catalog_only.user_permissions.add(
        Permission.objects.get(codename="view_sku", content_type__app_label="catalog"),
    )
    client.force_login(catalog_only)
    hidden = client.get(url)
    assert hidden.status_code == 200
    assert "в заказах" not in hidden.content.decode()
    unfiltered = client.get(url, {"stock_flow": "move-1"})
    listing = unfiltered.content.decode()
    assert "UI-MOVED" in listing
    assert "UI-IDLE" in listing
