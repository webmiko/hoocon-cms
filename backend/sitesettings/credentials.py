"""Resolve social bot credentials: Admin SiteSettings first, then .env."""

from __future__ import annotations

from django.conf import settings

from sitesettings.models import SiteSettings


def telegram_bot_token(site: SiteSettings | None = None) -> str:
    """Return Telegram bot token (Admin, else TELEGRAM_BOT_TOKEN env)."""
    row = site if site is not None else SiteSettings.load()
    return (row.telegram_bot_token or "").strip() or getattr(
        settings,
        "TELEGRAM_BOT_TOKEN",
        "",
    ).strip()


def vk_access_token(site: SiteSettings | None = None) -> str:
    """Return VK access token (Admin, else VK_ACCESS_TOKEN env)."""
    row = site if site is not None else SiteSettings.load()
    return (row.vk_access_token or "").strip() or getattr(
        settings,
        "VK_ACCESS_TOKEN",
        "",
    ).strip()


def max_bot_token(site: SiteSettings | None = None) -> str:
    """Return MAX bot token (Admin, else MAX_BOT_TOKEN env)."""
    row = site if site is not None else SiteSettings.load()
    return (row.max_bot_token or "").strip() or getattr(
        settings,
        "MAX_BOT_TOKEN",
        "",
    ).strip()


def token_source_label(admin_value: str, env_value: str) -> str:
    """Human status for Admin readonly indicators.

    Args:
        admin_value: token stored on SiteSettings.
        env_value: token from Django settings / env.

    Returns:
        Short Russian status string.
    """
    if (admin_value or "").strip():
        return "задан в Admin"
    if (env_value or "").strip():
        return "задан в .env"
    return "не задан"
