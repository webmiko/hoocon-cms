from django.apps import AppConfig


class ContentConfig(AppConfig):
    """CMS-контент: страницы, статьи, новости."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "content"
    verbose_name = "Контент"

    def ready(self) -> None:
        """Delete cover files when an Article/News row is removed or re-covered."""
        from catalog.media_hygiene import register_file_cleanup
        from content.models import Article, News

        register_file_cleanup(Article, News)
