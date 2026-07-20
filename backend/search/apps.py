from django.apps import AppConfig


class SearchConfig(AppConfig):
    """Поиск по каталогу и контенту."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "search"
    verbose_name = "Поиск"
