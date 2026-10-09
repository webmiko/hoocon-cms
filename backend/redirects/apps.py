from django.apps import AppConfig


class RedirectsConfig(AppConfig):
    """SEO-редиректы со старых URL Tilda."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "redirects"
    verbose_name = "Редиректы"

    def ready(self) -> None:
        """Invalidate redirect index when Admin or ETL changes rows."""
        from redirects import signals  # noqa: F401
