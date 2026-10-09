"""Telephony widgets: Admin settings first, environment as fallback."""

from __future__ import annotations

from django.conf import settings

from sitesettings.models import SiteSettings


def _site(site: SiteSettings | None) -> SiteSettings:
    return site if site is not None else SiteSettings.load()


def mango_settings(site: SiteSettings | None = None) -> tuple[bool, str, str, str]:
    """Return Mango enable flag, API key, salt, and callback URL template.

    Args:
        site: Optional singleton. Loaded when omitted.

    Returns:
        ``(enabled, api_key, api_salt, callback_webhook_url)``.
        Empty Admin secrets fall back to ``MANGO_*`` environment settings.
    """
    row = _site(site)
    key = (row.mango_api_key or "").strip() or getattr(settings, "MANGO_VPBX_API_KEY", "").strip()
    salt = (row.mango_api_salt or "").strip() or getattr(settings, "MANGO_VPBX_API_SALT", "").strip()
    callback = (row.mango_callback_webhook_url or "").strip() or getattr(
        settings,
        "MANGO_CALLBACK_WEBHOOK_URL",
        "",
    ).strip()
    return bool(row.mango_enabled), key, salt, callback


def novosystem_settings(site: SiteSettings | None = None) -> tuple[bool, str, str, str]:
    """Return Novosystem enable flag, access token, virtual phone, webhook secret.

    Args:
        site: Optional singleton. Loaded when omitted.

    Returns:
        ``(enabled, access_token, virtual_phone, webhook_secret)``.
    """
    row = _site(site)
    token = (row.novosystem_access_token or "").strip()
    phone = "".join(ch for ch in (row.novosystem_virtual_phone or "") if ch.isdigit())
    secret = (row.novosystem_webhook_secret or "").strip()
    return bool(row.novosystem_enabled), token, phone, secret
