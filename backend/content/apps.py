from django.apps import AppConfig


class ContentConfig(AppConfig):
    """CMS-контент: страницы, статьи, новости."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "content"
    verbose_name = "Контент"
