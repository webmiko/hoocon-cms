"""Social announcements app: Telegram / VK / MAX."""

from django.apps import AppConfig


class SocialConfig(AppConfig):
    """Анонсы контента в соцсети."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "social"
    verbose_name = "Соцсети / анонсы"
