from django.apps import AppConfig


class CatalogConfig(AppConfig):
    """Каталог HVAC: категории, продукты, SKU, файлы."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "catalog"
    verbose_name = "Каталог"

    def ready(self) -> None:
        """Invalidate catalog HTTP cache when public price gate changes."""
        from django.db.models.signals import post_save

        from catalog.http_cache import invalidate_catalog_http_cache
        from sitesettings.models import SiteSettings

        def _invalidate_on_site_settings(**_kwargs: object) -> None:
            invalidate_catalog_http_cache()

        post_save.connect(
            _invalidate_on_site_settings,
            sender=SiteSettings,
            dispatch_uid="catalog.invalidate_http_cache_on_sitesettings",
        )
