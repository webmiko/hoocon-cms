"""Blank integration secrets after a production database is copied locally.

The dump is still full of client data (that is why it was copied). Tokens
that can send mail, chat messages or place calls must not stay live on a
laptop. Mailbox passwords are wiped even though they are encrypted: the
laptop often has the same SECRET_KEY.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.sessions.models import Session

from accounts.models import StaffMailbox, StaffVpbxProfile
from sitesettings.models import SiteSettings

# ``db`` is the production compose hostname as well as a laptop service
# name, so it is not treated as local.
_LOCAL_DB_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1"})

_SITE_SECRET_FIELDS: tuple[str, ...] = (
    "telegram_bot_token",
    "vk_access_token",
    "max_bot_token",
    "gigachat_credentials",
    "novosystem_access_token",
    "novosystem_webhook_secret",
    "mango_api_key",
    "mango_api_salt",
)


def copied_database_host() -> str:
    """Host Django would write. Empty means a local Unix socket."""
    return str(settings.DATABASES["default"].get("HOST") or "")


def mask_copied_production_secrets() -> dict[str, int]:
    """Clear SiteSettings tokens, mailbox secrets and browser sessions.

    Raises:
        RuntimeError: the configured database host is not loopback.

    Returns:
        Counts of rows touched. Site settings is 0 or 1.
    """
    host = copied_database_host().strip().lower()
    if host not in _LOCAL_DB_HOSTS:
        raise RuntimeError(f"refusing to mask secrets: database host {host!r} is not local")
    site_rows = SiteSettings.objects.update(**dict.fromkeys(_SITE_SECRET_FIELDS, ""))
    mailboxes = StaffMailbox.objects.exclude(imap_password="").update(imap_password="")
    softphone = StaffVpbxProfile.objects.exclude(uis_webrtc_token="").update(uis_webrtc_token="")
    sessions = Session.objects.count()
    Session.objects.all().delete()
    report: dict[str, Any] = {
        "sitesettings": site_rows,
        "mailboxes": mailboxes,
        "softphone": softphone,
        "sessions": sessions,
    }
    return {key: int(value) for key, value in report.items()}
