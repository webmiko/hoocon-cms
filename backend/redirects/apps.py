from django.apps import AppConfig


class RedirectsConfig(AppConfig):
    """SEO-редиректы со старых URL Tilda."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "redirects"
    verbose_name = "Редиректы"

    def ready(self) -> None:
        """Invalidate redirect index when Admin or ETL changes rows."""
        from django.db.models.signals import post_delete, post_save

        from redirects.lookup import clear_redirect_index
        from redirects.models import Redirect

        def _invalidate(**_kwargs: object) -> None:
            clear_redirect_index()

        post_save.connect(_invalidate, sender=Redirect)
        post_delete.connect(_invalidate, sender=Redirect)
