"""Coverage tests for social credential resolution helpers."""

from __future__ import annotations

import pytest
from django.test import override_settings

from sitesettings.credentials import (
    max_bot_token,
    telegram_bot_token,
    token_source_label,
    vk_access_token,
)
from sitesettings.models import SiteSettings


@pytest.mark.django_db
@override_settings(VK_ACCESS_TOKEN="env-vk", MAX_BOT_TOKEN="env-max")
def test_vk_and_max_tokens_prefer_admin_then_env() -> None:
    """Admin SiteSettings wins; empty Admin falls back to env."""
    site = SiteSettings.load()
    site.vk_access_token = ""
    site.max_bot_token = ""
    site.save(update_fields=["vk_access_token", "max_bot_token"])
    assert vk_access_token(site) == "env-vk"
    assert max_bot_token(site) == "env-max"

    site.vk_access_token = " admin-vk "
    site.max_bot_token = "admin-max"
    site.save(update_fields=["vk_access_token", "max_bot_token"])
    assert vk_access_token(site) == "admin-vk"
    assert max_bot_token(site) == "admin-max"


@pytest.mark.parametrize(
    ("admin", "env", "label"),
    [
        ("tok", "env", "задан в Admin"),
        ("", "env", "задан в .env"),
        ("  ", "", "не задан"),
    ],
)
def test_token_source_label(admin: str, env: str, label: str) -> None:
    """Readonly Admin status for token provenance."""
    assert token_source_label(admin, env) == label


@pytest.mark.django_db
@override_settings(TELEGRAM_BOT_TOKEN="")
def test_telegram_token_empty_when_unset() -> None:
    """No Admin and no env → empty string."""
    site = SiteSettings.load()
    site.telegram_bot_token = ""
    site.save(update_fields=["telegram_bot_token"])
    assert telegram_bot_token(site) == ""
