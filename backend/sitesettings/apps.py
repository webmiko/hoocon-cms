from django.apps import AppConfig


class SitesettingsConfig(AppConfig):
    """Глобальные настройки сайта (singleton)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "sitesettings"
    verbose_name = "Настройки сайта"
