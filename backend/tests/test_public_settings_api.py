"""Tests for SiteSettings analytics + social channel fields."""

from __future__ import annotations

import pytest
from django.test import Client


@pytest.mark.django_db
def test_site_settings_analytics_defaults_empty() -> None:
    """Analytics counter IDs default to empty (opt-in via Admin)."""
    from sitesettings.models import SiteSettings

    s = SiteSettings.load()
    assert s.yandex_metrika_id == ""
    assert s.ga4_measurement_id == ""


@pytest.mark.django_db
def test_site_settings_social_flags_default_off() -> None:
    """Social announce channels are disabled until configured."""
    from sitesettings.models import SiteSettings

    s = SiteSettings.load()
    assert s.social_announce_on_publish is False
    assert s.telegram_enabled is False
    assert s.vk_enabled is False
    assert s.max_enabled is False


@pytest.mark.django_db
def test_public_settings_api_returns_analytics_ids_only() -> None:
    """GET /api/settings/public/ exposes counter IDs, never tokens."""
    from sitesettings.models import SiteSettings

    s = SiteSettings.load()
    s.yandex_metrika_id = "12345678"
    s.ga4_measurement_id = "G-TEST123"
    s.telegram_chat_id = "-100123"
    s.save()

    response = Client().get("/api/settings/public/")
    assert response.status_code == 200
    data = response.json()
    assert data["yandex_metrika_id"] == "12345678"
    assert data["ga4_measurement_id"] == "G-TEST123"
    assert "telegram" not in str(data).lower() or "token" not in str(data).lower()
    assert "token" not in data
    assert "vk_access_token" not in data
