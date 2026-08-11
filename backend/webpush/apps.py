"""App config for Web Push."""

from __future__ import annotations

from django.apps import AppConfig


class WebpushConfig(AppConfig):
    """Browser / PWA push subscriptions and delivery."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "webpush"
    verbose_name = "Web Push"
