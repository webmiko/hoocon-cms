"""App config for support chat."""

from __future__ import annotations

from django.apps import AppConfig


class SupportchatConfig(AppConfig):
    """Unified support inbox (site widget + messengers)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "supportchat"
    verbose_name = "Поддержка"

    def ready(self) -> None:
        """Delete attachment files when a support Message row is removed."""
        from catalog.media_hygiene import register_file_cleanup
        from supportchat.models import Message

        register_file_cleanup(Message)
