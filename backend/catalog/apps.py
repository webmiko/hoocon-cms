from django.apps import AppConfig


class CatalogConfig(AppConfig):
    """Каталог HVAC: категории, продукты, SKU, файлы."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "catalog"
    verbose_name = "Каталог"
