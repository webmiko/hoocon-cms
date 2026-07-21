"""App config for staff roles (Groups + permission sync)."""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Staff Groups: Админ / Менеджер / Аналитик."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Учётные записи / роли"
