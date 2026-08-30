"""App config for first-party site analytics."""

from __future__ import annotations

from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    """SPA page/SKU view counters for Admin (no third-party consent)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "analytics"
    verbose_name = "Аналитика сайта"
