"""Tests for Admin site analytics overview."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from analytics.models import ObjectType, PageDailyStat, SiteDailyStat

User = get_user_model()


@pytest.mark.django_db
def test_analytics_stats_page_for_superuser(client) -> None:
    admin_user = User.objects.create_superuser(
        username="analytics-admin",
        email="analytics-admin@example.com",
        password="password12",
    )
    today = timezone.localdate()
    SiteDailyStat.objects.create(day=today, views=5, unique_visitors=3)
    PageDailyStat.objects.create(
        day=today,
        path="/catalog/x/sku-1",
        object_type=ObjectType.SKU,
        object_key="sku-1",
        title="SKU 1",
        views=4,
        unique_visitors=2,
    )
    client.force_login(admin_user)
    url = reverse("admin:analytics_pagedailystat_stats")
    response = client.get(url)
    assert response.status_code == 200
    html = response.content.decode()
    assert "Аналитика сайта" in html
    assert "sku-1" in html
    assert "Топ артикулов" in html
    assert "hoocon-lead-stats__table" in html
    assert "hoocon-admin-tables.js" in html


@pytest.mark.django_db
def test_dashboard_includes_analytics_cards(client) -> None:
    admin_user = User.objects.create_superuser(
        username="dash-analytics",
        email="dash-analytics@example.com",
        password="password12",
    )
    SiteDailyStat.objects.create(
        day=timezone.localdate(),
        views=9,
        unique_visitors=4,
    )
    client.force_login(admin_user)
    response = client.get(reverse("admin:index"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "Просмотры сегодня" in html
    assert "Аналитика сайта" in html
