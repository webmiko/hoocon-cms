from django.apps import AppConfig


class RedirectsConfig(AppConfig):
    """SEO-редиректы со старых URL Tilda."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "redirects"
    verbose_name = "Редиректы"
