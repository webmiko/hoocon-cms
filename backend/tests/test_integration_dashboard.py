"""Tests for SiteSettings Admin integration dashboard."""

from __future__ import annotations

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_build_integration_dashboard_telegram_connected(settings) -> None:
    """Enabled Telegram with token + chat_id is status «on»."""
    settings.TELEGRAM_BOT_TOKEN = ""
    from sitesettings.integration_dashboard import build_integration_dashboard
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    site.telegram_enabled = True
    site.telegram_bot_token = "token-test"
    site.telegram_chat_id = "-1001"
    site.yandex_metrika_id = "73321399"
    site.save()

    dash = build_integration_dashboard(site)
    by_name = {card["name"]: card for card in dash["cards"]}
    assert by_name["Telegram"]["status"] == "on"
    assert by_name["Яндекс.Метрика"]["status"] == "on"
    assert by_name["Цены на сайте"]["status"] == "off"
    assert dash["connected_count"] >= 2
    assert "sitesettings" in dash["change_url"]


@pytest.mark.django_db
def test_sitesettings_changelist_shows_integration_dashboard(
    client,
    django_user_model,
) -> None:
    """Changelist renders integration cards instead of the singleton table row."""
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    site.telegram_enabled = True
    site.telegram_bot_token = "token-test"
    site.telegram_chat_id = "@hoocon_moscow"
    site.save()

    user = django_user_model.objects.create_superuser(
        username="integ-dash",
        email="integ-dash@example.com",
        password="password12",
    )
    client.force_login(user)
    response = client.get(reverse("admin:sitesettings_sitesettings_changelist"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "hoocon-integrations" in html
    assert "Telegram" in html
    assert "Подключён" in html
    assert "Настроить" in html
    assert "Настройки сайта (цены:" not in html


@pytest.mark.django_db
def test_sitesettings_model_verbose_name_is_integrations() -> None:
    """Admin model labels are «интеграции» under app «Настройки сайта»."""
    from sitesettings.models import SiteSettings

    assert SiteSettings._meta.verbose_name == "интеграция"
    assert SiteSettings._meta.verbose_name_plural == "интеграции"
