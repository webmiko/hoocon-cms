"""Tests for Admin home dashboard (stats, feeds, notifications)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from leads.models import Lead

User = get_user_model()


@pytest.mark.django_db
def test_admin_index_shows_dashboard_for_superuser() -> None:
    """Home page renders dashboard cards, alerts, and feeds."""
    admin_user = User.objects.create_superuser(
        username="dash-admin",
        email="dash-admin@example.com",
        password="password12",
    )
    Lead.objects.create(
        name="Dash Lead",
        email="dash-lead@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.NEW,
    )
    client = Client()
    client.force_login(admin_user)
    response = client.get(reverse("admin:index"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "hoocon-dash" in html or "Панель управления" in html
    assert "Оповещения" in html
    assert "Заявки по статусам" in html
    assert "Последние заявки" in html
    assert "Dash Lead" in html
    assert "Изменения в админке" in html


@pytest.mark.django_db
def test_build_admin_dashboard_payload_keys() -> None:
    """Service returns expected dashboard sections for staff."""
    from django.test import RequestFactory

    from config.dashboard import build_admin_dashboard

    user = User.objects.create_superuser(
        username="dash-svc",
        email="dash-svc@example.com",
        password="password12",
    )
    request = RequestFactory().get("/admin/")
    request.user = user
    payload = build_admin_dashboard(request)
    dash = payload["hoocon_dashboard"]
    assert "notifications" in dash
    assert "cards" in dash
    assert "chart" in dash
    assert "recent_leads" in dash
    assert "admin_log" in dash
    assert dash["period_days"] == 30
