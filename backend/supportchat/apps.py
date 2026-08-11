"""App config for support chat."""

from __future__ import annotations

from django.apps import AppConfig


class SupportchatConfig(AppConfig):
    """Unified support inbox (site widget + messengers)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "supportchat"
    verbose_name = "Поддержка"
